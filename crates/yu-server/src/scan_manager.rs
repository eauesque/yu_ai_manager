use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use serde_json::json;

use scan_core::ipc::clear_scan_state;

use crate::scan_native::{self, ScanProgress};
use crate::sse::SseEvent;
use crate::state::AppState;

/// Lock without letting a poisoned mutex take the server down with it.
///
/// A panic anywhere while one of these locks was held poisons it, and
/// `.lock().unwrap()` then panics on *every* later access -- so a single
/// failure inside the scan task turned `/api/scan/status` and every subsequent
/// scan into a panicking endpoint until the process was restarted.
///
/// Recovering is correct here rather than merely convenient: the guarded
/// values are a plain status struct and an `Option<JoinHandle>`, neither of
/// which carries an invariant that a half-finished write could violate. The
/// worst case is a status field left mid-update, which the next progress tick
/// overwrites anyway.
fn lock_recover<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

#[derive(Debug)]
pub enum ScanError {
    AlreadyRunning,
    NoRoots,
}

impl std::fmt::Display for ScanError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ScanError::AlreadyRunning => write!(f, "scan worker already running"),
            ScanError::NoRoots => write!(f, "no enabled scan roots"),
        }
    }
}

pub enum ScanCmd {
    Start {
        root: String,
        recursive: bool,
        force: bool,
        #[allow(dead_code)] // zip-archive traversal is not implemented natively yet
        scan_zips: bool,
        #[allow(dead_code)]
        // native scan runs should_rescan against files directly, not a resume marker
        resume: bool,
        #[allow(dead_code)] // db access goes through AppState's pool, not a re-opened path
        db_path: String,
    },
    ScanAll {
        force: bool,
        #[allow(dead_code)]
        db_path: String,
    },
}

#[derive(Serialize, Clone, Default)]
pub struct ScanStatus {
    pub running: bool,
    pub phase: Option<String>,
    pub message: Option<String>,
    pub current: u64,
    pub total: u64,
    pub percent: f32,
    pub job_id: String,
}

/// Runs the scan (walk + native import + delete sync) as an in-process
/// tokio task — no Python worker process is spawned. See `scan_native` for
/// the actual walking/import/delete-sync logic.
pub struct ScanManager {
    running: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
    status: Arc<Mutex<ScanStatus>>,
    task_handle: Mutex<Option<tokio::task::JoinHandle<()>>>,
    project_root: PathBuf,
}

impl ScanManager {
    pub fn new(project_root: PathBuf) -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            cancel: Arc::new(AtomicBool::new(false)),
            status: Arc::new(Mutex::new(ScanStatus {
                job_id: "scan".to_string(),
                ..Default::default()
            })),
            task_handle: Mutex::new(None),
            project_root,
        }
    }

    pub async fn spawn_worker(&self, cmd: ScanCmd, state: Arc<AppState>) -> Result<(), ScanError> {
        if self.running.swap(true, Ordering::SeqCst) {
            return Err(ScanError::AlreadyRunning);
        }
        if matches!(cmd, ScanCmd::ScanAll { .. }) && scan_native::enabled_roots(&state).is_empty() {
            self.running.store(false, Ordering::SeqCst);
            return Err(ScanError::NoRoots);
        }
        self.cancel.store(false, Ordering::SeqCst);
        *lock_recover(&self.status) = ScanStatus {
            running: true,
            job_id: "scan".to_string(),
            ..Default::default()
        };

        send_sse(
            &state,
            "scan.started",
            json!({
                "recursive": true,
                "label": "フォルダスキャン",
                "job_id": "scan",
            }),
        );

        let running = self.running.clone();
        let cancel = self.cancel.clone();
        let status = self.status.clone();
        let handle = tokio::spawn(run_native_scan(cmd, state, running, cancel, status));
        *lock_recover(&self.task_handle) = Some(handle);
        Ok(())
    }

    /// In-process tasks do not survive a server restart, so there is nothing
    /// to reconnect to on startup (unlike the old Python-worker-process
    /// design, where the worker could outlive a web_ui restart).
    pub async fn reconnect_if_running(&self, _state: Arc<AppState>) {}

    pub fn status(&self) -> ScanStatus {
        lock_recover(&self.status).clone()
    }

    pub fn stop(&self) -> bool {
        self.cancel.store(true, Ordering::SeqCst);
        self.running.load(Ordering::SeqCst)
    }

    pub fn dismiss(&self) -> Result<(), ScanError> {
        clear_scan_state(&self.project_root);
        Ok(())
    }
}

fn now_ts() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::ZERO)
        .as_secs_f64()
}

fn send_sse(state: &AppState, event_type: &str, data: serde_json::Value) {
    state.sse_hub.send(SseEvent {
        event_type: event_type.to_string(),
        timestamp: now_ts(),
        data,
        source: "scan".to_string(),
    });
}

async fn run_native_scan(
    cmd: ScanCmd,
    state: Arc<AppState>,
    running: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
    status: Arc<Mutex<ScanStatus>>,
) {
    send_sse(
        &state,
        "scan.db_busy",
        json!({"busy": true, "job_id": "scan"}),
    );

    let state_for_progress = state.clone();
    let status_for_progress = status.clone();
    let on_progress = move |p: ScanProgress| {
        let percent = if p.total > 0 {
            (p.current as f32 / p.total as f32) * 100.0
        } else {
            0.0
        };
        {
            let mut st = lock_recover(&status_for_progress);
            st.phase = Some(p.phase.clone());
            st.message = Some(p.message.clone());
            st.current = p.current;
            st.total = p.total;
            st.percent = percent;
        }
        send_sse(
            &state_for_progress,
            "scan.progress",
            json!({
                "current": p.current, "total": p.total, "percent": percent,
                "detail": p.detail, "phase": p.phase, "job_id": "scan",
            }),
        );
    };

    let outcome = match cmd {
        ScanCmd::Start {
            root,
            recursive,
            force,
            ..
        } => {
            scan_native::run_scan_root(&state, &root, recursive, force, &cancel, on_progress).await
        }
        ScanCmd::ScanAll { force, .. } => {
            scan_native::run_scan_all(&state, force, &cancel, on_progress).await
        }
    };

    running.store(false, Ordering::SeqCst);
    lock_recover(&status).running = false;
    send_sse(
        &state,
        "scan.db_busy",
        json!({"busy": false, "job_id": "scan"}),
    );
    send_sse(
        &state,
        "scan.complete",
        json!({
            "count": outcome.added,
            "errors": outcome.errors,
            "deleted": outcome.deleted,
            "cancelled": outcome.cancelled,
            "job_id": "scan",
        }),
    );
}

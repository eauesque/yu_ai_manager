use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use serde_json::json;
use tracing::{info, warn};

use scan_core::ipc::clear_scan_state;

use crate::scan_native::{self, ScanProgress};
use crate::sse::SseEvent;
use crate::state::AppState;

/// Pause between a finishing scan and the next queued one, matching Python's
/// `_INTER_SCAN_DELAY`.
const INTER_SCAN_DELAY: Duration = Duration::from_secs(2);

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
    scan_all: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
    status: Arc<Mutex<ScanStatus>>,
    task_handle: Mutex<Option<tokio::task::JoinHandle<()>>>,
    project_root: PathBuf,
}

impl ScanManager {
    pub fn new(project_root: PathBuf) -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            scan_all: Arc::new(AtomicBool::new(false)),
            cancel: Arc::new(AtomicBool::new(false)),
            status: Arc::new(Mutex::new(ScanStatus {
                job_id: "scan".to_string(),
                ..Default::default()
            })),
            task_handle: Mutex::new(None),
            project_root,
        }
    }

    /// Not `async`: the body only spawns. Keeping it sync also breaks the
    /// type cycle it would otherwise form with `consume_next_queued_scan`
    /// (spawn_worker -> run_native_scan -> consume -> spawn_worker), which
    /// rustc cannot resolve through opaque future types.
    pub fn spawn_worker(&self, cmd: ScanCmd, state: Arc<AppState>) -> Result<(), ScanError> {
        if self.running.swap(true, Ordering::SeqCst) {
            return Err(ScanError::AlreadyRunning);
        }
        let is_scan_all = matches!(cmd, ScanCmd::ScanAll { .. });
        if is_scan_all && scan_native::enabled_roots(&state).is_empty() {
            self.running.store(false, Ordering::SeqCst);
            return Err(ScanError::NoRoots);
        }
        self.scan_all.store(is_scan_all, Ordering::SeqCst);
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
        let handle = tokio::spawn(run_native_scan(
            cmd,
            state,
            running,
            self.scan_all.clone(),
            cancel,
            status,
        ));
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

    pub fn is_scan_all(&self) -> bool {
        self.scan_all.load(Ordering::SeqCst)
    }

    #[cfg(test)]
    pub fn set_test_running(&self, is_scan_all: bool) {
        self.running.store(true, Ordering::SeqCst);
        self.scan_all.store(is_scan_all, Ordering::SeqCst);
        self.cancel.store(false, Ordering::SeqCst);
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
    scan_all: Arc<AtomicBool>,
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
            scan_zips,
            ..
        } => {
            scan_native::run_scan_root(
                &state,
                &root,
                recursive,
                force,
                scan_zips,
                &cancel,
                on_progress,
            )
            .await
        }
        ScanCmd::ScanAll { force, .. } => {
            // Python's scan-all always includes archives
            // (`core/scan_roots_api/scan_all.py` enqueues scan_zips=True).
            scan_native::run_scan_all(&state, force, true, &cancel, on_progress).await
        }
    };

    running.store(false, Ordering::SeqCst);
    scan_all.store(false, Ordering::SeqCst);
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

    consume_next_queued_scan(state).await;
}

/// Start the request at the front of the queue, if any. Port of Python's
/// `core/scan_core/scan_queue_consumer.py::consume_next_queued_scan`, which
/// runs from the scan bridge's finally block for the same reason: without it a
/// queued request sits in `data/scan_queue.json` until someone starts a scan
/// by hand.
async fn consume_next_queued_scan(state: Arc<AppState>) {
    let Some(item) = state.scan_queue.pop_next() else {
        return;
    };
    let remaining = state.scan_queue.size();
    info!(
        "Queue consumer: starting '{}' (remaining={remaining})",
        item.label
    );
    send_sse(
        &state,
        "scan.queue_next",
        json!({
            "queue_id": item.queue_id,
            "root": item.root,
            "label": item.label,
            "remaining": remaining,
        }),
    );

    // Python waits the same 2s so the finishing scan's cleanup (delete sync,
    // state file removal) does not race the next one's start.
    tokio::time::sleep(INTER_SCAN_DELAY).await;

    let Some(sm) = state.scan_manager.get() else {
        warn!(
            "Queue consumer: scan manager unavailable, dropping '{}'",
            item.label
        );
        return;
    };
    clear_scan_state(&state.config.project_root);
    let cmd = if item.root == crate::scan_queue::SCAN_ALL_ROOT {
        ScanCmd::ScanAll {
            force: item.force,
            db_path: state.config.db_path.clone(),
        }
    } else {
        ScanCmd::Start {
            root: item.root.clone(),
            recursive: item.recursive,
            force: item.force,
            scan_zips: item.scan_zips,
            resume: false,
            db_path: state.config.db_path.clone(),
        }
    };
    if let Err(e) = sm.spawn_worker(cmd, state.clone()) {
        warn!("Queue consumer: failed to start '{}': {e}", item.label);
    }
}

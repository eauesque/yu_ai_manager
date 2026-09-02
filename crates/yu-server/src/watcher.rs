use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use notify::event::{CreateKind, ModifyKind, RemoveKind, RenameMode};
use notify::{
    Config as NotifyConfig, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher,
};
use serde::Serialize;
use sqlx::SqlitePool;
use tracing::{debug, error, info, warn};

use tagdb_core::{mark_deleted, upsert_file, UpsertFileParams};

use crate::jobs::JobManager;

const SCAN_EXTS: &[&str] = &[
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".jxl", ".avif", ".heif", ".heic", ".svg", ".webm",
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".ogv", ".mp3", ".wav", ".ogg", ".opus", ".m4a",
    ".aac", ".flac", ".pdf",
];

const FLUSH_BATCH_MAX: usize = 200;
const DEBOUNCE_SECS: f64 = 3.0;

#[derive(Debug, Clone, Copy, PartialEq)]
enum Action {
    Created,
    Modified,
    Deleted,
}

#[derive(Default, Clone, Serialize)]
pub struct WatcherStats {
    pub added: u64,
    pub modified: u64,
    pub deleted: u64,
    pub errors: u64,
}

struct Inner {
    running: bool,
    watched_roots: Vec<String>,
    stats: WatcherStats,
    // ponytail: held for Drop-based stop
    _watcher: Option<RecommendedWatcher>,
    stop_tx: Option<std::sync::mpsc::SyncSender<()>>,
}

pub struct ScanWatcher {
    inner: Arc<Mutex<Inner>>,
}

impl ScanWatcher {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(Inner {
                running: false,
                watched_roots: vec![],
                stats: WatcherStats::default(),
                _watcher: None,
                stop_tx: None,
            })),
        }
    }

    pub fn info(&self) -> (bool, Vec<String>, WatcherStats) {
        let g = self.inner.lock().unwrap();
        (g.running, g.watched_roots.clone(), g.stats.clone())
    }

    pub fn start(
        &self,
        roots: Vec<serde_json::Value>,
        db: SqlitePool,
        job_manager: Arc<JobManager>,
    ) -> Result<Vec<String>, String> {
        let mut g = self.inner.lock().unwrap();
        if g.running {
            return Err("Already running".to_string());
        }

        let (event_tx, event_rx) = std::sync::mpsc::channel::<Event>();
        let (stop_tx, stop_rx) = std::sync::mpsc::sync_channel::<()>(1);

        let mut watcher = RecommendedWatcher::new(
            move |res: Result<Event, notify::Error>| {
                if let Ok(ev) = res {
                    let _ = event_tx.send(ev);
                }
            },
            NotifyConfig::default(),
        )
        .map_err(|e| format!("notify init failed: {e}"))?;

        let mut watched_roots = vec![];
        for root in &roots {
            let path_str = root
                .get("path")
                .and_then(|v| v.as_str())
                .unwrap_or_default();
            if path_str.is_empty() {
                continue;
            }
            let p = Path::new(path_str);
            if !p.is_dir() {
                warn!("Watcher: skipping non-existent root: {path_str}");
                continue;
            }
            let recursive = root
                .get("recursive")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            let mode = if recursive {
                RecursiveMode::Recursive
            } else {
                RecursiveMode::NonRecursive
            };
            watcher
                .watch(p, mode)
                .map_err(|e| format!("watch failed for {path_str}: {e}"))?;
            watched_roots.push(path_str.to_string());
            info!("Watcher: watching {path_str} (recursive={recursive})");
        }

        if watched_roots.is_empty() {
            return Err("No valid roots to watch".to_string());
        }

        g._watcher = Some(watcher);
        g.running = true;
        g.watched_roots = watched_roots.clone();
        g.stats = WatcherStats::default();
        g.stop_tx = Some(stop_tx);

        let inner_arc = Arc::clone(&self.inner);
        let tokio_handle = tokio::runtime::Handle::current();

        thread::spawn(move || {
            run_flush_loop(
                event_rx,
                stop_rx,
                watched_roots,
                db,
                job_manager,
                inner_arc,
                tokio_handle,
            );
        });

        Ok(g.watched_roots.clone())
    }

    pub fn stop(&self) -> bool {
        let mut g = self.inner.lock().unwrap();
        if !g.running {
            return false;
        }
        if let Some(tx) = g.stop_tx.take() {
            let _ = tx.try_send(());
        }
        g._watcher = None;
        g.running = false;
        g.watched_roots.clear();
        true
    }
}

fn is_relevant(path: &Path) -> bool {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_ascii_lowercase()));
    ext.as_deref()
        .map(|e| SCAN_EXTS.contains(&e))
        .unwrap_or(false)
}

fn run_flush_loop(
    event_rx: std::sync::mpsc::Receiver<Event>,
    stop_rx: std::sync::mpsc::Receiver<()>,
    watched_roots: Vec<String>,
    db: SqlitePool,
    job_manager: Arc<JobManager>,
    inner: Arc<Mutex<Inner>>,
    tokio_handle: tokio::runtime::Handle,
) {
    let debounce = Duration::from_secs_f64(DEBOUNCE_SECS);
    let mut pending: HashMap<PathBuf, Action> = HashMap::new();
    let mut last_event = SystemTime::now();

    loop {
        if stop_rx.try_recv().is_ok() {
            break;
        }

        match event_rx.recv_timeout(Duration::from_millis(200)) {
            Ok(ev) => {
                process_event(&ev, &mut pending);
                last_event = SystemTime::now();
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {}
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
        }

        if pending.is_empty() {
            continue;
        }
        let elapsed = last_event.elapsed().unwrap_or_default();
        if elapsed < debounce {
            continue;
        }

        // scan job実行中は延期
        if job_manager.is_running("scan") || job_manager.is_running("scan-all") {
            debug!(
                "Watcher: scan job running, deferring {} events",
                pending.len()
            );
            last_event = SystemTime::now();
            continue;
        }

        flush_batch(&mut pending, &watched_roots, &db, &inner, &tokio_handle);
    }
    info!("Watcher flush loop exited");
}

fn process_event(ev: &Event, pending: &mut HashMap<PathBuf, Action>) {
    for path in &ev.paths {
        if !is_relevant(path) {
            continue;
        }
        let action = match &ev.kind {
            EventKind::Create(CreateKind::File)
            | EventKind::Create(CreateKind::Any)
            | EventKind::Create(_) => Action::Created,
            EventKind::Modify(ModifyKind::Data(_))
            | EventKind::Modify(ModifyKind::Any)
            | EventKind::Modify(_) => {
                // 既にCreatedがペンディング中なら上書きしない
                if let Some(Action::Created) = pending.get(path) {
                    continue;
                }
                Action::Modified
            }
            EventKind::Remove(RemoveKind::File)
            | EventKind::Remove(RemoveKind::Any)
            | EventKind::Remove(_) => Action::Deleted,
            EventKind::Access(_) | EventKind::Any | EventKind::Other => continue,
        };

        // Rename: paths[0]=from → Deleted、paths[1]=to → Created
        // notifyはRenameMode付きで別eventとして発行するため
        // 上記の Create/Remove でそのまま捕捉できる
        match (ev.kind, action) {
            (EventKind::Remove(_), _) => {
                pending.insert(path.clone(), Action::Deleted);
            }
            _ => {
                pending.insert(path.clone(), action);
            }
        }
    }
}

fn flush_batch(
    pending: &mut HashMap<PathBuf, Action>,
    watched_roots: &[String],
    db: &SqlitePool,
    inner: &Arc<Mutex<Inner>>,
    tokio_handle: &tokio::runtime::Handle,
) {
    let items: Vec<(PathBuf, Action)>;
    let overflow: Vec<(PathBuf, Action)>;
    if pending.len() > FLUSH_BATCH_MAX {
        let all: Vec<_> = pending.drain().collect();
        items = all[..FLUSH_BATCH_MAX].to_vec();
        overflow = all[FLUSH_BATCH_MAX..].to_vec();
    } else {
        items = pending.drain().collect();
        overflow = vec![];
    }

    let mut added = 0u64;
    let mut modified = 0u64;
    let mut deleted = 0u64;
    let mut errors = 0u64;

    for (path, action) in &items {
        let path_str = path.to_string_lossy().into_owned();
        let under_root = watched_roots
            .iter()
            .any(|r| path_str.starts_with(r.as_str()));
        if !under_root {
            warn!("Watcher: SKIPPED out-of-scope: {path_str}");
            continue;
        }

        match action {
            Action::Deleted => {
                let db2 = db.clone();
                let p = path_str.clone();
                match tokio_handle.block_on(mark_deleted(&db2, &p)) {
                    Ok(true) => deleted += 1,
                    Ok(false) => {}
                    Err(e) => {
                        error!("Watcher: mark_deleted error {p}: {e}");
                        errors += 1;
                    }
                }
            }
            Action::Created | Action::Modified => {
                if !path.exists() {
                    continue;
                }
                let Ok(meta) = path.metadata() else {
                    errors += 1;
                    continue;
                };
                let mtime = meta
                    .modified()
                    .ok()
                    .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                    .map(|d| d.as_secs() as i64)
                    .unwrap_or(0);
                let size = meta.len() as i64;
                let db2 = db.clone();
                let p = path_str.clone();
                match tokio_handle.block_on(upsert_file(
                    &db2,
                    UpsertFileParams {
                        path: &p,
                        mtime,
                        size,
                        meta_source: None,
                        content_hash: None,
                        is_zip_member: false,
                        width: None,
                        height: None,
                    },
                )) {
                    Ok(_) => {
                        if *action == Action::Created {
                            added += 1;
                        } else {
                            modified += 1;
                        }
                    }
                    Err(e) => {
                        error!("Watcher: upsert error {p}: {e}");
                        errors += 1;
                    }
                }
            }
        }
    }

    // オーバーフロー分を再キュー
    for (p, a) in overflow {
        pending.insert(p, a);
    }

    {
        let mut g = inner.lock().unwrap();
        g.stats.added += added;
        g.stats.modified += modified;
        g.stats.deleted += deleted;
        g.stats.errors += errors;
    }

    info!("Watcher sync: +{added} ~{modified} -{deleted} err={errors}");
}

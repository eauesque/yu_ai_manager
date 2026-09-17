use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime};

use notify::event::{CreateKind, ModifyKind, RemoveKind, RenameMode};
use notify::{
    Config as NotifyConfig, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher,
};
use serde::Serialize;
use sqlx::SqlitePool;
use tracing::{debug, error, info, warn};

use tagdb_core::mark_deleted;

use crate::ext_config::ScanRootCfg;
use crate::jobs::JobManager;
use crate::routes::sweep_common::{bare_upsert_one, native_import_one_with};

const SCAN_EXTS: &[&str] = &[
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".jxl", ".avif", ".heif", ".heic", ".svg", ".webm",
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".ogv", ".mp3", ".wav", ".ogg", ".opus", ".m4a",
    ".aac", ".flac", ".pdf",
];

const FLUSH_BATCH_MAX: usize = 200;
const DEBOUNCE_SECS: f64 = 3.0;

/// Added on top of `SCAN_EXTS` when the extension's `scan_archives` is on
/// (default true), matching Python's `_get_scan_exts`.
const ARCHIVE_EXTS: &[&str] = &[".zip", ".7z"];

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

    /// Stop (if running) and start again with an updated root list, mirroring
    /// Python's `ScanWatcher.restart` on SCAN_ROOTS_CHANGED.
    pub fn restart(
        &self,
        roots: Vec<ScanRootCfg>,
        db: SqlitePool,
        job_manager: Arc<JobManager>,
        config_path: PathBuf,
    ) -> Result<Vec<String>, String> {
        self.stop();
        self.start(roots, db, job_manager, config_path)
    }

    /// `config_path` is kept rather than a snapshot of its contents: the flush
    /// loop outlives any number of settings edits, and the per-format scan
    /// toggles must take effect without restarting the watcher.
    pub fn start(
        &self,
        roots: Vec<ScanRootCfg>,
        db: SqlitePool,
        job_manager: Arc<JobManager>,
        config_path: PathBuf,
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
        let mut watched_roots_resolved = vec![];
        for root in &roots {
            let path_str = root.path.as_str();
            if path_str.is_empty() {
                continue;
            }
            let p = Path::new(path_str);
            if !p.is_dir() {
                warn!("Watcher: skipping non-existent root: {path_str}");
                continue;
            }
            let recursive = root.recursive;
            let mode = if recursive {
                RecursiveMode::Recursive
            } else {
                RecursiveMode::NonRecursive
            };
            watcher
                .watch(p, mode)
                .map_err(|e| format!("watch failed for {path_str}: {e}"))?;
            watched_roots.push(path_str.to_string());
            watched_roots_resolved.push(resolve_norm(p));
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
                watched_roots_resolved,
                db,
                job_manager,
                inner_arc,
                tokio_handle,
                config_path,
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

fn is_relevant(path: &Path, scan_archives: bool) -> bool {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_ascii_lowercase()));
    match ext.as_deref() {
        Some(e) => SCAN_EXTS.contains(&e) || (scan_archives && ARCHIVE_EXTS.contains(&e)),
        None => false,
    }
}

/// Python's `os.path.normcase`: case-insensitive and backslash-separated on
/// Windows, byte-exact everywhere else.
fn normcase(path: &Path) -> String {
    let s = path.to_string_lossy().into_owned();
    #[cfg(windows)]
    {
        s.replace('/', "\\").to_lowercase()
    }
    #[cfg(not(windows))]
    {
        s
    }
}

/// Python's `_resolve_path`: `Path.resolve()` + `normcase`, so a root written
/// as `C:/photos` in config.json and an event path delivered as `C:\Photos`
/// (or via a junction such as Japanese Windows' `C:\ユーザー`) compare equal.
/// Comparing the raw strings, as this used to, silently dropped every event as
/// out-of-scope on such setups -- the watcher looked alive and imported nothing.
///
/// A deleted file no longer canonicalizes, so fall back to resolving its parent
/// and re-joining the file name: one lexical level, matching Python's
/// non-strict `resolve()`. This is a scope filter, not a security boundary --
/// the join cannot escape the resolved parent.
fn resolve_norm(path: &Path) -> String {
    if let Ok(c) = std::fs::canonicalize(path) {
        return normcase(&c);
    }
    match (path.parent(), path.file_name()) {
        (Some(parent), Some(name)) => match std::fs::canonicalize(parent) {
            Ok(c) => normcase(&c.join(name)),
            Err(_) => normcase(path),
        },
        _ => normcase(path),
    }
}

fn is_under_watched_root(resolved: &str, watched_roots_resolved: &[String]) -> bool {
    watched_roots_resolved.iter().any(|root| {
        resolved == root.as_str()
            || resolved.starts_with(&format!("{root}{}", std::path::MAIN_SEPARATOR))
    })
}

#[allow(clippy::too_many_arguments)]
fn run_flush_loop(
    event_rx: std::sync::mpsc::Receiver<Event>,
    stop_rx: std::sync::mpsc::Receiver<()>,
    watched_roots_resolved: Vec<String>,
    db: SqlitePool,
    job_manager: Arc<JobManager>,
    inner: Arc<Mutex<Inner>>,
    tokio_handle: tokio::runtime::Handle,
    config_path: PathBuf,
) {
    // Read once per run, matching Python's `_on_register`: these settings are
    // captured when the watcher starts and take effect on the next start/restart.
    // A negative or NaN `debounce_seconds` would panic `from_secs_f64`, so the
    // configured value is clamped rather than trusted.
    let ext_cfg = crate::ext_config::read_config(&config_path).unwrap_or_default();
    let debounce_secs = crate::ext_config::extension_value(
        &ext_cfg,
        crate::routes::watcher::WATCHER_EXT_NAME,
        "debounce_seconds",
    )
    .and_then(|v| v.as_f64())
    .filter(|v| v.is_finite() && *v >= 0.0)
    .unwrap_or(DEBOUNCE_SECS);
    let scan_archives = crate::ext_config::extension_value(
        &ext_cfg,
        crate::routes::watcher::WATCHER_EXT_NAME,
        "scan_archives",
    )
    .and_then(|v| v.as_bool())
    .unwrap_or(true);
    let debounce = Duration::from_secs_f64(debounce_secs);
    let mut pending: HashMap<PathBuf, Action> = HashMap::new();
    let mut last_event = SystemTime::now();

    loop {
        if stop_rx.try_recv().is_ok() {
            // Python's stop() flushes the pending batch before tearing the
            // observer down; dropping it here would silently lose every event
            // buffered inside the debounce window.
            if !pending.is_empty() {
                flush_batch(
                    &mut pending,
                    &watched_roots_resolved,
                    &db,
                    &inner,
                    &tokio_handle,
                    &config_path,
                );
            }
            break;
        }

        match event_rx.recv_timeout(Duration::from_millis(200)) {
            Ok(ev) => {
                process_event(&ev, &mut pending, scan_archives);
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

        flush_batch(
            &mut pending,
            &watched_roots_resolved,
            &db,
            &inner,
            &tokio_handle,
            &config_path,
        );
    }
    info!("Watcher flush loop exited");
}

fn process_event(ev: &Event, pending: &mut HashMap<PathBuf, Action>, scan_archives: bool) {
    for path in &ev.paths {
        if !is_relevant(path, scan_archives) {
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
    watched_roots_resolved: &[String],
    db: &SqlitePool,
    inner: &Arc<Mutex<Inner>>,
    tokio_handle: &tokio::runtime::Handle,
    config_path: &Path,
) {
    // Re-read per flush: a settings change must reach the watcher without a
    // restart, and a flush happens at most every few seconds.
    let toggles = crate::ext_config::parser_toggles(
        &crate::ext_config::read_config(config_path).unwrap_or_default(),
    );
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
        if !is_under_watched_root(&resolve_norm(path), watched_roots_resolved) {
            warn!("Watcher: SKIPPED out-of-scope: {path_str}");
            continue;
        }

        match action {
            Action::Deleted => {
                let db2 = db.clone();
                // Native import (Created/Modified, below) writes DB rows
                // through normalize_db_path (see sweep_common.rs); deletion
                // must match against that same normalized form or a raw event
                // path (differing slash style / case on Windows) leaves the
                // row stranded as is_deleted=0.
                let p = crate::routes::sweep_common::normalize_db_path(&path_str);
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
                let db2 = db.clone();
                let p = path_str.clone();
                // Same per-file ladder as a regular scan (scan_native): a full
                // native import extracts metadata, resolution, tags and the
                // template; only if that fails do we fall back to a bare row,
                // whose sentinel parser_version makes a later scan reprocess
                // the file. Registering the path alone -- as this used to --
                // left watched files permanently untagged.
                let imported = tokio_handle.block_on(async {
                    match native_import_one_with(&db2, &p, false, toggles).await {
                        Ok(id) => Ok(id),
                        Err(e) => {
                            debug!("Watcher: native import failed for {p}: {e}; bare upsert");
                            bare_upsert_one(&db2, &p).await
                        }
                    }
                });
                match imported {
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

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;

    const TEST_KEY: &str = "watcher-test-key";

    /// A root written in non-canonical form (extra `.` segment, trailing
    /// separator) must still match the canonical event paths the OS delivers.
    /// The old raw `starts_with` comparison fails this, which is exactly how a
    /// Windows root spelled `C:/photos` silently dropped every `C:\photos\…`
    /// event.
    #[test]
    fn non_canonical_root_still_matches_event_paths() {
        let dir = tempfile::TempDir::new().unwrap();
        let root = dir.path().join("images");
        std::fs::create_dir(&root).unwrap();
        let file = root.join("a.png");
        std::fs::write(&file, b"x").unwrap();

        let noisy_root = root.join(".").join("..").join("images");
        let roots = vec![resolve_norm(&noisy_root)];

        assert!(is_under_watched_root(&resolve_norm(&file), &roots));
        // A sibling directory sharing the root's string prefix is out of scope.
        let sibling = dir.path().join("images-backup");
        std::fs::create_dir(&sibling).unwrap();
        assert!(!is_under_watched_root(
            &resolve_norm(&sibling.join("b.png")),
            &roots
        ));
    }

    /// A deleted file cannot be canonicalized; its parent still can, so the
    /// scope check must keep working for the delete half of the batch. The
    /// non-canonical segment sits ABOVE the root boundary on purpose: put it
    /// below (`images/./gone.png`) and a raw prefix test still matches, so the
    /// test would pass with the fallback removed. Without the fallback,
    /// `resolve_norm` hands back `.../x/./images/gone.png`, which does not
    /// start with the resolved root -- the delete is dropped and the row stays
    /// alive in the DB forever.
    #[test]
    fn deleted_file_resolves_via_parent() {
        let dir = tempfile::TempDir::new().unwrap();
        let root = dir.path().join("images");
        std::fs::create_dir(&root).unwrap();
        let roots = vec![resolve_norm(&root)];
        let gone = dir
            .path()
            .join(".")
            .join("images")
            .join("already-deleted.png");

        assert!(!gone.exists());
        assert!(is_under_watched_root(&resolve_norm(&gone), &roots));
    }

    #[test]
    fn archives_are_watched_only_when_enabled() {
        assert!(is_relevant(Path::new("/x/a.zip"), true));
        assert!(is_relevant(Path::new("/x/a.7z"), true));
        assert!(!is_relevant(Path::new("/x/a.zip"), false));
        // Regular scan extensions are unaffected by the archive toggle.
        assert!(is_relevant(Path::new("/x/a.PNG"), false));
        assert!(!is_relevant(Path::new("/x/a.txt"), true));
    }

    /// A file dropped into a watched root must come back fully imported --
    /// metadata source and prompt tags -- not merely registered by path.
    /// Injecting `bare_upsert_one` in place of `native_import_one` in
    /// `flush_batch` fails this test on the tag assertion.
    ///
    /// The root is configured in NON-CANONICAL form on purpose: `start` must
    /// resolve it, because the OS delivers canonical event paths. Dropping the
    /// `resolve_norm` call in `start` -- leaving the raw config string as the
    /// scope key, as the pre-fix code did -- fails this test outright, every
    /// event landing as `SKIPPED out-of-scope`. That is the Windows
    /// `C:/photos` vs `C:\photos\…` failure, reproduced on a case-sensitive
    /// filesystem.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn watched_file_is_imported_with_tags() {
        let dir = tempfile::TempDir::new().unwrap();
        let db_path = dir.path().join("tags.db");
        let root = dir.path().join("images");
        std::fs::create_dir(&root).unwrap();
        let noisy_root = root.join(".").join("..").join("images");

        tagdb_core::create_fresh_database(db_path.to_str().unwrap(), TEST_KEY)
            .await
            .expect("genesis");
        let opts = SqliteConnectOptions::from_str(&format!("sqlite:{}", db_path.display()))
            .unwrap()
            .pragma("cipher_memory_security", "OFF")
            .pragma("key", format!("'{TEST_KEY}'"))
            .pragma("mmap_size", "0")
            .create_if_missing(false);
        let pool = SqlitePoolOptions::new()
            .max_connections(2)
            .connect_with(opts)
            .await
            .unwrap();
        tagdb_core::apply_pending_rust_migrations(&pool)
            .await
            .expect("rust migrations");

        let watcher = ScanWatcher::new();
        watcher
            .start(
                vec![ScanRootCfg {
                    path: noisy_root.to_string_lossy().into_owned(),
                    recursive: true,
                }],
                pool.clone(),
                Arc::new(JobManager::new()),
                dir.path().join("config.json"),
            )
            .expect("watcher start");

        // Written after start, so only the watcher can have imported it.
        let image = root.join("sample.png");
        std::fs::write(&image, b"not a real png").unwrap();
        std::fs::write(root.join("sample.txt"), "1girl, solo").unwrap();

        let image_path = image.to_string_lossy().into_owned();
        let deadline = std::time::Instant::now() + Duration::from_secs(30);
        let mut tags: Vec<String> = vec![];
        // Matched by row, not by path text: the watcher stores the event path as
        // the OS delivers it (relative to the watched root, exactly as
        // `scan_native` stores its walk results), so a non-canonical root yields
        // a non-canonical stored path. That is pre-existing, shared behaviour --
        // not what this test is pinning. What it pins is that the file was
        // imported at all, which is what the scope check decides.
        while std::time::Instant::now() < deadline {
            tags = sqlx::query_scalar::<_, String>(
                "SELECT t.tag FROM tags t
                   JOIN file_tags ft ON ft.tag_id = t.id
                   JOIN files f ON f.id = ft.file_id",
            )
            .fetch_all(&pool)
            .await
            .unwrap();
            if !tags.is_empty() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
        watcher.stop();

        let all_paths: Vec<String> = sqlx::query_scalar("SELECT path FROM files")
            .fetch_all(&pool)
            .await
            .unwrap();
        assert!(
            tags.iter().any(|t| t == "1girl"),
            "watcher must import prompt tags, got {tags:?}; rows in DB: {all_paths:?}; \
             watched file: {image_path}"
        );
        let meta_source: Option<String> = sqlx::query_scalar("SELECT meta_source FROM files")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(meta_source.as_deref(), Some("txt"));
    }
}

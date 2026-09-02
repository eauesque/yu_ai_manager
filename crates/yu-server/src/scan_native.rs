//! Rust-native folder scan orchestration (no Python worker process).
//!
//! Walks scan roots and imports each file through the same Tier-1/Tier-3
//! pipeline the image-generation bridges already use
//! (`routes::sweep_common::native_import_one` / `bare_upsert_one`), then
//! syncs deletions. Zip-archive traversal (`scan_zips`) stays out of scope:
//! `is_zip_member` rows are skipped by the deletion-sync queries below so a
//! zip member's virtual path is never mistaken for a missing real file.

use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use scan_core::{iter_files, WalkConfig};
use serde_json::Value;
use sqlx::SqlitePool;

use crate::ext_config::{all_scan_root_paths, read_config, scan_root_configs, ScanRootCfg};
use crate::routes::sweep_common::{bare_upsert_one, native_import_one};
use crate::state::SharedState;

/// Mirrors Python's `core/scan/runtime_prepare.py::SCAN_EXTS`.
const SCAN_EXTS: &[&str] = &[
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".jxl", ".avif", ".heif", ".heic", ".svg", ".webm",
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".ogv", ".mp3", ".wav", ".ogg", ".opus", ".m4a",
    ".aac", ".flac", ".pdf",
];

/// Mirrors `core/configuration/defaults.py::scan_exclude_dirs`.
const DEFAULT_EXCLUDE_DIRS: &[&str] = &[
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "venv",
    ".venv",
    "env",
    "site-packages",
    "dist-packages",
    "custom_nodes",
    "extensions",
    "extensions-builtin",
    "screenshots",
    "reports",
];

const DELETE_CHUNK: usize = 500;

#[derive(Clone, Debug, Default)]
pub struct ScanProgress {
    pub phase: String,
    pub message: String,
    pub current: u64,
    pub total: u64,
    pub detail: String,
}

#[derive(Default)]
pub struct ScanOutcome {
    pub added: u64,
    pub errors: u64,
    pub deleted: u64,
    pub cancelled: bool,
}

fn exclude_dirs(config: &Value) -> Vec<String> {
    config
        .get("scan_exclude_dirs")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_else(|| DEFAULT_EXCLUDE_DIRS.iter().map(|s| s.to_string()).collect())
}

fn scan_exts() -> Vec<String> {
    SCAN_EXTS.iter().map(|s| s.to_string()).collect()
}

/// Enumerate the enabled roots from config.json, keeping each root's
/// `recursive` flag.
pub fn enabled_roots(state: &SharedState) -> Vec<ScanRootCfg> {
    let config = read_config(&state.config.config_path).unwrap_or_default();
    scan_root_configs(&config)
}

/// Every configured root path, enabled or not — see `all_scan_root_paths`.
fn all_root_paths(state: &SharedState) -> Vec<String> {
    let config = read_config(&state.config.config_path).unwrap_or_default();
    all_scan_root_paths(&config)
}

/// Scan one root directory: walk + native import each file, then delete DB
/// rows for files under this root that no longer exist on disk.
pub async fn run_scan_root(
    state: &SharedState,
    root: &str,
    recursive: bool,
    force: bool,
    cancel: &Arc<AtomicBool>,
    mut on_progress: impl FnMut(ScanProgress),
) -> ScanOutcome {
    // An unreadable root (unmounted share, typo) must not be treated as "all
    // files gone" — that would wipe every row under it in sync_deleted_files.
    if !Path::new(root).is_dir() {
        tracing::warn!("scan_native: root not accessible, skipping: {root}");
        on_progress(ScanProgress {
            phase: "error".to_string(),
            message: format!("Root not accessible, skipped: {root}"),
            ..Default::default()
        });
        return ScanOutcome::default();
    }

    let config = read_config(&state.config.config_path).unwrap_or_default();
    let walk_cfg = WalkConfig {
        recursive,
        extensions: scan_exts(),
        exclude_dirs: exclude_dirs(&config),
    };

    on_progress(ScanProgress {
        phase: "listing".to_string(),
        message: format!("Listing files under {root}"),
        ..Default::default()
    });

    // Directory walking is synchronous I/O; keep it off the tokio worker.
    let root_buf = Path::new(root).to_path_buf();
    let cancel_for_walk = cancel.clone();
    let files: Vec<std::path::PathBuf> = tokio::task::spawn_blocking(move || {
        iter_files(&root_buf, &walk_cfg, Some(cancel_for_walk)).collect()
    })
    .await
    .unwrap_or_default();
    let total = files.len() as u64;

    let mut outcome = ScanOutcome::default();
    for (idx, path) in files.iter().enumerate() {
        if cancel.load(Ordering::Relaxed) {
            outcome.cancelled = true;
            return outcome;
        }
        let path_str = path.to_string_lossy().into_owned();
        let ok = match native_import_one(&state.db, &path_str, force).await {
            Ok(_) => true,
            Err(e) => {
                tracing::debug!("scan_native: rust-native import failed for {path_str}: {e}");
                bare_upsert_one(&state.db, &path_str).await.is_ok()
            }
        };
        if ok {
            outcome.added += 1;
        } else {
            outcome.errors += 1;
        }

        let current = idx as u64 + 1;
        if current.is_multiple_of(20) || current == total {
            on_progress(ScanProgress {
                phase: "scanning".to_string(),
                message: format!("Scanning {root}"),
                current,
                total,
                detail: path_str,
            });
        }
    }

    outcome.deleted = sync_deleted_files(&state.db, root, total).await;
    outcome
}

/// Scan every enabled root from config.json sequentially, then purge DB
/// entries no longer under any registered root (orphans left behind after a
/// root is removed from config.json).
pub async fn run_scan_all(
    state: &SharedState,
    force: bool,
    cancel: &Arc<AtomicBool>,
    mut on_progress: impl FnMut(ScanProgress),
) -> ScanOutcome {
    let roots = enabled_roots(state);
    if roots.is_empty() {
        on_progress(ScanProgress {
            phase: "error".to_string(),
            message: "No enabled scan roots".to_string(),
            ..Default::default()
        });
        return ScanOutcome::default();
    }

    let mut outcome = ScanOutcome::default();
    let n = roots.len();
    for (idx, r) in roots.iter().enumerate() {
        if cancel.load(Ordering::Relaxed) {
            outcome.cancelled = true;
            return outcome;
        }
        on_progress(ScanProgress {
            phase: "scanning".to_string(),
            message: format!("Scanning root {}/{}: {}", idx + 1, n, r.path),
            current: idx as u64,
            total: n as u64,
            detail: r.path.clone(),
        });
        let root_outcome =
            run_scan_root(state, &r.path, r.recursive, force, cancel, &mut on_progress).await;
        outcome.added += root_outcome.added;
        outcome.errors += root_outcome.errors;
        outcome.deleted += root_outcome.deleted;
        if root_outcome.cancelled {
            outcome.cancelled = true;
            return outcome;
        }
    }

    on_progress(ScanProgress {
        phase: "cleanup".to_string(),
        message: "Detecting orphan files...".to_string(),
        current: n as u64,
        total: n as u64,
        ..Default::default()
    });
    // Orphan purge must consider every registered root, not just enabled
    // ones — a disabled root's files are absent from disk-side comparison
    // (not walked) but stay registered, so they must not be classified as
    // "no longer registered" and deleted.
    outcome.deleted += purge_orphan_files(&state.db, &all_root_paths(state)).await;
    outcome
}

/// Delete `files`/`file_tags`/`templates` rows under `root` whose path no
/// longer exists on disk. Zip-member rows (`is_zip_member = 1`) are excluded
/// — their `path` is an archive-internal virtual path, not a real file, so a
/// plain existence check would always misreport them as deleted.
///
/// `walked` is how many files the just-completed walk of `root` yielded.
/// If it found none but the DB still has rows registered under `root`, that
/// is far more likely a partial read failure (unmounted mid-walk, permission
/// error) than a genuinely emptied folder, so deletion sync is skipped
/// rather than wiping every row. The same >50%-of-matched-rows floor used by
/// `purge_orphan_files` guards the LIKE-prefix match itself.
async fn sync_deleted_files(pool: &SqlitePool, root: &str, walked: u64) -> u64 {
    fn escape_like(s: &str) -> String {
        s.replace('%', "\\%").replace('_', "\\_")
    }
    // A trailing "/%"/"\\%" separator (not bare "%") keeps a root like
    // "O:/Pictures" from also matching a sibling "O:/Pictures2/...".
    let fwd = format!(
        "{}/%",
        escape_like(&root.replace('\\', "/")).trim_end_matches('/')
    );
    let bwd = format!(
        "{}\\%",
        escape_like(&root.replace('/', "\\")).trim_end_matches('\\')
    );

    let rows: Vec<(i64, String)> = sqlx::query_as(
        "SELECT id, path FROM files \
         WHERE (path LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\') \
           AND is_deleted = 0 AND is_zip_member = 0",
    )
    .bind(&fwd)
    .bind(&bwd)
    .fetch_all(pool)
    .await
    .unwrap_or_default();
    let matched = rows.len();

    if walked == 0 && matched > 0 {
        tracing::warn!(
            "scan_native: walk of {root} yielded 0 files but {matched} DB rows are registered under it, skipping deletion sync (likely partial read failure)"
        );
        return 0;
    }

    // Filesystem existence checks are blocking I/O; run off the tokio worker.
    let missing_ids: Vec<i64> = tokio::task::spawn_blocking(move || {
        rows.into_iter()
            .filter(|(_, path)| !Path::new(path).exists())
            .map(|(id, _)| id)
            .collect()
    })
    .await
    .unwrap_or_default();

    if exceeds_delete_floor(missing_ids.len(), matched) {
        tracing::warn!(
            "scan_native: deletion sync for {root} would delete {}/{matched} matched rows, skipping as likely path mismatch",
            missing_ids.len()
        );
        return 0;
    }

    let count = missing_ids.len() as u64;
    delete_file_ids(pool, &missing_ids).await;
    count
}

/// Pure predicate factored out of `purge_orphan_files` for testability: is
/// `path` outside every root in `normalized_roots` (already `\`→`/`,
/// trailing-slash-trimmed)? Comparison goes through `normalize_for_compare`
/// so a case-only difference between a registered root and a walked path
/// (routine on Windows/macOS, whose filesystems are case-insensitive) can't
/// make a live file look orphaned and get deleted.
fn is_orphan(path: &str, normalized_roots: &[String]) -> bool {
    let norm = crate::routes::scan_roots::normalize_for_compare(path);
    !normalized_roots.iter().any(|root| {
        let root = crate::routes::scan_roots::normalize_for_compare(root);
        norm == root || norm.starts_with(&format!("{root}/"))
    })
}

/// Shared safety-floor check for both delete paths: true when `candidates`
/// exceeds half of `total` matched/registered rows, the point at which a
/// path-normalization mismatch is a more likely explanation than a genuine
/// mass deletion.
fn exceeds_delete_floor(candidates: usize, total: usize) -> bool {
    total > 0 && candidates * 2 > total
}

/// Delete rows not under any currently-registered root at all (leftovers
/// from a root that was removed from config.json — `roots` must be *every*
/// configured root, enabled or disabled, see `all_scan_root_paths`).
/// Zip-member rows are excluded for the same reason as `sync_deleted_files`.
///
/// A safety floor guards against a normalization mismatch between `roots`
/// and `files.path` (case, separators, unresolved symlinks) turning the
/// whole table into a false-positive orphan set: if more than half of all
/// rows would be deleted, skip and log instead of deleting.
async fn purge_orphan_files(pool: &SqlitePool, roots: &[String]) -> u64 {
    if roots.is_empty() {
        return 0;
    }
    let normalized: Vec<String> = roots
        .iter()
        .map(|r| r.replace('\\', "/").trim_end_matches('/').to_string())
        .collect();

    let rows: Vec<(i64, String)> =
        sqlx::query_as("SELECT id, path FROM files WHERE is_deleted = 0 AND is_zip_member = 0")
            .fetch_all(pool)
            .await
            .unwrap_or_default();
    let total = rows.len();

    let orphan_ids: Vec<i64> = tokio::task::spawn_blocking(move || {
        rows.into_iter()
            .filter(|(_, path)| is_orphan(path, &normalized))
            .map(|(id, _)| id)
            .collect()
    })
    .await
    .unwrap_or_default();

    if exceeds_delete_floor(orphan_ids.len(), total) {
        tracing::warn!(
            "scan_native: orphan purge would delete {}/{total} rows, skipping as likely root-path mismatch",
            orphan_ids.len()
        );
        return 0;
    }

    let count = orphan_ids.len() as u64;
    delete_file_ids(pool, &orphan_ids).await;
    count
}

async fn delete_file_ids(pool: &SqlitePool, ids: &[i64]) {
    for chunk in ids.chunks(DELETE_CHUNK) {
        let placeholders = vec!["?"; chunk.len()].join(",");
        // Null out dangling zip-extraction references before deleting rows
        // they point to (mirrors routes::scan_admin::scanned_roots_purge).
        let null_sql = format!(
            "UPDATE files SET extracted_to_file_id = NULL WHERE extracted_to_file_id IN ({placeholders})"
        );
        let mut q = sqlx::query(&null_sql);
        for id in chunk {
            q = q.bind(id);
        }
        if let Err(e) = q.execute(pool).await {
            tracing::warn!("scan_native: clearing extracted_to_file_id failed: {e}");
        }

        for table_and_col in [
            ("file_tags", "file_id"),
            ("templates", "file_id"),
            ("files", "id"),
        ] {
            let (table, col) = table_and_col;
            let sql = format!("DELETE FROM {table} WHERE {col} IN ({placeholders})");
            let mut q = sqlx::query(&sql);
            for id in chunk {
                q = q.bind(id);
            }
            if let Err(e) = q.execute(pool).await {
                tracing::warn!("scan_native: delete from {table} failed: {e}");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{exceeds_delete_floor, is_orphan};

    fn norm(roots: &[&str]) -> Vec<String> {
        roots
            .iter()
            .map(|r| r.replace('\\', "/").trim_end_matches('/').to_string())
            .collect()
    }

    #[test]
    fn row_under_disabled_root_is_not_orphan() {
        // purge_orphan_files must be called with ALL roots (enabled + disabled),
        // so a disabled root's own path still counts as "registered".
        let roots = norm(&["O:/Pictures", "O:/Disabled"]);
        assert!(!is_orphan("O:/Disabled/a.png", &roots));
        assert!(!is_orphan("O:/Pictures/sub/b.png", &roots));
    }

    #[test]
    fn row_outside_every_root_is_orphan() {
        let roots = norm(&["O:/Pictures"]);
        assert!(is_orphan("O:/Elsewhere/a.png", &roots));
    }

    #[test]
    fn windows_backslash_path_matches_forward_slash_root() {
        let roots = norm(&["O:/Pictures"]);
        assert!(!is_orphan(r"O:\Pictures\sub\b.png", &roots));
    }

    #[test]
    fn case_only_mismatch_is_not_orphan_on_windows() {
        // Registered root and a walked path differing only in case (drive
        // letter, folder name) must not be treated as "outside the root" —
        // Windows/macOS filesystems are case-insensitive, so this is routine,
        // not a sign the file moved.
        let roots = norm(&["o:/pictures"]);
        assert_eq!(
            is_orphan("O:/Pictures/sub/b.png", &roots),
            !cfg!(windows),
            "case-only path difference must not flag a live file as orphaned on Windows"
        );
    }

    #[test]
    fn safety_floor_blocks_majority_deletion() {
        assert!(exceeds_delete_floor(6, 10)); // 60% -> blocked
        assert!(!exceeds_delete_floor(5, 10)); // exactly half -> allowed
        assert!(!exceeds_delete_floor(0, 0)); // nothing matched -> allowed (no-op)
    }
}

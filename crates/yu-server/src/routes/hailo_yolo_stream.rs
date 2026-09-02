//! Native filesystem routes and un-wired rule logic for Hailo YOLO streams.
//!
//! Tests in this module that can wait on child processes, channels, semaphores, or similar
//! synchronization must use a bounded real-time timeout and panic when the deadline expires.
//! Without that timeout, a broken test hangs instead of reporting `FAILED`, so CI cannot
//! distinguish a hang from a test that is still running. This defect recurred in T2 and T3a.
//! Tests must not use a fixed real-time sleep to assume work has probably finished: load can
//! exceed that margin and cause intermittent failures. Use a virtual clock with
//! `tokio::time::pause()` or explicit synchronization instead. This defect occurred in the T4,
//! T5, and T6b tests and reproduced in three of six full-suite runs.

use axum::{
    body::Body,
    http::{Request, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use std::{path::Path, time::UNIX_EPOCH};
use tower::ServiceExt;
use tower_http::services::ServeFile;

use crate::path_guard;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

pub(crate) mod actions;
pub(crate) mod config;
pub(crate) mod detect;
pub(crate) mod devices;
pub(crate) mod draw;
pub(crate) mod frame_source;
pub(crate) mod handlers;
pub(crate) mod input;
pub(crate) mod mjpeg;
pub(crate) mod recorder;
pub(crate) mod registry;
pub(crate) mod rules;
pub(crate) mod secrets;
pub(crate) mod source_task;

#[cfg(test)]
pub(crate) fn run_bounded_test(
    timeout: std::time::Duration,
    test: impl std::future::Future<Output = ()> + Send + 'static,
) {
    run_bounded_test_with_time(timeout, false, test);
}

#[cfg(test)]
pub(crate) fn run_bounded_paused_test(
    timeout: std::time::Duration,
    test: impl std::future::Future<Output = ()> + Send + 'static,
) {
    run_bounded_test_with_time(timeout, true, test);
}

#[cfg(test)]
fn run_bounded_test_with_time(
    timeout: std::time::Duration,
    start_paused: bool,
    test: impl std::future::Future<Output = ()> + Send + 'static,
) {
    use std::{
        panic::{catch_unwind, resume_unwind, AssertUnwindSafe},
        sync::mpsc::{self, RecvTimeoutError},
        thread,
    };

    let (done_tx, done_rx) = mpsc::channel();
    let worker = thread::spawn(move || {
        let result = catch_unwind(AssertUnwindSafe(|| {
            let runtime = if start_paused {
                tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .start_paused(true)
                    .build()
            } else {
                tokio::runtime::Builder::new_multi_thread()
                    .worker_threads(2)
                    .enable_all()
                    .build()
            }
            .unwrap();
            runtime.block_on(test);
        }));
        let _ = done_tx.send(result);
    });

    match done_rx.recv_timeout(timeout) {
        Ok(result) => {
            worker.join().unwrap();
            if let Err(panic) = result {
                resume_unwind(panic);
            }
        }
        Err(RecvTimeoutError::Timeout) => {
            panic!("test exceeded the {timeout:?} real-time deadline")
        }
        Err(RecvTimeoutError::Disconnected) => {
            worker.join().expect("bounded test worker panicked");
            panic!("bounded test worker disconnected")
        }
    }
}

#[derive(Debug, Serialize)]
struct Recording {
    name: String,
    path: String,
    size_bytes: u64,
    modified: f64,
}

pub(crate) async fn recordings(
    state: &SharedState,
    auth_context: Option<&AuthContext>,
) -> Response {
    if let Some(response) = require_admin_scope(state.config.pin_auth_enabled, auth_context) {
        return response;
    }

    // Resolve from project_root for CWD-independent access, but keep the legacy
    // relative path in JSON because the stream UI treats it as a public contract.
    let directory = state.config.project_root.join("detections").join("videos");
    if !tokio::fs::metadata(&directory)
        .await
        .is_ok_and(|metadata| metadata.is_dir())
    {
        return Json(serde_json::json!({"status": "ok", "recordings": []})).into_response();
    }

    match list_recordings(&directory).await {
        Ok(recordings) => {
            Json(serde_json::json!({"status": "ok", "recordings": recordings})).into_response()
        }
        Err(error) => {
            tracing::error!(%error, "failed to list Hailo YOLO recordings");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({"error": "Failed to list recordings"})),
            )
                .into_response()
        }
    }
}

async fn list_recordings(directory: &Path) -> std::io::Result<Vec<Recording>> {
    let mut entries = tokio::fs::read_dir(directory).await?;
    let mut names = Vec::new();
    while let Some(entry) = entries.next_entry().await? {
        let name = entry.file_name().to_string_lossy().into_owned();
        if name.ends_with(".mp4") {
            names.push(name);
        }
    }
    names.sort();

    let mut recordings = Vec::with_capacity(names.len());
    for name in names {
        let path = directory.join(&name);
        let Ok(metadata) = tokio::fs::metadata(&path).await else {
            continue;
        };
        let Ok(modified) = metadata.modified() else {
            continue;
        };
        let modified = modified.duration_since(UNIX_EPOCH).map_or_else(
            |error| -error.duration().as_secs_f64(),
            |duration| duration.as_secs_f64(),
        );
        recordings.push(Recording {
            path: format!("./detections/videos/{name}"),
            name,
            size_bytes: metadata.len(),
            modified,
        });
    }
    Ok(recordings)
}

pub(crate) async fn snapshot(
    state: &SharedState,
    auth_context: Option<&AuthContext>,
    filename: &str,
) -> Response {
    if let Some(response) = require_admin_scope(state.config.pin_auth_enabled, auth_context) {
        return response;
    }

    let Some(path) = resolve_snapshot(&state.config.project_root, filename).await else {
        return (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "Not found"})),
        )
            .into_response();
    };

    match ServeFile::new(path)
        .oneshot(Request::new(Body::empty()))
        .await
    {
        Ok(response) => response.into_response(),
        Err(error) => match error {},
    }
}

/// Resolves a requested snapshot filename to a real file inside the snapshot
/// directory, or `None` if it does not exist or resolves outside the directory.
///
/// `Path::file_name()` discards any directory components in `filename`, matching
/// Python's `os.path.basename` semantics (`..`, an absolute path, `/`, and a
/// path with only directory components all yield `None` here). That alone is
/// not sufficient: the containment check below is the actual security boundary.
/// `tokio::fs::canonicalize` on the *full* joined path resolves every symlink
/// in the chain (including the final component) the same way `realpath(3)`
/// does, so a symlink placed inside the snapshot directory that points outside
/// it resolves to its real, outside target before the containment check runs.
/// `path_guard::path_is_within` then compares the two canonical paths
/// component-wise (not a string prefix compare), so a sibling directory whose
/// name happens to share a prefix (e.g. `snapshots-backup`) cannot be
/// misclassified as "inside". See `crates/yu-server/src/path_guard.rs` for the
/// rationale on why an unresolved comparison is unsafe.
async fn resolve_snapshot(project_root: &Path, filename: &str) -> Option<std::path::PathBuf> {
    let safe = Path::new(filename).file_name()?;
    let directory = project_root.join("detections").join("snapshots");
    let resolved_directory = tokio::fs::canonicalize(&directory).await.ok()?;
    let resolved_path = tokio::fs::canonicalize(directory.join(safe)).await.ok()?;
    let metadata = tokio::fs::metadata(&resolved_path).await.ok()?;
    (metadata.is_file() && path_guard::path_is_within(&resolved_path, &resolved_directory))
        .then_some(resolved_path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    async fn write(path: &Path, contents: &[u8]) {
        if let Some(parent) = path.parent() {
            tokio::fs::create_dir_all(parent).await.unwrap();
        }
        tokio::fs::write(path, contents).await.unwrap();
    }

    #[test]
    fn resolve_snapshot_serves_a_real_file_inside_the_directory() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let snapshots = root.path().join("detections").join("snapshots");
            write(&snapshots.join("real.jpg"), b"SNAPSHOT-BYTES").await;

            let resolved = resolve_snapshot(root.path(), "real.jpg").await;
            assert_eq!(
                resolved,
                Some(
                    tokio::fs::canonicalize(snapshots.join("real.jpg"))
                        .await
                        .unwrap()
                )
            );
        });
    }

    #[test]
    fn resolve_snapshot_path_escape_fixtures_never_leave_the_directory() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let snapshots = root.path().join("detections").join("snapshots");
            write(&snapshots.join("real.jpg"), b"SNAPSHOT-BYTES").await;

            let fixtures: &[&str] = &[
                "..",
                "../../etc/passwd",
                "/etc/passwd",
                "/",
                "\\",
                "C:\\Windows\\win.ini",
                "\\\\server\\share\\file",
                "evil\0.mp4",
                "",
            ];
            for filename in fixtures {
                assert_eq!(
                    resolve_snapshot(root.path(), filename).await,
                    None,
                    "fixture {filename:?} unexpectedly resolved to a path"
                );
            }
        });
    }

    #[cfg(unix)]
    #[test]
    fn resolve_snapshot_blocks_an_outward_symlink_placed_inside_the_directory() {
        use std::os::unix::fs::symlink;

        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let snapshots = root.path().join("detections").join("snapshots");
            tokio::fs::create_dir_all(&snapshots).await.unwrap();
            let outside = root.path().join("outside");
            write(&outside.join("secret.txt"), b"SECRET-OUTSIDE").await;

            // A symlink that lives inside the snapshot directory but whose target
            // resolves outside it. This is the exact shape the module doc and the
            // T8b task call out: naive containment checks that compare an
            // unresolved (lexical) path against a canonicalized base pass this
            // case even though the real file is outside the directory.
            symlink(outside.join("secret.txt"), snapshots.join("escape")).unwrap();

            assert_eq!(
                resolve_snapshot(root.path(), "escape").await,
                None,
                "outward symlink must not resolve to a servable path"
            );
        });
    }

    #[cfg(unix)]
    #[test]
    fn list_recordings_filters_sorts_and_skips_stat_failures() {
        use std::os::unix::fs::symlink;

        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let videos = root.path().join("detections").join("videos");
            write(&videos.join("b.mp4"), b"B").await;
            write(&videos.join("a.mp4"), b"A").await;
            write(&videos.join("note.txt"), b"not a recording").await;
            // A dangling symlink ending in .mp4 passes the name filter but fails
            // `tokio::fs::metadata`, so it must be silently skipped, matching
            // Python's `except OSError: continue`.
            symlink(videos.join("does-not-exist"), videos.join("broken.mp4")).unwrap();

            let recordings = list_recordings(&videos).await.unwrap();
            let names: Vec<&str> = recordings.iter().map(|r| r.name.as_str()).collect();
            assert_eq!(names, ["a.mp4", "b.mp4"]);
            for recording in &recordings {
                assert_eq!(
                    recording.path,
                    format!("./detections/videos/{}", recording.name)
                );
                assert!(recording.size_bytes > 0);
            }
        });
    }

    const TEST_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(15);
}

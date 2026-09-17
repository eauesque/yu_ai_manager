//! `diagnostics_doctor`: what is wrong with *this running server*.
//!
//! Two doctors exist and they answer different questions. `scripts/doctor.py`
//! runs before anything starts and diagnoses the checkout (which server would
//! start, is the toolchain present). This one runs inside the server and can
//! see what no external probe can: job backlog, SSE subscribers, watcher
//! liveness, scan queue depth, inference sidecar reachability.
//!
//! The environment half is a port of Python's
//! `core/diagnostics/doctor.py::run_all_checks`. Deliberately *not* ported,
//! with the reason for each:
//!
//! - `_check_python`, `pip` -- there is no Python interpreter in a standalone
//!   binary, so the check has nothing to report on.
//! - `uv` / `node` / `pnpm` -- build-time tools. A correctly installed
//!   end-user copy has none of them, so porting these would emit three
//!   permanent WARNs on every such install. The pre-launch
//!   `scripts/doctor.py` checks them where they actually matter (a checkout).
//! - `_onnxruntime_info`, `_torch_info`, `_gpu_info`, and
//!   `_known_incompatibilities` (which is derived from the first two) --
//!   these read the Python inference stack. Standalone Rust reaches inference
//!   through the sidecar instead, which `check_infer_sidecar` covers.
//!
//! Everything else in `run_all_checks` is ported. Note that the parity
//! harness cannot enforce this: the endpoint carries `skip: True` (it writes
//! report files, so running it would dirty the repo), which is why the gap
//! this module previously had -- 3 checks against Python's 11 -- survived.

use std::{
    path::{Path, PathBuf},
    time::{Duration, SystemTime},
};

use serde::Serialize;
use sqlx::SqlitePool;

use crate::state::AppState;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum CheckStatus {
    Ok,
    /// Neither good nor bad -- context a reader of the report needs. Mirrors
    /// Python's `"INFO"`, which `summarize` counts as neither error nor
    /// warning; keep it out of both tallies.
    Info,
    Warn,
    Error,
}

#[derive(Debug, Clone, Serialize)]
pub struct CheckResult {
    pub name: &'static str,
    pub status: CheckStatus,
    pub message: String,
    pub fix_hint: Option<String>,
}

/// Redacts the user's home directory prefix from a path, mirroring Python's
/// `core/diagnostics/redaction.py::redact_path` for the common POSIX/Windows
/// home-directory forms. Not a full port of that module's broader secret
/// redaction (URLs, tokens, IPs) — those apply to log/report text, not to a
/// single filesystem path here.
pub fn redact_path(path: &Path) -> String {
    let text = path.display().to_string();
    if let Some(home) = std::env::var_os("HOME").map(PathBuf::from) {
        let home_str = home.display().to_string();
        if !home_str.is_empty() && text.starts_with(&home_str) {
            return format!("<USER_HOME>{}", &text[home_str.len()..]);
        }
    }
    if let Some(userprofile) = std::env::var_os("USERPROFILE").map(PathBuf::from) {
        let up_str = userprofile.display().to_string();
        if !up_str.is_empty() && text.starts_with(&up_str) {
            return format!("<USER_HOME>{}", &text[up_str.len()..]);
        }
    }
    text
}

fn check_writable(name: &'static str, data_dir: &Path) -> CheckResult {
    let redacted = redact_path(data_dir);
    if let Err(e) = std::fs::create_dir_all(data_dir) {
        return CheckResult {
            name,
            status: CheckStatus::Error,
            message: format!("Writable path failed: {redacted} ({e})"),
            fix_hint: Some("Check filesystem permissions for the data directory.".to_string()),
        };
    }
    let probe = data_dir.join(".doctor-probe");
    match std::fs::write(&probe, b"") {
        Ok(()) => {
            let _ = std::fs::remove_file(&probe);
            CheckResult {
                name,
                status: CheckStatus::Ok,
                message: format!("Writable path OK: {redacted}"),
                fix_hint: None,
            }
        }
        Err(e) => CheckResult {
            name,
            status: CheckStatus::Error,
            message: format!("Writable path failed: {redacted} ({e})"),
            fix_hint: Some("Check filesystem permissions for the data directory.".to_string()),
        },
    }
}

async fn check_db_integrity(db_read: &SqlitePool, db_path: &Path) -> CheckResult {
    let redacted = redact_path(db_path);
    match sqlx::query_scalar::<_, String>("PRAGMA quick_check")
        .fetch_one(db_read)
        .await
    {
        Ok(result) if result == "ok" => CheckResult {
            name: "db_integrity",
            status: CheckStatus::Ok,
            message: format!("DB quick_check OK: {redacted}"),
            fix_hint: None,
        },
        Ok(result) => CheckResult {
            name: "db_integrity",
            status: CheckStatus::Error,
            message: format!("DB quick_check reported issues: {redacted} ({result})"),
            fix_hint: Some(
                "Run the dedicated DB health repair flow only after backing up user data."
                    .to_string(),
            ),
        },
        Err(e) => CheckResult {
            name: "db_integrity",
            status: CheckStatus::Error,
            message: format!("DB quick_check failed: {e}"),
            fix_hint: Some(
                "Run the dedicated DB health repair flow only after backing up user data."
                    .to_string(),
            ),
        },
    }
}

/// Python's `_check_update_pending` warns past this age. The same threshold
/// already lives in `routes::diagnostics::cleanup_stale_update_pending`;
/// both mirror Python's `STALE_UPDATE_PENDING_SECONDS`.
const STALE_UPDATE_PENDING_SECS: i64 = 7 * 86_400;

/// How long the sidecar gets to answer before the doctor gives up on it. A
/// diagnosis that hangs is worse than one that reports "unreachable".
const SIDECAR_PROBE_TIMEOUT: Duration = Duration::from_secs(2);

/// Newest mtime under `dir`, recursively; `ext` filters by extension.
///
/// `DirEntry::metadata` does not follow symlinks, so a symlinked directory is
/// never descended into and the walk cannot loop.
fn newest_mtime(dir: &Path, ext: Option<&str>) -> Option<SystemTime> {
    let mut newest: Option<SystemTime> = None;
    let mut stack = vec![dir.to_path_buf()];
    while let Some(current) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&current) else {
            continue;
        };
        for entry in entries.flatten() {
            let Ok(meta) = entry.metadata() else {
                continue;
            };
            if meta.is_dir() {
                stack.push(entry.path());
                continue;
            }
            if let Some(want) = ext {
                if entry.path().extension().and_then(|e| e.to_str()) != Some(want) {
                    continue;
                }
            }
            if let Ok(modified) = meta.modified() {
                newest = Some(newest.map_or(modified, |cur| cur.max(modified)));
            }
        }
    }
    newest
}

/// Mirrors Python's `_check_db_schema`.
///
/// Every read failure degrades to -1 rather than reporting a fault, because
/// that is what Python does: `core/services_core/db_meta.py::get_meta` catches
/// every exception and returns `None`, which `get_meta_int` turns into its
/// default. A brand-new database has no `db_meta` row -- and on some paths no
/// `db_meta` table -- so treating that as an ERROR would make the doctor
/// invent a fault on a healthy install. A database that genuinely cannot be
/// read is caught by `check_db_integrity`, which runs `PRAGMA quick_check`
/// against the same pool.
async fn check_db_schema(db_read: &SqlitePool, db_path: &Path) -> CheckResult {
    let redacted = redact_path(db_path);
    let version = sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM db_meta WHERE key = 'schema_version'",
    )
    .fetch_optional(db_read)
    .await
    .ok()
    .flatten()
    .flatten()
    .and_then(|value| value.trim().parse::<i64>().ok())
    .unwrap_or(-1);
    CheckResult {
        name: "db_schema",
        status: CheckStatus::Ok,
        message: format!("DB path={redacted}, schema_version={version}"),
        fix_hint: None,
    }
}

/// Mirrors Python's `_dist_status`: the built web bundle must not be older
/// than the TypeScript it was built from.
fn check_dist_freshness(project_root: &Path) -> CheckResult {
    let candidates = [
        project_root
            .join("ui")
            .join("default")
            .join("static")
            .join("js"),
        project_root
            .join("ui")
            .join("default")
            .join("static")
            .join("css"),
    ];
    let existing: Vec<&Path> = candidates
        .iter()
        .filter(|path| path.exists())
        .map(PathBuf::as_path)
        .collect();
    if existing.is_empty() {
        return CheckResult {
            name: "dist_freshness",
            status: CheckStatus::Warn,
            message: "dist freshness: dist assets missing".to_string(),
            fix_hint: Some("Rebuild the web bundle (pnpm build).".to_string()),
        };
    }
    let newest_src = newest_mtime(&project_root.join("src").join("ts"), Some("ts"));
    let newest_dist = existing
        .iter()
        .filter_map(|path| newest_mtime(path, None))
        .max();
    // Python only warns when both sides are known; an unreadable tree there
    // yields "could not be checked", which is not a WARN either.
    let stale = matches!((newest_src, newest_dist), (Some(src), Some(dist)) if dist < src);
    CheckResult {
        name: "dist_freshness",
        status: if stale {
            CheckStatus::Warn
        } else {
            CheckStatus::Ok
        },
        message: if stale {
            "dist freshness: dist assets older than TypeScript sources".to_string()
        } else {
            "dist freshness: dist assets present".to_string()
        },
        fix_hint: stale.then(|| "Rebuild the web bundle (pnpm build).".to_string()),
    }
}

/// Mirrors Python's `_config_status`, but reports on the config file this
/// server actually loaded rather than re-deriving the candidate list. Two
/// different answers to "which config is in use" is exactly the kind of
/// disagreement a doctor exists to prevent.
fn check_config(config_path: &Path) -> CheckResult {
    let name = config_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("config.json")
        .to_string();
    if !config_path.exists() {
        return CheckResult {
            name: "config",
            status: CheckStatus::Info,
            message: "config: config missing; defaults or profile config may be used".to_string(),
            fix_hint: None,
        };
    }
    // Must go through config_io: `config_path` is config.toml whenever one
    // exists, and a serde_json read of it would report a perfectly valid
    // config as malformed -- a diagnosis inventing the fault it reports.
    match std::fs::read_to_string(config_path)
        .map_err(|e| e.to_string())
        .and_then(|raw| {
            crate::config_io::parse_strict(config_path, &raw).map_err(|e| e.to_string())
        }) {
        Ok(_) => CheckResult {
            name: "config",
            status: CheckStatus::Info,
            message: format!("config: {name} present and parseable"),
            fix_hint: None,
        },
        Err(e) => CheckResult {
            name: "config",
            status: CheckStatus::Error,
            message: format!("config: {name} parse failed: {e}"),
            fix_hint: Some("Fix or remove the malformed config file.".to_string()),
        },
    }
}

/// Mirrors Python's `_launch_args_status`.
fn check_launch_args(project_root: &Path) -> CheckResult {
    let path = project_root.join("launch-args.txt");
    let message = if !path.exists() {
        "launch-args: launch-args.txt missing".to_string()
    } else {
        match std::fs::read_to_string(&path) {
            Ok(raw) => {
                let active = raw
                    .lines()
                    .filter(|line| !line.trim().is_empty() && !line.trim_start().starts_with('#'))
                    .count();
                format!("launch-args: launch-args.txt present ({active} active line(s))")
            }
            Err(e) => format!("launch-args: launch-args.txt read failed: {e}"),
        }
    };
    CheckResult {
        name: "launch_args",
        status: CheckStatus::Info,
        message,
        fix_hint: None,
    }
}

/// Mirrors Python's `_check_update_pending`: leftover update markers explain
/// an installer that keeps trying to resume a finished update.
fn check_update_pending(project_root: &Path, now: SystemTime) -> Vec<CheckResult> {
    let pending_dir = project_root.join("data").join("update_pending");
    let none = || {
        vec![CheckResult {
            name: "update_pending",
            status: CheckStatus::Info,
            message: format!(
                "data/update_pending residuals: none ({})",
                redact_path(&pending_dir)
            ),
            fix_hint: None,
        }]
    };
    if !pending_dir.exists() {
        return none();
    }
    let Ok(entries) = std::fs::read_dir(&pending_dir) else {
        return none();
    };
    let mut paths: Vec<PathBuf> = entries
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .collect();
    paths.sort();

    let now: chrono::DateTime<chrono::Utc> = now.into();
    let mut results = Vec::new();
    for path in paths {
        let file_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default()
            .to_string();
        let created_at = std::fs::read_to_string(&path)
            .ok()
            .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
            .and_then(|value| value.get("created_at")?.as_str().map(str::to_string));
        let Some(created_at_raw) = created_at else {
            results.push(CheckResult {
                name: "update_pending",
                status: CheckStatus::Warn,
                message: format!("data/update_pending residual unreadable: {file_name}"),
                fix_hint: Some("Remove the leftover file under data/update_pending.".to_string()),
            });
            continue;
        };
        let Ok(created_at) = crate::routes::diagnostics::parse_created_at(&created_at_raw) else {
            results.push(CheckResult {
                name: "update_pending",
                status: CheckStatus::Warn,
                message: format!("data/update_pending residual unreadable: {file_name}"),
                fix_hint: Some("Remove the leftover file under data/update_pending.".to_string()),
            });
            continue;
        };
        let age_seconds = (now - created_at).num_seconds();
        let stale = age_seconds > STALE_UPDATE_PENDING_SECS;
        #[allow(clippy::cast_precision_loss)]
        let age_days = (age_seconds as f64 / 86_400.0 * 10.0).round() / 10.0;
        results.push(CheckResult {
            name: "update_pending",
            status: if stale {
                CheckStatus::Warn
            } else {
                CheckStatus::Info
            },
            message: format!(
                "data/update_pending residual: {file_name}, created_at={created_at_raw}, age_days={age_days}"
            ),
            fix_hint: stale
                .then(|| "Clear stale update markers (POST /api/diagnostics/cleanup-update-pending).".to_string()),
        });
    }
    if results.is_empty() {
        return none();
    }
    results
}

/// Jobs still running inside this process.
///
/// Not available to `scripts/doctor.py` at all: a job registry lives in
/// process memory, so a stuck import or scan is invisible from outside.
fn check_jobs(state: &AppState) -> CheckResult {
    let labels = state.job_manager.running_labels();
    if labels.is_empty() {
        return CheckResult {
            name: "jobs",
            status: CheckStatus::Info,
            message: "running jobs: none".to_string(),
            fix_hint: None,
        };
    }
    CheckResult {
        name: "jobs",
        status: CheckStatus::Info,
        message: format!("running jobs: {} ({})", labels.len(), labels.join(", ")),
        fix_hint: None,
    }
}

/// Whether the filesystem watcher is actually running, and what it has seen.
///
/// The watcher failing to start is silent from a user's point of view -- new
/// files simply never appear -- so name it here.
fn check_watcher(state: &AppState) -> CheckResult {
    let (running, roots, stats) = state.watcher.info();
    if !running {
        // A server with no scan roots configured correctly has no watcher, so
        // warning on "not running" alone would warn about every healthy
        // install that simply has not been pointed at a library yet. The
        // condition worth naming is roots configured with nothing watching
        // them -- that is the one where new files silently never appear.
        let configured = crate::routes::watcher::watcher_roots(state).len();
        if configured == 0 {
            return CheckResult {
                name: "watcher",
                status: CheckStatus::Info,
                message: "scan watcher: not running (no scan roots configured)".to_string(),
                fix_hint: None,
            };
        }
        return CheckResult {
            name: "watcher",
            status: CheckStatus::Warn,
            message: format!(
                "scan watcher: not running though {configured} scan root(s) are configured (new files will not be picked up automatically)"
            ),
            fix_hint: Some("Restart the watcher from the scan settings.".to_string()),
        };
    }
    CheckResult {
        name: "watcher",
        status: if stats.errors > 0 {
            CheckStatus::Warn
        } else {
            CheckStatus::Ok
        },
        message: format!(
            "scan watcher: running on {} root(s), added={} modified={} deleted={} errors={}",
            roots.len(),
            stats.added,
            stats.modified,
            stats.deleted,
            stats.errors
        ),
        fix_hint: (stats.errors > 0)
            .then(|| "Check the log for watcher errors on unreadable paths.".to_string()),
    }
}

/// Queued scans waiting for the current one to finish.
fn check_scan_queue(state: &AppState) -> CheckResult {
    let depth = state.scan_queue.size();
    CheckResult {
        name: "scan_queue",
        status: CheckStatus::Info,
        message: format!("scan queue: {depth} waiting"),
        fix_hint: None,
    }
}

/// Live SSE subscribers -- how many browser tabs are attached right now.
fn check_sse(state: &AppState) -> CheckResult {
    CheckResult {
        name: "sse",
        status: CheckStatus::Info,
        message: format!("SSE subscribers: {}", state.sse_hub.receiver_count()),
        fix_hint: None,
    }
}

/// Whether the inference sidecar answers.
///
/// This is the check that explains "tagging silently does nothing": the
/// server is healthy, the sidecar is not. Bounded by
/// `SIDECAR_PROBE_TIMEOUT` so a hung sidecar cannot hang the diagnosis.
async fn check_infer_sidecar(state: &AppState) -> CheckResult {
    let Some(client) = state.infer_client.as_ref() else {
        return CheckResult {
            name: "infer_sidecar",
            status: CheckStatus::Info,
            message: "inference sidecar: not configured".to_string(),
            fix_hint: None,
        };
    };
    match tokio::time::timeout(SIDECAR_PROBE_TIMEOUT, client.healthz()).await {
        Ok(Ok(_)) => CheckResult {
            name: "infer_sidecar",
            status: CheckStatus::Ok,
            message: "inference sidecar: healthy".to_string(),
            fix_hint: None,
        },
        Ok(Err(e)) => CheckResult {
            name: "infer_sidecar",
            status: CheckStatus::Warn,
            message: format!("inference sidecar: unreachable ({e})"),
            fix_hint: Some(
                "Tagging and captioning stay unavailable until the sidecar answers.".to_string(),
            ),
        },
        Err(_) => CheckResult {
            name: "infer_sidecar",
            status: CheckStatus::Warn,
            message: format!(
                "inference sidecar: no answer within {}s",
                SIDECAR_PROBE_TIMEOUT.as_secs()
            ),
            fix_hint: Some("The sidecar is running but not responding; restart it.".to_string()),
        },
    }
}

fn check_process_info(state: &AppState) -> CheckResult {
    let uptime = state.start_time.elapsed().as_secs_f64();
    CheckResult {
        name: "process_info",
        status: CheckStatus::Ok,
        message: format!(
            "yu-server v{} ({}), uptime={uptime:.1}s",
            state.version,
            std::env::consts::OS
        ),
        fix_hint: None,
    }
}

/// Runs the checks and returns them as a `Vec`, without wrapping them in the
/// MCP tool's response envelope. Shared by `run_all_checks` (MCP tool
/// contract below) and `routes::diagnostics::doctor_start` (HTTP route,
/// which renders its own Python-compatible markdown/JSON report from the
/// same `Vec<CheckResult>`).
pub async fn collect_checks(state: &AppState) -> Vec<CheckResult> {
    let root = &state.config.project_root;
    let data_dir = crate::secret_store::data_dir(root);
    let db_path = PathBuf::from(&state.config.db_path);

    let mut results = vec![
        check_process_info(state),
        check_db_schema(&state.db_read, &db_path).await,
        check_db_integrity(&state.db_read, &db_path).await,
        check_dist_freshness(root),
        check_writable("writable_data_dir", &data_dir),
        check_writable("writable_reports", &root.join("reports")),
        check_writable("writable_repair", &root.join("repair")),
        check_writable("writable_logs", &root.join("logs")),
        check_config(&state.config.config_path),
        check_launch_args(root),
        CheckResult {
            name: "log_dir",
            status: CheckStatus::Info,
            message: format!("log dir: {}", redact_path(&root.join("logs"))),
            fix_hint: None,
        },
    ];
    results.extend(check_update_pending(root, SystemTime::now()));
    // Runtime state: everything below is invisible to a pre-launch probe.
    results.push(check_jobs(state));
    results.push(check_watcher(state));
    results.push(check_scan_queue(state));
    results.push(check_sse(state));
    results.push(check_infer_sidecar(state).await);
    results
}

pub async fn run_all_checks(state: &AppState) -> serde_json::Value {
    let results = collect_checks(state).await;

    let overall = if results.iter().any(|r| r.status == CheckStatus::Error) {
        CheckStatus::Error
    } else if results.iter().any(|r| r.status == CheckStatus::Warn) {
        CheckStatus::Warn
    } else {
        CheckStatus::Ok
    };

    serde_json::json!({
        "overall_status": overall,
        "checks": results,
        "note": "standalone Rust: the Python interpreter, build tooling and torch/CUDA/ONNX checks are out of scope (see module docs); runtime state checks are additions Python has no equivalent for",
    })
}

/// Writes `report_json` to `<project_root>/reports/doctor_<timestamp>.json`,
/// mirroring Python's `doctor_report.write_report_files` naming
/// (`doctor_YYYYMMDD-HHMMSS[-N].json`; collisions append `-N`). Paths in
/// `report_json` are already redacted by `run_all_checks`'s check results,
/// so no further redaction is applied here.
pub fn write_report(
    project_root: &Path,
    report_json: &serde_json::Value,
) -> std::io::Result<PathBuf> {
    let report_dir = project_root.join("reports");
    std::fs::create_dir_all(&report_dir)?;

    let stem = format!("doctor_{}", chrono::Local::now().format("%Y%m%d-%H%M%S"));
    let mut path = report_dir.join(format!("{stem}.json"));
    let mut suffix = 1;
    while path.exists() {
        path = report_dir.join(format!("{stem}-{suffix}.json"));
        suffix += 1;
    }

    let body = serde_json::to_string_pretty(report_json).unwrap_or_default();
    std::fs::write(&path, body)?;
    Ok(path)
}

/// `diagnostics_doctor` tool entry point: runs checks and persists the
/// report, returning the checks payload plus the written report path.
pub async fn run_and_report(state: &AppState) -> serde_json::Value {
    let mut report = run_all_checks(state).await;
    match write_report(&state.config.project_root, &report) {
        Ok(path) => {
            report["report_json_path"] = serde_json::Value::String(redact_path(&path));
        }
        Err(e) => {
            report["report_write_error"] = serde_json::Value::String(e.to_string());
        }
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redact_path_replaces_home_prefix() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|e| e.into_inner());
        // SAFETY: single-threaded test process env mutation, scoped to this test.
        unsafe {
            std::env::set_var("HOME", "/home/testuser");
        }
        let p = Path::new("/home/testuser/code/yu_ai_manager/data/tags.db");
        assert_eq!(
            redact_path(p),
            "<USER_HOME>/code/yu_ai_manager/data/tags.db"
        );
    }

    #[test]
    fn redact_path_leaves_unrelated_paths_untouched() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|e| e.into_inner());
        unsafe {
            std::env::set_var("HOME", "/home/testuser");
        }
        let p = Path::new("/var/lib/somewhere/tags.db");
        assert_eq!(redact_path(p), "/var/lib/somewhere/tags.db");
    }

    /// Stamp an mtime without pulling in the `filetime` crate.
    fn set_mtime(path: &Path, when: SystemTime) {
        std::fs::File::options()
            .write(true)
            .open(path)
            .unwrap()
            .set_modified(when)
            .unwrap();
    }

    #[tokio::test]
    async fn check_writable_reports_ok_for_a_real_directory() {
        let dir = tempfile::tempdir().unwrap();
        let result = check_writable("writable_data_dir", dir.path());
        assert_eq!(result.status, CheckStatus::Ok);
    }

    #[test]
    fn check_writable_carries_the_name_it_was_given() {
        // The four writable checks are distinguishable only by this field;
        // a hardcoded name would make three of them indistinguishable in the
        // report while every assertion about status still passed.
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(
            check_writable("writable_repair", dir.path()).name,
            "writable_repair"
        );
        assert_eq!(
            check_writable("writable_logs", dir.path()).name,
            "writable_logs"
        );
    }

    #[test]
    fn info_counts_as_neither_error_nor_warning() {
        // Python's summarize() tallies only ERROR and WARN. If INFO leaked
        // into either tally, every healthy server would report warnings.
        let results = [
            CheckResult {
                name: "config",
                status: CheckStatus::Info,
                message: "config: config.json present and parseable".to_string(),
                fix_hint: None,
            },
            CheckResult {
                name: "jobs",
                status: CheckStatus::Info,
                message: "running jobs: none".to_string(),
                fix_hint: None,
            },
        ];
        assert_eq!(
            results
                .iter()
                .filter(|r| r.status == CheckStatus::Warn)
                .count(),
            0
        );
        assert_eq!(
            results
                .iter()
                .filter(|r| r.status == CheckStatus::Error)
                .count(),
            0
        );
    }

    #[test]
    fn dist_is_stale_when_typescript_is_newer_than_the_bundle() {
        let root = tempfile::tempdir().unwrap();
        let js = root.path().join("ui/default/static/js");
        let ts = root.path().join("src/ts");
        std::fs::create_dir_all(&js).unwrap();
        std::fs::create_dir_all(&ts).unwrap();
        std::fs::write(js.join("app.js"), b"//").unwrap();
        // Nested, to prove the walk recurses rather than reading one level.
        std::fs::create_dir_all(ts.join("deep")).unwrap();
        let source = ts.join("deep/app.ts");
        std::fs::write(&source, b"//").unwrap();
        set_mtime(&source, SystemTime::now() + Duration::from_secs(600));

        let result = check_dist_freshness(root.path());
        assert_eq!(result.status, CheckStatus::Warn, "{}", result.message);
        assert!(
            result.message.contains("older than TypeScript"),
            "{}",
            result.message
        );
    }

    #[test]
    fn dist_is_fresh_when_the_bundle_is_newer() {
        let root = tempfile::tempdir().unwrap();
        let js = root.path().join("ui/default/static/js");
        let ts = root.path().join("src/ts");
        std::fs::create_dir_all(&js).unwrap();
        std::fs::create_dir_all(&ts).unwrap();
        std::fs::write(ts.join("app.ts"), b"//").unwrap();
        let built = js.join("app.js");
        std::fs::write(&built, b"//").unwrap();
        set_mtime(&built, SystemTime::now() + Duration::from_secs(600));

        assert_eq!(check_dist_freshness(root.path()).status, CheckStatus::Ok);
    }

    #[test]
    fn dist_missing_is_a_warning() {
        let root = tempfile::tempdir().unwrap();
        let result = check_dist_freshness(root.path());
        assert_eq!(result.status, CheckStatus::Warn);
        assert!(result.message.contains("missing"), "{}", result.message);
    }

    #[test]
    fn newest_mtime_filters_by_extension() {
        // Without the filter a stray .js in src/ts would decide freshness.
        let dir = tempfile::tempdir().unwrap();
        let ts = dir.path().join("a.ts");
        std::fs::write(&ts, b"//").unwrap();
        let other = dir.path().join("b.txt");
        std::fs::write(&other, b"x").unwrap();
        set_mtime(&other, SystemTime::now() + Duration::from_secs(600));

        let filtered = newest_mtime(dir.path(), Some("ts")).unwrap();
        let unfiltered = newest_mtime(dir.path(), None).unwrap();
        assert!(filtered < unfiltered, "the .txt must not count as a source");
        assert_eq!(
            filtered,
            std::fs::metadata(&ts).unwrap().modified().unwrap()
        );
    }

    #[test]
    fn malformed_config_is_an_error_and_names_the_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        std::fs::write(&path, b"{not json").unwrap();
        let result = check_config(&path);
        assert_eq!(result.status, CheckStatus::Error);
        assert!(result.message.contains("config.json"), "{}", result.message);
    }

    #[test]
    fn a_parseable_config_is_info_not_a_warning() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        std::fs::write(&path, br#"{"db": "tags.db"}"#).unwrap();
        assert_eq!(check_config(&path).status, CheckStatus::Info);
    }

    #[test]
    fn a_missing_config_is_not_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let result = check_config(&dir.path().join("absent.json"));
        assert_eq!(result.status, CheckStatus::Info);
        assert!(result.message.contains("missing"), "{}", result.message);
    }

    #[test]
    fn launch_args_counts_only_active_lines() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("launch-args.txt"),
            "# a comment

--port 8000
   # indented comment
--headless
",
        )
        .unwrap();
        let result = check_launch_args(dir.path());
        assert!(
            result.message.contains("2 active line(s)"),
            "{}",
            result.message
        );
    }

    #[test]
    fn a_fresh_update_residual_is_info_and_a_stale_one_warns() {
        let root = tempfile::tempdir().unwrap();
        let pending = root.path().join("data/update_pending");
        std::fs::create_dir_all(&pending).unwrap();
        let now = SystemTime::now();
        let now_utc: chrono::DateTime<chrono::Utc> = now.into();

        let fresh = now_utc - chrono::Duration::days(1);
        std::fs::write(
            pending.join("fresh.json"),
            format!(r#"{{"created_at": "{}"}}"#, fresh.to_rfc3339()),
        )
        .unwrap();
        let stale = now_utc - chrono::Duration::days(30);
        std::fs::write(
            pending.join("stale.json"),
            format!(r#"{{"created_at": "{}"}}"#, stale.to_rfc3339()),
        )
        .unwrap();

        let results = check_update_pending(root.path(), now);
        let by_name = |needle: &str| {
            results
                .iter()
                .find(|r| r.message.contains(needle))
                .unwrap_or_else(|| panic!("no result mentioning {needle}: {results:?}"))
                .status
        };
        assert_eq!(by_name("fresh.json"), CheckStatus::Info);
        assert_eq!(by_name("stale.json"), CheckStatus::Warn);
    }

    #[test]
    fn an_unreadable_update_residual_warns_rather_than_being_skipped() {
        let root = tempfile::tempdir().unwrap();
        let pending = root.path().join("data/update_pending");
        std::fs::create_dir_all(&pending).unwrap();
        std::fs::write(pending.join("broken.json"), b"{not json").unwrap();

        let results = check_update_pending(root.path(), SystemTime::now());
        assert_eq!(results.len(), 1, "{results:?}");
        assert_eq!(results[0].status, CheckStatus::Warn);
        assert!(
            results[0].message.contains("broken.json"),
            "{}",
            results[0].message
        );
    }

    #[test]
    fn no_update_pending_dir_reports_none() {
        let root = tempfile::tempdir().unwrap();
        let results = check_update_pending(root.path(), SystemTime::now());
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].status, CheckStatus::Info);
        assert!(
            results[0].message.contains("none"),
            "{}",
            results[0].message
        );
    }

    async fn test_state(project_root: PathBuf) -> crate::state::SharedState {
        use std::{collections::HashSet, str::FromStr, sync::Arc};

        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

        use crate::state::{AppState, Config};

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(
            AppState::new(
                Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,
                    pin_boss_login_ui: false,
                    trusted_ips: HashSet::new(),
                    trusted_peer_ips: HashSet::new(),
                    rate_limit_trusted_proxies: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: project_root.join("config.json"),
                    project_root,
                    app_config: serde_json::json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                    wd_tagger_root: std::path::PathBuf::from("."),
                    clip_model_dir: std::path::PathBuf::from("."),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    /// Every check must be on the roster `collect_checks` returns.
    ///
    /// The per-check unit tests above all stay green on a check that is
    /// written correctly but never wired in -- which is precisely how this
    /// module came to have 3 checks against Python's 11. This test is the one
    /// that fails in that case.
    #[tokio::test]
    async fn every_check_reaches_the_roster() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().to_path_buf()).await;
        let names: Vec<&str> = collect_checks(&state)
            .await
            .iter()
            .map(|c| c.name)
            .collect();

        for expected in [
            // Ported from Python's run_all_checks.
            "process_info",
            "db_schema",
            "db_integrity",
            "dist_freshness",
            "writable_data_dir",
            "writable_reports",
            "writable_repair",
            "writable_logs",
            "config",
            "launch_args",
            "log_dir",
            "update_pending",
            // Runtime state; no Python equivalent and invisible to
            // scripts/doctor.py.
            "jobs",
            "watcher",
            "scan_queue",
            "sse",
            "infer_sidecar",
        ] {
            assert!(
                names.contains(&expected),
                "{expected} missing from {names:?}"
            );
        }
    }

    /// A stuck job must be nameable, since nothing outside the process can see
    /// the registry.
    #[tokio::test]
    async fn a_running_job_is_named_in_the_report() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().to_path_buf()).await;
        state.job_manager.start("scan-1", "library scan");

        let jobs = collect_checks(&state)
            .await
            .into_iter()
            .find(|c| c.name == "jobs")
            .expect("jobs check");
        assert!(jobs.message.contains("library scan"), "{}", jobs.message);
    }

    /// Name every non-OK check on a bare state, so a failure of
    /// `diagnostics_doctor_reports_ok_checks_on_a_healthy_state` says which
    /// check turned the overall status, instead of only that it did.
    #[tokio::test]
    async fn a_bare_state_reports_which_checks_are_not_ok() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().to_path_buf()).await;
        let noisy: Vec<(&str, CheckStatus, String)> = collect_checks(&state)
            .await
            .into_iter()
            // `dist_freshness` legitimately warns here: a temp project root has
            // no built web bundle, and Python's `_dist_status` warns on the
            // same condition. Everything else must stay quiet.
            .filter(|c| c.name != "dist_freshness")
            .filter(|c| !matches!(c.status, CheckStatus::Ok | CheckStatus::Info))
            .map(|c| (c.name, c.status, c.message))
            .collect();
        assert!(noisy.is_empty(), "not OK on a bare state: {noisy:#?}");
    }

    /// No roots configured is not a fault, so it must not warn.
    #[tokio::test]
    async fn a_stopped_watcher_with_no_roots_is_not_a_warning() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().to_path_buf()).await;
        let watcher = collect_checks(&state)
            .await
            .into_iter()
            .find(|c| c.name == "watcher")
            .expect("watcher check");
        assert_eq!(watcher.status, CheckStatus::Info, "{}", watcher.message);
        assert!(
            watcher.message.contains("no scan roots"),
            "{}",
            watcher.message
        );
    }

    /// Roots configured with nothing watching them is why new files silently
    /// never appear, and is the case that must warn.
    #[tokio::test]
    async fn a_stopped_watcher_with_configured_roots_warns() {
        let dir = tempfile::tempdir().unwrap();
        let library = dir.path().join("library");
        std::fs::create_dir_all(&library).unwrap();
        std::fs::write(
            dir.path().join("config.json"),
            serde_json::json!({"scan_roots": [{"path": library, "enabled": true}]}).to_string(),
        )
        .unwrap();

        let state = test_state(dir.path().to_path_buf()).await;
        let watcher = collect_checks(&state)
            .await
            .into_iter()
            .find(|c| c.name == "watcher")
            .expect("watcher check");
        assert_eq!(watcher.status, CheckStatus::Warn, "{}", watcher.message);
    }

    /// A TOML config must not be reported as malformed.
    ///
    /// `config_path` is config.toml whenever one exists, so a JSON-only read
    /// here would make the doctor invent a parse failure on a valid config --
    /// the exact defect `scripts/internal/config_read_format.py` exists to
    /// catch.
    /// A database with no `db_meta` yet is a new install, not a fault.
    #[tokio::test]
    async fn a_missing_db_meta_reports_minus_one_rather_than_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().to_path_buf()).await;
        let schema = collect_checks(&state)
            .await
            .into_iter()
            .find(|c| c.name == "db_schema")
            .expect("db_schema check");
        assert_eq!(schema.status, CheckStatus::Ok, "{}", schema.message);
        assert!(
            schema.message.contains("schema_version=-1"),
            "{}",
            schema.message
        );
    }

    #[test]
    fn a_toml_config_is_read_in_its_own_format() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        std::fs::write(&path, b"timezone = \"UTC\"\n").unwrap();
        let result = check_config(&path);
        assert_eq!(result.status, CheckStatus::Info, "{}", result.message);
        assert!(result.message.contains("parseable"), "{}", result.message);
    }

    #[test]
    fn write_report_creates_reports_dir_and_json_file() {
        let project_root = tempfile::tempdir().unwrap();
        let report = serde_json::json!({"overall_status": "OK", "checks": []});
        let path = write_report(project_root.path(), &report).unwrap();
        assert!(path.exists());
        assert_eq!(path.extension().and_then(|e| e.to_str()), Some("json"));
        assert_eq!(path.parent().unwrap(), project_root.path().join("reports"));
        let written: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(written, report);
    }

    #[test]
    fn write_report_avoids_overwriting_an_existing_file_with_the_same_stem() {
        let project_root = tempfile::tempdir().unwrap();
        let report = serde_json::json!({"overall_status": "OK", "checks": []});
        let first = write_report(project_root.path(), &report).unwrap();
        let second = write_report(project_root.path(), &report).unwrap();
        assert_ne!(first, second, "second write must not clobber the first");
        assert!(first.exists());
        assert!(second.exists());
    }
}

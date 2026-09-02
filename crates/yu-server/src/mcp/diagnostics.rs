//! Minimal `diagnostics_doctor` port for standalone Rust.
//!
//! Python's `core/diagnostics/doctor.py::run_all_checks` inspects the
//! Python toolchain itself (pip/uv, torch, CUDA, ONNX Runtime provider),
//! which has no meaning in a standalone Rust binary where none of that is
//! present. Only the environment-agnostic checks are ported here: DB
//! integrity, data-directory writability, and this process's own runtime
//! info. See the approved spec's O-1 for the full scoping rationale.

use std::path::{Path, PathBuf};

use serde::Serialize;
use sqlx::SqlitePool;

use crate::state::AppState;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum CheckStatus {
    Ok,
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

fn check_writable(data_dir: &Path) -> CheckResult {
    let redacted = redact_path(data_dir);
    if let Err(e) = std::fs::create_dir_all(data_dir) {
        return CheckResult {
            name: "writable_data_dir",
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
                name: "writable_data_dir",
                status: CheckStatus::Ok,
                message: format!("Writable path OK: {redacted}"),
                fix_hint: None,
            }
        }
        Err(e) => CheckResult {
            name: "writable_data_dir",
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
    let data_dir = crate::secret_store::data_dir(&state.config.project_root);
    let db_path = PathBuf::from(&state.config.db_path);

    vec![
        check_process_info(state),
        check_writable(&data_dir),
        check_db_integrity(&state.db_read, &db_path).await,
    ]
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
        "note": "standalone Rust subset: Python toolchain/torch/CUDA/ONNX checks are out of scope",
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

    #[tokio::test]
    async fn check_writable_reports_ok_for_a_real_directory() {
        let dir = tempfile::tempdir().unwrap();
        let result = check_writable(dir.path());
        assert_eq!(result.status, CheckStatus::Ok);
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

#![allow(clippy::result_large_err)]
//! Agent Safety Gateway: Kill Switch (Phase 1).
//!
//! Native port of Python `routes/agent_api_core.py` kill/resume endpoints.
//! Cross-process contract: the kill flag file path MUST match Python
//! `kill_switch._kill_flag_path()` = `core.paths.data_path("agent_kill.flag")`
//! so the Python MCP subprocess observes a kill issued via this server.
//!
//! Only kill/resume are ported in Phase 1. status / circuit-breaker / budget
//! stay on the Python proxy (volatile session_id + in-memory-only fields make
//! their live-oracle parity unachievable until parity is redefined — Phase 1b).
//!
//! Event-bus note: Python `kill()`/`resume()` also emit `agent.killed` /
//! `agent.resumed` on `core.event_bus` for in-process subscribers. A kill issued
//! via this Rust endpoint is observed by Python only through the flag file
//! (polled in `is_killed()`), so synchronous in-process Python event subscribers
//! do not fire. This matches the existing cross-process model: a kill from the
//! MCP subprocess is likewise detected via file poll, not via the web process's
//! event bus.

use std::path::{Path, PathBuf};

use axum::{
    extract::{rejection::JsonRejection, State},
    response::{IntoResponse, Response},
    Json,
};
use chrono::Utc;
use serde_json::{json, Value};

use crate::state::SharedState;

/// Default reason matching Python `data.get("reason", "Manual kill via API")`.
const DEFAULT_KILL_REASON: &str = "Manual kill via API";

/// Kill flag path, identical to Python `kill_switch._kill_flag_path()`.
/// `secret_store::data_dir` mirrors `core.paths`: `$TAGDB_DATA_DIR` else
/// `<project_root>/data`. Production launches the Rust server with
/// `project_root == cwd`, so this resolves to the same absolute path Python uses.
pub(crate) fn kill_flag_path(project_root: &Path) -> PathBuf {
    crate::secret_store::data_dir(project_root).join("agent_kill.flag")
}

/// Write the kill flag at `flag_path` with `reason` as content (activate).
/// Mirrors Python `AgentKillSwitch.kill`: best-effort I/O (errors are logged,
/// never raised) and the returned status reports `killed: true` regardless of
/// write success, matching Python's in-memory `status()` right after `kill()`.
/// Takes the resolved path (not `project_root`) so it is unit-testable without
/// depending on `TAGDB_DATA_DIR` / `data_dir` resolution.
fn write_kill_flag(flag_path: &Path, reason: &str) -> Value {
    if let Some(parent) = flag_path.parent() {
        if let Err(error) = std::fs::create_dir_all(parent) {
            tracing::warn!(?error, "failed to create data dir for kill flag");
        }
    }
    if let Err(error) = std::fs::write(flag_path, reason) {
        tracing::warn!(?error, "failed to write kill flag file");
    }
    json!({
        "killed": true,
        "reason": reason,
        "killed_at": Utc::now().to_rfc3339(),
    })
}

/// Remove the kill flag at `flag_path` (deactivate).
/// Mirrors Python `AgentKillSwitch.resume`: `unlink(missing_ok=True)` and
/// best-effort error handling. Returns the post-resume status.
fn remove_kill_flag(flag_path: &Path) -> Value {
    match std::fs::remove_file(flag_path) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => tracing::warn!(?error, "failed to remove kill flag file"),
    }
    json!({"killed": false, "reason": "", "killed_at": ""})
}

/// Extract `reason` like Python `str(data.get("reason", "Manual kill via API"))`.
///
/// Documented divergence: Python coerces any JSON value to string via `str()`
/// (`{"reason": 42}` → `"42"`). This Rust port treats a non-string / absent /
/// invalid body as the default reason instead. kill/resume are excluded from the
/// live parity oracle (see inputs.yaml skip), so this degenerate-input gap is not
/// a parity-gate concern; the default is always a valid, safe reason.
fn extract_reason(body: Result<Json<Value>, JsonRejection>) -> String {
    match body {
        Ok(Json(Value::Object(map))) => map
            .get("reason")
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| DEFAULT_KILL_REASON.to_string()),
        _ => DEFAULT_KILL_REASON.to_string(),
    }
}

/// POST /api/agent/kill — activate Kill Switch.
pub async fn agent_kill(
    State(state): State<SharedState>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    let reason = extract_reason(body);
    let status = write_kill_flag(&kill_flag_path(&state.config.project_root), &reason);
    api_result(json!({"ok": true, "status": status}))
}

/// POST /api/agent/resume — deactivate Kill Switch.
pub async fn agent_resume(State(state): State<SharedState>) -> Response {
    let status = remove_kill_flag(&kill_flag_path(&state.config.project_root));
    api_result(json!({"ok": true, "status": status}))
}

/// Mirror Python `api_result`: merge payload at top level, ensure ok/error/data.
fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return Json(json!({"ok": true, "error": null, "data": other})).into_response();
        }
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static COUNTER: AtomicU64 = AtomicU64::new(0);

    /// Unique temp dir per call. The I/O tests pass an explicit flag path under
    /// this dir, so they never read `TAGDB_DATA_DIR` / `data_dir` and stay
    /// hermetic even under parallel test threads.
    fn temp_dir() -> PathBuf {
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let dir = std::env::temp_dir().join(format!("yu_agent_kill_{}_{}", std::process::id(), n));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn write_then_remove_kill_flag_roundtrip() {
        let dir = temp_dir();
        let flag = dir.join("agent_kill.flag");

        let status = write_kill_flag(&flag, "boom");
        assert_eq!(status["killed"], true);
        assert_eq!(status["reason"], "boom");
        assert!(!status["killed_at"].as_str().unwrap().is_empty());
        assert!(flag.exists(), "flag file must exist after kill");
        // Cross-process content contract: Python is_killed() reads this content.
        assert_eq!(std::fs::read_to_string(&flag).unwrap(), "boom");

        let status = remove_kill_flag(&flag);
        assert_eq!(status["killed"], false);
        assert_eq!(status["reason"], "");
        assert_eq!(status["killed_at"], "");
        assert!(!flag.exists(), "flag file must be gone after resume");

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn remove_absent_flag_is_ok() {
        let dir = temp_dir();
        let status = remove_kill_flag(&dir.join("agent_kill.flag"));
        assert_eq!(status["killed"], false);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn write_creates_missing_parent_dir() {
        let dir = temp_dir();
        // Parent ("data") does not exist yet — mirrors Python mkdir(parents=True).
        let flag = dir.join("data").join("agent_kill.flag");
        let status = write_kill_flag(&flag, "x");
        assert_eq!(status["killed"], true);
        assert!(flag.exists(), "parent dir must be created on write");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn extract_reason_defaults_when_absent() {
        assert_eq!(extract_reason(Ok(Json(json!({})))), "Manual kill via API");
    }

    #[test]
    fn extract_reason_uses_provided_string() {
        assert_eq!(
            extract_reason(Ok(Json(json!({"reason": "stop now"})))),
            "stop now"
        );
    }

    #[test]
    fn extract_reason_non_string_falls_back_to_default() {
        // Documented divergence from Python str(): non-string reason → default.
        assert_eq!(
            extract_reason(Ok(Json(json!({"reason": 42})))),
            "Manual kill via API"
        );
        assert_eq!(
            extract_reason(Ok(Json(json!({"reason": null})))),
            "Manual kill via API"
        );
    }

    #[test]
    fn flag_path_uses_python_contract_filename() {
        // Holds regardless of TAGDB_DATA_DIR: both $TAGDB_DATA_DIR/agent_kill.flag
        // and <project_root>/data/agent_kill.flag end with this exact name.
        assert!(kill_flag_path(Path::new("/some/root")).ends_with("agent_kill.flag"));
    }
}

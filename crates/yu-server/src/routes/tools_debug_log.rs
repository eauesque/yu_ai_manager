//! tools_debug_log.rs -- the debug log viewer (`/api/tools/debug-log*`).
//!
//! These three routes were fabricated stubs: `debug_log()` always answered
//! `enabled: false`, `debug_log_clear()` deleted nothing and answered
//! `{"ok": true}`, and **neither carried an authorization check** while Python
//! requires admin scope and a loopback client. A stub that answers 200 is
//! worse than a 501: the UI cannot tell it apart from a real empty log.
//!
//! Path and enablement resolution mirror `core/infra_core/debug_log.py` and
//! `core/paths.py`:
//!   - enabled  <- `TAGDB_DEBUG` in {1, true, yes, on, debug} (case-insensitive)
//!   - log file <- `TAGDB_DEBUG_LOG`, else `<log dir>/debug.log`
//!   - log dir  <- `TAGDB_LOG_DIR`, else `<cwd>/logs`

use axum::{
    extract::{ConnectInfo, Extension, Query, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::json;
use std::net::SocketAddr;
use std::path::PathBuf;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::routes::tools_fs::is_local;
use crate::state::SharedState;

/// Mirrors `core/infra_core/debug_log.py:_DEBUG_ENABLED`.
///
/// Python evaluates this once at module load; we read the environment each
/// time. The variable is set before startup in both, so the observable
/// behaviour is the same -- and re-reading avoids a stale answer after a
/// live restart, which reuses the process.
fn is_debug_enabled() -> bool {
    let raw = std::env::var("TAGDB_DEBUG").unwrap_or_default();
    matches!(
        raw.trim().to_ascii_lowercase().as_str(),
        "1" | "true" | "yes" | "on" | "debug"
    )
}

/// Mirrors `get_debug_log_path()` over `core/paths.py:log_path("debug.log")`.
fn debug_log_path() -> PathBuf {
    let explicit = std::env::var("TAGDB_DEBUG_LOG").unwrap_or_default();
    if !explicit.trim().is_empty() {
        return PathBuf::from(explicit.trim());
    }
    let log_dir = std::env::var("TAGDB_LOG_DIR").unwrap_or_default();
    if !log_dir.trim().is_empty() {
        return PathBuf::from(log_dir.trim()).join("debug.log");
    }
    PathBuf::from("logs").join("debug.log")
}

/// Admin scope AND a loopback client, matching Python's two-call preamble.
/// The log carries whatever the operator's machine logged; it is not
/// something to hand to a LAN peer holding an admin PIN.
/// Takes `pin_auth_enabled` rather than the whole `SharedState` so both
/// halves can be exercised without standing up a server.
fn gate_local_admin(
    pin_auth_enabled: bool,
    auth: Option<&Extension<AuthContext>>,
    addr: Option<&Extension<ConnectInfo<SocketAddr>>>,
    what: &str,
) -> Option<Response> {
    if let Some(r) = require_admin_scope(pin_auth_enabled, auth.map(|e| &e.0)) {
        return Some(r);
    }
    if !is_local(addr.map(|e| &e.0)) {
        return Some(
            (
                StatusCode::FORBIDDEN,
                Json(json!({
                    "ok": false,
                    "error": format!("{what} is only available from the local machine"),
                })),
            )
                .into_response(),
        );
    }
    None
}

#[derive(Deserialize)]
pub struct DebugLogQuery {
    limit: Option<i64>,
    filter: Option<String>,
}

/// GET /api/tools/debug-log
pub async fn debug_log(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
    Query(params): Query<DebugLogQuery>,
) -> Response {
    if let Some(r) = gate_local_admin(
        s.config.pin_auth_enabled,
        auth.as_ref(),
        addr.as_ref(),
        "Log view",
    ) {
        return r;
    }
    if !is_debug_enabled() {
        return Json(
            json!({"ok": true, "error": null, "data": null, "enabled": false, "lines": []}),
        )
        .into_response();
    }

    let path = debug_log_path();
    if !path.exists() {
        return Json(json!({
            "ok": true,
            "error": null,
            "data": null,
            "enabled": true,
            "lines": [],
            "total_lines": 0,
            "log_path": path.to_string_lossy(),
            "log_size_kb": 0,
        }))
        .into_response();
    }

    let text = match tokio::fs::read(&path).await {
        Ok(bytes) => String::from_utf8_lossy(&bytes).into_owned(),
        Err(error) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": format!("Failed to read log: {error}")})),
            )
                .into_response();
        }
    };

    // Python clamps to [1, 5000] with a default of 200. A caller asking for
    // 100_000 lines gets 5000, not the whole file.
    // `clamp(1, 5000)` leaves a positive value, but say so without a cast.
    let limit = usize::try_from(params.limit.unwrap_or(200).clamp(1, 5000)).unwrap_or(200);
    let filter = params.filter.unwrap_or_default();
    let filter = filter.trim();

    let all_lines: Vec<&str> = text.lines().collect();
    let total = all_lines.len();
    let filtered: Vec<&str> = if filter.is_empty() {
        all_lines
    } else {
        all_lines
            .into_iter()
            .filter(|l| l.contains(filter))
            .collect()
    };
    // The LAST `limit` lines -- a log viewer wants the tail, not the head.
    let tail: Vec<&str> = filtered
        .iter()
        .skip(filtered.len().saturating_sub(limit))
        .copied()
        .collect();

    let size_kb = match tokio::fs::metadata(&path).await {
        Ok(meta) => (meta.len() as f64 / 1024.0 * 10.0).round() / 10.0,
        Err(_) => 0.0,
    };

    Json(json!({
        "ok": true,
        "error": null,
        "data": null,
        "enabled": true,
        "lines": tail,
        "total_lines": total,
        "log_path": path.to_string_lossy(),
        "log_size_kb": size_kb,
    }))
    .into_response()
}

/// GET /api/tools/debug-log/download
pub async fn debug_log_download(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(r) = gate_local_admin(
        s.config.pin_auth_enabled,
        auth.as_ref(),
        addr.as_ref(),
        "Log download",
    ) {
        return r;
    }
    if !is_debug_enabled() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "Debug logging is not enabled"})),
        )
            .into_response();
    }
    let path = debug_log_path();
    let bytes = match tokio::fs::read(&path).await {
        Ok(bytes) => bytes,
        Err(_) => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"ok": false, "error": "Log file not found"})),
            )
                .into_response();
        }
    };
    // The name is taken from the resolved path, as Python does, but a
    // `TAGDB_DEBUG_LOG` pointing somewhere odd must not let a quote or a
    // newline out into the header.
    let name: String = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "debug.log".to_string())
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_'))
        .collect();
    let name = if name.is_empty() {
        "debug.log".to_string()
    } else {
        name
    };
    (
        [
            (
                header::CONTENT_TYPE,
                "text/plain; charset=utf-8".to_string(),
            ),
            (
                header::CONTENT_DISPOSITION,
                format!("attachment; filename=\"{name}\""),
            ),
        ],
        bytes,
    )
        .into_response()
}

/// POST /api/tools/debug-log/clear
pub async fn debug_log_clear(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(r) = gate_local_admin(
        s.config.pin_auth_enabled,
        auth.as_ref(),
        addr.as_ref(),
        "Log clear",
    ) {
        return r;
    }
    if !is_debug_enabled() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "Debug logging is not enabled"})),
        )
            .into_response();
    }
    let path = debug_log_path();
    if !path.exists() {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "Log file not found"})),
        )
            .into_response();
    }
    // Truncate rather than remove: the running logger holds this path open.
    if let Err(error) = tokio::fs::write(&path, b"").await {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": format!("Failed to clear log: {error}")})),
        )
            .into_response();
    }
    Json(
        json!({"ok": true, "error": null, "data": null, "success": true, "message": "Log cleared"}),
    )
    .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::net::{IpAddr, Ipv4Addr};

    fn ci(ip: IpAddr) -> Extension<ConnectInfo<SocketAddr>> {
        Extension(ConnectInfo(SocketAddr::new(ip, 1234)))
    }

    /// The stubs these replaced had NO authorization at all. Each half of the
    /// gate is checked on its own, so a change that drops one but leaves the
    /// other cannot pass unnoticed.
    #[test]
    fn a_remote_client_is_refused_even_with_auth_disabled() {
        // `pin_auth_enabled: false` makes the admin-scope half a no-op --
        // which is exactly the case where only the loopback half stands.
        let refused = gate_local_admin(
            false,
            None,
            Some(&ci(IpAddr::V4(Ipv4Addr::new(192, 168, 1, 50)))),
            "Log view",
        );
        assert!(refused.is_some(), "a LAN client must not reach the log");
    }

    #[test]
    fn a_request_with_no_peer_address_is_refused() {
        // `is_local(None)` is false; an unknown peer must not be treated as
        // local. This is the case a middleware change could silently create.
        assert!(gate_local_admin(false, None, None, "Log view").is_some());
    }

    #[test]
    fn a_loopback_client_passes_when_auth_is_disabled() {
        let allowed = gate_local_admin(
            false,
            None,
            Some(&ci(IpAddr::V4(Ipv4Addr::LOCALHOST))),
            "Log view",
        );
        assert!(allowed.is_none(), "loopback with auth off must be allowed");
    }

    #[test]
    fn a_loopback_client_still_needs_admin_scope() {
        // With PIN auth on and no credentials, the admin half must refuse
        // even though the loopback half is satisfied.
        let refused = gate_local_admin(
            true,
            None,
            Some(&ci(IpAddr::V4(Ipv4Addr::LOCALHOST))),
            "Log view",
        );
        assert!(refused.is_some(), "loopback alone must not grant admin");
    }

    #[test]
    fn debug_enablement_matches_pythons_truthy_set() {
        for on in ["1", "true", "YES", "On", "debug"] {
            temp_env(&[("TAGDB_DEBUG", Some(on))], || {
                assert!(is_debug_enabled(), "{on:?} should enable debug logging");
            });
        }
        for off in ["", "0", "false", "no", "off", "maybe"] {
            temp_env(&[("TAGDB_DEBUG", Some(off))], || {
                assert!(!is_debug_enabled(), "{off:?} should not enable it");
            });
        }
    }

    #[test]
    fn the_log_path_follows_pythons_precedence() {
        temp_env(
            &[
                ("TAGDB_DEBUG_LOG", Some("/tmp/explicit.log")),
                ("TAGDB_LOG_DIR", Some("/tmp/dir")),
            ],
            || {
                assert_eq!(debug_log_path(), PathBuf::from("/tmp/explicit.log"));
            },
        );
        temp_env(
            &[
                ("TAGDB_DEBUG_LOG", None),
                ("TAGDB_LOG_DIR", Some("/tmp/dir")),
            ],
            || {
                assert_eq!(debug_log_path(), PathBuf::from("/tmp/dir/debug.log"));
            },
        );
        temp_env(
            &[("TAGDB_DEBUG_LOG", None), ("TAGDB_LOG_DIR", None)],
            || {
                assert_eq!(debug_log_path(), PathBuf::from("logs/debug.log"));
            },
        );
    }

    /// The environment is process-wide, so these must not run concurrently
    /// with each other. A single mutex serialises them.
    fn temp_env(vars: &[(&str, Option<&str>)], body: impl FnOnce()) {
        use std::sync::Mutex;
        static LOCK: Mutex<()> = Mutex::new(());
        let _guard = LOCK.lock().unwrap_or_else(|p| p.into_inner());

        let saved: Vec<(String, Option<String>)> = vars
            .iter()
            .map(|(k, _)| ((*k).to_string(), std::env::var(k).ok()))
            .collect();
        for (key, value) in vars {
            match value {
                // SAFETY: serialised by LOCK; tests only.
                Some(v) => unsafe { std::env::set_var(key, v) },
                None => unsafe { std::env::remove_var(key) },
            }
        }
        body();
        for (key, value) in saved {
            match value {
                Some(v) => unsafe { std::env::set_var(&key, v) },
                None => unsafe { std::env::remove_var(&key) },
            }
        }
    }
}

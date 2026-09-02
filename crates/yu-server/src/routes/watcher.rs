use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde_json::json;

use crate::state::{AppState, SharedState};

pub fn watcher_info_body(s: &AppState) -> serde_json::Value {
    let (running, watched_roots, stats) = s.watcher.info();
    json!({
        "running": running,
        "watched_roots": watched_roots,
        "stats": stats,
    })
}

pub async fn watcher_info(State(s): State<SharedState>) -> impl IntoResponse {
    Json(watcher_info_body(&s))
}

/// Core `auto_scan_start` logic shared by the REST route and the MCP
/// `auto_scan_start` tool. The HTTP status is meaningful only to the REST
/// caller; the MCP tool returns the JSON body as-is regardless of status,
/// matching the Python reference (which surfaces the relayed response body
/// as tool content independent of the underlying HTTP status).
pub fn watcher_start_result(s: &AppState) -> (StatusCode, serde_json::Value) {
    if s.config.safe_mode {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            json!({"ok": false, "error": "safe mode active"}),
        );
    }

    let roots = s
        .config
        .app_config
        .get("scan_roots")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    if roots.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            json!({"ok": false, "error": "No scan_roots configured"}),
        );
    }

    match s.watcher.start(roots, s.db.clone(), s.job_manager.clone()) {
        Ok(watched) => (
            StatusCode::OK,
            json!({"ok": true, "watched_roots": watched}),
        ),
        Err(e) if e == "Already running" => {
            (StatusCode::CONFLICT, json!({"ok": false, "error": e}))
        }
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            json!({"ok": false, "error": e}),
        ),
    }
}

pub async fn watcher_start(State(s): State<SharedState>) -> impl IntoResponse {
    let (status, body) = watcher_start_result(&s);
    (status, Json(body)).into_response()
}

pub async fn watcher_stop(State(s): State<SharedState>) -> impl IntoResponse {
    if s.watcher.stop() {
        Json(json!({"ok": true})).into_response()
    } else {
        (
            StatusCode::CONFLICT,
            Json(json!({"ok": false, "error": "Not running"})),
        )
            .into_response()
    }
}

//! Scan control endpoints.
//!
//! status/start/cancel/resume/scan-all/dismiss use Rust ScanManager.
//! queue endpoints remain Python forwarders.

use axum::{
    body::Bytes,
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};

use serde::Deserialize;
use serde_json::json;

use crate::{
    auth::{scope::require_scope, AuthContext},
    scan_manager::{ScanCmd, ScanError},
    state::SharedState,
};

fn gate(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0), "scan")
}

async fn fwd_get(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "scan_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .get(&url)
        .header("X-Remote-User", "yu-proxy-auth")
        .send()
        .await
    {
        Ok(r) => {
            let s = r.status();
            r.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |b| (s, b).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

async fn fwd_post(state: &SharedState, path: &str, body: Bytes) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "scan_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .post(&url)
        .header("X-Remote-User", "yu-proxy-auth")
        .body(body)
        .send()
        .await
    {
        Ok(r) => {
            let s = r.status();
            r.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |b| (s, b).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

async fn fwd_delete(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "scan_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .delete(&url)
        .header("X-Remote-User", "yu-proxy-auth")
        .send()
        .await
    {
        Ok(r) => {
            let s = r.status();
            r.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |b| (s, b).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

/// GET /api/scan/status
pub async fn scan_status(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    };
    Json(sm.status()).into_response()
}

#[derive(Deserialize)]
struct StartBody {
    root: String,
    #[serde(default)]
    recursive: bool,
    #[serde(default)]
    force: bool,
    #[serde(default)]
    scan_zips: bool,
}

/// POST /api/scan/start
pub async fn scan_start(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    };
    let parsed: StartBody = match serde_json::from_slice(&body) {
        Ok(b) => b,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid body"})),
            )
                .into_response()
        }
    };
    match sm
        .spawn_worker(
            ScanCmd::Start {
                root: parsed.root,
                recursive: parsed.recursive,
                force: parsed.force,
                scan_zips: parsed.scan_zips,
                resume: false,
                db_path: s.config.db_path.clone(),
            },
            s.clone(),
        )
        .await
    {
        Ok(_) => Json(json!({"status": "started"})).into_response(),
        Err(ScanError::AlreadyRunning) => (
            StatusCode::CONFLICT,
            Json(json!({"ok": false, "error": "scan already running"})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// POST /api/scan/cancel
pub async fn scan_cancel(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    };
    sm.stop();
    Json(json!({"status": "stopping"})).into_response()
}

#[derive(Deserialize)]
struct ResumeBody {
    root: String,
    #[serde(default)]
    recursive: bool,
    #[serde(default)]
    scan_zips: bool,
}

/// POST /api/scan/resume
pub async fn scan_resume(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    };
    let parsed: ResumeBody = match serde_json::from_slice(&body) {
        Ok(b) => b,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid body"})),
            )
                .into_response()
        }
    };
    match sm
        .spawn_worker(
            ScanCmd::Start {
                root: parsed.root,
                recursive: parsed.recursive,
                force: false,
                scan_zips: parsed.scan_zips,
                resume: true,
                db_path: s.config.db_path.clone(),
            },
            s.clone(),
        )
        .await
    {
        Ok(_) => Json(json!({"status": "started"})).into_response(),
        Err(ScanError::AlreadyRunning) => (
            StatusCode::CONFLICT,
            Json(json!({"error": "already running"})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// GET /api/scan/queue  — standalone Rust has no Python queue; always empty
pub async fn scan_queue_list(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    Json(json!({"items": [], "count": 0})).into_response()
}

#[derive(Deserialize)]
struct ScanAllBody {
    #[serde(default)]
    force: bool,
}

/// POST /api/scan-all
pub async fn scan_all(State(s): State<SharedState>, body: Bytes) -> Response {
    let Some(sm) = s.scan_manager.get() else {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    };
    let parsed: ScanAllBody = serde_json::from_slice(&body).unwrap_or(ScanAllBody { force: false });
    scan_core::ipc::clear_scan_state(&s.config.project_root);
    match sm
        .spawn_worker(
            ScanCmd::ScanAll {
                force: parsed.force,
                db_path: s.config.db_path.clone(),
            },
            s.clone(),
        )
        .await
    {
        Ok(_) => Json(json!({"status": "started"})).into_response(),
        Err(ScanError::AlreadyRunning) => (
            StatusCode::CONFLICT,
            Json(json!({"ok": false, "error": "scan already running"})),
        )
            .into_response(),
        Err(ScanError::NoRoots) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "No enabled scan roots"})),
        )
            .into_response(),
    }
}

/// POST /api/scan/dismiss
pub async fn scan_dismiss(State(s): State<SharedState>, body: Bytes) -> Response {
    let Some(sm) = s.scan_manager.get() else {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    };
    let _ = sm.dismiss();
    Json(json!({"status": "dismissed"})).into_response()
}

/// POST /api/scan/queue/clear  — no in-process queue in standalone mode
pub async fn scan_queue_clear(State(_s): State<SharedState>, _body: Bytes) -> Response {
    Json(json!({"status": "cleared", "cleared": 0})).into_response()
}

/// DELETE /api/scan/queue/:queue_id  — no in-process queue in standalone mode
pub async fn scan_queue_remove(
    State(_s): State<SharedState>,
    Path(_queue_id): Path<String>,
) -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({"ok": false, "error": "not_found"})),
    )
        .into_response()
}

#[derive(Deserialize)]
struct PurgeBody {
    root: String,
}

/// POST /api/scanned-roots/purge
pub async fn scanned_roots_purge(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let root: String = match serde_json::from_slice::<PurgeBody>(&body) {
        Ok(b) => b.root,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"ok": false, "error": "missing root"})),
            )
                .into_response();
        }
    };
    if root.trim().is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "empty root"})),
        )
            .into_response();
    }
    // Escape LIKE metacharacters ('%' and '_') so user input cannot widen the pattern.
    fn escape_like(s: &str) -> String {
        s.replace('%', "\\%").replace('_', "\\_")
    }
    let fwd = escape_like(&root.replace('\\', "/"));
    let bwd = escape_like(&root.replace('/', "\\"));
    let like_fwd = format!("{}/%", fwd.trim_end_matches('/'));
    let like_bwd = format!("{}\\%", bwd.trim_end_matches('\\'));

    let res = sqlx::query(
        "UPDATE files SET extracted_to_file_id = NULL \
         WHERE extracted_to_file_id IN \
           (SELECT id FROM files WHERE path LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\')",
    )
    .bind(&like_fwd)
    .bind(&like_bwd)
    .execute(&s.db)
    .await;
    if let Err(e) = res {
        tracing::error!("scanned_roots_purge UPDATE: {e}");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "db_error"})),
        )
            .into_response();
    }

    match sqlx::query("DELETE FROM files WHERE path LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\'")
        .bind(&like_fwd)
        .bind(&like_bwd)
        .execute(&s.db)
        .await
    {
        Ok(r) => {
            Json(json!({"ok": true, "purged": r.rows_affected(), "pruned_tags": 0})).into_response()
        }
        Err(e) => {
            tracing::error!("scanned_roots_purge DELETE: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

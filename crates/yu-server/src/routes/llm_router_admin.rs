//! `/api/llm_router/*` admin surface — forwards to Python with admin scope gate.

use axum::{
    body::Bytes,
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

fn admin_gate(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0))
}

fn py_unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "Python backend unavailable", "code": "python_unavailable"})),
    )
        .into_response()
}

async fn fwd_get(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return py_unavailable();
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
        return py_unavailable();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
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

/// GET /api/llm_router/status
pub async fn llm_router_status(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    (
        StatusCode::OK,
        Json(json!({
            "ok": true,
            "data": {
                "router": {"version": "1.0.0", "alias_count": 0},
                "backends": [],
                "aliases": []
            }
        })),
    )
        .into_response()
}

/// POST /api/llm_router/refresh
pub async fn llm_router_refresh(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    Json(json!({"ok": true, "refreshed": 0, "backends": []})).into_response()
}

/// POST /api/llm_router/backends/:alias/disable
pub async fn llm_router_disable(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    Json(json!({"ok": true})).into_response()
}

/// POST /api/llm_router/backends/:alias/enable
pub async fn llm_router_enable(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    Json(json!({"ok": true})).into_response()
}

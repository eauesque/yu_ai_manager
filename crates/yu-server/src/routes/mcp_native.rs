use std::convert::Infallible;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::body::Bytes;
use axum::extract::{ConnectInfo, Query, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::response::sse::{Event, Sse};
use axum::response::{IntoResponse, Response};
use axum::Json;
use futures_util::stream;
use serde::Deserialize;
use serde_json::json;
use uuid::Uuid;

use crate::auth::client_ip::resolve_client_ip;
use crate::mcp::auth::check_mcp_auth;
use crate::mcp::session::{McpSessionGuard, TrySendKind};
use crate::routes::server_info::is_local_ip;
use crate::state::SharedState;

// ── helpers ──────────────────────────────────────────────────────────────────

fn api_err(msg: &str) -> serde_json::Value {
    json!({"ok": false, "error": msg})
}

fn extract_ip(headers: &HeaderMap, addr: &SocketAddr, state: &crate::state::AppState) -> String {
    let xff = headers.get("x-forwarded-for").and_then(|v| v.to_str().ok());
    resolve_client_ip(
        &addr.ip().to_string(),
        xff,
        state.config.trusted_proxy_enabled,
        &state.config.trusted_ips,
    )
}

fn auth_header(headers: &HeaderMap) -> &str {
    headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
}

// ── GET /mcp ─────────────────────────────────────────────────────────────────

/// GET /mcp — establish SSE session.
pub async fn sse_handler(
    State(state): State<SharedState>,
    headers: HeaderMap,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
) -> Response {
    let resolved_ip = extract_ip(&headers, &addr, &state);

    if let Some(status) = check_mcp_auth(
        &resolved_ip,
        auth_header(&headers),
        &state.config.config_path,
    ) {
        return (status, Json(api_err("Unauthorized"))).into_response();
    }

    let session_id = Uuid::new_v4().to_string();
    let rx = match state.mcp_sessions.try_register(&session_id, &resolved_ip) {
        Ok(rx) => rx,
        Err(status) => return (status, Json(api_err("Too many MCP sessions"))).into_response(),
    };

    let guard = McpSessionGuard {
        store: Arc::clone(&state.mcp_sessions),
        session_id: session_id.clone(),
        owner_ip: resolved_ip,
    };

    let event_stream = stream::unfold((rx, guard, true), move |state| async move {
        let (mut rx, guard, is_first) = state;

        if is_first {
            let ev = Event::default()
                .event("endpoint")
                .data(format!("/mcp/message?session_id={}", guard.session_id));
            return Some((Ok::<_, Infallible>(ev), (rx, guard, false)));
        }

        match tokio::time::timeout(Duration::from_secs(29), rx.recv()).await {
            Err(_) => {
                let ev = Event::default().comment("keepalive");
                Some((Ok(ev), (rx, guard, false)))
            }
            Ok(Some(Some(msg))) => {
                let data = serde_json::to_string(&msg).unwrap_or_default();
                let ev = Event::default().event("message").data(data);
                Some((Ok(ev), (rx, guard, false)))
            }
            Ok(None) | Ok(Some(None)) => None,
        }
    });

    let sse = Sse::new(event_stream);
    let mut resp = sse.into_response();
    resp.headers_mut()
        .insert("X-Accel-Buffering", HeaderValue::from_static("no"));
    resp.headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    resp.headers_mut()
        .insert(header::CONNECTION, HeaderValue::from_static("keep-alive"));
    resp
}

// ── POST /mcp/message?session_id=xxx ─────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct SessionIdParam {
    #[serde(default)]
    pub session_id: String,
}

/// POST /mcp/message?session_id=xxx — JSON-RPC receive for an existing SSE session.
pub async fn message_handler(
    State(state): State<SharedState>,
    Query(params): Query<SessionIdParam>,
    headers: HeaderMap,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    body: Bytes,
) -> Response {
    let resolved_ip = extract_ip(&headers, &addr, &state);

    if let Some(status) = check_mcp_auth(
        &resolved_ip,
        auth_header(&headers),
        &state.config.config_path,
    ) {
        return (status, Json(api_err("Unauthorized"))).into_response();
    }

    let session_id = &params.session_id;
    let owner_ip = match state.mcp_sessions.get_owner_ip(session_id) {
        Some(ip) => ip,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(api_err("Invalid or expired session")),
            )
                .into_response()
        }
    };

    if owner_ip != resolved_ip {
        return (
            StatusCode::FORBIDDEN,
            Json(api_err("Session owner mismatch")),
        )
            .into_response();
    }

    let msg: serde_json::Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => return (StatusCode::BAD_REQUEST, Json(api_err("Invalid JSON"))).into_response(),
    };
    if !msg.is_object() {
        return (
            StatusCode::BAD_REQUEST,
            Json(api_err("Expected JSON object")),
        )
            .into_response();
    }

    let response =
        crate::mcp::dispatch::dispatch(&state, is_local_ip(&resolved_ip), session_id, msg).await;

    if let Some(ref data) = response {
        match state.mcp_sessions.send_to(session_id, data.clone()) {
            Ok(()) => {}
            Err(TrySendKind::Full) => {
                state.mcp_sessions.close_session(session_id);
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    Json(api_err("Session queue full")),
                )
                    .into_response();
            }
            Err(TrySendKind::Disconnected) => {
                return (StatusCode::NOT_FOUND, Json(api_err("Session disconnected")))
                    .into_response();
            }
        }
        (StatusCode::OK, Json(data.clone())).into_response()
    } else {
        StatusCode::ACCEPTED.into_response()
    }
}

// ── POST /mcp ────────────────────────────────────────────────────────────────

/// POST /mcp — stateless single-request JSON-RPC (no SSE session).
pub async fn stateless_handler(
    State(state): State<SharedState>,
    headers: HeaderMap,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    body: Bytes,
) -> Response {
    let resolved_ip = extract_ip(&headers, &addr, &state);

    if let Some(status) = check_mcp_auth(
        &resolved_ip,
        auth_header(&headers),
        &state.config.config_path,
    ) {
        return (status, Json(api_err("Unauthorized"))).into_response();
    }

    let msg: serde_json::Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => return (StatusCode::BAD_REQUEST, Json(api_err("Invalid JSON"))).into_response(),
    };
    if !msg.is_object() {
        return (
            StatusCode::BAD_REQUEST,
            Json(api_err("Expected JSON object")),
        )
            .into_response();
    }

    match crate::mcp::dispatch::dispatch(&state, is_local_ip(&resolved_ip), "__stateless__", msg)
        .await
    {
        Some(data) => (StatusCode::OK, Json(data)).into_response(),
        None => StatusCode::ACCEPTED.into_response(),
    }
}

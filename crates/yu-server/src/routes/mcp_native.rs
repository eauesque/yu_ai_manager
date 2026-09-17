use std::convert::Infallible;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::body::Bytes;
use axum::extract::{ConnectInfo, Extension, Query, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::response::sse::{Event, Sse};
use axum::response::{IntoResponse, Response};
use axum::Json;
use futures_util::stream;
use serde::Deserialize;
use serde_json::{json, Value};
use uuid::Uuid;

use crate::auth::client_ip::{resolve_client_ip, ClientIp};
use crate::mcp::auth::check_mcp_auth;
use crate::mcp::dispatch::{dispatch_with_version, SUPPORTED_VERSIONS};
use crate::mcp::session::{McpSessionGuard, TrySendKind};
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

#[derive(Debug, PartialEq, Eq)]
enum VersionReject {
    Unsupported(String),
    Mismatch { header: String, meta: String },
    InvalidHeader,
}

fn meta_protocol_version(params: Option<&Value>) -> Option<&str> {
    params
        .and_then(|params| params.get("_meta"))
        .and_then(Value::as_object)
        .and_then(|meta| meta.get("io.modelcontextprotocol/protocolVersion"))
        .and_then(Value::as_str)
}

/// Transport-layer version gate. Only the header and _meta are consulted.
fn classify_protocol_version(
    headers: &HeaderMap,
    params: Option<&Value>,
) -> Result<(), VersionReject> {
    let header = match headers.get("MCP-Protocol-Version") {
        Some(value) => Some(value.to_str().map_err(|_| VersionReject::InvalidHeader)?),
        None => None,
    };
    let meta = meta_protocol_version(params);

    for version in header.into_iter().chain(meta) {
        if !SUPPORTED_VERSIONS.contains(&version) {
            return Err(VersionReject::Unsupported(version.to_string()));
        }
    }
    if let (Some(header), Some(meta)) = (header, meta) {
        if header != meta {
            return Err(VersionReject::Mismatch {
                header: header.to_string(),
                meta: meta.to_string(),
            });
        }
    }
    Ok(())
}

fn version_reject_response(rejection: VersionReject, msg_id: Option<&Value>) -> Response {
    let error = match rejection {
        VersionReject::Unsupported(requested) => json!({
            "code": -32022,
            "message": "Unsupported protocol version",
            "data": {"supported": SUPPORTED_VERSIONS, "requested": requested},
        }),
        VersionReject::Mismatch { header, meta } => json!({
            "code": -32600,
            "message": "Invalid Request",
            "data": {"header": header, "meta": meta},
        }),
        VersionReject::InvalidHeader => json!({
            "code": -32600,
            "message": "Invalid Request",
        }),
    };
    match msg_id {
        Some(id) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"jsonrpc": "2.0", "id": id, "error": error})),
        )
            .into_response(),
        None => StatusCode::BAD_REQUEST.into_response(),
    }
}

/// Does this request name 2026-07-28 through any applicable declaration source?
fn declared_2026(headers: &HeaderMap, method: &str, params: Option<&Value>) -> bool {
    headers
        .get("MCP-Protocol-Version")
        .and_then(|value| value.to_str().ok())
        == Some("2026-07-28")
        || meta_protocol_version(params) == Some("2026-07-28")
        || (method == "initialize"
            && params
                .and_then(|params| params.get("protocolVersion"))
                .and_then(Value::as_str)
                == Some("2026-07-28"))
}

// ── GET /mcp ─────────────────────────────────────────────────────────────────

/// GET /mcp — establish SSE session.
pub async fn sse_handler(
    State(state): State<SharedState>,
    headers: HeaderMap,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
) -> Response {
    let resolved_ip = extract_ip(&headers, &addr, &state);

    if let Some(status) = check_mcp_auth(auth_header(&headers), &state.config.config_path) {
        return (status, Json(api_err("Unauthorized"))).into_response();
    }
    if let Err(rejection) = classify_protocol_version(&headers, None) {
        return version_reject_response(rejection, None);
    }
    if declared_2026(&headers, "", None) {
        return StatusCode::METHOD_NOT_ALLOWED.into_response();
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

    if let Some(status) = check_mcp_auth(auth_header(&headers), &state.config.config_path) {
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
    if let Err(rejection) = classify_protocol_version(&headers, msg.get("params")) {
        return version_reject_response(rejection, msg.get("id"));
    }
    let declared = declared_2026(
        &headers,
        msg.get("method").and_then(Value::as_str).unwrap_or(""),
        msg.get("params"),
    );

    // Same helper the REST route uses (server_restart::local_request), not
    // is_local_ip(resolved_ip) alone -- design-advisor S1. /mcp is mounted by
    // default, so a bare loopback-string check here let a forwarded-hint
    // loopback caller through even after the REST route was fixed to reject
    // it via server_restart::local_request.
    let is_local = crate::routes::server_restart::local_request(
        &state,
        Some(Extension(ClientIp(resolved_ip.clone()))),
        headers,
    )
    .await;
    let response = dispatch_with_version(&state, is_local, session_id, msg, declared).await;

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

    if let Some(status) = check_mcp_auth(auth_header(&headers), &state.config.config_path) {
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
    if let Err(rejection) = classify_protocol_version(&headers, msg.get("params")) {
        return version_reject_response(rejection, msg.get("id"));
    }
    let declared = declared_2026(
        &headers,
        msg.get("method").and_then(Value::as_str).unwrap_or(""),
        msg.get("params"),
    );
    let is_local = crate::routes::server_restart::local_request(
        &state,
        Some(Extension(ClientIp(resolved_ip))),
        headers,
    )
    .await;
    match dispatch_with_version(&state, is_local, "__stateless__", msg, declared).await {
        Some(data) => (StatusCode::OK, Json(data)).into_response(),
        None => StatusCode::ACCEPTED.into_response(),
    }
}

#[cfg(test)]
mod tests {
    use std::{
        collections::HashSet,
        fs,
        path::PathBuf,
        str::FromStr,
        sync::Arc,
        time::{SystemTime, UNIX_EPOCH},
    };

    use axum::body::to_bytes;
    use sha2::{Digest, Sha256};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use super::*;
    use crate::state::{AppState, Config};

    async fn test_state_with_config(config_path: PathBuf) -> SharedState {
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
                    config_path,
                    project_root: PathBuf::from("."),
                    app_config: serde_json::json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: true,
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

    async fn test_state() -> SharedState {
        test_state_with_config(PathBuf::from("/tmp/nonexistent-mcp-auth-test-config.json")).await
    }

    fn temp_config(key_id: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("yu-server-mcp-{key_id}-{suffix}.json"));
        let key = "sk_0123456789abcdef0123456789abcdef";
        let hash = hex::encode(Sha256::digest(key.as_bytes()));
        fs::write(
            &path,
            json!({"api_keys": [{
                "id": key_id,
                "key_hash": hash,
                "key_prefix": "sk_0123456",
                "label": "MCP test key",
                "scopes": ["admin"]
            }]})
            .to_string(),
        )
        .unwrap();
        path
    }

    async fn authenticated_state(key_id: &str) -> (SharedState, PathBuf) {
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let path = temp_config(key_id);
        (test_state_with_config(path.clone()).await, path)
    }

    fn headers(version: Option<&str>) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            HeaderValue::from_static("Bearer sk_0123456789abcdef0123456789abcdef"),
        );
        if let Some(version) = version {
            headers.insert(
                "MCP-Protocol-Version",
                HeaderValue::from_str(version).unwrap(),
            );
        }
        headers
    }

    async fn rejection_json(rejection: VersionReject) -> (StatusCode, Value) {
        let response = version_reject_response(rejection, Some(&json!(1)));
        let status = response.status();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        (status, serde_json::from_slice(&body).unwrap())
    }

    async fn response_json(response: Response) -> Value {
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap()
    }

    #[tokio::test]
    async fn rejects_unsupported_header() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "MCP-Protocol-Version",
            HeaderValue::from_static("1999-01-01"),
        );
        let (status, body) =
            rejection_json(classify_protocol_version(&headers, None).unwrap_err()).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["error"]["code"], -32022);
        assert_eq!(body["error"]["data"]["requested"], "1999-01-01");
        assert!(body["error"]["data"]["supported"]
            .as_array()
            .unwrap()
            .contains(&json!("2026-07-28")));
    }

    #[tokio::test]
    async fn rejects_header_meta_mismatch() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "MCP-Protocol-Version",
            HeaderValue::from_static("2026-07-28"),
        );
        let params = json!({"_meta": {"io.modelcontextprotocol/protocolVersion": "2025-11-25"}});
        let (status, body) =
            rejection_json(classify_protocol_version(&headers, Some(&params)).unwrap_err()).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["error"]["code"], -32600);
        assert_eq!(
            body["error"]["data"],
            json!({"header": "2026-07-28", "meta": "2025-11-25"})
        );
    }

    #[test]
    fn accepts_matching_header_and_meta() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "MCP-Protocol-Version",
            HeaderValue::from_static("2026-07-28"),
        );
        let params = json!({"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}});
        assert_eq!(classify_protocol_version(&headers, Some(&params)), Ok(()));
    }

    #[test]
    fn accepts_missing_declarations() {
        assert_eq!(classify_protocol_version(&HeaderMap::new(), None), Ok(()));
    }

    #[test]
    fn rejects_unsupported_meta() {
        let params = json!({"_meta": {"io.modelcontextprotocol/protocolVersion": "1999-01-01"}});
        assert_eq!(
            classify_protocol_version(&HeaderMap::new(), Some(&params)),
            Err(VersionReject::Unsupported("1999-01-01".into()))
        );
    }

    #[test]
    fn ignores_lifecycle_protocol_version() {
        let params = json!({"protocolVersion": "1999-01-01"});
        assert_eq!(
            classify_protocol_version(&HeaderMap::new(), Some(&params)),
            Ok(())
        );
    }

    #[test]
    fn does_not_compare_meta_with_lifecycle_protocol_version() {
        let params = json!({"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}, "protocolVersion": "2024-11-05"});
        assert_eq!(
            classify_protocol_version(&HeaderMap::new(), Some(&params)),
            Ok(())
        );
    }

    #[test]
    fn accepts_header_without_meta() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "MCP-Protocol-Version",
            HeaderValue::from_static("2026-07-28"),
        );
        assert_eq!(classify_protocol_version(&headers, None), Ok(()));
    }

    #[test]
    fn ignores_non_string_meta_protocol_version() {
        let params = json!({"_meta": {"io.modelcontextprotocol/protocolVersion": 20260728}});
        assert_eq!(
            classify_protocol_version(&HeaderMap::new(), Some(&params)),
            Ok(())
        );
    }

    #[tokio::test]
    async fn rejects_non_ascii_header() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "MCP-Protocol-Version",
            HeaderValue::from_bytes(b"\xff").unwrap(),
        );
        let (status, body) =
            rejection_json(classify_protocol_version(&headers, None).unwrap_err()).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["error"]["code"], -32600);
    }

    #[test]
    fn declared_2026_from_header() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "MCP-Protocol-Version",
            HeaderValue::from_static("2026-07-28"),
        );
        assert!(declared_2026(&headers, "tools/list", None));
    }

    #[test]
    fn declared_2026_from_meta() {
        assert!(declared_2026(
            &HeaderMap::new(),
            "tools/list",
            Some(&json!({"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}))
        ));
    }

    #[test]
    fn declared_2026_from_initialize_params() {
        assert!(declared_2026(
            &HeaderMap::new(),
            "initialize",
            Some(&json!({"protocolVersion": "2026-07-28"}))
        ));
    }

    #[test]
    fn declared_2026_ignores_non_initialize_params() {
        assert!(!declared_2026(
            &HeaderMap::new(),
            "tools/list",
            Some(&json!({"protocolVersion": "2026-07-28"}))
        ));
    }

    #[test]
    fn declared_2026_is_false_without_sources() {
        assert!(!declared_2026(&HeaderMap::new(), "tools/list", None));
    }

    #[test]
    fn declared_2026_is_false_for_other_versions() {
        assert!(!declared_2026(
            &HeaderMap::new(),
            "tools/list",
            Some(
                &json!({"_meta": {"io.modelcontextprotocol/protocolVersion": "2025-11-25"}, "protocolVersion": "2025-11-25"})
            )
        ));
    }

    #[tokio::test]
    async fn sse_rejects_declared_2026() {
        let key_id = "mcp-sse-405";
        let (state, path) = authenticated_state(key_id).await;
        let response = sse_handler(
            State(state),
            headers(Some("2026-07-28")),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn sse_accepts_undeclared_legacy_client() {
        let key_id = "mcp-sse-legacy";
        let (state, path) = authenticated_state(key_id).await;
        let response = sse_handler(
            State(state),
            headers(None),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn sse_rejects_unsupported_version_before_405() {
        let key_id = "mcp-sse-unsupported";
        let (state, path) = authenticated_state(key_id).await;
        let response = sse_handler(
            State(state),
            headers(Some("1999-01-01")),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn stateless_notification_rejection_has_no_body() {
        let key_id = "mcp-stateless-notification";
        let (state, path) = authenticated_state(key_id).await;
        let response = stateless_handler(
            State(state),
            headers(Some("1999-01-01")),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Bytes::from_static(br#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap()
            .is_empty());
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn stateless_handler_applies_version_gate() {
        let key_id = "mcp-stateless-gate";
        let (state, path) = authenticated_state(key_id).await;
        let response = stateless_handler(
            State(state),
            headers(Some("1999-01-01")),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Bytes::from_static(br#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn stateless_handler_injects_result_type_for_2026() {
        let key_id = "mcp-stateless-result-type-2026";
        let (state, path) = authenticated_state(key_id).await;
        let response = stateless_handler(
            State(state),
            headers(Some("2026-07-28")),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Bytes::from_static(br#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response_json(response).await["result"]["resultType"],
            "complete"
        );
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn stateless_handler_omits_result_type_for_legacy_version() {
        let key_id = "mcp-stateless-result-type-legacy";
        let (state, path) = authenticated_state(key_id).await;
        let response = stateless_handler(
            State(state),
            headers(Some("2024-11-05")),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Bytes::from_static(br#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert!(response_json(response).await["result"]
            .get("resultType")
            .is_none());
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn message_handler_applies_version_gate() {
        let key_id = "mcp-message-gate";
        let (state, path) = authenticated_state(key_id).await;
        let owner_ip = "127.0.0.1";
        let _rx = state
            .mcp_sessions
            .try_register("test-session", owner_ip)
            .unwrap();
        let response = message_handler(
            State(state),
            Query(SessionIdParam {
                session_id: "test-session".into(),
            }),
            headers(Some("1999-01-01")),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Bytes::from_static(br#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn message_handler_accepts_undeclared_legacy_client() {
        let key_id = "mcp-message-legacy";
        let (state, path) = authenticated_state(key_id).await;
        let owner_ip = "127.0.0.1";
        let _rx = state
            .mcp_sessions
            .try_register("test-session", owner_ip)
            .unwrap();
        let response = message_handler(
            State(state),
            Query(SessionIdParam {
                session_id: "test-session".into(),
            }),
            headers(None),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Bytes::from_static(br#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::ACCEPTED);
        crate::auth::apikey::reset_rate_limit_for_test(key_id);
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn loopback_sse_without_bearer_gets_401() {
        let response = sse_handler(
            State(test_state().await),
            HeaderMap::new(),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
        )
        .await;

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }
}

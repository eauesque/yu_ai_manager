//! mcp_client.rs — `/ext/mcp-client/api/connections` CRUD.
//!
//! Native port of Python's
//! `extensions/builtin_mcp_client/core_impl/connection_config.py` (pure
//! config.json CRUD) + the config-facing parts of `connection_manager.py`
//! (`list_connections`'s status-merge/masking, `add_connection`/
//! `update_connection`/`delete_connection` delegates).
//!
//! Live MCP session management (connect/disconnect/tools/call-tool,
//! `mcp_session.py`/`async_bridge.py`) is intentionally out of scope — Rust
//! has no live MCP client session manager. Python's `update_connection`/
//! `delete_connection` disconnect an active session before mutating config,
//! but only when one exists in that process's in-memory `_connections` dict;
//! since no such live state exists here, that step is vacuously a no-op, not
//! a gap for the config-CRUD surface this file implements.

use std::net::SocketAddr;

use axum::{
    extract::{ConnectInfo, Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use super::tools_fs::is_local;
use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::config_io::{load as load_config_json, write as write_config_json};
use crate::secret_store;
use crate::state::SharedState;

const EXT_NAME: &str = "builtin-mcp-client";
const CONNECTIONS_KEY: &str = "connections";
const VALID_TRANSPORTS: &[&str] = &["stdio", "sse", "streamable_http"];

fn admin_guard(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|e| &e.0))
}

/// Mirrors Python's `require_local()`: loopback-only guard, used for
/// stdio-transport connections (which spawn a local child process).
fn require_local(is_local_request: bool, label: &str) -> Option<Response> {
    if is_local_request {
        None
    } else {
        Some(api_err(
            &format!("{label} is only available from localhost"),
            StatusCode::FORBIDDEN,
        ))
    }
}

fn api_ok(payload: Value) -> Json<Value> {
    let mut body = json!({"ok": true});
    if let (Value::Object(base), Value::Object(extra)) = (&mut body, payload) {
        for (k, v) in extra {
            base.insert(k, v);
        }
    }
    Json(body)
}

fn api_err(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn raw_connections(state: &SharedState) -> Vec<Value> {
    load_config_json(&state.config.config_path)
        .get("extensions")
        .and_then(|e| e.get(EXT_NAME))
        .and_then(|e| e.get(CONNECTIONS_KEY))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
}

fn save_raw_connections(state: &SharedState, connections: Vec<Value>) -> std::io::Result<()> {
    let mut full = load_config_json(&state.config.config_path);
    full["extensions"][EXT_NAME][CONNECTIONS_KEY] = json!(connections);
    write_config_json(&state.config.config_path, &full)
}

fn is_nonempty_object(v: &Value) -> bool {
    v.as_object().map(|o| !o.is_empty()).unwrap_or(false)
}

/// Mirrors Python's `_encrypt_sensitive`: encrypt `sse.headers`/
/// `streamable_http.headers`/`stdio.env` (if present as a non-empty JSON
/// object) into an `enc:...` string before persisting.
fn encrypt_sensitive(cfg: &Value, project_root: &std::path::Path) -> Value {
    let mut cfg = cfg.clone();
    for key in ["sse", "streamable_http"] {
        if let Some(headers) = cfg.get(key).and_then(|t| t.get("headers")) {
            if is_nonempty_object(headers) {
                let plain = serde_json::to_string(headers).unwrap_or_default();
                let enc = secret_store::encrypt(&plain, project_root);
                cfg[key]["headers"] = json!(enc);
            }
        }
    }
    if let Some(env) = cfg.get("stdio").and_then(|s| s.get("env")) {
        if is_nonempty_object(env) {
            let plain = serde_json::to_string(env).unwrap_or_default();
            let enc = secret_store::encrypt(&plain, project_root);
            cfg["stdio"]["env"] = json!(enc);
        }
    }
    cfg
}

/// Mirrors Python's `_decrypt_sensitive`: decrypt back to a JSON object any
/// `enc:...`-prefixed `headers`/`env` string. Values that are already an
/// object (never encrypted) or fail to decrypt/parse fall back to `{}`,
/// matching Python's `except Exception: ... = {}`.
fn decrypt_sensitive(cfg: &Value, project_root: &std::path::Path) -> Value {
    let mut cfg = cfg.clone();
    for key in ["sse", "streamable_http"] {
        if let Some(headers) = cfg.get(key).and_then(|t| t.get("headers")) {
            if let Some(s) = headers.as_str() {
                if s.starts_with("enc:") {
                    let plain = secret_store::decrypt(s, project_root);
                    let parsed: Value = serde_json::from_str(&plain).unwrap_or_else(|_| json!({}));
                    cfg[key]["headers"] = parsed;
                }
            }
        }
    }
    if let Some(env) = cfg.get("stdio").and_then(|s| s.get("env")) {
        if let Some(s) = env.as_str() {
            if s.starts_with("enc:") {
                let plain = secret_store::decrypt(s, project_root);
                let parsed: Value = serde_json::from_str(&plain).unwrap_or_else(|_| json!({}));
                cfg["stdio"]["env"] = parsed;
            }
        }
    }
    cfg
}

/// Mirrors Python's `_validate`.
fn validate_connection(cfg: &Value) -> Option<String> {
    let obj = cfg.as_object()?;
    let mut missing: Vec<&str> = Vec::new();
    if !obj.contains_key("name") {
        missing.push("name");
    }
    if !obj.contains_key("transport") {
        missing.push("transport");
    }
    if !missing.is_empty() {
        missing.sort_unstable();
        return Some(format!("Missing required fields: {}", missing.join(", ")));
    }

    let transport = cfg.get("transport").and_then(Value::as_str).unwrap_or("");
    if !VALID_TRANSPORTS.contains(&transport) {
        return Some(format!(
            "Invalid transport: {transport}. Must be one of {VALID_TRANSPORTS:?}"
        ));
    }
    match transport {
        "stdio" => {
            let has_command = cfg
                .get("stdio")
                .and_then(|s| s.get("command"))
                .and_then(Value::as_str)
                .map(|s| !s.is_empty())
                .unwrap_or(false);
            if !has_command {
                return Some("stdio.command is required for stdio transport".to_string());
            }
        }
        "sse" => {
            let has_url = cfg
                .get("sse")
                .and_then(|s| s.get("url"))
                .and_then(Value::as_str)
                .map(|s| !s.is_empty())
                .unwrap_or(false);
            if !has_url {
                return Some("sse.url is required for sse transport".to_string());
            }
        }
        "streamable_http" => {
            let has_url = cfg
                .get("streamable_http")
                .and_then(|s| s.get("url"))
                .and_then(Value::as_str)
                .map(|s| !s.is_empty())
                .unwrap_or(false);
            if !has_url {
                return Some(
                    "streamable_http.url is required for streamable_http transport".to_string(),
                );
            }
        }
        // `VALID_TRANSPORTS` above already rejected anything else. Repeating the
        // rejection is fail-closed and costs nothing; panicking here would turn
        // a drift between the table and this match into a downed request.
        _ => return Some(format!("Invalid transport: {transport}")),
    }
    None
}

fn new_connection_id() -> String {
    uuid::Uuid::new_v4().simple().to_string()[..12].to_string()
}

fn redact_headers(headers: &Value) -> Value {
    match headers.as_object() {
        Some(obj) => {
            let redacted: serde_json::Map<String, Value> =
                obj.keys().map(|k| (k.clone(), json!("***"))).collect();
            Value::Object(redacted)
        }
        None => json!({}),
    }
}

/// Mirrors Python `ConnectionManager.list_connections()`'s masking step,
/// applied on top of an already-decrypted connection dict, for display.
fn mask_for_list(cfg: &Value) -> Value {
    let mut cfg = cfg.clone();
    if let Some(env) = cfg.get("stdio").and_then(|s| s.get("env")) {
        if env.is_object() {
            let masked: serde_json::Map<String, Value> = env
                .as_object()
                .unwrap()
                .keys()
                .map(|k| (k.clone(), json!("***")))
                .collect();
            cfg["stdio"]["env"] = Value::Object(masked);
        }
    }
    for key in ["sse", "streamable_http"] {
        if let Some(headers) = cfg.get(key).and_then(|t| t.get("headers")) {
            if headers.is_object() {
                cfg[key]["headers"] = redact_headers(headers);
            }
        }
    }
    cfg
}

/// GET /ext/mcp-client/api/connections
///
/// No live session in this process, so every connection's runtime status is
/// the same "never connected" fallback Python uses when `_connections.get(id)`
/// is `None` — mirrors `ConnectionManager.list_connections()`.
pub async fn list_connections(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let connections: Vec<Value> = raw_connections(&state)
        .into_iter()
        .map(|c| decrypt_sensitive(&c, &state.config.project_root))
        .map(|mut c| {
            if let Value::Object(obj) = &mut c {
                obj.insert("status".to_string(), json!("disconnected"));
                obj.insert("error".to_string(), json!(""));
                obj.insert("tool_count".to_string(), json!(0));
                obj.insert("connected_at".to_string(), json!(0.0));
            }
            c
        })
        .map(|c| mask_for_list(&c))
        .collect();
    api_ok(json!({"connections": connections})).into_response()
}

/// POST /ext/mcp-client/api/connections
pub async fn add_connection(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect_info: Option<Extension<ConnectInfo<SocketAddr>>>,
    Json(mut data): Json<Value>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    if !data.is_object() {
        return api_err("JSON body required", StatusCode::BAD_REQUEST);
    }
    if data.get("transport").and_then(Value::as_str) == Some("stdio") {
        if let Some(r) = require_local(
            is_local(connect_info.as_ref().map(|e| &e.0)),
            "MCP stdio connection",
        ) {
            return r;
        }
    }

    if let Some(msg) = validate_connection(&data) {
        return api_err(&msg, StatusCode::BAD_REQUEST);
    }

    let obj = data.as_object_mut().unwrap();
    obj.entry("id")
        .or_insert_with(|| json!(new_connection_id()));
    obj.entry("enabled").or_insert_with(|| json!(true));
    obj.entry("auto_connect").or_insert_with(|| json!(false));
    let new_id = data
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    let mut connections = raw_connections(&state);
    if connections
        .iter()
        .any(|c| c.get("id").and_then(Value::as_str) == Some(new_id.as_str()))
    {
        return api_err(
            &format!("Connection ID already exists: {new_id}"),
            StatusCode::BAD_REQUEST,
        );
    }
    connections.push(encrypt_sensitive(&data, &state.config.project_root));
    if let Err(e) = save_raw_connections(&state, connections) {
        return internal_error(e, "failed to write config");
    }
    (StatusCode::CREATED, api_ok(json!({"connection": data}))).into_response()
}

/// PUT /ext/mcp-client/api/connections/{id}
pub async fn update_connection(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect_info: Option<Extension<ConnectInfo<SocketAddr>>>,
    AxumPath(conn_id): AxumPath<String>,
    Json(updates): Json<Value>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    if !updates.is_object() {
        return api_err("JSON body required", StatusCode::BAD_REQUEST);
    }

    let mut connections = raw_connections(&state);
    let Some(idx) = connections
        .iter()
        .position(|c| c.get("id").and_then(Value::as_str) == Some(conn_id.as_str()))
    else {
        return api_err(
            &format!("Connection not found: {conn_id}"),
            StatusCode::NOT_FOUND,
        );
    };

    let mut decrypted = decrypt_sensitive(&connections[idx], &state.config.project_root);
    if let (Value::Object(base), Value::Object(patch)) = (&mut decrypted, &updates) {
        for (k, v) in patch {
            base.insert(k.clone(), v.clone());
        }
    }
    decrypted["id"] = json!(conn_id);

    if let Some(msg) = validate_connection(&decrypted) {
        return api_err(&msg, StatusCode::BAD_REQUEST);
    }

    if decrypted.get("transport").and_then(Value::as_str) == Some("stdio") {
        if let Some(r) = require_local(
            is_local(connect_info.as_ref().map(|e| &e.0)),
            "MCP stdio connection",
        ) {
            return r;
        }
    }

    connections[idx] = encrypt_sensitive(&decrypted, &state.config.project_root);
    if let Err(e) = save_raw_connections(&state, connections) {
        return internal_error(e, "failed to write config");
    }
    api_ok(json!({"connection": decrypted})).into_response()
}

/// DELETE /ext/mcp-client/api/connections/{id}
pub async fn delete_connection(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(conn_id): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let connections = raw_connections(&state);
    let orig_len = connections.len();
    let new_connections: Vec<Value> = connections
        .into_iter()
        .filter(|c| c.get("id").and_then(Value::as_str) != Some(conn_id.as_str()))
        .collect();
    if new_connections.len() == orig_len {
        return api_err(
            &format!("Connection not found: {conn_id}"),
            StatusCode::NOT_FOUND,
        );
    }
    if let Err(e) = save_raw_connections(&state, new_connections) {
        return internal_error(e, "failed to write config");
    }
    api_ok(json!({})).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": "internal_server_error"})),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use std::sync::Arc;

    async fn test_state(config_path: std::path::PathBuf) -> SharedState {
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
        use std::str::FromStr;

        let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|p| p.parent()) // crate-escapes-root: This cross-language test helper intentionally targets the yu_ai_manager checkout to compare Python extensions, which are absent from the extracted crates/ mirror and make this test unable to run there.
            .unwrap()
            .to_path_buf();
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(
            crate::state::AppState::new(
                crate::state::Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: Default::default(),
                    trusted_peer_ips: Default::default(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path,
                    project_root,
                    app_config: json!({}),
                    cache_dir: std::path::PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    async fn response_json(resp: Response) -> Value {
        let body = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[test]
    fn validate_rejects_missing_fields() {
        let err = validate_connection(&json!({})).unwrap();
        assert!(err.contains("name"));
        assert!(err.contains("transport"));
    }

    #[test]
    fn validate_rejects_unknown_transport() {
        let err =
            validate_connection(&json!({"name": "x", "transport": "carrier-pigeon"})).unwrap();
        assert!(err.contains("Invalid transport"));
    }

    #[test]
    fn validate_requires_transport_specific_fields() {
        assert!(validate_connection(&json!({"name": "x", "transport": "stdio"})).is_some());
        assert!(validate_connection(
            &json!({"name": "x", "transport": "stdio", "stdio": {"command": "run"}})
        )
        .is_none());
        assert!(validate_connection(&json!({"name": "x", "transport": "sse"})).is_some());
        assert!(validate_connection(
            &json!({"name": "x", "transport": "sse", "sse": {"url": "http://h"}})
        )
        .is_none());
        assert!(
            validate_connection(&json!({"name": "x", "transport": "streamable_http"})).is_some()
        );
    }

    #[test]
    fn encrypt_then_decrypt_sensitive_round_trips() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let cfg = json!({
            "name": "x",
            "transport": "sse",
            "sse": {"url": "http://h", "headers": {"Authorization": "Bearer t"}},
        });
        let encrypted = encrypt_sensitive(&cfg, root);
        let headers = encrypted["sse"]["headers"].as_str().unwrap();
        assert!(headers.starts_with("enc:"));

        let decrypted = decrypt_sensitive(&encrypted, root);
        assert_eq!(decrypted["sse"]["headers"]["Authorization"], "Bearer t");
    }

    #[test]
    fn encrypt_skips_empty_headers() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let cfg = json!({"name": "x", "transport": "sse", "sse": {"url": "h", "headers": {}}});
        let encrypted = encrypt_sensitive(&cfg, root);
        assert_eq!(encrypted["sse"]["headers"], json!({}));
    }

    #[test]
    fn mask_for_list_redacts_headers_and_env() {
        let cfg = json!({
            "stdio": {"env": {"SECRET": "v"}},
            "sse": {"headers": {"Authorization": "Bearer t"}},
        });
        let masked = mask_for_list(&cfg);
        assert_eq!(masked["stdio"]["env"]["SECRET"], "***");
        assert_eq!(masked["sse"]["headers"]["Authorization"], "***");
    }

    #[tokio::test]
    async fn add_then_list_then_update_then_delete_round_trip() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;

        let resp = add_connection(
            State(Arc::clone(&state)),
            None,
            None,
            Json(json!({
                "name": "srv1",
                "transport": "sse",
                "sse": {"url": "http://example", "headers": {"X": "y"}},
            })),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::CREATED);
        let body = response_json(resp).await;
        let conn_id = body["connection"]["id"].as_str().unwrap().to_string();
        assert_eq!(body["connection"]["enabled"], true);
        assert_eq!(body["connection"]["sse"]["headers"]["X"], "y");

        // stored on disk encrypted, not plaintext
        let raw = raw_connections(&state);
        assert_eq!(raw.len(), 1);
        assert!(raw[0]["sse"]["headers"]
            .as_str()
            .unwrap()
            .starts_with("enc:"));

        let resp = list_connections(State(Arc::clone(&state)), None).await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = response_json(resp).await;
        let listed = &body["connections"][0];
        assert_eq!(listed["id"], conn_id);
        assert_eq!(listed["status"], "disconnected");
        assert_eq!(listed["sse"]["headers"]["X"], "***");

        let resp = update_connection(
            State(Arc::clone(&state)),
            None,
            None,
            AxumPath(conn_id.clone()),
            Json(json!({"enabled": false})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = response_json(resp).await;
        assert_eq!(body["connection"]["enabled"], false);
        assert_eq!(body["connection"]["id"], conn_id);

        let resp = delete_connection(State(Arc::clone(&state)), None, AxumPath(conn_id)).await;
        assert_eq!(resp.status(), StatusCode::OK);
        assert!(raw_connections(&state).is_empty());
    }

    #[tokio::test]
    async fn add_connection_rejects_duplicate_id() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let body = json!({"id": "dup", "name": "a", "transport": "sse", "sse": {"url": "h"}});

        let resp = add_connection(State(Arc::clone(&state)), None, None, Json(body.clone())).await;
        assert_eq!(resp.status(), StatusCode::CREATED);

        let resp = add_connection(State(Arc::clone(&state)), None, None, Json(body)).await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn add_connection_rejects_invalid_body() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let resp =
            add_connection(State(state), None, None, Json(json!({"name": "only-name"}))).await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn update_connection_rejects_unknown_id() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let resp = update_connection(
            State(state),
            None,
            None,
            AxumPath("missing".to_string()),
            Json(json!({"enabled": false})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn update_connection_preserves_id_even_if_body_tries_to_change_it() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        add_connection(
            State(Arc::clone(&state)),
            None,
            None,
            Json(json!({"id": "keep-me", "name": "a", "transport": "sse", "sse": {"url": "h"}})),
        )
        .await;

        let resp = update_connection(
            State(Arc::clone(&state)),
            None,
            None,
            AxumPath("keep-me".to_string()),
            Json(json!({"id": "hijacked", "name": "b"})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = response_json(resp).await;
        assert_eq!(body["connection"]["id"], "keep-me");
    }

    #[tokio::test]
    async fn delete_connection_rejects_unknown_id() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let resp = delete_connection(State(state), None, AxumPath("missing".to_string())).await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn add_connection_stdio_requires_local_request() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let remote: SocketAddr = "203.0.113.1:1234".parse().unwrap();
        let resp = add_connection(
            State(state),
            None,
            Some(Extension(ConnectInfo(remote))),
            Json(json!({"name": "a", "transport": "stdio", "stdio": {"command": "run"}})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn add_connection_stdio_allows_loopback_request() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let local: SocketAddr = "127.0.0.1:1234".parse().unwrap();
        let resp = add_connection(
            State(state),
            None,
            Some(Extension(ConnectInfo(local))),
            Json(json!({"name": "a", "transport": "stdio", "stdio": {"command": "run"}})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::CREATED);
    }
}

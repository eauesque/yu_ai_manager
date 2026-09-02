//! `/v1/router/capabilities` and `/v1/node/services` — Rust native.
//!
//! Both mirror Python `routes/gateway_status.py`: gateway bearer/loopback
//! auth, a scope check, then a small JSON body. Neither forwards.

use axum::{
    extract::{ConnectInfo, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde_json::{json, Value};
use std::net::SocketAddr;

use crate::auth::gateway;
use crate::state::SharedState;

/// Python `core/gateway/errors.py::openai_error`.
fn openai_error(
    message: &str,
    code: &str,
    status: StatusCode,
    error_type: &str,
    param: Option<&str>,
) -> Response {
    let mut error = json!({"message": message, "type": error_type, "code": code});
    if let Some(param) = param {
        error["param"] = json!(param);
    }
    (status, Json(json!({"error": error}))).into_response()
}

fn err_401() -> Response {
    openai_error(
        "Unauthorized",
        "invalid_api_key",
        StatusCode::UNAUTHORIZED,
        "authentication_error",
        None,
    )
}

fn err_403_scope(needed: &str) -> Response {
    openai_error(
        "Insufficient scope",
        "insufficient_scope",
        StatusCode::FORBIDDEN,
        "invalid_request_error",
        Some(needed),
    )
}

/// Gateway auth + scope gate shared by both routes, mirroring the identical
/// preamble in Python's `capabilities()` and `node_services()`.
fn gateway_gate(
    state: &SharedState,
    headers: &HeaderMap,
    connect: Option<&ConnectInfo<SocketAddr>>,
    needed: &str,
) -> Option<Response> {
    let client_ip = connect.map_or_else(String::new, |ConnectInfo(sa)| sa.ip().to_string());
    let Some(auth) = gateway::check_request(
        &state.gateway_keys,
        state.gateway_loopback_bypass,
        headers,
        &client_ip,
    ) else {
        return Some(err_401());
    };
    if !gateway::has_scope(&auth, needed) {
        return Some(err_403_scope(needed));
    }
    None
}

/// Python `core/gateway/capabilities.py::build_capabilities`. Every field but
/// `models` is a constant announcing what this gateway speaks.
fn build_capabilities(models: Vec<Value>) -> Value {
    json!({
        "version": "1",
        "phase": 1,
        "responses_api_subset": {
            "non_stream": false,
            "stream": false,
            "tools_function": false,
            "tools_builtin": false,
            "previous_response_id": "unsupported",
            "reasoning_items": false,
            "background": false,
        },
        "chat_completions": {"stream": true, "tools": true},
        "anthropic_messages": {"stream": true, "tools": true},
        "image_backends": ["sd_webui", "comfyui"],
        "models": models,
    })
}

/// GET /v1/router/capabilities
///
/// `models` comes from the LLM router's backend catalog
/// (`core/llm_router/state.py::get_catalog`), which is a process-local
/// singleton populated only by mDNS discovery
/// (`mdns_integration_helpers.py::_catalog.set_backend`). Rust runs no such
/// discovery, so the list is empty — which is also Python's own answer: its
/// catalog lookup sits inside a bare `except` that falls back to `[]`, and a
/// Python process that has discovered nothing yet reports the same.
pub async fn router_capabilities(
    State(state): State<SharedState>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = gateway_gate(
        &state,
        &headers,
        connect.as_ref().map(|e| &e.0),
        gateway::SCOPE_LLM_MODELS,
    ) {
        return r;
    }
    Json(build_capabilities(Vec::new())).into_response()
}

/// Python `core/web/runtime_app.py` builds the health probe's backend map from
/// `gateway.backends` — keeping only entries that carry a `base_url` — and then
/// `setdefault`s `agentmemory` and `headroom` so those two are always probed.
///
/// Order differs from Python and deliberately so: `serde_json`'s object map is
/// sorted by key (no `preserve_order` feature), so configured entries come out
/// alphabetically rather than in the order they appear in config.json, with the
/// two defaults appended after. The response is a list of self-identifying
/// objects and nothing consumes its order, so this is stable and sufficient —
/// but it is not the same sequence Python emits, and no test here claims it is.
fn configured_backends(config: &Value) -> Vec<(String, String)> {
    const AGENTMEMORY_DEFAULT: &str = "http://127.0.0.1:3111";
    const HEADROOM_DEFAULT: &str = "http://127.0.0.1:8787";

    let backends = config.get("gateway").and_then(|g| g.get("backends"));
    let mut out: Vec<(String, String)> = Vec::new();
    if let Some(map) = backends.and_then(Value::as_object) {
        for (id, entry) in map {
            // Python's comprehension keeps only `if "base_url" in v`.
            if let Some(url) = entry.get("base_url").and_then(Value::as_str) {
                out.push((id.clone(), url.to_string()));
            }
        }
    }
    for (id, default_url) in [
        ("agentmemory", AGENTMEMORY_DEFAULT),
        ("headroom", HEADROOM_DEFAULT),
    ] {
        if out.iter().any(|(existing, _)| existing == id) {
            continue;
        }
        // `setdefault` uses the URL Python resolved earlier, which is
        // `gateway.backends.<id>.base_url` or the default. Reaching here means
        // that key had no usable `base_url`, so the default is what applies.
        out.push((id.to_string(), default_url.to_string()));
    }
    out
}

/// GET /v1/node/services
///
/// `state` is a live health verdict from `HealthProbe`, which Rust does not
/// run. Every entry therefore reports `unknown` — not a placeholder but the
/// value Python itself holds: `HealthProbe.__init__` seeds
/// `{k: BackendState.UNKNOWN for k in backends}`, so a Python process reports
/// exactly this until its first probe tick lands, and reports it indefinitely
/// when `gateway.health_probe.enabled` is false.
///
/// The `id` and `endpoint` fields are config-derived, so they are real. The
/// alternative — an empty list — would claim this node has no services at all,
/// which is a stronger and wronger statement than "their health is unknown".
pub async fn node_services(
    State(state): State<SharedState>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = gateway_gate(
        &state,
        &headers,
        connect.as_ref().map(|e| &e.0),
        gateway::SCOPE_NODE_STATUS,
    ) {
        return r;
    }
    let config = crate::ext_config::read_config(&state.config.config_path).unwrap_or(json!({}));
    let services: Vec<Value> = configured_backends(&config)
        .into_iter()
        .map(|(id, endpoint)| json!({"id": id, "state": "unknown", "endpoint": endpoint}))
        .collect();
    Json(json!({"services": services})).into_response()
}

#[cfg(test)]
mod tests {
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use axum::http::{HeaderName, HeaderValue};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tempfile::TempDir;

    use super::*;
    use crate::state::{AppState, Config};

    async fn test_state(
        project_root: PathBuf,
        config_body: &str,
        keys: Vec<gateway::GatewayKey>,
        bypass: bool,
    ) -> SharedState {
        let config_path = project_root.join("config.json");
        std::fs::write(&config_path, config_body).unwrap();
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        let mut app = AppState::new(
            Config {
                db_path: "sqlite::memory:".to_string(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,
                pin_boss_login_ui: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                quick_lock_enabled: true,
                pin_auth_enabled: false,
                min_pin_length: 4,
                python_url: String::new(),
                config_path,
                project_root,
                app_config: json!({}),
                cache_dir: PathBuf::from("."),
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
        .await;
        app.gateway_keys = keys;
        app.gateway_loopback_bypass = bypass;
        Arc::new(app)
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    fn loopback() -> Option<Extension<ConnectInfo<SocketAddr>>> {
        Some(Extension(ConnectInfo(SocketAddr::from((
            [127, 0, 0, 1],
            9999,
        )))))
    }

    fn remote() -> Option<Extension<ConnectInfo<SocketAddr>>> {
        Some(Extension(ConnectInfo(SocketAddr::from((
            [203, 0, 113, 9],
            9999,
        )))))
    }

    fn bearer(token: &str) -> HeaderMap {
        let mut h = HeaderMap::new();
        h.insert(
            HeaderName::from_static("authorization"),
            HeaderValue::from_str(&format!("Bearer {token}")).unwrap(),
        );
        h
    }

    // ── auth ────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn both_routes_401_without_a_credential_when_bypass_is_off() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}", Vec::new(), false).await;

        for (label, resp) in [
            (
                "capabilities",
                router_capabilities(State(Arc::clone(&state)), remote(), HeaderMap::new()).await,
            ),
            (
                "node/services",
                node_services(State(Arc::clone(&state)), remote(), HeaderMap::new()).await,
            ),
        ] {
            assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "{label}");
            let body = json_body(resp).await;
            assert_eq!(body["error"]["code"], "invalid_api_key", "{label}");
            assert_eq!(body["error"]["type"], "authentication_error", "{label}");
        }
    }

    #[tokio::test]
    async fn each_route_names_its_own_scope_when_refusing() {
        // Python passes `param=str(Scope.X)`, and the two routes need
        // *different* scopes: llm:models vs node:status. A shared constant
        // would let a key scoped for one reach the other.
        let temp = TempDir::new().unwrap();
        let keys = scoped_keys(temp.path(), &["sd:query"]);
        let state = test_state(temp.path().to_path_buf(), "{}", keys, false).await;

        let resp = router_capabilities(State(Arc::clone(&state)), remote(), bearer("secret")).await;
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);
        let body = json_body(resp).await;
        assert_eq!(body["error"]["code"], "insufficient_scope");
        assert_eq!(body["error"]["param"], "llm:models");

        let resp = node_services(State(Arc::clone(&state)), remote(), bearer("secret")).await;
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);
        assert_eq!(json_body(resp).await["error"]["param"], "node:status");
    }

    #[tokio::test]
    async fn a_key_scoped_for_one_route_cannot_reach_the_other() {
        let temp = TempDir::new().unwrap();
        let keys = scoped_keys(temp.path(), &["llm:models"]);
        let state = test_state(temp.path().to_path_buf(), "{}", keys, false).await;

        let ok = router_capabilities(State(Arc::clone(&state)), remote(), bearer("secret")).await;
        assert_eq!(ok.status(), StatusCode::OK);

        let refused = node_services(State(Arc::clone(&state)), remote(), bearer("secret")).await;
        assert_eq!(refused.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn loopback_bypass_admits_both_routes_when_enabled() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}", Vec::new(), true).await;
        assert_eq!(
            router_capabilities(State(Arc::clone(&state)), loopback(), HeaderMap::new())
                .await
                .status(),
            StatusCode::OK
        );
        assert_eq!(
            node_services(State(Arc::clone(&state)), loopback(), HeaderMap::new())
                .await
                .status(),
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn loopback_bypass_does_not_admit_a_remote_caller() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}", Vec::new(), true).await;
        assert_eq!(
            node_services(State(Arc::clone(&state)), remote(), HeaderMap::new())
                .await
                .status(),
            StatusCode::UNAUTHORIZED
        );
    }

    // ── capabilities body ───────────────────────────────────────────────────

    #[tokio::test]
    async fn capabilities_reports_the_declared_surface_and_no_models() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}", Vec::new(), true).await;
        let body = json_body(
            router_capabilities(State(Arc::clone(&state)), loopback(), HeaderMap::new()).await,
        )
        .await;

        assert_eq!(body["version"], "1");
        assert_eq!(body["phase"], 1);
        assert_eq!(
            body["chat_completions"],
            json!({"stream": true, "tools": true})
        );
        assert_eq!(
            body["anthropic_messages"],
            json!({"stream": true, "tools": true})
        );
        assert_eq!(body["image_backends"], json!(["sd_webui", "comfyui"]));
        // The Responses API subset is entirely unsupported in phase 1; a `true`
        // here would advertise a surface that does not answer.
        let subset = &body["responses_api_subset"];
        for flag in [
            "non_stream",
            "stream",
            "tools_function",
            "tools_builtin",
            "reasoning_items",
            "background",
        ] {
            assert_eq!(subset[flag], false, "responses_api_subset.{flag}");
        }
        assert_eq!(subset["previous_response_id"], "unsupported");
        // No mDNS discovery runs here, so the catalog is empty — as it is in a
        // Python process that has discovered nothing.
        assert_eq!(body["models"], json!([]));
    }

    // ── node services body ──────────────────────────────────────────────────

    #[tokio::test]
    async fn node_services_lists_configured_backends_as_unknown() {
        let temp = TempDir::new().unwrap();
        let state = test_state(
            temp.path().to_path_buf(),
            r#"{"gateway": {"backends": {
                 "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"},
                 "sd": {"type": "sd_webui", "base_url": "http://127.0.0.1:7860"}}}}"#,
            Vec::new(),
            true,
        )
        .await;
        let body =
            json_body(node_services(State(Arc::clone(&state)), loopback(), HeaderMap::new()).await)
                .await;
        let services = body["services"].as_array().unwrap();

        let find = |id: &str| {
            services
                .iter()
                .find(|s| s["id"] == id)
                .unwrap_or_else(|| panic!("{id} missing from {body}"))
                .clone()
        };
        assert_eq!(find("ollama")["endpoint"], "http://127.0.0.1:11434");
        assert_eq!(find("sd")["endpoint"], "http://127.0.0.1:7860");
        // Rust runs no health probe, so every state is the seed value Python
        // uses before its first tick. Reporting "running" would be a claim
        // nobody checked.
        for service in services {
            assert_eq!(service["state"], "unknown", "{service}");
        }
    }

    #[tokio::test]
    async fn agentmemory_and_headroom_are_always_present() {
        // Python `setdefault`s both regardless of config.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}", Vec::new(), true).await;
        let body =
            json_body(node_services(State(Arc::clone(&state)), loopback(), HeaderMap::new()).await)
                .await;
        let services = body["services"].as_array().unwrap();
        assert_eq!(services.len(), 2, "{body}");
        let by_id = |id: &str| services.iter().find(|s| s["id"] == id).cloned();
        assert_eq!(
            by_id("agentmemory").unwrap()["endpoint"],
            "http://127.0.0.1:3111"
        );
        assert_eq!(
            by_id("headroom").unwrap()["endpoint"],
            "http://127.0.0.1:8787"
        );
    }

    #[tokio::test]
    async fn a_configured_agentmemory_url_wins_over_the_default() {
        let temp = TempDir::new().unwrap();
        let state = test_state(
            temp.path().to_path_buf(),
            r#"{"gateway": {"backends": {
                 "agentmemory": {"base_url": "http://10.0.0.2:3111"}}}}"#,
            Vec::new(),
            true,
        )
        .await;
        let body =
            json_body(node_services(State(Arc::clone(&state)), loopback(), HeaderMap::new()).await)
                .await;
        let services = body["services"].as_array().unwrap();
        // Exactly one agentmemory entry — the default must not be appended
        // alongside the configured one.
        let am: Vec<&Value> = services
            .iter()
            .filter(|s| s["id"] == "agentmemory")
            .collect();
        assert_eq!(am.len(), 1, "{body}");
        assert_eq!(am[0]["endpoint"], "http://10.0.0.2:3111");
    }

    #[tokio::test]
    async fn a_backend_without_a_base_url_is_skipped() {
        // Python's comprehension filters on `if "base_url" in v`, so an entry
        // that only declares a type never reaches the probe.
        let temp = TempDir::new().unwrap();
        let state = test_state(
            temp.path().to_path_buf(),
            r#"{"gateway": {"backends": {
                 "halfdone": {"type": "ollama"},
                 "real": {"base_url": "http://127.0.0.1:1234"}}}}"#,
            Vec::new(),
            true,
        )
        .await;
        let body =
            json_body(node_services(State(Arc::clone(&state)), loopback(), HeaderMap::new()).await)
                .await;
        let ids: Vec<&str> = body["services"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["id"].as_str().unwrap())
            .collect();
        assert!(!ids.contains(&"halfdone"), "{body}");
        assert!(ids.contains(&"real"), "{body}");
    }

    #[tokio::test]
    async fn an_agentmemory_entry_without_a_base_url_falls_back_to_the_default() {
        // It is dropped by the comprehension, then re-added by `setdefault`
        // with the URL Python resolved — which for a missing `base_url` is the
        // default, not nothing.
        let temp = TempDir::new().unwrap();
        let state = test_state(
            temp.path().to_path_buf(),
            r#"{"gateway": {"backends": {"agentmemory": {"type": "agentmemory"}}}}"#,
            Vec::new(),
            true,
        )
        .await;
        let body =
            json_body(node_services(State(Arc::clone(&state)), loopback(), HeaderMap::new()).await)
                .await;
        let am: Vec<&Value> = body["services"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|s| s["id"] == "agentmemory")
            .collect();
        assert_eq!(am.len(), 1, "{body}");
        assert_eq!(am[0]["endpoint"], "http://127.0.0.1:3111");
    }

    /// Build a real gateway key through `load_keys`, the only constructor:
    /// `GatewayKey`'s fields are private, so a test that hand-rolled one would
    /// be exercising a shape production never produces.
    fn scoped_keys(root: &std::path::Path, scopes: &[&str]) -> Vec<gateway::GatewayKey> {
        use base64::Engine as _;
        std::fs::create_dir_all(root.join("data")).unwrap();
        let secret_key = base64::engine::general_purpose::URL_SAFE.encode([29_u8; 32]);
        std::fs::write(root.join("data").join("secret.key"), &secret_key).unwrap();
        let sealed = format!(
            "enc:{}",
            crate::secret_store::encrypt_for_test("secret", secret_key.as_bytes())
        );
        let cfg = json!({"api_keys": [{"id": "k", "secret_enc": sealed, "scopes": scopes}]});
        let keys = gateway::load_keys(&cfg, root);
        assert_eq!(keys.len(), 1, "test key must load");
        keys
    }
}

//! Gateway wildcard proxy handlers (E-2): Ollama + SD WebUI

use std::{net::SocketAddr, time::Duration};

use axum::{
    body::{to_bytes, Body},
    extract::{ConnectInfo, Path, State},
    http::{HeaderMap, HeaderName, Method, Request, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use reqwest::Url;
use serde_json::json;

use crate::{
    auth::{chain::is_loopback_addr, gateway},
    config_io::load as load_config_json,
    routes::sd_webui_bridge::{ext_config, sd_api_url},
    state::SharedState,
};

/// Port of Python `core/gateway/sd_proxy.py:SD_ALLOWED_ENDPOINTS`, which is a
/// `dict[(method, path) -> Scope]`. The scope column is load-bearing: it is what
/// separates a query key from one that may switch the running model. An earlier
/// port kept only the (method, path) pair, which silently turned the table into
/// a bare allowlist and dropped the authorization mapping.
static SD_ALLOWED: &[(&str, &str, &str)] = &[
    ("POST", "/sdapi/v1/txt2img", gateway::SCOPE_SD_GENERATE),
    ("POST", "/sdapi/v1/img2img", gateway::SCOPE_SD_GENERATE),
    (
        "POST",
        "/sdapi/v1/extra-single-image",
        gateway::SCOPE_SD_GENERATE,
    ),
    ("POST", "/sdapi/v1/interrupt", gateway::SCOPE_SD_GENERATE),
    ("GET", "/sdapi/v1/samplers", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/sd-models", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/loras", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/embeddings", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/upscalers", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/sd-vae", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/progress", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/scripts", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/script-info", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/cmd-flags", gateway::SCOPE_SD_QUERY),
    ("GET", "/sdapi/v1/options", gateway::SCOPE_SD_ADMIN),
    ("POST", "/sdapi/v1/options", gateway::SCOPE_SD_ADMIN),
    (
        "POST",
        "/sdapi/v1/refresh-checkpoints",
        gateway::SCOPE_SD_ADMIN,
    ),
    ("POST", "/sdapi/v1/refresh-vae", gateway::SCOPE_SD_ADMIN),
    ("POST", "/sdapi/v1/refresh-loras", gateway::SCOPE_SD_ADMIN),
    (
        "POST",
        "/sdapi/v1/reload-checkpoint",
        gateway::SCOPE_SD_ADMIN,
    ),
];

/// Python `core/gateway/sd_proxy.py:get_sd_scope`. `None` means "not on the
/// allowlist", which the caller answers with 404 — never with an auth error, so
/// that an unauthenticated caller cannot probe which paths exist.
fn sd_scope_for(method: &str, path: &str) -> Option<&'static str> {
    SD_ALLOWED
        .iter()
        .find(|(m, p, _)| *m == method && *p == path)
        .map(|(_, _, scope)| *scope)
}

static REQ_STRIP: &[&str] = &[
    "authorization",
    "x-api-key",
    "cookie",
    "host",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "connection",
    "keep-alive",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "user-agent",
];

static RESP_STRIP: &[&str] = &[
    "connection",
    "keep-alive",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "server",
    "set-cookie",
];

fn err_401() -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({"error":{"message":"Unauthorized","type":"authentication_error","code":"invalid_api_key"}})),
    )
        .into_response()
}

fn err_403() -> Response {
    (
        StatusCode::FORBIDDEN,
        Json(json!({"error":{"message":"Forbidden","type":"invalid_request_error","code":"forbidden"}})),
    )
        .into_response()
}

fn err_403_scope(needed: &str) -> Response {
    (
        StatusCode::FORBIDDEN,
        Json(json!({"error":{"message":"Insufficient scope","type":"invalid_request_error","code":"insufficient_scope","param":needed}})),
    )
        .into_response()
}

fn err_404_backend() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({"error":{"message":"Backend not found","type":"server_error","code":"backend_not_found"}})),
    )
        .into_response()
}

fn err_404_path() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({"error":{"message":"Not Found","type":"invalid_request_error","code":"not_found"}})),
    )
        .into_response()
}

fn err_502() -> Response {
    (
        StatusCode::BAD_GATEWAY,
        Json(json!({"error":{"message":"Bad Gateway","type":"server_error","code":"backend_unavailable"}})),
    )
        .into_response()
}

fn err_504() -> Response {
    (
        StatusCode::GATEWAY_TIMEOUT,
        Json(json!({"error":{"message":"Gateway Timeout","type":"server_error","code":"backend_timeout"}})),
    )
        .into_response()
}

fn proxy_origin_allowed(headers: &HeaderMap) -> bool {
    let host_str = match headers.get("host").and_then(|v| v.to_str().ok()) {
        Some(h) => h,
        None => return true,
    };
    let expected = parse_host_port(host_str);
    for name in ["origin", "referer"] {
        if let Some(value) = headers.get(name).and_then(|v| v.to_str().ok()) {
            if !value.is_empty() && parse_url_host_port(value) != expected {
                return false;
            }
        }
    }
    true
}

fn parse_host_port(host: &str) -> Option<(String, Option<u16>)> {
    let (h, p) = if let Some((h, p)) = host.rsplit_once(':') {
        (h, p.parse::<u16>().ok())
    } else {
        (host, None)
    };
    if h.is_empty() {
        None
    } else {
        Some((h.to_lowercase(), p))
    }
}

fn parse_url_host_port(url: &str) -> Option<(String, Option<u16>)> {
    let u = Url::parse(url).ok()?;
    Some((u.host_str()?.to_lowercase(), u.port()))
}

async fn stream_proxy(
    upstream_url: Url,
    method: Method,
    mut headers: HeaderMap,
    client_ip: &str,
    body_bytes: bytes::Bytes,
    timeout: Option<Duration>,
    strip_content_length: bool,
) -> Response {
    if let Ok(v) = client_ip.parse::<axum::http::HeaderValue>() {
        headers.insert("x-forwarded-for", v);
    }

    let strip_names: Vec<HeaderName> = REQ_STRIP
        .iter()
        .filter_map(|s| s.parse::<HeaderName>().ok())
        .collect();
    for name in &strip_names {
        headers.remove(name);
    }
    if strip_content_length {
        headers.remove("content-length");
    }

    let client = {
        let mut b = reqwest::Client::builder();
        if let Some(d) = timeout {
            b = b.timeout(d);
        }
        match b.build() {
            Ok(c) => c,
            Err(_) => return err_502(),
        }
    };

    let mut req_builder = client.request(method, upstream_url).body(body_bytes);
    for (name, value) in &headers {
        req_builder = req_builder.header(name, value);
    }

    let upstream_resp = match req_builder.send().await {
        Ok(r) => r,
        Err(e) => {
            if e.is_timeout() {
                return err_504();
            }
            return err_502();
        }
    };

    let status = upstream_resp.status();
    let resp_headers = upstream_resp.headers().clone();
    let resp_stream = upstream_resp.bytes_stream();
    let body = Body::from_stream(resp_stream);

    let mut builder = Response::builder().status(status.as_u16());
    let bh = builder.headers_mut().expect("builder valid");
    let resp_strip: Vec<HeaderName> = RESP_STRIP
        .iter()
        .filter_map(|s| s.parse::<HeaderName>().ok())
        .collect();
    for (name, value) in resp_headers {
        if let Some(n) = name {
            if !resp_strip.contains(&n) {
                bh.insert(n, value);
            }
        }
    }

    builder.body(body).unwrap_or_else(|_| err_502())
}

pub async fn ollama_handler(
    State(state): State<SharedState>,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    Path((name, sub)): Path<(String, String)>,
    request: Request<Body>,
) -> Response {
    let client_ip = addr.ip().to_string();

    if !is_loopback_addr(&client_ip) {
        return err_401();
    }

    let (parts, body) = request.into_parts();

    if !proxy_origin_allowed(&parts.headers) {
        return err_403();
    }

    // L3 runs before the body is buffered: a request we are going to reject must
    // not first cost us an unbounded upload in memory.
    let Some(auth) = gateway::check_request(
        &state.gateway_keys,
        state.gateway_loopback_bypass,
        &parts.headers,
        &client_ip,
    ) else {
        return err_401();
    };
    if !gateway::has_scope(&auth, gateway::SCOPE_OLLAMA_PROXY) {
        return err_403_scope(gateway::SCOPE_OLLAMA_PROXY);
    }

    let body_bytes = match to_bytes(body, usize::MAX).await {
        Ok(b) => b,
        Err(_) => return err_502(),
    };

    // config_path から毎回ディスク再読込し backend を解決
    let base_url = {
        let cfg = load_config_json(&state.config.config_path);
        cfg.get("gateway")
            .and_then(|g| g.get("backends"))
            .and_then(|b| b.as_object())
            .and_then(|map| {
                map.values().find(|v| {
                    v.get("type").and_then(|t| t.as_str()) == Some("ollama")
                        && v.get("name").and_then(|n| n.as_str()) == Some(&name)
                })
            })
            .and_then(|v| v.get("base_url")?.as_str().map(|s| s.to_string()))
    };
    let base_url = match base_url {
        Some(u) => u,
        None => return err_404_backend(),
    };

    // /ollama/{name}/api/blobs/* は無制限、それ以外は 300s
    let timeout = if sub.starts_with("api/blobs/") {
        None
    } else {
        Some(Duration::from_secs(300))
    };

    let upstream_url = match Url::parse(&format!("{}/{sub}", base_url.trim_end_matches('/'))) {
        Ok(u) => u,
        Err(_) => return err_502(),
    };

    stream_proxy(
        upstream_url,
        parts.method,
        parts.headers,
        &client_ip,
        body_bytes,
        timeout,
        true,
    )
    .await
}

pub async fn sd_handler(
    State(state): State<SharedState>,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    Path(sub): Path<String>,
    request: Request<Body>,
) -> Response {
    let client_ip = addr.ip().to_string();

    if !is_loopback_addr(&client_ip) {
        return err_401();
    }

    let (parts, body) = request.into_parts();

    if !proxy_origin_allowed(&parts.headers) {
        return err_403();
    }

    // layer 3a: SD path allowlist. A path that is not on the table is 404 —
    // answered before authentication so that it stays indistinguishable from a
    // path that does not exist upstream.
    let full_path = format!("/sdapi/v1/{sub}");
    let Some(scope_needed) = sd_scope_for(parts.method.as_str(), &full_path) else {
        return err_404_path();
    };

    // layer 3b: gateway key + scope. This runs before the body is buffered: a
    // request we are going to reject must not first cost us an unbounded upload
    // in memory. Order and bypass semantics follow `routes/gateway_sd.py:187-198`
    // — `check_request` honours `gateway.auth.allow_loopback_bypass`, so an
    // administrator who sets it to false really does require a key here.
    let Some(auth) = gateway::check_request(
        &state.gateway_keys,
        state.gateway_loopback_bypass,
        &parts.headers,
        &client_ip,
    ) else {
        return err_401();
    };
    if !gateway::has_scope(&auth, scope_needed) {
        return err_403_scope(scope_needed);
    }

    let body_bytes = match to_bytes(body, usize::MAX).await {
        Ok(b) => b,
        Err(_) => return err_502(),
    };

    let cfg = ext_config(&state);
    let sd_base = sd_api_url(&cfg);

    let upstream_url = match Url::parse(&format!("{}{}", sd_base.trim_end_matches('/'), full_path))
    {
        Ok(u) => u,
        Err(_) => return err_502(),
    };

    stream_proxy(
        upstream_url,
        parts.method,
        parts.headers,
        &client_ip,
        body_bytes,
        Some(Duration::from_secs(1800)),
        false,
    )
    .await
}

#[cfg(test)]
mod tests {
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use base64::Engine as _;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use super::*;
    use crate::{
        auth::gateway::{SCOPE_OLLAMA_PROXY, SCOPE_SD_ADMIN, SCOPE_SD_GENERATE, SCOPE_SD_QUERY},
        state::{AppState, Config},
    };

    /// A project root carrying its own `data/secret.key`.
    fn temp_root(name: &str) -> (PathBuf, String) {
        let root =
            std::env::temp_dir().join(format!("yu-ollama-gate-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("data")).unwrap();
        let key = base64::engine::general_purpose::URL_SAFE.encode([31_u8; 32]);
        std::fs::write(root.join("data").join("secret.key"), &key).unwrap();
        (root, key)
    }

    fn seal(plaintext: &str, key: &str) -> String {
        format!(
            "enc:{}",
            crate::secret_store::encrypt_for_test(plaintext, key.as_bytes())
        )
    }

    async fn test_state(app_config: serde_json::Value, project_root: PathBuf) -> SharedState {
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
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: project_root.join("config.json"),
                    project_root,
                    app_config,
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
            .await,
        )
    }

    async fn call(state: SharedState, authorization: Option<&str>) -> Response {
        let mut builder = Request::builder()
            .method("POST")
            .uri("/ollama/local/api/chat")
            .header("host", "127.0.0.1:8000");
        if let Some(value) = authorization {
            builder = builder.header("authorization", value);
        }
        ollama_handler(
            State(state),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Path(("local".to_string(), "api/chat".to_string())),
            builder.body(Body::from(r#"{"model":"x"}"#)).unwrap(),
        )
        .await
    }

    async fn body_json(response: Response) -> serde_json::Value {
        let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    /// No gateway backend is configured in any of these tests, so 404
    /// `backend_not_found` is what "the request got past authentication" looks
    /// like. 401/403 means it did not.
    const PASSED_AUTH: StatusCode = StatusCode::NOT_FOUND;

    #[tokio::test]
    async fn ollama_without_bearer_still_works_by_default() {
        let (root, _key) = temp_root("default");
        let response = call(test_state(json!({}), root).await, None).await;
        assert_eq!(response.status(), PASSED_AUTH);
    }

    #[tokio::test]
    async fn a_dummy_bearer_is_not_verified_while_the_bypass_is_on() {
        let (root, _key) = temp_root("dummy-bearer");
        let response = call(
            test_state(json!({}), root).await,
            Some("Bearer sk-dummy-openai-client-key"),
        )
        .await;
        assert_eq!(response.status(), PASSED_AUTH);
    }

    #[tokio::test]
    async fn ollama_requires_a_key_when_loopback_bypass_is_disabled() {
        let (root, _key) = temp_root("bypass-off");
        let config = json!({"gateway": {"auth": {"allow_loopback_bypass": false, "api_keys": []}}});
        let response = call(test_state(config, root).await, None).await;

        // 401 rather than 404 also proves the gate runs before the backend is
        // resolved — and therefore before the body is buffered.
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn ollama_rejects_a_key_lacking_the_proxy_scope() {
        let (root, key) = temp_root("wrong-scope");
        let config = json!({"gateway": {"auth": {
            "allow_loopback_bypass": false,
            "api_keys": [{"id": "k", "secret_enc": seal("tok", &key), "scopes": ["sd:generate"]}],
        }}});
        let response = call(test_state(config, root).await, Some("Bearer tok")).await;

        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let body = body_json(response).await;
        assert_eq!(body["error"]["code"], "insufficient_scope");
        assert_eq!(body["error"]["param"], SCOPE_OLLAMA_PROXY);
    }

    #[tokio::test]
    async fn ollama_accepts_a_key_carrying_the_proxy_scope() {
        let (root, key) = temp_root("right-scope");
        let config = json!({"gateway": {"auth": {
            "allow_loopback_bypass": false,
            "api_keys": [{"id": "k", "secret_enc": seal("tok", &key), "scopes": [SCOPE_OLLAMA_PROXY]}],
        }}});
        let response = call(test_state(config, root).await, Some("Bearer tok")).await;
        assert_eq!(response.status(), PASSED_AUTH);
    }

    #[tokio::test]
    async fn a_wrong_key_is_rejected_when_the_bypass_is_off() {
        let (root, key) = temp_root("wrong-key");
        let config = json!({"gateway": {"auth": {
            "allow_loopback_bypass": false,
            "api_keys": [{"id": "k", "secret_enc": seal("tok", &key), "scopes": [SCOPE_OLLAMA_PROXY]}],
        }}});
        let response = call(test_state(config, root).await, Some("Bearer not-tok")).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn a_rejected_request_does_not_buffer_the_body() {
        // This body errors the instant anyone polls it, so reaching `to_bytes`
        // turns the response into a 502. A clean 401 is the proof that the gate
        // ran before we spent memory on an upload we were going to refuse.
        let (root, _key) = temp_root("unbuffered");
        let config = json!({"gateway": {"auth": {"allow_loopback_bypass": false, "api_keys": []}}});
        let body = Body::from_stream(futures_util::stream::once(async {
            Err::<bytes::Bytes, std::io::Error>(std::io::Error::other("body must not be read"))
        }));
        let response = ollama_handler(
            State(test_state(config, root).await),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Path(("local".to_string(), "api/chat".to_string())),
            Request::builder()
                .method("POST")
                .uri("/ollama/local/api/chat")
                .header("host", "127.0.0.1:8000")
                .body(body)
                .unwrap(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn non_loopback_is_still_refused_before_any_of_this() {
        let (root, _key) = temp_root("non-loopback");
        let response = ollama_handler(
            State(test_state(json!({}), root).await),
            ConnectInfo(SocketAddr::from(([192, 168, 1, 40], 45678))),
            Path(("local".to_string(), "api/chat".to_string())),
            Request::builder()
                .method("POST")
                .uri("/ollama/local/api/chat")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    // --- SD proxy scope gate -------------------------------------------------
    //
    // Port of `routes/gateway_sd.py:179-198`. The SD table is not a flat
    // allowlist: each (method, path) carries the scope it demands, so a key that
    // may only query must not be able to switch the running model.

    /// A project root whose `config.json` points the SD bridge at a closed port,
    /// so "the request got past authentication" is a deterministic 502 rather
    /// than whatever happens to listen on the default SD port on this machine.
    fn sd_root(name: &str) -> (PathBuf, String) {
        let (root, key) = temp_root(name);
        std::fs::write(
            root.join("config.json"),
            serde_json::to_vec(&json!({
                "extensions": {"sd-webui-bridge": {"api_url": "http://127.0.0.1:9"}}
            }))
            .unwrap(),
        )
        .unwrap();
        (root, key)
    }

    async fn sd_call(
        state: SharedState,
        method: &str,
        sub: &str,
        authorization: Option<&str>,
    ) -> Response {
        let mut builder = Request::builder()
            .method(method)
            .uri(format!("/sd/sdapi/v1/{sub}"))
            .header("host", "127.0.0.1:8000");
        if let Some(value) = authorization {
            builder = builder.header("authorization", value);
        }
        sd_handler(
            State(state),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Path(sub.to_string()),
            builder.body(Body::from("{}")).unwrap(),
        )
        .await
    }

    /// Upstream is a closed port, so 502 is what "authentication passed" looks
    /// like here. 401/403/404 means it did not.
    const SD_PASSED_AUTH: StatusCode = StatusCode::BAD_GATEWAY;

    #[tokio::test]
    async fn sd_without_bearer_still_works_by_default() {
        let (root, _key) = sd_root("sd-default");
        let response = sd_call(test_state(json!({}), root).await, "GET", "samplers", None).await;
        assert_eq!(response.status(), SD_PASSED_AUTH);
    }

    #[tokio::test]
    async fn sd_requires_a_key_when_loopback_bypass_is_disabled() {
        let (root, _key) = sd_root("sd-bypass-off");
        let config = json!({"gateway": {"auth": {"allow_loopback_bypass": false, "api_keys": []}}});
        let response = sd_call(test_state(config, root).await, "GET", "samplers", None).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    /// The one that grips the scope column. A key scoped `sd:query` reaches the
    /// query paths but must be refused on `POST /sdapi/v1/options`, which
    /// switches the running model. Flattening the table back to (method, path)
    /// makes this test pass a request it should refuse.
    #[tokio::test]
    async fn sd_rejects_a_query_key_on_an_admin_path() {
        let (root, key) = sd_root("sd-query-vs-admin");
        let config = json!({"gateway": {"auth": {
            "allow_loopback_bypass": false,
            "api_keys": [{"id": "k", "secret_enc": seal("tok", &key), "scopes": [SCOPE_SD_QUERY]}],
        }}});
        let state = test_state(config, root).await;

        let allowed = sd_call(state.clone(), "GET", "samplers", Some("Bearer tok")).await;
        assert_eq!(allowed.status(), SD_PASSED_AUTH);

        let refused = sd_call(state, "POST", "options", Some("Bearer tok")).await;
        assert_eq!(refused.status(), StatusCode::FORBIDDEN);
        let body = body_json(refused).await;
        assert_eq!(body["error"]["code"], "insufficient_scope");
        assert_eq!(body["error"]["param"], SCOPE_SD_ADMIN);
    }

    #[tokio::test]
    async fn sd_accepts_a_key_carrying_the_admin_scope() {
        let (root, key) = sd_root("sd-admin-scope");
        let config = json!({"gateway": {"auth": {
            "allow_loopback_bypass": false,
            "api_keys": [{"id": "k", "secret_enc": seal("tok", &key), "scopes": [SCOPE_SD_ADMIN]}],
        }}});
        let response = sd_call(
            test_state(config, root).await,
            "POST",
            "options",
            Some("Bearer tok"),
        )
        .await;
        assert_eq!(response.status(), SD_PASSED_AUTH);
    }

    #[tokio::test]
    async fn sd_generate_scope_does_not_reach_query_or_admin_paths() {
        let (root, key) = sd_root("sd-generate-scope");
        let config = json!({"gateway": {"auth": {
            "allow_loopback_bypass": false,
            "api_keys": [{"id": "k", "secret_enc": seal("tok", &key), "scopes": [SCOPE_SD_GENERATE]}],
        }}});
        let state = test_state(config, root).await;

        let allowed = sd_call(state.clone(), "POST", "txt2img", Some("Bearer tok")).await;
        assert_eq!(allowed.status(), SD_PASSED_AUTH);

        for (method, sub) in [("GET", "samplers"), ("GET", "options")] {
            let refused = sd_call(state.clone(), method, sub, Some("Bearer tok")).await;
            assert_eq!(
                refused.status(),
                StatusCode::FORBIDDEN,
                "{method} /sdapi/v1/{sub} must not be reachable with sd:generate"
            );
        }
    }

    /// Order check: an unlisted path is 404 even with the bypass off and no key.
    /// Answering 401 first would let an unauthenticated caller enumerate which
    /// SD paths this gateway forwards. Python decides the same way
    /// (`gateway_sd.py:183-185` runs before `check_request`).
    #[tokio::test]
    async fn sd_unlisted_path_is_404_before_authentication() {
        let (root, _key) = sd_root("sd-unlisted");
        let config = json!({"gateway": {"auth": {"allow_loopback_bypass": false, "api_keys": []}}});
        let state = test_state(config, root).await;

        let unknown = sd_call(state.clone(), "GET", "definitely-not-a-path", None).await;
        assert_eq!(unknown.status(), StatusCode::NOT_FOUND);

        // Same path, wrong method: the table is keyed by both.
        let wrong_method = sd_call(state, "GET", "txt2img", None).await;
        assert_eq!(wrong_method.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn a_rejected_sd_request_does_not_buffer_the_body() {
        let (root, _key) = sd_root("sd-unbuffered");
        let config = json!({"gateway": {"auth": {"allow_loopback_bypass": false, "api_keys": []}}});
        let body = Body::from_stream(futures_util::stream::once(async {
            Err::<bytes::Bytes, std::io::Error>(std::io::Error::other("body must not be read"))
        }));
        let response = sd_handler(
            State(test_state(config, root).await),
            ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 45678))),
            Path("txt2img".to_string()),
            Request::builder()
                .method("POST")
                .uri("/sd/sdapi/v1/txt2img")
                .header("host", "127.0.0.1:8000")
                .body(body)
                .unwrap(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn sd_non_loopback_is_refused_before_any_of_this() {
        let (root, _key) = sd_root("sd-non-loopback");
        let response = sd_handler(
            State(test_state(json!({}), root).await),
            ConnectInfo(SocketAddr::from(([192, 168, 1, 40], 45678))),
            Path("samplers".to_string()),
            Request::builder()
                .method("GET")
                .uri("/sd/sdapi/v1/samplers")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    /// The Rust table and the Python table must demand the same scope for the
    /// same (method, path). This reads the Python source rather than a copy, so
    /// widening one side alone fails here.
    #[test]
    fn the_sd_table_matches_the_python_one() {
        let src = match std::fs::read_to_string(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../core/gateway/sd_proxy.py"),
        ) {
            Ok(s) => s,
            // The crate is built standalone (no repo checkout around it).
            Err(_) => return,
        };
        let table = src
            .split_once("SD_ALLOWED_ENDPOINTS")
            .and_then(|(_, rest)| rest.split_once('}'))
            .map(|(body, _)| body.to_string())
            .expect("SD_ALLOWED_ENDPOINTS block not found — update this test with the Python side");

        let mut python: Vec<(String, String, String)> = Vec::new();
        for line in table.lines() {
            let Some((key, value)) = line.split_once("):") else {
                continue;
            };
            let key = key.trim().trim_start_matches('(');
            let Some((method, path)) = key.split_once(',') else {
                continue;
            };
            let scope = match value.trim().trim_end_matches(',').rsplit_once('.') {
                Some((_, name)) => name,
                None => continue,
            };
            python.push((
                method.trim().trim_matches('"').to_string(),
                path.trim().trim_matches('"').to_string(),
                scope.to_string(),
            ));
        }
        assert_eq!(
            python.len(),
            SD_ALLOWED.len(),
            "Python has {} entries, Rust has {}",
            python.len(),
            SD_ALLOWED.len()
        );

        for (method, path, py_scope) in python {
            let rust_scope = sd_scope_for(&method, &path)
                .unwrap_or_else(|| panic!("{method} {path} is missing from the Rust table"));
            let expected = match py_scope.as_str() {
                "SD_GENERATE" => SCOPE_SD_GENERATE,
                "SD_QUERY" => SCOPE_SD_QUERY,
                "SD_ADMIN" => SCOPE_SD_ADMIN,
                other => panic!("unmapped Python scope {other} for {method} {path}"),
            };
            assert_eq!(rust_scope, expected, "scope differs for {method} {path}");
        }
    }
}

use std::net::SocketAddr;

use axum::{
    extract::{ConnectInfo, Request, State},
    http::{header, StatusCode},
    middleware::Next,
    response::{Html, IntoResponse, Response},
    Json,
};
use tower_sessions::Session;

use crate::auth::apikey;
use crate::auth::chain::{run_chain, ChainParams};
use crate::auth::client_ip::{resolve_client_ip, ClientIp};
use crate::auth::AuthContext;
use crate::pages;
use crate::state::SharedState;

fn is_api_auth_path(path: &str) -> bool {
    path.starts_with("/api/") || (path.starts_with("/ext/") && path.contains("/api/"))
}

/// Renders the unauthenticated PIN gate, gated on `pin_boss_login_ui` like
/// every other boss-gate wire-in site.
async fn boss_or_plain_pin_page(
    state: &SharedState,
    error: &str,
    next_url: &str,
    nonce: &str,
) -> Response {
    if state.config.pin_boss_login_ui {
        Html(
            crate::pages_boss::boss_gate_html(
                crate::pages_boss::BossMode::Pin,
                error,
                next_url,
                nonce,
            )
            .await,
        )
        .into_response()
    } else {
        Html(pages::pin_page(error, next_url)).into_response()
    }
}

/// axum middleware equivalent to Python's before_request check_auth.
///
/// Session は関数パラメータとして抽出せず request.extensions() 経由で参照する。
/// パラメータ抽出で Session を clone すると post_pin_check の Form 抽出と競合し
/// ハングする既知パターンを回避するため。
pub async fn auth_middleware(
    State(state): State<SharedState>,
    mut request: Request,
    next: Next,
) -> Response {
    // Resolve real client IP before the early-return so ClientIp extension is always
    // available to downstream handlers regardless of pin_auth_enabled.
    let tcp_ip = request
        .extensions()
        .get::<ConnectInfo<SocketAddr>>()
        .map(|ci| ci.0.ip().to_string())
        .unwrap_or_else(|| "unknown".to_string());
    let xff = request
        .headers()
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());
    let remote_addr = resolve_client_ip(
        &tcp_ip,
        xff.as_deref(),
        state.config.trusted_proxy_enabled,
        &state.config.trusted_ips,
    );
    request
        .extensions_mut()
        .insert(ClientIp(remote_addr.clone()));
    // LAN Cowork's pairing routes extract the identical resolved IP through
    // their own neutral extension type, so `routes::lan_cowork_pairing`
    // never names this module's `ClientIp` (S4b decoupling; see
    // `PeerSourceIp`'s doc).
    request
        .extensions_mut()
        .insert(crate::routes::lan_cowork_host::PeerSourceIp(
            remote_addr.clone(),
        ));

    let csp_nonce = request
        .extensions()
        .get::<crate::security::CspNonce>()
        .map(|n| n.0.clone())
        .unwrap_or_default();

    if !state.config.pin_auth_enabled {
        return next.run(request).await;
    }

    let path = request.uri().path().to_string();
    let method = request.method().as_str().to_string();

    let auth_header = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    let remote_user_header = request
        .headers()
        .get("x-remote-user")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    // Session は extensions から直接借用して pin_ok を読む（clone 不要）。
    let session_pin_ok: bool = {
        let s = request.extensions().get::<Session>().cloned();
        if let Some(s) = s {
            s.get::<bool>("pin_ok")
                .await
                .unwrap_or(None)
                .unwrap_or(false)
        } else {
            false
        }
    };

    let cookie_token = request
        .headers()
        .get(header::COOKIE)
        .and_then(|v| v.to_str().ok())
        .and_then(|s| {
            s.split(';').find_map(|part| {
                let p = part.trim();
                p.strip_prefix("pin_token=")
            })
        })
        .unwrap_or("")
        .to_string();

    let params = ChainParams {
        path: &path,
        method: &method,
        auth_header: &auth_header,
        is_locked: state.quick_lock.is_locked(),
        trusted_proxy_enabled: state.config.trusted_proxy_enabled,
        remote_addr: &remote_addr,
        tcp_peer: &tcp_ip,
        trusted_ips: &state.config.trusted_ips,
        trusted_peer_ips: &state.config.trusted_peer_ips,
        remote_user_header: &remote_user_header,
        session_pin_ok,
        cookie_token: &cookie_token,
        valid_token: &state.config.valid_token,
    };

    match run_chain(&params) {
        None => {
            // No check matched → unauthenticated.
            if is_api_auth_path(&path) {
                return (
                    StatusCode::UNAUTHORIZED,
                    Json(serde_json::json!({
                        "error": "認証が必要です",
                        "code": "pin_auth_required"
                    })),
                )
                    .into_response();
            }
            let next_url = if method == "GET" && path != "/" {
                path.clone()
            } else {
                String::new()
            };
            return boss_or_plain_pin_page(&state, "", &next_url, &csp_nonce).await;
        }
        Some(r) if !r.passed => {
            // Explicitly denied (quick_lock).
            if path.starts_with("/api/") {
                return (
                    StatusCode::from_u16(423).unwrap_or(StatusCode::FORBIDDEN),
                    Json(serde_json::json!({
                        "error": "locked",
                        "message": "アプリはロック中です"
                    })),
                )
                    .into_response();
            }
            if state.config.pin_boss_login_ui {
                return Html(
                    crate::pages_boss::boss_gate_html(
                        crate::pages_boss::BossMode::Lock,
                        "",
                        "",
                        &csp_nonce,
                    )
                    .await,
                )
                .into_response();
            }
            Html(pages::lock_page().to_string()).into_response()
        }
        Some(r) => {
            let mut reason = r.reason.clone();
            let mut scopes = None;
            if r.reason == "api_key_candidate" {
                let bearer = auth_header
                    .strip_prefix("Bearer ")
                    .map(str::trim)
                    .unwrap_or("");
                if let Some(key_info) = apikey::verify_key(&state.config.config_path, bearer) {
                    if !apikey::check_rate_limit(&key_info.id) {
                        return (
                            StatusCode::TOO_MANY_REQUESTS,
                            Json(serde_json::json!({
                                "ok": false,
                                "error": "Rate limit exceeded"
                            })),
                        )
                            .into_response();
                    }
                    if let Some(required_scope) = apikey::get_required_scope(&method, &path) {
                        if !apikey::key_has_scope(&key_info, required_scope) {
                            return (
                                StatusCode::FORBIDDEN,
                                Json(serde_json::json!({
                                    "ok": false,
                                    "error": format!("Insufficient scope: requires '{required_scope}'")
                                })),
                            )
                                .into_response();
                        }
                    }
                    reason = "api_key".to_string();
                    scopes = key_info.scopes;
                } else if path.starts_with("/api/gateway/") {
                    // Gateway routes are proxied; Python's gateway auth validates
                    // its separate token store.
                    reason = "gateway_candidate".to_string();
                } else if bearer.starts_with("internal_")
                    && (path.starts_with("/mcp") || path.starts_with("/api/mcp/"))
                {
                    // MCP internal tokens are Python-process-local and proxied;
                    // Python validates token value and loopback origin.
                    reason = "internal_candidate".to_string();
                } else if is_api_auth_path(&path) {
                    return (
                        StatusCode::UNAUTHORIZED,
                        Json(serde_json::json!({
                            "ok": false,
                            "error": "Invalid API key"
                        })),
                    )
                        .into_response();
                } else {
                    let next_url = if method == "GET" && path != "/" {
                        path.clone()
                    } else {
                        String::new()
                    };
                    return boss_or_plain_pin_page(&state, "", &next_url, &csp_nonce).await;
                }
            }
            // Promote cookie / trusted_proxy pass to session.
            if r.reason == "cookie" || r.reason == "trusted_proxy" {
                if let Some(s) = request.extensions().get::<Session>().cloned() {
                    let _ = s.insert("pin_ok", true).await;
                }
            }
            let mut request = request;
            request
                .extensions_mut()
                .insert(AuthContext { reason, scopes });
            next.run(request).await
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        collections::{HashMap, HashSet},
        fs,
        path::PathBuf,
        str::FromStr,
        sync::{Arc, Mutex},
        time::{SystemTime, UNIX_EPOCH},
    };

    use std::net::SocketAddr;

    use axum::{
        body::{to_bytes, Body},
        extract::ConnectInfo,
        middleware,
        response::Html,
        routing::get,
        Router,
    };
    use serde_json::{json, Value};
    use sha2::{Digest, Sha256};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tower::ServiceExt;

    use crate::{
        groups_index::GroupsIndexCache,
        routes::{collections, hailo_tagger},
        state::{AppState, Config, SharedState},
    };

    struct TestRoot {
        path: PathBuf,
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn test_root() -> TestRoot {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("yu-server-auth-middleware-{suffix}"));
        fs::create_dir_all(&path).unwrap();
        TestRoot { path }
    }

    fn hash_key(raw: &str) -> String {
        hex::encode(Sha256::digest(raw.as_bytes()))
    }

    fn write_config(
        root: &TestRoot,
        no_scope_key: &str,
        admin_key: &str,
        rate_key: &str,
    ) -> PathBuf {
        let config_path = root.path.join("config.json");
        fs::write(
            &config_path,
            json!({
                "api_keys": [
                    {
                        "id": "ak_no_scope",
                        "key_hash": hash_key(no_scope_key),
                        "key_prefix": &no_scope_key[..10],
                        "label": "No scope",
                        "created_at": 1,
                        "last_used_at": null
                    },
                    {
                        "id": "ak_admin",
                        "key_hash": hash_key(admin_key),
                        "key_prefix": &admin_key[..10],
                        "label": "Admin",
                        "created_at": 1,
                        "last_used_at": null,
                        "scopes": ["admin"]
                    },
                    {
                        "id": "ak_rate",
                        "key_hash": hash_key(rate_key),
                        "key_prefix": &rate_key[..10],
                        "label": "Rate",
                        "created_at": 1,
                        "last_used_at": null
                    }
                ]
            })
            .to_string(),
        )
        .unwrap();
        config_path
    }

    async fn test_state(root: &TestRoot, config_path: PathBuf) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE file_hailo_tags (
               id INTEGER PRIMARY KEY,
               file_id INTEGER NOT NULL,
               tag_name TEXT NOT NULL,
               confidence REAL NOT NULL,
               source TEXT NOT NULL DEFAULT 'hailo_remote',
               created_at INTEGER NOT NULL
             );
             CREATE TABLE collections (
               id INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               sort_order INTEGER NOT NULL DEFAULT 0,
               created_at INTEGER,
               query_json TEXT
             );
             CREATE TABLE favorites (
               file_id INTEGER NOT NULL,
               collection_id INTEGER NOT NULL
             );
             INSERT INTO file_hailo_tags(file_id, tag_name, confidence, source, created_at)
             VALUES (1, 'alpha', 0.9, 'hailo_remote', 10);
             INSERT INTO collections(id, name, sort_order, created_at, query_json)
             VALUES (1, 'default', 0, 10, NULL);",
        )
        .execute(&pool)
        .await
        .unwrap();

        Arc::new(AppState {
            effective_port: 5000,
            gateway_keys: Vec::new(),
            gateway_loopback_bypass: true,
            settings_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            infer_notify_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            scan_roots_generation: std::sync::atomic::AtomicU64::new(0),
            config: Config {
                db_path: "sqlite::memory:".to_string(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,

                pin_boss_login_ui: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                quick_lock_enabled: true,
                pin_auth_enabled: true,
                min_pin_length: 4,
                python_url: String::new(),
                config_path,
                project_root: root.path.clone(),
                app_config: json!({}),
                cache_dir: root.path.join("cache"),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                mcp_native: false,
                standalone: false,
                infer_standalone: true,
                active_profile: None,
                python_executable: String::new(),
            },
            db: pool.clone(),
            db_read: pool.clone(),
            vectors_db: pool.clone(),
            vectors_db_read: pool,
            clip_index: std::sync::Arc::new(
                crate::routes::clip_index::ClipIndex::new_default(std::env::temp_dir())
                    .expect("clip index test default"),
            ),
            clip_indexer: std::sync::Arc::new(crate::routes::clip_indexer::ClipIndexer::new()),
            caption_runner: std::sync::Arc::new(crate::routes::caption_runner::CaptionRunner::new()),
            s2t_runner: std::sync::Arc::new(crate::routes::s2t_runner::S2tRunner::new()),
            clip_runtime_cache: crate::state::TtlCache::new(crate::state::CLIP_RUNTIME_CACHE_TTL),
            inference_client: reqwest::Client::new(),
            python_client: reqwest::Client::new(),
            quick_lock: crate::auth::QuickLock::new(),
            rate_limiter: crate::auth::PinRateLimiter::new(),
            groups_index_cache: GroupsIndexCache::new(root.path.join("cache")),
            proxy_hits: Mutex::new(HashMap::new()),
            fleet_log_stream_connections: Mutex::new(HashMap::new()),
            sse_hub: Arc::new(crate::sse::SseHub::new()),
            job_manager: Arc::new(crate::jobs::JobManager::new()),
            watcher: Arc::new(crate::watcher::ScanWatcher::new()),
            log_ring: Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            mcp_sessions: Arc::new(crate::mcp::session::McpSessionStore::new(1000, 20, 256)),
            approval_gate: Mutex::new(crate::approval_gate::ApprovalGate::default()),
            env: minijinja::Environment::new(),
            dist_v: "dev".to_string(),
            version: "0.0.0".to_string(),
            start_time: std::time::Instant::now(),
            scheduler_state: std::sync::OnceLock::new(),
            wd_infer: std::sync::Arc::new(std::sync::Mutex::new(std::collections::HashMap::new())),
            infer_client: None,
            infer_child: None,
            scan_manager: std::sync::OnceLock::new(),
            hailo_yolo_stream: None,
            stats_basic_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_models_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_timeline_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_resolutions_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            checkpoints_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            server_info_stats_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
        })
    }

    fn app(state: SharedState) -> Router {
        Router::new()
            .route("/api/hailo-tagger/tags/{file_id}", get(hailo_tagger::tags))
            .route("/api/collections", get(collections::list))
            .route("/api/webhooks", get(crate::routes::webhook::list_webhooks))
            .route(
                "/ext/chatlog/api/conversations",
                get(crate::routes::chatlog::conversations),
            )
            .route(
                "/ext/auth-test/api/ping",
                get(|| async { Json(json!({"ok": true, "route": "ext-api"})) }),
            )
            .route(
                "/ext/auth-test/",
                get(|| async { Html("<main>extension page</main>") }),
            )
            .fallback(|| async { StatusCode::NOT_FOUND })
            .layer(middleware::from_fn_with_state(
                Arc::clone(&state),
                auth_middleware,
            ))
            .with_state(state)
    }

    fn peer() -> SocketAddr {
        "127.0.0.1:12345".parse().unwrap()
    }

    async fn get_json(app: Router, path: &str, bearer: &str) -> (StatusCode, Value) {
        let request = axum::http::Request::builder()
            .uri(path)
            .header(header::AUTHORIZATION, format!("Bearer {bearer}"))
            .extension(ConnectInfo(peer()))
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        let status = response.status();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let value = serde_json::from_slice(&body).unwrap_or(Value::Null);
        (status, value)
    }

    async fn get_json_without_auth(app: Router, path: &str) -> (StatusCode, Value) {
        let request = axum::http::Request::builder()
            .uri(path)
            .extension(ConnectInfo(peer()))
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        let status = response.status();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let value = serde_json::from_slice(&body).unwrap_or(Value::Null);
        (status, value)
    }

    async fn get_text_without_auth(app: Router, path: &str) -> (StatusCode, String) {
        let request = axum::http::Request::builder()
            .uri(path)
            .extension(ConnectInfo(peer()))
            .body(Body::empty())
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        let status = response.status();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let text = String::from_utf8(body.to_vec()).unwrap();
        (status, text)
    }

    #[tokio::test]
    async fn garbage_bearer_on_native_api_route_is_unauthorized() {
        let root = test_root();
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, value) = get_json(app(state), "/api/hailo-tagger/tags/1", "garbage").await;

        assert_eq!(status, StatusCode::UNAUTHORIZED);
        assert_eq!(value, json!({"ok": false, "error": "Invalid API key"}));
    }

    #[tokio::test]
    async fn unauthenticated_native_ext_api_route_is_unauthorized() {
        let root = test_root();
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, value) = get_json_without_auth(app(state), "/ext/auth-test/api/ping").await;

        assert_eq!(status, StatusCode::UNAUTHORIZED);
        assert_eq!(
            value,
            json!({"error": "認証が必要です", "code": "pin_auth_required"})
        );
    }

    #[tokio::test]
    async fn unauthenticated_webhook_and_chatlog_native_routes_are_unauthorized() {
        let root = test_root();
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;
        let app = app(state);

        for path in ["/api/webhooks", "/ext/chatlog/api/conversations"] {
            let (status, value) = get_json_without_auth(app.clone(), path).await;
            assert_eq!(status, StatusCode::UNAUTHORIZED);
            assert_eq!(
                value,
                json!({"error": "認証が必要です", "code": "pin_auth_required"})
            );
        }
    }

    #[tokio::test]
    async fn valid_bearer_passes_native_ext_api_route() {
        let root = test_root();
        let no_scope = "sk_11111111111111111111111111111111";
        let state = test_state(
            &root,
            write_config(
                &root,
                no_scope,
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, value) = get_json(app(state), "/ext/auth-test/api/ping", no_scope).await;

        assert_eq!(status, StatusCode::OK);
        assert_eq!(value, json!({"ok": true, "route": "ext-api"}));
    }

    #[tokio::test]
    async fn ext_page_route_is_not_api_gated() {
        let root = test_root();
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, text) = get_text_without_auth(app(state), "/ext/auth-test/").await;

        assert_eq!(status, StatusCode::OK);
        assert!(text.contains("PIN"));
        assert!(!text.contains("pin_auth_required"));
    }

    #[tokio::test]
    async fn valid_no_scope_key_can_read_native_get_route() {
        let root = test_root();
        let no_scope = "sk_11111111111111111111111111111111";
        let state = test_state(
            &root,
            write_config(
                &root,
                no_scope,
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, value) = get_json(app(state), "/api/hailo-tagger/tags/1", no_scope).await;

        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["tags"][0]["tag_name"], "alpha");
    }

    #[tokio::test]
    async fn valid_no_scope_key_is_denied_by_native_admin_route() {
        let root = test_root();
        let no_scope = "sk_11111111111111111111111111111111";
        let state = test_state(
            &root,
            write_config(
                &root,
                no_scope,
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, value) = get_json(app(state), "/api/collections", no_scope).await;

        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(
            value,
            json!({"ok": false, "error": "Insufficient scope: requires 'admin'"})
        );
    }

    #[tokio::test]
    async fn valid_admin_key_can_read_native_admin_route() {
        let root = test_root();
        let admin = "sk_22222222222222222222222222222222";
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                admin,
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, value) = get_json(app(state), "/api/collections", admin).await;

        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["collections"][0]["name"], "default");
    }

    #[tokio::test]
    async fn invalid_gateway_bearer_on_unknown_path_returns_404() {
        let root = test_root();
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;

        let (status, _) = get_json(app(state), "/api/gateway/x", "gateway-token").await;

        assert_ne!(status, StatusCode::UNAUTHORIZED); // auth 層を通過して 404 に到達している証跡
        assert_eq!(status, StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn valid_key_is_rate_limited_after_120_hits() {
        let root = test_root();
        let rate_key = "sk_33333333333333333333333333333333";
        apikey::reset_rate_limit_for_test("ak_rate");
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                "sk_22222222222222222222222222222222",
                rate_key,
            ),
        )
        .await;
        let app = app(state);

        for _ in 0..120 {
            let (status, _) = get_json(app.clone(), "/api/hailo-tagger/tags/1", rate_key).await;
            assert_eq!(status, StatusCode::OK);
        }
        let (status, value) = get_json(app, "/api/hailo-tagger/tags/1", rate_key).await;

        assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(value, json!({"ok": false, "error": "Rate limit exceeded"}));
        apikey::reset_rate_limit_for_test("ak_rate");
    }

    /// Regression guard for the boss-mode CSP-nonce wiring: exercises the
    /// real `security::layer` -> `get_pin_page` request path and proves the
    /// nonce inside `content-security-policy`'s `'nonce-XXXX'` token is the
    /// SAME value threaded into the rendered `<script nonce="XXXX">` tag. A
    /// future middleware-order or extension-type regression that breaks
    /// this wiring would silently break lock-mode unlock (the inline JS
    /// would be blocked by the strict `script-src 'strict-dynamic'` CSP).
    #[tokio::test]
    async fn pin_page_script_nonce_matches_csp_header_nonce() {
        let root = test_root();
        let state = test_state(
            &root,
            write_config(
                &root,
                "sk_11111111111111111111111111111111",
                "sk_22222222222222222222222222222222",
                "sk_33333333333333333333333333333333",
            ),
        )
        .await;
        // test_state() always yields a fresh Arc with refcount 1, so
        // try_unwrap cannot fail here.
        let mut inner_state =
            Arc::try_unwrap(state).unwrap_or_else(|_| panic!("state has more than one owner"));
        inner_state.config.pin_boss_login_ui = true;
        let state: SharedState = Arc::new(inner_state);

        let router = Router::new()
            .route("/_pin", get(crate::auth::routes::get_pin_page))
            .layer(middleware::from_fn(crate::security::layer))
            .with_state(state);

        let request = axum::http::Request::builder()
            .uri("/_pin")
            .body(Body::empty())
            .unwrap();
        let response = router.oneshot(request).await.unwrap();

        assert_eq!(response.status(), StatusCode::OK);

        let csp = response
            .headers()
            .get(axum::http::HeaderName::from_static(
                "content-security-policy",
            ))
            .expect("content-security-policy header present")
            .to_str()
            .unwrap()
            .to_string();
        let nonce = csp
            .split("'nonce-")
            .nth(1)
            .and_then(|rest| rest.split('\'').next())
            .expect("nonce-XXXX token present in csp header")
            .to_string();
        assert!(!nonce.is_empty());

        let body_bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let body = String::from_utf8(body_bytes.to_vec()).unwrap();

        let expected_script_tag = format!(r#"<script nonce="{nonce}">"#);
        assert!(
            body.contains(&expected_script_tag),
            "body did not contain {expected_script_tag:?}; csp nonce was {nonce:?}"
        );
        assert!(body.contains(r#"data-skin="wsj""#));
    }
}

use std::net::SocketAddr;

use axum::{
    extract::{ConnectInfo, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde_json::json;

use super::SseEvent;
use crate::state::SharedState;

/// POST `/_internal/sse-emit`
///
/// Accepts only loopback connections (ConnectInfo peer addr — XFF is not
/// trusted here per spec D_internal). Broadcasts each event to the SSE hub.
pub async fn handler(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(state): State<SharedState>,
    Json(events): Json<Vec<SseEvent>>,
) -> impl IntoResponse {
    if !addr.ip().is_loopback() {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"ok": false, "error": "local only"})),
        )
            .into_response();
    }
    for event in events {
        state.sse_hub.send(event);
    }
    (StatusCode::OK, Json(json!({"ok": true}))).into_response()
}

// ── helpers shared by emit + stream tests ─────────────────────────────────

#[cfg(test)]
pub(crate) mod test_helpers {
    use std::collections::HashMap;
    use std::collections::HashSet;
    use std::path::PathBuf;
    use std::sync::{Arc, Mutex};

    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;

    use crate::jobs::JobManager;
    use crate::logs::LogRingBuffer;
    use crate::sse::SseHub;
    use crate::state::{AppState, Config, SharedState};

    pub async fn make_state() -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
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
                db_path: String::new(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,

                pin_boss_login_ui: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                quick_lock_enabled: false,
                pin_auth_enabled: false,
                min_pin_length: 4,
                python_url: String::new(),
                config_path: PathBuf::from("config.json"),
                project_root: std::env::temp_dir(),
                app_config: serde_json::json!({}),
                cache_dir: std::env::temp_dir(),
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
            groups_index_cache: crate::groups_index::GroupsIndexCache::new(std::env::temp_dir()),
            proxy_hits: Mutex::new(HashMap::new()),
            fleet_log_stream_connections: Mutex::new(HashMap::new()),
            sse_hub: Arc::new(SseHub::new()),
            log_ring: Arc::new(LogRingBuffer::new(64)),
            mcp_sessions: Arc::new(crate::mcp::session::McpSessionStore::new(1000, 20, 256)),
            job_manager: Arc::new(JobManager::new()),
            watcher: Arc::new(crate::watcher::ScanWatcher::new()),
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
}

#[cfg(test)]
mod tests {
    use super::test_helpers::make_state;
    use super::*;

    use axum::{
        body::{to_bytes, Body},
        http::{Method, Request, StatusCode},
        routing::post,
        Router,
    };
    use serde_json::Value;
    use tower::Service;

    type Svc = axum::extract::connect_info::IntoMakeServiceWithConnectInfo<Router<()>, SocketAddr>;

    fn make_svc(state: SharedState) -> Svc {
        Router::new()
            .route("/_internal/sse-emit", post(handler))
            .with_state(state)
            .into_make_service_with_connect_info::<SocketAddr>()
    }

    async fn call(svc: &mut Svc, peer: SocketAddr, body: &str) -> (StatusCode, Value) {
        let conn_svc = svc.call(peer).await.unwrap();
        let req = Request::builder()
            .method(Method::POST)
            .uri("/_internal/sse-emit")
            .header("content-type", "application/json")
            .body(Body::from(body.to_string()))
            .unwrap();
        let resp = tower::ServiceExt::oneshot(conn_svc, req).await.unwrap();
        let status = resp.status();
        let bytes = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: Value = serde_json::from_slice(&bytes).unwrap_or(json!(null));
        (status, v)
    }

    #[tokio::test]
    async fn test_emit_loopback_accepted() {
        let state = make_state().await;
        let mut svc = make_svc(state);
        let peer: SocketAddr = "127.0.0.1:9999".parse().unwrap();
        let body = r#"[{"type":"test.evt","timestamp":1.0,"data":{},"source":"t"}]"#;
        let (status, v) = call(&mut svc, peer, body).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(v["ok"], true);
    }

    #[tokio::test]
    async fn test_emit_ipv6_loopback_accepted() {
        let state = make_state().await;
        let mut svc = make_svc(state);
        let peer: SocketAddr = "[::1]:9999".parse().unwrap();
        let body = r#"[{"type":"test.evt","timestamp":1.0,"data":{},"source":"t"}]"#;
        let (status, _) = call(&mut svc, peer, body).await;
        assert_eq!(status, StatusCode::OK);
    }

    #[tokio::test]
    async fn test_emit_non_loopback_rejected() {
        let state = make_state().await;
        let mut svc = make_svc(state);
        let peer: SocketAddr = "10.0.0.1:9999".parse().unwrap();
        let body = r#"[{"type":"test.evt","timestamp":1.0,"data":{},"source":"t"}]"#;
        let (status, v) = call(&mut svc, peer, body).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(v["ok"], false);
    }

    #[tokio::test]
    async fn test_emit_empty_array_ok() {
        let state = make_state().await;
        let mut svc = make_svc(state);
        let peer: SocketAddr = "127.0.0.1:9999".parse().unwrap();
        let (status, v) = call(&mut svc, peer, "[]").await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(v["ok"], true);
    }

    #[tokio::test]
    async fn test_emit_invalid_json_rejected() {
        let state = make_state().await;
        let mut svc = make_svc(state);
        let peer: SocketAddr = "127.0.0.1:9999".parse().unwrap();
        let (status, _) = call(&mut svc, peer, "not-json-at-all").await;
        assert!(
            status == StatusCode::UNPROCESSABLE_ENTITY || status == StatusCode::BAD_REQUEST,
            "expected 422 or 400, got {status}"
        );
    }

    #[tokio::test]
    async fn test_emit_broadcasts_to_subscriber() {
        let state = make_state().await;
        let mut rx = state.sse_hub.subscribe();
        let mut svc = make_svc(state);
        let peer: SocketAddr = "127.0.0.1:9999".parse().unwrap();
        let body =
            r#"[{"type":"scan.progress","timestamp":100.0,"data":{"pct":50},"source":"scanner"}]"#;
        let (status, _) = call(&mut svc, peer, body).await;
        assert_eq!(status, StatusCode::OK);
        let event = rx.try_recv().expect("event must be broadcast");
        assert_eq!(event.event_type, "scan.progress");
        assert_eq!(event.data["pct"], 50);
    }

    #[tokio::test]
    async fn test_emit_multiple_events_all_broadcast() {
        let state = make_state().await;
        let mut rx = state.sse_hub.subscribe();
        let mut svc = make_svc(state);
        let peer: SocketAddr = "127.0.0.1:9999".parse().unwrap();
        let body = r#"[
            {"type":"a","timestamp":1.0,"data":{},"source":"s"},
            {"type":"b","timestamp":2.0,"data":{},"source":"s"},
            {"type":"c","timestamp":3.0,"data":{},"source":"s"}
        ]"#;
        call(&mut svc, peer, body).await;
        let ev1 = rx.try_recv().unwrap();
        let ev2 = rx.try_recv().unwrap();
        let ev3 = rx.try_recv().unwrap();
        assert_eq!(ev1.event_type, "a");
        assert_eq!(ev2.event_type, "b");
        assert_eq!(ev3.event_type, "c");
    }
}

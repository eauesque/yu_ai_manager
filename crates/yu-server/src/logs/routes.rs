use std::convert::Infallible;
use std::net::{IpAddr, SocketAddr};
use std::sync::Arc;
use std::time::{Duration, Instant};

use axum::{
    extract::{ConnectInfo, Query, State},
    http::{header, HeaderValue, StatusCode},
    response::{
        sse::{Event, Sse},
        IntoResponse, Response,
    },
    Extension, Json,
};
use futures_util::stream;
use serde::Deserialize;
use serde_json::json;
use tokio::sync::broadcast::error::RecvError;

use crate::auth::{client_ip::ClientIp, scope::require_admin_scope, AuthContext};
use crate::state::SharedState;

use super::ring::{level_rank, LogRingBuffer};

#[derive(Debug, Deserialize)]
pub struct RecentParams {
    pub limit: Option<usize>,
    pub level: Option<String>,
    pub after_seq: Option<u64>,
}

/// GET `/api/logs/native/recent` — admin scope required.
pub async fn recent(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<RecentParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    let limit = params.limit.unwrap_or(200).min(2000);
    let entries = state
        .log_ring
        .recent(limit, params.level.as_deref(), params.after_seq);
    let count = entries.len();
    (
        StatusCode::OK,
        Json(json!({ "ok": true, "error": null, "entries": entries, "count": count })),
    )
        .into_response()
}

/// POST `/_internal/log` — loopback-only, outside auth middleware.
pub async fn internal_log(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(state): State<SharedState>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if !addr.ip().is_loopback() {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"ok": false, "error": "local only"})),
        )
            .into_response();
    }
    let level = body
        .get("level")
        .and_then(|v| v.as_str())
        .unwrap_or("INFO")
        .to_ascii_uppercase();
    let message = body
        .get("message")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let target = body
        .get("source")
        .and_then(|v| v.as_str())
        .unwrap_or("mcp_subprocess")
        .to_string();
    let mut fields = serde_json::Map::new();
    if let Some(obj) = body.as_object() {
        for (k, v) in obj {
            if !matches!(k.as_str(), "level" | "message" | "source") {
                fields.insert(k.clone(), v.clone());
            }
        }
    }
    state.log_ring.push(super::ring::PartialEntry {
        level,
        target,
        message,
        fields: if fields.is_empty() {
            None
        } else {
            Some(fields)
        },
    });
    (StatusCode::OK, Json(json!({"ok": true}))).into_response()
}

const MAX_STREAM_AGE_SECS: u64 = 3600;
const HEARTBEAT_SECS: u64 = 30;

struct LogConnectionGuard {
    ring: Arc<LogRingBuffer>,
    ip: IpAddr,
}

impl Drop for LogConnectionGuard {
    fn drop(&mut self) {
        self.ring.unregister_connection(self.ip);
    }
}

#[derive(Debug, Deserialize)]
pub struct StreamParams {
    pub level: Option<String>,
}

/// GET `/api/logs/native/stream` — admin scope + per-IP 3-connection limit.
pub async fn stream_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    resolved: Option<Extension<ClientIp>>,
    Query(params): Query<StreamParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    let ip: IpAddr = resolved
        .and_then(|Extension(ClientIp(s))| s.parse().ok())
        .unwrap_or_else(|| addr.ip());

    if !state.log_ring.register_connection(ip) {
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(json!({"ok": false, "error": "Too many log SSE connections"})),
        )
            .into_response();
    }

    let guard = LogConnectionGuard {
        ring: Arc::clone(&state.log_ring),
        ip,
    };
    let rx = state.log_ring.subscribe();
    let start = Instant::now();
    let min_rank = params
        .level
        .as_deref()
        .map(|l| level_rank(&l.to_ascii_uppercase()))
        .unwrap_or(0);

    let event_stream = stream::unfold(
        (rx, start, guard),
        move |(mut rx, start, guard)| async move {
            loop {
                let elapsed = start.elapsed();
                if elapsed >= Duration::from_secs(MAX_STREAM_AGE_SECS) {
                    return None;
                }
                let remaining = Duration::from_secs(MAX_STREAM_AGE_SECS).saturating_sub(elapsed);
                let timeout_dur = remaining.min(Duration::from_secs(HEARTBEAT_SECS));

                match tokio::time::timeout(timeout_dur, rx.recv()).await {
                    Err(_) => {
                        return Some((
                            Ok::<_, Infallible>(Event::default().comment("heartbeat")),
                            (rx, start, guard),
                        ));
                    }
                    Ok(Err(RecvError::Lagged(count))) => {
                        tracing::warn!(
                            client_ip = %ip,
                            "log SSE client lagged by {count} messages, disconnecting"
                        );
                        return None;
                    }
                    Ok(Err(RecvError::Closed)) => return None,
                    Ok(Ok(entry)) => {
                        if level_rank(&entry.level) < min_rank {
                            continue;
                        }
                        let data = serde_json::to_string(&entry).unwrap_or_default();
                        let ev = Event::default().event("log.entry").data(data);
                        return Some((Ok(ev), (rx, start, guard)));
                    }
                }
            }
        },
    );

    let mut resp = Sse::new(event_stream).into_response();
    resp.headers_mut()
        .insert("x-accel-buffering", HeaderValue::from_static("no"));
    resp.headers_mut()
        .insert(header::CONNECTION, HeaderValue::from_static("keep-alive"));
    resp
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures_util::StreamExt;

    async fn test_state() -> SharedState {
        let config = crate::state::Config {
            db_path: "sqlite::memory:".to_string(),
            pin_hash: String::new(),
            valid_token: String::new(),
            secret: String::new(),
            trusted_proxy_enabled: false,

            pin_boss_login_ui: false,
            trusted_ips: Default::default(),
            trusted_peer_ips: Default::default(),
            quick_lock_enabled: false,
            pin_auth_enabled: false,
            min_pin_length: 4,
            python_url: String::new(),
            standalone: true,
            infer_standalone: true,
            active_profile: None,
            python_executable: String::new(),
            config_path: std::path::PathBuf::from("config.json"),
            project_root: std::path::PathBuf::from("."),
            app_config: serde_json::json!({}),
            cache_dir: std::path::PathBuf::from("."),
            server_mode: "full".to_string(),
            headless: false,
            safe_mode: false,
            mcp_native: false,
        };
        let db = sqlx::pool::Pool::connect_lazy("sqlite::memory:").unwrap();
        let db_read = sqlx::pool::Pool::connect_lazy("sqlite::memory:").unwrap();
        let log_ring = Arc::new(LogRingBuffer::new(8));
        Arc::new(crate::state::AppState::new(config, db, db_read, log_ring).await)
    }

    /// Regression test: the frontend (`logs-tab.ts`) listens for the SSE
    /// event name `log.entry`, matching the legacy Python implementation in
    /// `routes/logs_api.py`. A prior Rust port used `event("log")` instead,
    /// which silently broke the log viewer since `EventSource.addEventListener`
    /// only fires on an exact event-name match.
    #[tokio::test]
    async fn stream_emits_log_entry_event_name() {
        let state = test_state().await;
        let addr: SocketAddr = "127.0.0.1:0".parse().unwrap();

        let resp = stream_handler(
            State(state.clone()),
            None,
            ConnectInfo(addr),
            None,
            Query(StreamParams { level: None }),
        )
        .await;

        state.log_ring.push(super::super::ring::PartialEntry {
            level: "WARN".to_string(),
            target: "sqlx::query".to_string(),
            message: "slow statement".to_string(),
            fields: None,
        });

        let mut body_stream = resp.into_body().into_data_stream();
        let chunk = tokio::time::timeout(Duration::from_secs(5), body_stream.next())
            .await
            .expect("timed out waiting for SSE frame")
            .expect("stream ended without emitting a frame")
            .expect("body stream yielded an error");
        let text = String::from_utf8_lossy(&chunk);
        assert!(
            text.contains("event: log.entry"),
            "expected SSE frame to use event name 'log.entry', got: {text:?}"
        );
    }
}

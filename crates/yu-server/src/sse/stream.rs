use std::collections::HashSet;
use std::convert::Infallible;
use std::net::{IpAddr, SocketAddr};
use std::sync::Arc;
use std::time::{Duration, Instant};

use axum::response::sse::{Event, Sse};
use axum::{
    extract::{ConnectInfo, Query, State},
    http::{header, HeaderValue},
    response::{IntoResponse, Response},
    Json,
};
use futures_util::stream;
use serde::Deserialize;
use serde_json::json;
use tokio::sync::broadcast::error::RecvError;

use super::{SseHub, HEARTBEAT_SECS, MAX_STREAM_AGE_SECS};
use crate::state::SharedState;

/// Calls `unregister_connection` when dropped — covers both graceful stream
/// termination and abrupt client disconnect (future cancelled by axum/hyper).
struct ConnectionGuard {
    hub: Arc<SseHub>,
    ip: IpAddr,
}

impl Drop for ConnectionGuard {
    fn drop(&mut self) {
        self.hub.unregister_connection(self.ip);
    }
}

#[derive(Debug, Deserialize)]
pub struct StreamParams {
    /// Comma-separated event type filter. Empty/absent = all types.
    pub types: Option<String>,
    /// Received and ignored per spec D6 (?auth=廃止).
    #[allow(dead_code)]
    pub auth: Option<String>,
}

/// GET `/api/events/stream`
///
/// Auth-protected (handled by middleware layer). This handler itself only
/// enforces the per-IP connection limit.
pub async fn handler(
    State(state): State<SharedState>,
    Query(params): Query<StreamParams>,
    headers: axum::http::HeaderMap,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
) -> Response {
    // Per-IP limit uses XFF-first (resource management, not security boundary).
    let ip: IpAddr = headers
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.split(',').next())
        .map(str::trim)
        .and_then(|s| s.parse::<IpAddr>().ok())
        .unwrap_or_else(|| addr.ip());

    if !state.sse_hub.register_connection(ip) {
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(json!({"ok": false, "error": "Too many SSE connections"})),
        )
            .into_response();
    }

    let type_filter: Option<HashSet<String>> =
        params.types.as_deref().filter(|s| !s.is_empty()).map(|s| {
            s.split(',')
                .filter(|p| !p.is_empty())
                .map(String::from)
                .collect()
        });

    let guard = ConnectionGuard {
        hub: Arc::clone(&state.sse_hub),
        ip,
    };
    let hub_for_stream = Arc::clone(&state.sse_hub);
    let rx = state.sse_hub.subscribe();
    let start = Instant::now();

    let event_stream = stream::unfold(
        (rx, type_filter, start, guard),
        move |(mut rx, type_filter, start, guard)| {
            let hub = Arc::clone(&hub_for_stream);
            async move {
                loop {
                    let elapsed = start.elapsed();
                    if elapsed >= Duration::from_secs(MAX_STREAM_AGE_SECS) {
                        // guard drops here → unregister_connection
                        return None;
                    }
                    let remaining =
                        Duration::from_secs(MAX_STREAM_AGE_SECS).saturating_sub(elapsed);
                    let timeout_dur = remaining.min(Duration::from_secs(HEARTBEAT_SECS));

                    match tokio::time::timeout(timeout_dur, rx.recv()).await {
                        Err(_timeout) => {
                            let ev = Event::default().comment("heartbeat");
                            return Some((
                                Ok::<_, Infallible>(ev),
                                (rx, type_filter, start, guard),
                            ));
                        }
                        Ok(Err(RecvError::Lagged(count))) => {
                            tracing::warn!(
                                client_ip = %ip,
                                "SSE client lagged by {} messages, disconnecting", count
                            );
                            hub.inc_lagged();
                            // guard drops here → unregister_connection
                            return None;
                        }
                        Ok(Err(RecvError::Closed)) => {
                            // guard drops here → unregister_connection
                            return None;
                        }
                        Ok(Ok(sse_event)) => {
                            if let Some(ref filter) = type_filter {
                                if !filter.contains(&sse_event.event_type) {
                                    continue;
                                }
                            }
                            let data = serde_json::to_string(&*sse_event).unwrap_or_default();
                            let ev = Event::default()
                                .event(sse_event.event_type.clone())
                                .data(data);
                            return Some((Ok(ev), (rx, type_filter, start, guard)));
                        }
                    }
                }
            }
        },
    );

    let mut resp = Sse::new(event_stream).into_response();
    // axum already sets Content-Type and Cache-Control; add nginx/proxy headers.
    resp.headers_mut()
        .insert("x-accel-buffering", HeaderValue::from_static("no"));
    resp.headers_mut()
        .insert(header::CONNECTION, HeaderValue::from_static("keep-alive"));
    resp
}

use axum::http::StatusCode;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sse::emit::test_helpers::make_state;
    use crate::sse::MAX_SSE_PER_IP;
    use axum::{
        body::{to_bytes, Body},
        http::{Method, Request, StatusCode},
        routing::get,
        Router,
    };
    use std::net::SocketAddr;
    use tower::ServiceExt;

    fn make_app(state: crate::state::SharedState) -> Router {
        Router::new()
            .route("/api/events/stream", get(handler))
            .with_state(state)
    }

    fn req_with_peer(uri: &str, peer: SocketAddr) -> Request<Body> {
        let (mut parts, body) = Request::builder()
            .method(Method::GET)
            .uri(uri)
            .body(Body::empty())
            .unwrap()
            .into_parts();
        parts.extensions.insert(ConnectInfo(peer));
        Request::from_parts(parts, body)
    }

    #[tokio::test]
    async fn test_stream_returns_sse_content_type() {
        let state = make_state().await;
        let app = make_app(state);
        let peer: SocketAddr = "127.0.0.1:1234".parse().unwrap();
        let resp = app
            .oneshot(req_with_peer("/api/events/stream", peer))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let ct = resp
            .headers()
            .get("content-type")
            .unwrap()
            .to_str()
            .unwrap();
        assert!(ct.contains("text/event-stream"), "unexpected: {ct}");
    }

    #[tokio::test]
    async fn test_stream_auth_param_ignored() {
        let state = make_state().await;
        let app = make_app(state);
        let peer: SocketAddr = "127.0.0.1:1234".parse().unwrap();
        // ?auth= must not cause an error (D6: ignored)
        let resp = app
            .oneshot(req_with_peer(
                "/api/events/stream?auth=some_invalid_token",
                peer,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_stream_429_when_over_limit() {
        let state = make_state().await;
        let ip: IpAddr = "10.0.0.99".parse().unwrap();
        // Fill up the limit
        for _ in 0..MAX_SSE_PER_IP {
            state.sse_hub.register_connection(ip);
        }
        let app = make_app(state);
        let peer: SocketAddr = "10.0.0.99:1234".parse().unwrap();
        let resp = app
            .oneshot(req_with_peer("/api/events/stream", peer))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
        let body = to_bytes(resp.into_body(), 512).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["ok"], false);
    }

    #[tokio::test]
    async fn test_stream_xff_used_for_limit() {
        let state = make_state().await;
        let xff_ip: IpAddr = "172.16.0.1".parse().unwrap();
        for _ in 0..MAX_SSE_PER_IP {
            state.sse_hub.register_connection(xff_ip);
        }
        let app = make_app(state);
        // Peer addr is 127.0.0.1 (loopback) but XFF says 172.16.0.1 (full)
        let (mut parts, body) = Request::builder()
            .method(Method::GET)
            .uri("/api/events/stream")
            .header("x-forwarded-for", "172.16.0.1")
            .body(Body::empty())
            .unwrap()
            .into_parts();
        parts
            .extensions
            .insert(ConnectInfo::<SocketAddr>("127.0.0.1:1234".parse().unwrap()));
        let req = Request::from_parts(parts, body);
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
    }

    #[tokio::test]
    async fn hub_register_connection_counts_per_ip() {
        // Named for what it actually asserts. It previously read
        // `test_stream_connection_count_incremented` and opened with
        // `let _ = app.oneshot(...)` — a future that was dropped without ever
        // being awaited, so the stream never ran and the name claimed coverage
        // the body did not provide. End-to-end registration through
        // `/api/events/stream` is still uncovered here.
        let state = make_state().await;
        let hub = Arc::clone(&state.sse_hub);
        let ip: IpAddr = "127.0.0.1".parse().unwrap();
        hub.register_connection(ip);
        assert_eq!(hub.connection_count(ip), 1);
    }

    // ── Unit tests for type filter logic ────────────────────────────────────

    #[test]
    fn test_type_filter_all_types_when_absent() {
        // None filter = accept all
        let filter: Option<HashSet<String>> = None;
        let event_type = "scan.progress";
        let passes = filter
            .as_ref()
            .map(|f| f.contains(event_type))
            .unwrap_or(true);
        assert!(passes);
    }

    #[test]
    fn test_type_filter_blocks_non_matching() {
        let filter: Option<HashSet<String>> = Some(
            ["job.done", "job.error"]
                .iter()
                .map(|s| s.to_string())
                .collect(),
        );
        let passes_job = filter
            .as_ref()
            .map(|f| f.contains("job.done"))
            .unwrap_or(true);
        let passes_scan = filter
            .as_ref()
            .map(|f| f.contains("scan.progress"))
            .unwrap_or(true);
        assert!(passes_job);
        assert!(!passes_scan);
    }

    #[test]
    fn test_sse_heartbeat_frame_format() {
        // comment("heartbeat") sets the SSE comment field
        let ev = Event::default().comment("heartbeat");
        let formatted = format!("{ev:?}");
        assert!(
            formatted.contains("heartbeat"),
            "heartbeat comment not found in Event debug: {formatted:?}"
        );
    }

    #[test]
    fn test_sse_event_frame_has_event_and_data_fields() {
        let ev = Event::default()
            .event("scan.progress")
            .data(r#"{"pct":50}"#);
        let formatted = format!("{ev:?}");
        assert!(
            formatted.contains("scan.progress"),
            "event name not found in Event debug: {formatted:?}"
        );
        assert!(
            formatted.contains("pct"),
            "data not found in Event debug: {formatted:?}"
        );
    }
}

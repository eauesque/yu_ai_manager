use axum::{extract::State, response::IntoResponse, Json};
use serde_json::json;

use crate::state::SharedState;

/// GET `/api/events/info`
///
/// Phase 1: returns the Python-compatible fallback shape.
/// Phase 2b: will return `dedicated_server: true` once the Rust SSE hub is
/// the active cutover.
pub async fn handler(State(_state): State<SharedState>) -> impl IntoResponse {
    Json(json!({
        "sse_port": null,
        "dedicated_server": false,
        "stream_url": null,
        "expires_at": null,
        "refresh_after": null
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sse::emit::test_helpers::make_state;
    use axum::body::Body;
    use axum::{
        body::to_bytes,
        http::{Request, StatusCode},
        routing::get,
        Router,
    };
    use serde_json::Value;
    use tower::ServiceExt;

    #[tokio::test]
    async fn test_info_returns_fallback_shape() {
        let state = make_state().await;
        let app = Router::new()
            .route("/api/events/info", get(handler))
            .with_state(state);
        let req = Request::builder()
            .uri("/api/events/info")
            .body(Body::empty())
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let bytes = to_bytes(resp.into_body(), 512).await.unwrap();
        let v: Value = serde_json::from_slice(&bytes).unwrap();
        assert!(v["sse_port"].is_null(), "sse_port must be null");
        assert_eq!(v["dedicated_server"], false);
        assert!(v["stream_url"].is_null(), "stream_url must be null");
        assert!(v["expires_at"].is_null(), "expires_at must be null");
        assert!(v["refresh_after"].is_null(), "refresh_after must be null");
    }

    #[tokio::test]
    async fn test_info_content_type_json() {
        let state = make_state().await;
        let app = Router::new()
            .route("/api/events/info", get(handler))
            .with_state(state);
        let req = Request::builder()
            .uri("/api/events/info")
            .body(Body::empty())
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        let ct = resp
            .headers()
            .get("content-type")
            .unwrap()
            .to_str()
            .unwrap();
        assert!(ct.contains("application/json"), "unexpected: {ct}");
    }
}

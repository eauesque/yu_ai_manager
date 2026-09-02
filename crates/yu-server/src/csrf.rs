use axum::{
    extract::Request,
    http::{Method, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

/// Middleware: CSRF protection for mutating /api/ and /ext/ endpoints.
///
/// Runs before session/auth resolution; checks raw request headers directly.
/// Mirrors Python's `core/web/request_hooks.py::_check_csrf_header`.
///
/// Pass conditions (any one):
/// 1. Authorization: Bearer ... header present (API key — CSRF exempt per arch-constraints)
/// 2. X-Requested-With header present (browser fetch interceptor auto-injects this)
/// 3. Path starts with /api/events/ (SSE — CSRF exempt)
/// 4. Path starts with /api/webhooks/receive/ (external webhook receiver, HMAC-authenticated)
/// 5. Path matches /ext/<name>/v1/* (OpenAI-compatible extension endpoints —
///    rely on trusted_peer / API-key auth instead)
///
/// Applies to: POST / PUT / PATCH / DELETE where path starts with /api/ or /ext/.
/// Other methods and out-of-scope paths pass unconditionally.
pub async fn layer(request: Request, next: Next) -> Response {
    let method = request.method().clone();
    let path = request.uri().path().to_owned();

    let is_mutating = matches!(
        method,
        Method::POST | Method::PUT | Method::PATCH | Method::DELETE
    );
    let in_scope = path.starts_with("/api/") || path.starts_with("/ext/");
    let exempt_path = path.starts_with("/api/events/")
        || path.starts_with("/api/webhooks/receive/")
        || is_ext_v1_path(&path);

    let needs_check = is_mutating && in_scope && !exempt_path;

    if needs_check {
        let headers = request.headers();
        let has_bearer = headers
            .get("authorization")
            .and_then(|v| v.to_str().ok())
            .map(|v| v.starts_with("Bearer "))
            .unwrap_or(false);
        let has_xrw = headers.contains_key("x-requested-with");

        if !has_bearer && !has_xrw {
            return (
                StatusCode::FORBIDDEN,
                Json(json!({"ok": false, "error": "csrf_required"})),
            )
                .into_response();
        }
    }

    next.run(request).await
}

/// Matches Python's `_CSRF_EXEMPT_EXT_V1_RE = re.compile(r"^/ext/[A-Za-z0-9][\w\-]*/v1/")`:
/// an extension name (first char alphanumeric, rest alphanumeric/`_`/`-`) followed by `/v1/`.
fn is_ext_v1_path(path: &str) -> bool {
    let Some(rest) = path.strip_prefix("/ext/") else {
        return false;
    };
    let Some(slash_idx) = rest.find('/') else {
        return false;
    };
    let name = &rest[..slash_idx];
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if !first.is_ascii_alphanumeric() {
        return false;
    }
    if !chars.all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-') {
        return false;
    }
    rest[slash_idx + 1..].starts_with("v1/")
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, middleware, routing::post, Router};
    use tower::ServiceExt;

    fn app() -> Router {
        Router::new()
            .route("/api/test", post(|| async { "ok" }))
            .route("/api/events/stream", post(|| async { "sse" }))
            .route(
                "/api/webhooks/receive/{token}",
                post(|| async { "webhook" }),
            )
            .route("/ext/my-ext/api/things", post(|| async { "ext" }))
            .route(
                "/ext/lan_cowork/api/settings/fleet",
                post(|| async { "fleet" }),
            )
            .route(
                "/ext/my-ext/v1/chat/completions",
                post(|| async { "ext-v1" }),
            )
            .route("/health", post(|| async { "health" }))
            .layer(middleware::from_fn(super::layer))
    }

    async fn status(method: Method, path: &str, headers: Vec<(&str, &str)>) -> StatusCode {
        let mut builder = axum::http::Request::builder().method(method).uri(path);
        for (k, v) in headers {
            builder = builder.header(k, v);
        }
        let req = builder.body(Body::empty()).unwrap();
        app().oneshot(req).await.unwrap().status()
    }

    #[tokio::test]
    async fn post_api_without_csrf_is_403() {
        assert_eq!(
            status(Method::POST, "/api/test", vec![]).await,
            StatusCode::FORBIDDEN
        );
    }

    #[tokio::test]
    async fn post_api_with_xrw_passes() {
        assert_eq!(
            status(
                Method::POST,
                "/api/test",
                vec![("x-requested-with", "XMLHttpRequest")]
            )
            .await,
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn post_api_with_bearer_passes() {
        assert_eq!(
            status(
                Method::POST,
                "/api/test",
                vec![("authorization", "Bearer token123")]
            )
            .await,
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn get_api_passes_without_csrf() {
        let req = axum::http::Request::builder()
            .method(Method::GET)
            .uri("/api/test")
            .body(Body::empty())
            .unwrap();
        // GET は対象外（RouterはGETを登録していないが、layer自体は通過する）
        // layer が 403 を返さないことを確認（router は 405 を返す）
        let resp = app().oneshot(req).await.unwrap();
        assert_ne!(resp.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn post_events_sse_passes_without_csrf() {
        assert_eq!(
            status(Method::POST, "/api/events/stream", vec![]).await,
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn post_non_api_passes_without_csrf() {
        assert_eq!(
            status(Method::POST, "/health", vec![]).await,
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn post_webhook_receive_passes_without_csrf() {
        assert_eq!(
            status(Method::POST, "/api/webhooks/receive/tok123", vec![]).await,
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn post_ext_without_csrf_is_403() {
        assert_eq!(
            status(Method::POST, "/ext/my-ext/api/things", vec![]).await,
            StatusCode::FORBIDDEN
        );
    }

    #[tokio::test]
    async fn post_fleet_settings_without_csrf_is_403() {
        assert_eq!(
            status(Method::POST, "/ext/lan_cowork/api/settings/fleet", vec![],).await,
            StatusCode::FORBIDDEN
        );
    }

    #[tokio::test]
    async fn post_ext_with_xrw_passes() {
        assert_eq!(
            status(
                Method::POST,
                "/ext/my-ext/api/things",
                vec![("x-requested-with", "XMLHttpRequest")]
            )
            .await,
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn post_ext_v1_passes_without_csrf() {
        assert_eq!(
            status(Method::POST, "/ext/my-ext/v1/chat/completions", vec![]).await,
            StatusCode::OK
        );
    }

    #[test]
    fn is_ext_v1_path_matches_python_regex_semantics() {
        assert!(is_ext_v1_path("/ext/my-ext/v1/chat/completions"));
        assert!(is_ext_v1_path("/ext/a1/v1/"));
        assert!(!is_ext_v1_path("/ext/my-ext/api/things"));
        assert!(!is_ext_v1_path("/ext//v1/"));
        assert!(!is_ext_v1_path("/ext/-leading-dash/v1/"));
        assert!(!is_ext_v1_path("/api/v1/"));
        assert!(!is_ext_v1_path("/ext/my-ext"));
    }
}

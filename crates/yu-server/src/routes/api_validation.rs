//! The one validation-error response shape, mirroring Python.
//!
//! `core/infra_core/api_request.py::validate_json_model` joins every error with "; ",
//! sets `code` to `validation_error`, and puts the COUNT in `detail`. `api_result` then
//! wraps it, so `ok: false` sits beside them.
//!
//! This lives here rather than in each route file because it already existed three
//! times in the tree, in three states of correctness: `routes/ratings.rs` had it right
//! (after v4.732.12 measured `detail`), `routes/analysis_servers.rs` had part of it, and
//! the analysis `discovered/*` handlers had their own `{"success": false, …}` instead --
//! which is a different contract for the same condition, measured at 400/400 against
//! Python in v4.734.5.

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

/// One validation error.
pub fn api_validation_error(message: &str) -> Response {
    api_validation_errors(&[message.to_string()])
}

/// Every validation error at once, counted.
///
/// `detail` must report the real count: hardcoding "1 validation error(s)" was false
/// whenever more than one field was wrong, and that is exactly what the un-suppressed
/// body comparison on POST /api/ratings/batch-set exposed (v4.732.12).
pub fn api_validation_errors(messages: &[String]) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({
            "ok": false,
            "error": messages.join("; "),
            "code": "validation_error",
            "detail": format!("{} validation error(s)", messages.len()),
        })),
    )
        .into_response()
}

/// Mirror of `require_json_dict` (core/infra_core/api_request.py:10-19).
///
/// Three distinct 400s, each with its own `code`, and Python reaches model validation
/// only after all three pass. A handler that treats an ABSENT body as `{}` answers the
/// validation error instead -- the right shape for the wrong condition, which is what
/// the two discovery DELETEs were measured doing (v4.734.5).
pub fn require_json_body(
    headers: &axum::http::HeaderMap,
    body: &[u8],
) -> Result<serde_json::Value, Response> {
    let is_json = headers
        .get(axum::http::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|ct| {
            let ct = ct
                .split(';')
                .next()
                .unwrap_or("")
                .trim()
                .to_ascii_lowercase();
            ct == "application/json" || ct.ends_with("+json")
        });
    if !is_json {
        return Err(json_error("JSON body is required", "invalid_content_type"));
    }
    let value: serde_json::Value = match serde_json::from_slice(body) {
        Ok(v) => v,
        Err(_) => return Err(json_error("Invalid JSON body", "invalid_json")),
    };
    if !value.is_object() {
        return Err(json_error(
            "JSON object body is required",
            "invalid_json_object",
        ));
    }
    Ok(value)
}

/// `api_result` puts `ok: false` beside the error payload; there is no `detail` on
/// these, unlike a validation error.
fn json_error(message: &str, code: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn detail_counts_the_errors_rather_than_saying_one() {
        // The regression v4.732.12 measured: two errors must not report "1".
        let body = response_body(api_validation_errors(&[
            "a: Field required".to_string(),
            "b: Field required".to_string(),
        ]))
        .await;
        assert_eq!(body["detail"], "2 validation error(s)");
        assert_eq!(body["error"], "a: Field required; b: Field required");
        assert_eq!(body["code"], "validation_error");
        assert_eq!(body["ok"], false);
        // `success` is Python-absent: a key invented here would differ from Python
        // in the other direction.
        assert!(body.get("success").is_none());
    }

    #[tokio::test]
    async fn a_single_error_says_one() {
        let body = response_body(api_validation_error("base_url: Field required")).await;
        assert_eq!(body["detail"], "1 validation error(s)");
        assert_eq!(body["error"], "base_url: Field required");
    }

    #[tokio::test]
    async fn require_json_body_mirrors_pythons_three_refusals() {
        use axum::http::{header, HeaderMap, HeaderValue};

        // No content-type: Python never looks at the body.
        let empty = HeaderMap::new();
        let err = require_json_body(&empty, b"{}").unwrap_err();
        let body = response_body(err).await;
        assert_eq!(body["code"], "invalid_content_type");
        assert_eq!(body["error"], "JSON body is required");
        assert_eq!(body["ok"], false);
        // Not a validation error: no `detail`.
        assert!(body.get("detail").is_none());

        let mut json_headers = HeaderMap::new();
        json_headers.insert(
            header::CONTENT_TYPE,
            HeaderValue::from_static("application/json; charset=utf-8"),
        );
        // Unparsable.
        let body = response_body(require_json_body(&json_headers, b"{oops").unwrap_err()).await;
        assert_eq!(body["code"], "invalid_json");
        // Parsable but not an object.
        let body = response_body(require_json_body(&json_headers, b"[1,2]").unwrap_err()).await;
        assert_eq!(body["code"], "invalid_json_object");
        // A real object passes, charset parameter and all.
        assert!(require_json_body(&json_headers, b"{\"a\":1}").is_ok());
    }

    async fn response_body(resp: Response) -> serde_json::Value {
        let bytes = axum::body::to_bytes(resp.into_body(), 64 * 1024)
            .await
            .expect("body");
        serde_json::from_slice(&bytes).expect("json")
    }
}

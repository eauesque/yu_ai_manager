use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{Map, Value};

/// Mirrors Python `api_error` (core/infra_core/api_errors.py:35-37): the
/// envelope always carries `ok: false` alongside `error`, before any
/// caller-supplied `extra` keys are merged in.
pub(crate) fn error_body(message: &str, extra: Value) -> Value {
    let mut body = Map::from_iter([
        ("ok".to_string(), Value::Bool(false)),
        ("error".to_string(), Value::String(message.to_string())),
    ]);
    if let Value::Object(extra) = extra {
        body.extend(extra);
    }
    Value::Object(body)
}

pub(crate) fn api_error(message: &str, status: StatusCode, extra: Value) -> Response {
    (status, Json(error_body(message, extra))).into_response()
}

pub(crate) fn api_error_code(message: &str, code: Option<&str>, status: StatusCode) -> Response {
    let extra = code.map_or_else(
        || Value::Object(Map::new()),
        |code| {
            Value::Object(Map::from_iter([(
                "code".to_string(),
                Value::String(code.to_string()),
            )]))
        },
    );
    api_error(message, status, extra)
}

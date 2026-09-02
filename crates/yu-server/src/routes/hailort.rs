use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    infer_client::InferClient,
    state::SharedState,
};

const MAX_TEXT_BYTES: usize = 16 * 1024;
const MAX_PROMPT_BYTES: usize = 16 * 1024;
const MAX_TIMEOUT_MS: u32 = 120_000;

#[derive(Debug, Deserialize)]
pub struct HefQuery {
    hef_path: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct TokenizeRequest {
    hef_path: Option<String>,
    text: String,
}

#[derive(Debug, Deserialize)]
pub struct LlmGenerateRequest {
    hef_path: Option<String>,
    prompt: String,
    timeout_ms: Option<u32>,
}

fn api_ok(data: Value) -> Response {
    Json(json!({"ok": true, "error": null, "data": data})).into_response()
}

fn api_error(status: StatusCode, code: &'static str, message: String) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": code, "message": message})),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn validate_text_len(text: &str) -> Option<Response> {
    if text.len() > MAX_TEXT_BYTES {
        return Some(api_error(
            StatusCode::PAYLOAD_TOO_LARGE,
            "text_too_large",
            format!("text exceeds {MAX_TEXT_BYTES} bytes"),
        ));
    }
    None
}

fn infer_client_unavailable() -> Response {
    api_error(
        StatusCode::SERVICE_UNAVAILABLE,
        "hailo_inference_unavailable",
        "Hailo inference unavailable".to_string(),
    )
}

fn infer_client_error(error: crate::infer_client::InferClientError) -> Response {
    match error {
        crate::infer_client::InferClientError::BadStatus { status, body } => {
            tracing::error!("yu-infer returned status {status}: {body}");
            api_error(
                StatusCode::from_u16(status).unwrap_or(StatusCode::BAD_GATEWAY),
                "hailo_inference_failed",
                body,
            )
        }
        error => {
            tracing::error!("yu-infer request failed: {error}");
            api_error(
                StatusCode::BAD_GATEWAY,
                "hailo_inference_failed",
                error.to_string(),
            )
        }
    }
}

async fn call_infer_client(
    _infer_client: &InferClient,
    call: impl std::future::Future<Output = Result<Value, crate::infer_client::InferClientError>>,
) -> Response {
    match call.await {
        Ok(value) => api_ok(value),
        Err(error) => infer_client_error(error),
    }
}

pub async fn yolo_metadata(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(query): Query<HefQuery>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return infer_client_unavailable();
    };
    call_infer_client(
        infer_client,
        infer_client.infer_yolo_metadata(query.hef_path),
    )
    .await
}

pub async fn yolo_smoke_zero(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(query): Query<HefQuery>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return infer_client_unavailable();
    };
    call_infer_client(
        infer_client,
        infer_client.infer_yolo_smoke_zero(query.hef_path),
    )
    .await
}

pub async fn speech2text_tokenize(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<TokenizeRequest>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = validate_text_len(&body.text) {
        return response;
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return infer_client_unavailable();
    };
    call_infer_client(
        infer_client,
        infer_client.speech2text_tokenize(body.hef_path, body.text),
    )
    .await
}

pub async fn llm_tokenize(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<TokenizeRequest>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = validate_text_len(&body.text) {
        return response;
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return infer_client_unavailable();
    };
    call_infer_client(
        infer_client,
        infer_client.llm_tokenize(body.hef_path, body.text),
    )
    .await
}

pub async fn llm_generate(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<LlmGenerateRequest>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if body.prompt.len() > MAX_PROMPT_BYTES {
        return api_error(
            StatusCode::PAYLOAD_TOO_LARGE,
            "prompt_too_large",
            format!("prompt exceeds {MAX_PROMPT_BYTES} bytes"),
        );
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return infer_client_unavailable();
    };
    call_infer_client(
        infer_client,
        infer_client.llm_generate(
            body.hef_path,
            body.prompt,
            Some(
                body.timeout_ms
                    .map(|value| value.min(MAX_TIMEOUT_MS))
                    .unwrap_or(crate::infer_client::DEFAULT_GENERATE_TIMEOUT_MS),
            ),
        ),
    )
    .await
}

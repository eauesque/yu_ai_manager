//! Native Rust chat-conversation persistence and generation for the
//! hailo-genai extension.
//!
//! Mirrors `extensions/builtin_hailo_genai/core_impl/chat_session.py` (a
//! thin `source="hailo"`-scoped wrapper over the shared chatlog store,
//! `chat_conversations`/`chat_messages`, see [`super::chatlog`]) and
//! `hailo_chat_routes_send.py`.
//!
//! `chat/new`, `chat/active`, and `chat/send` are migrated together as a
//! single unit (see the design review
//! `.claude/agent-outputs/design-advisor/2026-07-13-hailo-genai-chat-native-migration-rev1.md`)
//! because Python's old `chat_session._active_conv_id` module global was a
//! single point of authority spanning all three routes — moving only some of
//! them previously caused a real state-split bug (commit `5e7ed834b`).
//!
//! To avoid reintroducing that class of bug, this implementation has **no
//! volatile "active conversation" pointer at all**: `chat/active` derives the
//! active conversation from the database (`ORDER BY updated_at DESC LIMIT
//! 1`), which is exactly the row that `chat/send` (native or Python
//! fallback) just touched. This survives process restarts and stays correct
//! even when a fallback-path Python request creates or updates a
//! conversation Rust never saw a request for.
//!
//! `chat/send`'s native path covers text-only non-web-search chat and
//! multipart image uploads. JSON `file_id`, web search, and LLM subprocess
//! mode still fall back to Python before any native database write.

use std::{collections::HashMap, path::Path};

use axum::{
    body::Bytes,
    extract::{Extension, Path as AxumPath, Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    routes::auto_stubs::{model_name_to_hef_path, read_config_json, VLM_MAX_IMAGE_UPLOAD_BYTES},
    state::SharedState,
};

use super::chatlog::{columns, conversation_json, message_json};

const SOURCE: &str = "hailo";
const EMBEDDING_MODEL_ID: &str = "clip-vit-b-16";

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn openai_models_payload(
    registry: &HashMap<String, super::hailo_model_registry::GenAiModelInfo>,
    hef_dir: &Path,
    clip_text_available: bool,
) -> Value {
    let created = now_epoch_secs();
    let mut data = registry
        .iter()
        .filter(|(_, info)| {
            super::hailo_model_download::get_hef_path(&info.hef_filename, hef_dir).exists()
        })
        .map(|(name, _)| {
            json!({
                "id": name,
                "object": "model",
                "created": created,
                "owned_by": "hailo",
                "permission": [],
            })
        })
        .collect::<Vec<_>>();
    if clip_text_available {
        data.push(json!({
            "id": EMBEDDING_MODEL_ID,
            "object": "model",
            "created": created,
            "owned_by": "hailo",
            "permission": [],
        }));
    }
    json!({"object": "list", "data": data})
}

fn runtime_payload(
    registry: &HashMap<String, super::hailo_model_registry::GenAiModelInfo>,
    hef_dir: &Path,
) -> Value {
    json!({
        "status": "ok",
        "models": super::hailo_model_download::get_model_status(registry, hef_dir),
        // yu-hailo-infer creates and drops each LLM/VLM per request, so it retains no context.
        "context": Value::Null,
    })
}

pub async fn runtime(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let registry = super::hailo_model_registry::genai_models().await;
    let hef_dir = super::hailo_model_download::default_hef_dir();
    Json(runtime_payload(registry, &hef_dir)).into_response()
}

pub async fn openai_models(
    State(state): State<SharedState>,
    _auth_context: Option<Extension<AuthContext>>,
) -> Response {
    // Python deliberately leaves model discovery open to every authenticated scope.
    let registry = super::hailo_model_registry::genai_models().await;
    let hef_dir = super::hailo_model_download::default_hef_dir();
    Json(openai_models_payload(
        registry,
        &hef_dir,
        super::clip_model::model_ready(&state.config.cache_dir),
    ))
    .into_response()
}

fn error_response(status: StatusCode, message: &str) -> Response {
    (status, Json(json!({"status": "error", "message": message}))).into_response()
}

fn internal_error(error: impl std::fmt::Debug) -> Response {
    tracing::error!(?error, "hailo-genai chat db error");
    error_response(StatusCode::INTERNAL_SERVER_ERROR, "internal error")
}

pub async fn list_conversations(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let limit = params
        .get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(50)
        .clamp(1, 200);
    let offset = params
        .get("offset")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(0)
        .max(0);
    let cols = match columns(&state, "chat_conversations").await {
        Ok(cols) => cols,
        Err(error) => return internal_error(error),
    };
    let rows = match sqlx::query(
        "SELECT * FROM chat_conversations WHERE source = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
    )
    .bind(SOURCE)
    .bind(limit)
    .bind(offset)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error),
    };
    let conversations = rows
        .iter()
        .map(|row| conversation_json(row, &cols))
        .collect::<Vec<_>>();
    Json(json!({"status": "ok", "conversations": conversations})).into_response()
}

pub async fn get_conversation(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(conv_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let cols = match columns(&state, "chat_conversations").await {
        Ok(cols) => cols,
        Err(error) => return internal_error(error),
    };
    let row = match sqlx::query("SELECT * FROM chat_conversations WHERE id = ? AND source = ?")
        .bind(conv_id)
        .bind(SOURCE)
        .fetch_optional(&state.db_read)
        .await
    {
        Ok(Some(row)) => row,
        Ok(None) => return error_response(StatusCode::NOT_FOUND, "Not found"),
        Err(error) => return internal_error(error),
    };
    let mut conv = conversation_json(&row, &cols);
    let messages = match sqlx::query(
        "SELECT id, conversation_id, role, content, created_at, seq FROM chat_messages WHERE conversation_id = ? ORDER BY seq",
    )
    .bind(conv_id)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows.iter().map(message_json).collect::<Vec<_>>(),
        Err(error) => return internal_error(error),
    };
    conv["messages"] = json!(messages);
    Json(json!({"status": "ok", "conversation": conv})).into_response()
}

pub async fn delete_conversation(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(conv_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    // Note: Python's chat_session may still hold this id as its in-process
    // "active conversation" pointer; that becomes a harmless stale reference
    // once the row is gone (chat/send resolves conversations by id, never by
    // the active pointer, and a mismatched active id just forces the normal
    // "conversation switched" context-clear path on the next send).
    let result = match sqlx::query("DELETE FROM chat_conversations WHERE id = ? AND source = ?")
        .bind(conv_id)
        .bind(SOURCE)
        .execute(&state.db)
        .await
    {
        Ok(result) => result,
        Err(error) => return internal_error(error),
    };
    if result.rows_affected() == 0 {
        return error_response(StatusCode::NOT_FOUND, "Not found");
    }
    Json(json!({"status": "ok"})).into_response()
}

#[derive(Debug, Deserialize)]
pub struct RenameRequest {
    #[serde(default)]
    title: String,
}

pub async fn rename_conversation(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(conv_id): AxumPath<i64>,
    Json(body): Json<RenameRequest>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let title = body.title.trim();
    if title.is_empty() {
        return error_response(StatusCode::BAD_REQUEST, "title required");
    }
    let result =
        match sqlx::query("UPDATE chat_conversations SET title = ? WHERE id = ? AND source = ?")
            .bind(title)
            .bind(conv_id)
            .bind(SOURCE)
            .execute(&state.db)
            .await
        {
            Ok(result) => result,
            Err(error) => return internal_error(error),
        };
    if result.rows_affected() == 0 {
        return error_response(StatusCode::NOT_FOUND, "Not found");
    }
    Json(json!({"status": "ok", "title": title})).into_response()
}

fn now_epoch_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// Mirrors `get_extension_config_value("builtin-hailo-genai",
/// "default_llm_model", "qwen3-1.7b-instruct")`.
pub(crate) fn default_llm_model(state: &SharedState) -> String {
    const DEFAULT: &str = "qwen3-1.7b-instruct";
    read_config_json(state)["extensions"]["builtin-hailo-genai"]["default_llm_model"]
        .as_str()
        .unwrap_or(DEFAULT)
        .to_string()
}

/// Mirrors `use_subprocess()` (`llm_inference.py`) — this reads a top-level
/// config key (`hailo_genai.llm_subprocess`), NOT the extension config
/// section that `default_llm_model`/`default_vlm_model` read.
fn llm_subprocess_enabled(state: &SharedState) -> bool {
    read_config_json(state)["hailo_genai"]["llm_subprocess"]
        .as_bool()
        .unwrap_or(false)
}

/// The DB-derived "active conversation" — the most recently touched
/// hailo-scoped conversation. See the module doc for why this replaces a
/// volatile pointer.
async fn most_recent_hailo_conversation_id(
    state: &SharedState,
) -> Result<Option<i64>, sqlx::Error> {
    sqlx::query_scalar(
        "SELECT id FROM chat_conversations WHERE source = ? ORDER BY updated_at DESC LIMIT 1",
    )
    .bind(SOURCE)
    .fetch_optional(&state.db_read)
    .await
}

pub async fn chat_active(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match most_recent_hailo_conversation_id(&state).await {
        Ok(conv_id) => Json(json!({"status": "ok", "conversation_id": conv_id})).into_response(),
        Err(error) => internal_error(error),
    }
}

pub async fn chat_new(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let value: Value = serde_json::from_slice(&body).unwrap_or(json!({}));
    let model = value
        .get("model")
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .unwrap_or_else(|| default_llm_model(&state));

    let conv_id = match create_conversation_row(&state, &model).await {
        Ok(id) => id,
        Err(error) => return internal_error(error),
    };

    let cols = match columns(&state, "chat_conversations").await {
        Ok(cols) => cols,
        Err(error) => return internal_error(error),
    };
    let row = match sqlx::query("SELECT * FROM chat_conversations WHERE id = ?")
        .bind(conv_id)
        .fetch_one(&state.db_read)
        .await
    {
        Ok(row) => row,
        Err(error) => return internal_error(error),
    };
    Json(json!({"status": "ok", "conversation": conversation_json(&row, &cols)})).into_response()
}

/// Appends one message and bumps the parent conversation's `message_count`/
/// `updated_at` — mirrors `store_crud.append_message()`'s atomic `seq`
/// allocation (`MAX(seq)+1` in the same INSERT).
async fn append_message(
    state: &SharedState,
    conv_id: i64,
    role: &str,
    content: &str,
) -> Result<(), sqlx::Error> {
    let now = now_epoch_secs();
    sqlx::query(
        "INSERT INTO chat_messages (conversation_id, role, content, created_at, seq) \
         VALUES (?, ?, ?, ?, \
           COALESCE((SELECT MAX(seq) FROM chat_messages WHERE conversation_id = ?), 0) + 1)",
    )
    .bind(conv_id)
    .bind(role)
    .bind(content)
    .bind(now)
    .bind(conv_id)
    .execute(&state.db)
    .await?;
    sqlx::query(
        "UPDATE chat_conversations SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
    )
    .bind(now)
    .bind(conv_id)
    .execute(&state.db)
    .await?;
    Ok(())
}

/// Mirrors `chat_session.auto_title()`: 60-codepoint truncation with a
/// trailing "...", applied only if the title is still the "New Chat"
/// placeholder (so a user-renamed conversation is never silently
/// overwritten).
async fn auto_title(state: &SharedState, conv_id: i64, first_message: &str) -> String {
    let trimmed = first_message.trim();
    let mut title: String = trimmed.chars().take(60).collect();
    if trimmed.chars().count() > 60 {
        title.push_str("...");
    }
    let _ = sqlx::query(
        "UPDATE chat_conversations SET title = ? WHERE id = ? AND source = ? AND title = 'New Chat'",
    )
    .bind(&title)
    .bind(conv_id)
    .bind(SOURCE)
    .execute(&state.db)
    .await;
    title
}

/// Mirrors `store_crud.list_messages_recent()`: up to `limit` most recent
/// messages, oldest-first (for LLM prompt assembly).
async fn recent_messages(
    state: &SharedState,
    conv_id: i64,
    limit: i64,
) -> Result<Vec<(String, String)>, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT role, content FROM \
           (SELECT role, content, seq FROM chat_messages WHERE conversation_id = ? \
            ORDER BY seq DESC LIMIT ?) \
         ORDER BY seq ASC",
    )
    .bind(conv_id)
    .bind(limit)
    .fetch_all(&state.db_read)
    .await?;
    Ok(rows
        .into_iter()
        .map(|row| {
            (
                row.get::<String, _>("role"),
                row.get::<String, _>("content"),
            )
        })
        .collect())
}

pub async fn chat_send(
    State(state): State<SharedState>,
    headers: axum::http::HeaderMap,
    body: Bytes,
) -> Response {
    let content_type = headers
        .get(axum::http::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if let Some(infer_client) = state.infer_client.as_ref() {
        if content_type.starts_with("application/json") {
            if let Some(response) = chat_send_native(&state, infer_client, &body).await {
                return response;
            }
        } else if content_type.starts_with("multipart/form-data") {
            if let Some(response) =
                chat_send_multipart_native(&state, infer_client, &headers, &body).await
            {
                return response;
            }
        }
    }

    super::auto_stubs::fwd_ext_post_stream(
        &state,
        "/ext/hailo-genai/api/chat/send",
        body,
        headers.get("content-type"),
    )
    .await
}

#[derive(Debug)]
struct ChatVlmRequest {
    content: String,
    model: String,
    vlm_model: String,
    conversation_id: Option<i64>,
    temperature: f32,
    max_tokens: u32,
    frame_b64: String,
}

struct ChatMultipartDefaults {
    model: String,
    vlm_model: String,
    temperature: f32,
    max_tokens: u32,
}

fn chat_multipart_defaults(state: &SharedState) -> ChatMultipartDefaults {
    let config = read_config_json(state);
    let extension = &config["extensions"]["builtin-hailo-genai"];
    ChatMultipartDefaults {
        model: extension["default_llm_model"]
            .as_str()
            .unwrap_or("qwen3-1.7b-instruct")
            .to_string(),
        vlm_model: extension["default_vlm_model"]
            .as_str()
            .unwrap_or("qwen2-vl-2b-instruct")
            .to_string(),
        temperature: crate::num::narrow_f32(extension["temperature"].as_f64().unwrap_or(0.7)),
        max_tokens: extension["max_generated_tokens"]
            .as_u64()
            .and_then(|v| u32::try_from(v).ok())
            .unwrap_or(512),
    }
}

fn invalid_model_name(model: &str) -> bool {
    model.contains('/') || model.contains('\\') || model.contains("..")
}

fn chat_error(status: StatusCode, message: &str) -> Response {
    (status, Json(json!({"status": "error", "message": message}))).into_response()
}

fn with_thousands_separators(value: usize) -> String {
    let digits = value.to_string();
    let mut output = String::with_capacity(digits.len() + digits.len() / 3);
    for (index, character) in digits.chars().enumerate() {
        if index > 0 && (digits.len() - index).is_multiple_of(3) {
            output.push(',');
        }
        output.push(character);
    }
    output
}

async fn chat_send_multipart_native(
    state: &SharedState,
    infer_client: &crate::infer_client::InferClient,
    headers: &HeaderMap,
    body: &Bytes,
) -> Option<Response> {
    let defaults = chat_multipart_defaults(state);
    let request = match parse_chat_multipart(headers, body, &defaults).await? {
        Ok(request) => request,
        Err(response) => return Some(response),
    };

    let hef_path = match resolve_chat_request_vlm_hef(&request, resolve_chat_vlm_hef) {
        Ok(path) => path,
        Err(response) => return Some(response),
    };

    Some(chat_send_multipart_with_hef(state, infer_client, request, hef_path).await)
}

fn resolve_chat_request_vlm_hef(
    request: &ChatVlmRequest,
    resolve: impl FnOnce(&str) -> Result<String, Response>,
) -> Result<String, Response> {
    resolve(&request.vlm_model)
}

fn resolve_chat_vlm_hef(model: &str) -> Result<String, Response> {
    validate_chat_vlm_hef(model, model_name_to_hef_path(model))
}

fn validate_chat_vlm_hef(model: &str, hef_path: String) -> Result<String, Response> {
    Path::new(&hef_path)
        .exists()
        .then_some(hef_path)
        .ok_or_else(|| {
            chat_error(
                StatusCode::BAD_REQUEST,
                &format!("VLM model '{model}' not downloaded"),
            )
        })
}

async fn chat_send_multipart_with_hef(
    state: &SharedState,
    infer_client: &crate::infer_client::InferClient,
    request: ChatVlmRequest,
    hef_path: String,
) -> Response {
    let (conv_id, new_title) = match prepare_chat_conversation(
        state,
        request.conversation_id,
        &request.model,
        &format!("[Image] {}", request.content),
        &request.content,
    )
    .await
    {
        Ok(result) => result,
        Err(response) => return response,
    };

    let upstream = match infer_client
        .vlm_generate_stream(
            Some(hef_path),
            request.content,
            None,
            vec![request.frame_b64],
            Some(crate::infer_client::DEFAULT_GENERATE_TIMEOUT_MS),
            Some(request.temperature),
            None,
            None,
            None,
            Some(request.max_tokens),
            None,
            None,
        )
        .await
    {
        Ok(response) => response,
        Err(error) => {
            tracing::error!("yu-infer vlm_generate_stream request failed: {error}");
            return chat_error(StatusCode::BAD_GATEWAY, "Chat generation failed");
        }
    };

    chat_send_sse_response(state.clone(), upstream, conv_id, new_title, true)
}

async fn parse_chat_multipart(
    headers: &HeaderMap,
    body: &Bytes,
    defaults: &ChatMultipartDefaults,
) -> Option<Result<ChatVlmRequest, Response>> {
    let boundary = multer::parse_boundary(
        headers
            .get(axum::http::header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default(),
    )
    .ok()?;
    let owned = body.clone();
    let stream = futures_util::stream::once(async move { Ok::<_, std::io::Error>(owned) });
    let mut multipart = multer::Multipart::new(stream, boundary);
    let mut content = String::new();
    let mut model = None;
    let mut conversation_id = None;
    let mut temperature = None;
    let mut max_tokens = None;
    let mut web_search = false;
    let mut image = None;

    loop {
        let field = match multipart.next_field().await {
            Ok(Some(field)) => field,
            Ok(None) => break,
            Err(_) => return None,
        };
        let name = field.name().unwrap_or_default().to_string();
        match name.as_str() {
            "image" if field.file_name().is_some_and(|name| !name.is_empty()) => {
                let bytes = field.bytes().await.ok()?;
                if bytes.len() > VLM_MAX_IMAGE_UPLOAD_BYTES {
                    return Some(Err(chat_error(
                        StatusCode::PAYLOAD_TOO_LARGE,
                        &format!(
                            "file exceeds {} byte limit",
                            with_thousands_separators(VLM_MAX_IMAGE_UPLOAD_BYTES)
                        ),
                    )));
                }
                if !bytes.is_empty() {
                    image = Some(bytes);
                }
            }
            "content" => content = field.text().await.ok()?.trim().to_string(),
            "model" => model = field.text().await.ok(),
            "conversation_id" => conversation_id = field.text().await.ok()?.trim().parse().ok(),
            "temperature" => temperature = field.text().await.ok()?.trim().parse().ok(),
            "max_tokens" => max_tokens = field.text().await.ok()?.trim().parse().ok(),
            "web_search" => {
                web_search = matches!(
                    field.text().await.ok()?.to_lowercase().as_str(),
                    "true" | "1" | "yes"
                )
            }
            // Python collects extra_context but never passes it to the VLM branch.
            // Naming these keeps "known but deliberately dropped" distinct from
            // "unknown field", which is the whole point of listing them.
            #[allow(
                clippy::match_same_arms,
                reason = "the explicit arm lists fields Python drops"
            )]
            "system_prompt" | "extra_context" | "file_id" | "image" => {}
            _ => {}
        }
    }

    let image = image?;
    if web_search {
        return None;
    }
    if content.is_empty() {
        return Some(Err(chat_error(
            StatusCode::BAD_REQUEST,
            "content is required",
        )));
    }
    let model = model
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| defaults.model.clone());
    let vlm_model = defaults.vlm_model.clone();
    if invalid_model_name(&model) || invalid_model_name(&vlm_model) {
        return Some(Err(chat_error(
            StatusCode::BAD_REQUEST,
            "invalid model name",
        )));
    }
    use base64::Engine as _;
    Some(Ok(ChatVlmRequest {
        content,
        model,
        vlm_model,
        conversation_id,
        temperature: temperature.unwrap_or(defaults.temperature),
        max_tokens: max_tokens.unwrap_or(defaults.max_tokens),
        frame_b64: base64::engine::general_purpose::STANDARD.encode(image),
    }))
}

/// Attempts the native yu-infer path for a JSON chat/send request. Returns
/// `None` (falling back to the Python proxy, with **no DB writes performed
/// here**) for image chat (`file_id` present — multipart image uploads never
/// reach this function since the JSON content-type gate in [`chat_send`]
/// already excludes them), `web_search: true`, and LLM subprocess mode — all
/// checked before any side effect, so the fallback and native paths can
/// never both mutate the database for the same request.
async fn chat_send_native(
    state: &SharedState,
    infer_client: &crate::infer_client::InferClient,
    body: &Bytes,
) -> Option<Response> {
    let value: Value = serde_json::from_slice(body).ok()?;

    if value.get("file_id").and_then(|v| v.as_i64()).is_some() {
        return None;
    }
    if value
        .get("web_search")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
        return None;
    }
    if llm_subprocess_enabled(state) {
        return None;
    }

    let content = value
        .get("content")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if content.is_empty() {
        return Some(
            (
                StatusCode::BAD_REQUEST,
                Json(json!({"status": "error", "message": "content is required"})),
            )
                .into_response(),
        );
    }

    let model = value
        .get("model")
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .unwrap_or_else(|| default_llm_model(state));
    if model.contains('/') || model.contains('\\') || model.contains("..") {
        return Some(
            (
                StatusCode::BAD_REQUEST,
                Json(json!({"status": "error", "message": "invalid model name"})),
            )
                .into_response(),
        );
    }

    let requested_conv_id = value.get("conversation_id").and_then(|v| {
        v.as_i64()
            .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
    });
    let (conv_id, new_title) =
        match prepare_chat_conversation(state, requested_conv_id, &model, &content, &content).await
        {
            Ok(result) => result,
            Err(response) => return Some(response),
        };

    let system_prompt = value
        .get("system_prompt")
        .and_then(|v| v.as_str())
        .unwrap_or("You are a helpful assistant.")
        .to_string();
    let history = match recent_messages(state, conv_id, 20).await {
        Ok(rows) => rows,
        Err(error) => return Some(internal_error(error)),
    };
    let mut messages = vec![json!({"role": "system", "content": system_prompt})];
    messages.extend(
        history
            .into_iter()
            .map(|(role, msg_content)| json!({"role": role, "content": msg_content})),
    );

    let ext_cfg = read_config_json(state);
    let temperature = value
        .get("temperature")
        .and_then(|v| v.as_f64())
        .or_else(|| ext_cfg["extensions"]["builtin-hailo-genai"]["temperature"].as_f64())
        .map(crate::num::narrow_f32);
    let max_tokens = value
        .get("max_tokens")
        .and_then(|v| v.as_u64())
        .or_else(|| ext_cfg["extensions"]["builtin-hailo-genai"]["max_generated_tokens"].as_u64())
        .and_then(|v| u32::try_from(v).ok());

    let hef_path = model_name_to_hef_path(&model);
    let upstream = match infer_client
        .llm_generate_stream(
            Some(hef_path),
            messages,
            Vec::new(),
            Some(crate::infer_client::DEFAULT_GENERATE_TIMEOUT_MS),
            temperature,
            None,
            None,
            None,
            max_tokens,
            None,
            None,
        )
        .await
    {
        Ok(response) => response,
        Err(error) => {
            tracing::error!("yu-infer llm_generate_stream request failed: {error}");
            return Some(
                (
                    StatusCode::BAD_GATEWAY,
                    Json(json!({"status": "error", "message": "Chat generation failed"})),
                )
                    .into_response(),
            );
        }
    };

    Some(chat_send_sse_response(
        state.clone(),
        upstream,
        conv_id,
        new_title,
        false,
    ))
}

async fn prepare_chat_conversation(
    state: &SharedState,
    requested_conv_id: Option<i64>,
    model: &str,
    message_content: &str,
    title_content: &str,
) -> Result<(i64, Option<String>), Response> {
    let conv_id = match requested_conv_id {
        Some(id) => {
            let exists: Option<i64> =
                sqlx::query_scalar("SELECT id FROM chat_conversations WHERE id = ? AND source = ?")
                    .bind(id)
                    .bind(SOURCE)
                    .fetch_optional(&state.db_read)
                    .await
                    .ok()
                    .flatten();
            match exists {
                Some(id) => id,
                None => {
                    return Err(chat_error(StatusCode::NOT_FOUND, "Conversation not found"));
                }
            }
        }
        None => match create_conversation_row(state, model).await {
            Ok(id) => id,
            Err(error) => return Err(internal_error(error)),
        },
    };

    if let Err(error) = append_message(state, conv_id, "user", message_content).await {
        return Err(internal_error(error));
    }

    let user_message_count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM chat_messages WHERE conversation_id = ? AND role = 'user'",
    )
    .bind(conv_id)
    .fetch_one(&state.db_read)
    .await
    .unwrap_or(0);
    let new_title = if user_message_count == 1 {
        Some(auto_title(state, conv_id, title_content).await)
    } else {
        None
    };

    Ok((conv_id, new_title))
}

async fn create_conversation_row(state: &SharedState, model: &str) -> Result<i64, sqlx::Error> {
    let now = now_epoch_secs();
    let ext_id = uuid::Uuid::new_v4().to_string();
    let result = sqlx::query(
        "INSERT INTO chat_conversations \
         (source, external_id, title, model, created_at, updated_at, message_count) \
         VALUES (?, ?, 'New Chat', ?, ?, ?, 0)",
    )
    .bind(SOURCE)
    .bind(&ext_id)
    .bind(model)
    .bind(now)
    .bind(now)
    .execute(&state.db)
    .await?;
    Ok(result.last_insert_rowid())
}

/// Reshapes yu-infer's stateless `{token}`/`{done,full_text}` SSE schema
/// into Python's `{conversation_id,title}` init → `{token}`* →
/// `{done,full_text,conversation_id}` schema (`_generate_sse` in
/// `hailo_chat_routes_send.py`), persisting the assistant's full response to
/// the DB when the `done` event arrives — the native path owns this
/// persistence since yu-infer itself is a stateless inference process with
/// no knowledge of conversations.
fn chat_send_sse_response(
    state: SharedState,
    upstream: reqwest::Response,
    conv_id: i64,
    title: Option<String>,
    vlm: bool,
) -> Response {
    let (tx, rx) = tokio::sync::mpsc::unbounded_channel::<String>();
    let _ = tx.send(format!(
        "data: {}\n\n",
        if vlm {
            json!({"conversation_id": conv_id, "title": title, "vlm": true})
        } else {
            json!({"conversation_id": conv_id, "title": title})
        }
    ));

    tokio::spawn(async move {
        use futures_util::StreamExt;
        let mut stream = upstream.bytes_stream();
        let mut buffer = String::new();
        loop {
            let chunk = match stream.next().await {
                Some(Ok(bytes)) => bytes,
                Some(Err(error)) => {
                    let _ = tx.send(format!("data: {}\n\n", json!({"error": error.to_string()})));
                    return;
                }
                None => return,
            };
            buffer.push_str(&String::from_utf8_lossy(&chunk));
            while let Some(pos) = buffer.find("\n\n") {
                let event = buffer[..pos].to_string();
                buffer.drain(..=pos + 1);
                let Some(json_part) = event.strip_prefix("data: ") else {
                    continue;
                };
                let Ok(payload) = serde_json::from_str::<Value>(json_part) else {
                    continue;
                };
                if payload.get("done").and_then(|v| v.as_bool()) == Some(true) {
                    let full_text = payload
                        .get("full_text")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    if let Err(error) =
                        append_message(&state, conv_id, "assistant", &full_text).await
                    {
                        tracing::error!(?error, "failed to persist assistant chat message");
                    }
                    let _ = tx.send(format!(
                        "data: {}\n\n",
                        json!({"done": true, "full_text": full_text, "conversation_id": conv_id})
                    ));
                    return;
                }
                // Token and error events are relayed verbatim.
                let _ = tx.send(format!("data: {json_part}\n\n"));
            }
        }
    });

    let body_stream = futures_util::stream::unfold(rx, |mut rx| async move {
        rx.recv()
            .await
            .map(|chunk| (Ok::<_, std::io::Error>(axum::body::Bytes::from(chunk)), rx))
    });

    Response::builder()
        .status(StatusCode::OK)
        .header(axum::http::header::CONTENT_TYPE, "text/event-stream")
        .header(axum::http::header::CACHE_CONTROL, "no-cache")
        .header("x-accel-buffering", "no")
        .body(axum::body::Body::from_stream(body_stream))
        .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
}

#[cfg(test)]
mod tests {
    use axum::{body::to_bytes, extract::Path as AxumPath};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tempfile::TempDir;

    use super::*;
    use crate::{
        auth::{PinRateLimiter, QuickLock},
        groups_index::GroupsIndexCache,
        state::{AppState, Config},
    };
    use std::{
        collections::{HashMap, HashSet},
        sync::{
            atomic::{AtomicUsize, Ordering},
            Arc, Mutex,
        },
    };

    async fn test_state() -> (SharedState, TempDir) {
        test_state_with_infer_client(None).await
    }

    async fn test_state_with_infer_client(base_url: Option<&str>) -> (SharedState, TempDir) {
        let temp = TempDir::new().unwrap();
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(SqliteConnectOptions::new().filename(":memory:"))
            .await
            .unwrap();
        sqlx::raw_sql(
            "
            CREATE TABLE chat_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT,
                title TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                message_count INTEGER NOT NULL DEFAULT 0,
                imported_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0,
                seq INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO chat_conversations (id, source, external_id, title, model, created_at, updated_at, message_count, imported_at)
            VALUES (1, 'hailo', 'ext-1', 'Existing', 'qwen3-1.7b-instruct', 10, 20, 1, 10),
                   (2, 'chatgpt', 'ext-2', 'Imported', 'gpt-4.1', 11, 21, 0, 11);
            INSERT INTO chat_messages (id, conversation_id, role, content, created_at, seq)
            VALUES (1, 1, 'user', 'hello', 10, 0);
            ",
        )
        .execute(&pool)
        .await
        .unwrap();
        let state = Arc::new(AppState {
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
                pin_auth_enabled: false,
                min_pin_length: 4,
                python_url: String::new(),
                config_path: temp.path().join("config.json"),
                project_root: temp.path().to_path_buf(),
                app_config: json!({}),
                cache_dir: temp.path().join("cache"),
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
            quick_lock: QuickLock::new(),
            rate_limiter: PinRateLimiter::new(),
            groups_index_cache: GroupsIndexCache::new(temp.path().join("cache")),
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
            infer_client: base_url.map(|url| {
                crate::infer_client::InferClient::new(url.to_string(), "e2e-test-token".to_string())
            }),
            infer_child: None,
            scan_manager: std::sync::OnceLock::new(),
            hailo_yolo_stream: None,
            stats_basic_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_models_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_timeline_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_resolutions_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            checkpoints_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            server_info_stats_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
        });
        (state, temp)
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    fn sample_genai_registry() -> HashMap<String, super::super::hailo_model_registry::GenAiModelInfo>
    {
        use super::super::hailo_model_registry::{GenAiModelInfo, GenAiModelType};

        HashMap::from([
            (
                "present-model".to_string(),
                GenAiModelInfo {
                    name: "present-model".to_string(),
                    model_type: GenAiModelType::Llm,
                    hef_filename: "Present.hef".to_string(),
                    description: "Present model".to_string(),
                    url: "https://example.invalid/Present.hef".to_string(),
                },
            ),
            (
                "missing-model".to_string(),
                GenAiModelInfo {
                    name: "missing-model".to_string(),
                    model_type: GenAiModelType::Vlm,
                    hef_filename: "Missing.hef".to_string(),
                    description: "Missing model".to_string(),
                    url: "https://example.invalid/Missing.hef".to_string(),
                },
            ),
        ])
    }

    fn api_key_scope(scope: &str) -> Extension<AuthContext> {
        Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec![scope.to_string()]),
        })
    }

    fn enable_pin_auth(state: &mut SharedState) {
        Arc::get_mut(state)
            .expect("test state should have one owner")
            .config
            .pin_auth_enabled = true;
    }

    #[test]
    fn native_v1_models_lists_only_existing_hefs_with_openai_envelope() {
        let temp = TempDir::new().unwrap();
        std::fs::write(temp.path().join("Present.hef"), [0_u8; 1]).unwrap();

        let payload = openai_models_payload(&sample_genai_registry(), temp.path(), false);
        let data = payload["data"].as_array().unwrap();
        assert_eq!(payload["object"], "list");
        assert_eq!(data.len(), 1);
        assert_eq!(data[0]["id"], "present-model");
        assert_eq!(data[0]["object"], "model");
        assert!(data[0]["created"].as_i64().is_some());
        assert_eq!(data[0]["owned_by"], "hailo");
        assert_eq!(data[0]["permission"], json!([]));
    }

    #[test]
    fn native_v1_models_appends_embedding_model_when_clip_text_encoder_is_ready() {
        let temp = TempDir::new().unwrap();
        let payload = openai_models_payload(&sample_genai_registry(), temp.path(), true);
        let data = payload["data"].as_array().unwrap();
        assert_eq!(data.len(), 1);
        assert_eq!(data[0]["id"], EMBEDDING_MODEL_ID);
    }

    #[test]
    fn native_runtime_reports_present_and_absent_hefs() {
        let temp = TempDir::new().unwrap();
        let present_path = temp.path().join("Present.hef");
        std::fs::write(&present_path, vec![0_u8; 1024 * 1024]).unwrap();

        let payload = runtime_payload(&sample_genai_registry(), temp.path());
        assert_eq!(payload["status"], "ok");
        assert_eq!(payload["models"]["missing-model"]["available"], false);
        assert!(payload["models"]["missing-model"]["file_size_mb"].is_null());
        assert_eq!(payload["models"]["present-model"]["available"], true);
        assert_eq!(
            payload["models"]["present-model"]["path"],
            present_path.to_string_lossy().as_ref()
        );
        assert_eq!(payload["models"]["present-model"]["type"], "llm");
        assert_eq!(
            payload["models"]["present-model"]["description"],
            "Present model"
        );
        assert_eq!(payload["models"]["present-model"]["file_size_mb"], 1.0);
    }

    #[test]
    fn native_runtime_context_is_null_because_sidecar_retains_nothing() {
        let temp = TempDir::new().unwrap();
        let payload = runtime_payload(&sample_genai_registry(), temp.path());
        assert!(payload["context"].is_null());
    }

    #[tokio::test]
    async fn native_runtime_rejects_read_scope_and_allows_admin_scope() {
        let (mut state, _temp) = test_state().await;
        enable_pin_auth(&mut state);
        let read_response = runtime(State(state.clone()), Some(api_key_scope("read"))).await;
        assert_eq!(read_response.status(), StatusCode::FORBIDDEN);

        let admin_response = runtime(State(state), Some(api_key_scope("admin"))).await;
        assert_eq!(admin_response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn native_v1_models_allows_read_scope_for_openai_client_discovery() {
        let (mut state, _temp) = test_state().await;
        enable_pin_auth(&mut state);
        let response = openai_models(State(state), Some(api_key_scope("read"))).await;
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn list_only_returns_hailo_source() {
        let (state, _temp) = test_state().await;
        let response = list_conversations(State(state), None, Query(HashMap::new())).await;
        let body = json_body(response).await;
        assert_eq!(body["conversations"].as_array().unwrap().len(), 1);
        assert_eq!(body["conversations"][0]["id"], 1);
    }

    #[tokio::test]
    async fn get_excludes_other_source_conversation() {
        let (state, _temp) = test_state().await;
        let response = get_conversation(State(state), None, AxumPath(2)).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn get_includes_messages_for_hailo_conversation() {
        let (state, _temp) = test_state().await;
        let response = get_conversation(State(state), None, AxumPath(1)).await;
        let body = json_body(response).await;
        assert_eq!(body["conversation"]["messages"][0]["content"], "hello");
    }

    #[tokio::test]
    async fn rename_requires_nonempty_title() {
        let (state, _temp) = test_state().await;
        let response = rename_conversation(
            State(state),
            None,
            AxumPath(1),
            Json(RenameRequest {
                title: "  ".to_string(),
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn rename_updates_only_matching_source() {
        let (state, _temp) = test_state().await;
        let response = rename_conversation(
            State(state.clone()),
            None,
            AxumPath(2),
            Json(RenameRequest {
                title: "hijack".to_string(),
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let title: String = sqlx::query_scalar("SELECT title FROM chat_conversations WHERE id=2")
            .fetch_one(&state.db)
            .await
            .unwrap();
        assert_eq!(title, "Imported");
    }

    #[tokio::test]
    async fn delete_removes_matching_source_row() {
        let (state, _temp) = test_state().await;
        let response = delete_conversation(State(state.clone()), None, AxumPath(1)).await;
        assert_eq!(response.status(), StatusCode::OK);
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM chat_conversations WHERE id=1")
            .fetch_one(&state.db)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn delete_other_source_returns_not_found() {
        let (state, _temp) = test_state().await;
        let response = delete_conversation(State(state), None, AxumPath(2)).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn chat_new_creates_hailo_conversation() {
        let (state, _temp) = test_state().await;
        let response = chat_new(
            State(state.clone()),
            None,
            Bytes::from(json!({"model": "my-model"}).to_string()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["conversation"]["model"], "my-model");
        assert_eq!(body["conversation"]["source"], "hailo");
        assert_eq!(body["conversation"]["title"], "New Chat");
    }

    #[tokio::test]
    async fn chat_new_accepts_empty_body() {
        let (state, _temp) = test_state().await;
        let response = chat_new(State(state), None, Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn chat_active_derives_most_recently_updated_conversation() {
        let (state, _temp) = test_state().await;
        // Conversation 1 (hailo, updated_at=20) is the only hailo-scoped row
        // in the fixture, so it should be reported active.
        let response = chat_active(State(state.clone()), None).await;
        let body = json_body(response).await;
        assert_eq!(body["conversation_id"], 1);

        // A newer hailo conversation should take over as active.
        sqlx::query("INSERT INTO chat_conversations (id, source, external_id, title, model, created_at, updated_at, message_count) VALUES (3, 'hailo', 'ext-3', 'New Chat', 'm', 30, 30, 0)")
            .execute(&state.db)
            .await
            .unwrap();
        let response = chat_active(State(state), None).await;
        let body = json_body(response).await;
        assert_eq!(body["conversation_id"], 3);
    }

    #[tokio::test]
    async fn chat_active_returns_null_when_no_hailo_conversations() {
        let (state, _temp) = test_state().await;
        sqlx::query("DELETE FROM chat_conversations WHERE source = 'hailo'")
            .execute(&state.db)
            .await
            .unwrap();
        let response = chat_active(State(state), None).await;
        let body = json_body(response).await;
        assert!(body["conversation_id"].is_null());
    }

    #[tokio::test]
    async fn append_message_bumps_seq_count_and_updated_at() {
        let (state, _temp) = test_state().await;
        append_message(&state, 1, "assistant", "hi there")
            .await
            .unwrap();
        let (message_count, updated_at): (i64, i64) =
            sqlx::query_as("SELECT message_count, updated_at FROM chat_conversations WHERE id = 1")
                .fetch_one(&state.db)
                .await
                .unwrap();
        assert_eq!(message_count, 2);
        assert!(updated_at >= 20);
        let seq: i64 = sqlx::query_scalar(
            "SELECT seq FROM chat_messages WHERE conversation_id = 1 AND role = 'assistant'",
        )
        .fetch_one(&state.db)
        .await
        .unwrap();
        assert_eq!(seq, 1);
    }

    #[tokio::test]
    async fn auto_title_respects_new_chat_guard() {
        let (state, _temp) = test_state().await;
        sqlx::query("UPDATE chat_conversations SET title = 'Custom Title' WHERE id = 1")
            .execute(&state.db)
            .await
            .unwrap();
        auto_title(&state, 1, "first message").await;
        let title: String = sqlx::query_scalar("SELECT title FROM chat_conversations WHERE id = 1")
            .fetch_one(&state.db)
            .await
            .unwrap();
        assert_eq!(title, "Custom Title");
    }

    fn dummy_infer_client() -> crate::infer_client::InferClient {
        crate::infer_client::InferClient::new(
            "http://127.0.0.1:18799".to_string(),
            "e2e-test-token".to_string(),
        )
    }

    #[tokio::test]
    async fn chat_send_native_falls_back_for_image_file_id() {
        let (state, _temp) = test_state().await;
        let body = Bytes::from(json!({"content": "hi", "file_id": 1}).to_string());
        let response = chat_send_native(&state, &dummy_infer_client(), &body).await;
        assert!(response.is_none());
    }

    #[tokio::test]
    async fn chat_send_native_falls_back_for_web_search() {
        let (state, _temp) = test_state().await;
        let body = Bytes::from(json!({"content": "hi", "web_search": true}).to_string());
        let response = chat_send_native(&state, &dummy_infer_client(), &body).await;
        assert!(response.is_none());
    }

    #[tokio::test]
    async fn chat_send_native_falls_back_for_subprocess_mode() {
        let (state, _temp) = test_state().await;
        std::fs::write(
            &state.config.config_path,
            json!({"hailo_genai": {"llm_subprocess": true}}).to_string(),
        )
        .unwrap();
        let body = Bytes::from(json!({"content": "hi"}).to_string());
        let response = chat_send_native(&state, &dummy_infer_client(), &body).await;
        assert!(response.is_none());
    }

    #[tokio::test]
    async fn chat_send_native_rejects_empty_content() {
        let (state, _temp) = test_state().await;
        let body = Bytes::from(json!({"content": "   "}).to_string());
        let response = chat_send_native(&state, &dummy_infer_client(), &body)
            .await
            .expect("native path should handle empty content directly");
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn chat_send_native_rejects_unknown_conversation_id() {
        let (state, _temp) = test_state().await;
        let body = Bytes::from(json!({"content": "hi", "conversation_id": 999}).to_string());
        let response = chat_send_native(&state, &dummy_infer_client(), &body)
            .await
            .expect("native path should handle missing conversation directly");
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn chat_send_native_fallback_paths_perform_no_db_writes() {
        let (state, _temp) = test_state().await;
        let before: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM chat_messages")
            .fetch_one(&state.db)
            .await
            .unwrap();
        let body = Bytes::from(json!({"content": "hi", "web_search": true}).to_string());
        assert!(chat_send_native(&state, &dummy_infer_client(), &body)
            .await
            .is_none());
        let after: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM chat_messages")
            .fetch_one(&state.db)
            .await
            .unwrap();
        assert_eq!(before, after);
    }

    /// End-to-end against a real yu-infer instance: exercises the whole
    /// native chat/send flow (conversation creation, user message
    /// persistence, auto-title, SSE reshape with conversation_id/title init
    /// and a final done event, and assistant message persistence) followed
    /// by a second turn that must recall information from the first —
    /// proving the multi-turn `messages` contract (design-advisor M1) is
    /// actually wired through end-to-end, not just at the yu-infer layer.
    #[tokio::test]
    #[ignore = "requires a running yu-infer on 127.0.0.1:18799 with HAILO_LLM_HEF loaded"]
    async fn chat_send_native_streams_and_persists_from_real_yu_infer() {
        let (state, _temp) = test_state_with_infer_client(Some("http://127.0.0.1:18799")).await;

        let body = Bytes::from(
            json!({
                "content": "My favorite color is teal. Remember that in one short sentence.",
                "model": "Llama3.2-1B-Instruct",
                "max_tokens": 24,
            })
            .to_string(),
        );
        let response = chat_send(
            State(state.clone()),
            {
                let mut headers = axum::http::HeaderMap::new();
                headers.insert(
                    axum::http::header::CONTENT_TYPE,
                    axum::http::HeaderValue::from_static("application/json"),
                );
                headers
            },
            body,
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let text = String::from_utf8_lossy(&bytes);
        eprintln!("chat/send SSE response (turn 1): {text}");
        assert!(text.contains("\"conversation_id\""), "expected init event");
        assert!(
            text.contains("\"done\":true"),
            "expected a final done event"
        );

        let conv_id: i64 = sqlx::query_scalar(
            "SELECT id FROM chat_conversations WHERE source = 'hailo' ORDER BY updated_at DESC LIMIT 1",
        )
        .fetch_one(&state.db_read)
        .await
        .unwrap();
        let roles: Vec<String> = sqlx::query_scalar(
            "SELECT role FROM chat_messages WHERE conversation_id = ? ORDER BY seq",
        )
        .bind(conv_id)
        .fetch_all(&state.db_read)
        .await
        .unwrap();
        assert_eq!(roles, vec!["user".to_string(), "assistant".to_string()]);
        let title: String = sqlx::query_scalar("SELECT title FROM chat_conversations WHERE id = ?")
            .bind(conv_id)
            .fetch_one(&state.db_read)
            .await
            .unwrap();
        assert_ne!(title, "New Chat", "auto_title should have replaced it");

        // Second turn, same conversation: the model must be able to recall
        // "teal" from turn 1's history without the caller repeating it.
        let body2 = Bytes::from(
            json!({
                "content": "What is my favorite color? Answer in one word.",
                "conversation_id": conv_id,
                "model": "Llama3.2-1B-Instruct",
                "max_tokens": 16,
            })
            .to_string(),
        );
        let response2 = chat_send(
            State(state.clone()),
            {
                let mut headers = axum::http::HeaderMap::new();
                headers.insert(
                    axum::http::header::CONTENT_TYPE,
                    axum::http::HeaderValue::from_static("application/json"),
                );
                headers
            },
            body2,
        )
        .await;
        assert_eq!(response2.status(), StatusCode::OK);
        let bytes2 = axum::body::to_bytes(response2.into_body(), usize::MAX)
            .await
            .unwrap();
        let text2 = String::from_utf8_lossy(&bytes2);
        eprintln!("chat/send SSE response (turn 2): {text2}");
        assert!(
            text2.to_lowercase().contains("teal"),
            "expected turn 2 to recall turn 1's context, got: {text2}"
        );
    }

    fn chat_multipart_body(parts: &[(&str, Option<&str>, &[u8])]) -> Bytes {
        let mut body = Vec::new();
        for (name, filename, value) in parts {
            body.extend_from_slice(b"--chat-boundary\r\nContent-Disposition: form-data; name=\"");
            body.extend_from_slice(name.as_bytes());
            body.extend_from_slice(b"\"");
            if let Some(filename) = filename {
                body.extend_from_slice(b"; filename=\"");
                body.extend_from_slice(filename.as_bytes());
                body.extend_from_slice(b"\"");
            }
            body.extend_from_slice(b"\r\n\r\n");
            body.extend_from_slice(value);
            body.extend_from_slice(b"\r\n");
        }
        body.extend_from_slice(b"--chat-boundary--\r\n");
        Bytes::from(body)
    }

    fn chat_multipart_headers() -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(
            axum::http::header::CONTENT_TYPE,
            axum::http::HeaderValue::from_static("multipart/form-data; boundary=chat-boundary"),
        );
        headers
    }

    fn chat_defaults() -> ChatMultipartDefaults {
        ChatMultipartDefaults {
            model: "qwen3-1.7b-instruct".to_string(),
            vlm_model: "qwen2-vl-2b-instruct".to_string(),
            temperature: 0.7,
            max_tokens: 512,
        }
    }

    #[tokio::test]
    async fn hailo_genai_chat_multipart_maps_image_request() {
        let body = chat_multipart_body(&[
            ("content", None, b"describe this"),
            ("model", None, b"qwen3-1.7b-instruct"),
            ("vlm_model", None, b"ignored-client-vlm"),
            ("temperature", None, b"0.25"),
            ("max_tokens", None, b"77"),
            ("image", Some("cat.png"), b"image-bytes"),
        ]);
        let request = parse_chat_multipart(&chat_multipart_headers(), &body, &chat_defaults())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(request.content, "describe this");
        assert_eq!(request.model, "qwen3-1.7b-instruct");
        assert_eq!(request.vlm_model, "qwen2-vl-2b-instruct");
        assert_eq!(request.temperature, 0.25);
        assert_eq!(request.max_tokens, 77);
        assert_eq!(request.frame_b64, "aW1hZ2UtYnl0ZXM=");
    }

    #[tokio::test]
    async fn hailo_genai_chat_multipart_defaults_and_defers_match_python() {
        let defaults = ChatMultipartDefaults {
            model: "configured-llm".to_string(),
            vlm_model: "configured-vlm".to_string(),
            temperature: 0.3,
            max_tokens: 321,
        };
        let image =
            chat_multipart_body(&[("content", None, b"hi"), ("image", Some("a.png"), b"bytes")]);
        let request = parse_chat_multipart(&chat_multipart_headers(), &image, &defaults)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(request.model, "configured-llm");
        assert_eq!(request.vlm_model, "configured-vlm");
        assert_eq!(request.temperature, 0.3);
        assert_eq!(request.max_tokens, 321);

        let no_image = chat_multipart_body(&[("content", None, b"hi"), ("file_id", None, b"1")]);
        assert!(
            parse_chat_multipart(&chat_multipart_headers(), &no_image, &defaults)
                .await
                .is_none()
        );
        let searched = chat_multipart_body(&[
            ("content", None, b"hi"),
            ("web_search", None, b"true"),
            ("image", Some("a.png"), b"bytes"),
        ]);
        assert!(
            parse_chat_multipart(&chat_multipart_headers(), &searched, &defaults)
                .await
                .is_none()
        );
    }

    #[tokio::test]
    async fn hailo_genai_chat_multipart_rejects_invalid_input() {
        for (field, value) in [("content", b"   ".as_slice()), ("model", b"../../bad")] {
            let body = chat_multipart_body(&[
                (
                    "content",
                    None,
                    if field == "content" { value } else { b"hi" },
                ),
                (field, None, value),
                ("image", Some("a.png"), b"bytes"),
            ]);
            let response = parse_chat_multipart(&chat_multipart_headers(), &body, &chat_defaults())
                .await
                .unwrap()
                .unwrap_err();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        }
        let oversized = vec![0; VLM_MAX_IMAGE_UPLOAD_BYTES + 1];
        let body = chat_multipart_body(&[
            ("content", None, b"hi"),
            ("image", Some("big.png"), &oversized),
        ]);
        let response = parse_chat_multipart(&chat_multipart_headers(), &body, &chat_defaults())
            .await
            .unwrap()
            .unwrap_err();
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);

        let traversal_defaults = ChatMultipartDefaults {
            vlm_model: "../evil".to_string(),
            ..chat_defaults()
        };
        let body =
            chat_multipart_body(&[("content", None, b"hi"), ("image", Some("a.png"), b"bytes")]);
        let response = parse_chat_multipart(&chat_multipart_headers(), &body, &traversal_defaults)
            .await
            .unwrap()
            .unwrap_err();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn hailo_genai_chat_multipart_streams_vlm_only_and_persists_image_message() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let requests = Arc::new(AtomicUsize::new(0));
        let captured = Arc::new(Mutex::new(None));
        let app = axum::Router::new().route(
            "/v1/infer/vlm/generate/stream",
            axum::routing::post({
                let requests = requests.clone();
                let captured = captured.clone();
                move |Json(payload): Json<Value>| {
                    let requests = requests.clone();
                    let captured = captured.clone();
                    async move {
                        requests.fetch_add(1, Ordering::SeqCst);
                        *captured.lock().unwrap() = Some(payload);
                        "data: {\"token\":\"ok\"}\n\ndata: {\"done\":true,\"full_text\":\"done\"}\n\n"
                    }
                }
            }),
        );
        let _server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let (state, _temp) = test_state_with_infer_client(Some(&format!("http://{address}"))).await;
        let request = ChatVlmRequest {
            content: "describe".to_string(),
            model: "llm-model".to_string(),
            vlm_model: "vlm-model".to_string(),
            conversation_id: None,
            temperature: 0.4,
            max_tokens: 12,
            frame_b64: "aW1hZ2U=".to_string(),
        };
        let response = chat_send_multipart_with_hef(
            &state,
            state.infer_client.as_ref().unwrap(),
            request,
            tempfile::NamedTempFile::new()
                .unwrap()
                .path()
                .to_string_lossy()
                .into_owned(),
        )
        .await;
        let text = String::from_utf8_lossy(
            &axum::body::to_bytes(response.into_body(), usize::MAX)
                .await
                .unwrap(),
        )
        .into_owned();
        assert!(text.contains("\"vlm\":true"));
        let payload = captured.lock().unwrap().clone().unwrap();
        assert_eq!(requests.load(Ordering::SeqCst), 1);
        assert_eq!(payload["frames"], json!(["aW1hZ2U="]));
        assert!(payload["system_prompt"].is_null());
        assert!(payload.get("messages").is_none());
        let message: String = sqlx::query_scalar(
            "SELECT content FROM chat_messages WHERE role = 'user' ORDER BY id DESC LIMIT 1",
        )
        .fetch_one(&state.db_read)
        .await
        .unwrap();
        assert_eq!(message, "[Image] describe");

        let missing =
            validate_chat_vlm_hef("missing-vlm", "definitely-missing.hef".to_string()).unwrap_err();
        assert_eq!(missing.status(), StatusCode::BAD_REQUEST);
        assert_eq!(requests.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn hailo_genai_chat_resolves_the_configured_vlm_model() {
        let request = ChatVlmRequest {
            content: "hi".to_string(),
            model: "configured-llm".to_string(),
            vlm_model: "configured-vlm".to_string(),
            conversation_id: None,
            temperature: 0.7,
            max_tokens: 512,
            frame_b64: String::new(),
        };
        let file = tempfile::NamedTempFile::new().unwrap();
        let path = file.path().to_string_lossy().into_owned();
        let resolved = resolve_chat_request_vlm_hef(&request, |model| {
            assert_eq!(model, "configured-vlm");
            validate_chat_vlm_hef(model, path.clone())
        })
        .unwrap();
        assert_eq!(resolved, path);
    }

    #[test]
    fn hailo_genai_chat_send_route_has_body_limit() {
        let source = include_str!("../main.rs")
            .lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n");
        let route = source
            .split("/ext/hailo-genai/api/chat/send")
            .nth(1)
            .unwrap_or_default()
            .split("\n        .route(")
            .next()
            .unwrap_or_default();
        assert!(route.contains("DefaultBodyLimit::max"));
    }
}

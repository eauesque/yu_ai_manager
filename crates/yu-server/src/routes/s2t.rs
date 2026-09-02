//! Native Hailo speech2text: single-file transcribe, video transcribe,
//! saved-transcript lookup, and the OpenAI-compatible
//! `/v1/audio/transcriptions` endpoint.
//!
//! Batch transcription lives in `s2t_runner.rs` (a background job, mirroring
//! `caption_runner.rs`'s shape) since it needs its own progress/SSE state.
//!
//! yu-infer's `/v1/infer/speech2text/transcribe` decodes and resamples the
//! WAV itself, so unlike the Python extension (which reads PCM samples with
//! the stdlib `wave` module before calling the sidecar in-process), these
//! handlers never touch PCM directly -- they only need valid WAV bytes,
//! base64-encoded, to hand to `InferClient::speech2text_transcribe`.

use axum::{
    extract::{Extension, Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use base64::Engine as _;
use bytes::Bytes;
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    infer_client::{InferClientError, S2tSegment, S2tTranscription},
    state::SharedState,
};

use super::{auto_stubs::model_name_to_hef_path, vector_store::get_file_paths_by_ids};

pub(crate) const S2T_MAX_AUDIO_UPLOAD_BYTES: usize = 32 * 1024 * 1024;
pub(crate) const DEFAULT_S2T_MODEL: &str = "whisper-base";
const S2T_TIMEOUT_MS: u32 = 120_000;

fn admin_or_response(
    state: &SharedState,
    auth: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(
        state.config.pin_auth_enabled,
        auth.map(|extension| &extension.0),
    )
}

fn error_response(status: StatusCode, message: impl Into<String>) -> Response {
    (
        status,
        Json(json!({"status": "error", "message": message.into()})),
    )
        .into_response()
}

fn sidecar_unavailable() -> Response {
    error_response(
        StatusCode::SERVICE_UNAVAILABLE,
        "Hailo speech2text sidecar is unavailable",
    )
}

fn model_not_downloaded(model: &str) -> Response {
    error_response(
        StatusCode::BAD_REQUEST,
        format!("Model '{model}' not downloaded yet"),
    )
}

fn infer_error(error: InferClientError) -> Response {
    error_response(
        StatusCode::INTERNAL_SERVER_ERROR,
        format!("Transcription failed: {error}"),
    )
}

/// `None` when the model's `.hef` is not present on disk -- the same check
/// Python's `is_hef_available` performs.
pub(crate) fn hef_available(model: &str) -> Option<String> {
    let hef_path = model_name_to_hef_path(model);
    std::path::Path::new(&hef_path).exists().then_some(hef_path)
}

pub(crate) fn segments_json(segments: &[S2tSegment]) -> Value {
    Value::Array(
        segments
            .iter()
            .map(
                |segment| json!({"text": segment.text, "start": segment.start, "end": segment.end}),
            )
            .collect(),
    )
}

/// Converts arbitrary audio bytes (any container ffmpeg understands) into
/// base64-encoded WAV. Skips the ffmpeg round trip when the upload is
/// already `.wav`, matching Python's `_convert_path_to_wav` early-out.
pub(crate) async fn audio_bytes_to_wav_base64(
    bytes: &[u8],
    filename: &str,
) -> Result<String, String> {
    if filename.to_ascii_lowercase().ends_with(".wav") {
        return Ok(base64::engine::general_purpose::STANDARD.encode(bytes));
    }
    let suffix = filename
        .rsplit_once('.')
        .map(|(_, extension)| format!(".{extension}"))
        .unwrap_or_else(|| ".bin".to_string());
    let input = tempfile::Builder::new()
        .suffix(&suffix)
        .tempfile()
        .map_err(|error| error.to_string())?;
    tokio::fs::write(input.path(), bytes)
        .await
        .map_err(|error| error.to_string())?;
    ffmpeg_wav_base64(input.path()).await
}

/// Extracts/transcodes the given input's audio track into base64-encoded
/// 16 kHz mono WAV via ffmpeg. `-vn` is harmless on pure-audio input (there
/// is no video stream to drop), so this one function serves both video
/// files and non-WAV audio uploads.
pub(crate) async fn ffmpeg_wav_base64(input_path: &std::path::Path) -> Result<String, String> {
    let output = tempfile::Builder::new()
        .suffix(".wav")
        .tempfile()
        .map_err(|error| error.to_string())?;
    let result = tokio::process::Command::new("ffmpeg")
        .arg("-y")
        .arg("-i")
        .arg(input_path)
        .args(["-vn", "-ar", "16000", "-ac", "1", "-f", "wav"])
        .arg(output.path())
        .output()
        .await
        .map_err(|error| format!("ffmpeg spawn failed: {error}"))?;
    if !result.status.success() {
        return Err("audio conversion failed (ffmpeg)".to_string());
    }
    let wav_bytes = tokio::fs::read(output.path())
        .await
        .map_err(|error| error.to_string())?;
    Ok(base64::engine::general_purpose::STANDARD.encode(wav_bytes))
}

struct S2tMultipartRequest {
    filename: String,
    bytes: Vec<u8>,
    model: String,
    language: String,
    /// Only meaningful for `/v1/audio/transcriptions` (OpenAI's
    /// `response_format` field: `json`/`text`/`verbose_json`); the other
    /// callers of this shared parser ignore it.
    response_format: Option<String>,
}

/// Accepts either an `audio` part (`/api/s2t/transcribe`) or a `file` part
/// (`/v1/audio/transcriptions`, matching the OpenAI SDK's field name) -- the
/// two endpoints never see each other's requests, so one parser can serve
/// both.
async fn parse_s2t_multipart(
    headers: &HeaderMap,
    body: &Bytes,
) -> Result<S2tMultipartRequest, Response> {
    let boundary = multer::parse_boundary(
        headers
            .get(axum::http::header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default(),
    )
    .map_err(|_| error_response(StatusCode::BAD_REQUEST, "invalid multipart body"))?;
    let owned = body.clone();
    let stream = futures_util::stream::once(async move { Ok::<_, std::io::Error>(owned) });
    let mut multipart = multer::Multipart::new(stream, boundary);

    let mut filename = "audio.wav".to_string();
    let mut bytes: Option<Vec<u8>> = None;
    let mut model = DEFAULT_S2T_MODEL.to_string();
    let mut language = "en".to_string();
    let mut response_format: Option<String> = None;

    loop {
        let field = match multipart.next_field().await {
            Ok(Some(field)) => field,
            Ok(None) => break,
            Err(_) => {
                return Err(error_response(
                    StatusCode::BAD_REQUEST,
                    "malformed multipart body",
                ))
            }
        };
        let name = field.name().unwrap_or_default().to_string();
        match name.as_str() {
            "audio" | "file" => {
                filename = field.file_name().unwrap_or("audio.wav").to_string();
                let data = field.bytes().await.map_err(|_| {
                    error_response(StatusCode::BAD_REQUEST, "failed to read audio part")
                })?;
                if data.len() > S2T_MAX_AUDIO_UPLOAD_BYTES {
                    return Err(error_response(
                        StatusCode::PAYLOAD_TOO_LARGE,
                        format!("audio exceeds {S2T_MAX_AUDIO_UPLOAD_BYTES} bytes"),
                    ));
                }
                bytes = Some(data.to_vec());
            }
            "model" => model = field.text().await.unwrap_or(model),
            "language" => language = field.text().await.unwrap_or(language),
            "response_format" => response_format = field.text().await.ok(),
            _ => {}
        }
    }
    let bytes =
        bytes.ok_or_else(|| error_response(StatusCode::BAD_REQUEST, "audio file is required"))?;
    Ok(S2tMultipartRequest {
        filename,
        bytes,
        model,
        language,
        response_format,
    })
}

// ── POST /ext/hailo-genai/api/s2t/transcribe ───────────────────────────

pub async fn transcribe(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return sidecar_unavailable();
    };
    let request = match parse_s2t_multipart(&headers, &body).await {
        Ok(request) => request,
        Err(response) => return response,
    };
    let Some(hef_path) = hef_available(&request.model) else {
        return model_not_downloaded(&request.model);
    };
    let audio_base64 = match audio_bytes_to_wav_base64(&request.bytes, &request.filename).await {
        Ok(audio_base64) => audio_base64,
        Err(message) => {
            return error_response(
                StatusCode::BAD_REQUEST,
                format!("Audio conversion failed: {message}. Install ffmpeg or upload WAV format."),
            )
        }
    };
    match infer_client
        .speech2text_transcribe(
            Some(hef_path),
            audio_base64,
            Some(request.language.clone()),
            S2T_TIMEOUT_MS,
        )
        .await
    {
        Ok(result) => Json(json!({
            "status": "ok",
            "text": result.text,
            "segments": segments_json(&result.segments),
            "language": request.language,
        }))
        .into_response(),
        Err(error) => infer_error(error),
    }
}

// ── POST /ext/hailo-genai/api/s2t/transcribe-video ─────────────────────

pub async fn transcribe_video(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return sidecar_unavailable();
    };
    let Some(file_id) = body
        .get("file_id")
        .and_then(Value::as_i64)
        .filter(|id| *id > 0)
    else {
        return error_response(StatusCode::BAD_REQUEST, "file_id is required");
    };
    let model = body
        .get("model")
        .and_then(Value::as_str)
        .unwrap_or(DEFAULT_S2T_MODEL)
        .to_string();
    let language = body
        .get("language")
        .and_then(Value::as_str)
        .unwrap_or("en")
        .to_string();
    let Some(hef_path) = hef_available(&model) else {
        return model_not_downloaded(&model);
    };

    let paths = match get_file_paths_by_ids(&state.db_read, &[file_id]).await {
        Ok(paths) => paths,
        Err(error) => return error_response(StatusCode::INTERNAL_SERVER_ERROR, error.to_string()),
    };
    let Some(video_path) = paths.get(&file_id) else {
        return error_response(StatusCode::NOT_FOUND, "File not found");
    };

    let audio_base64 = match ffmpeg_wav_base64(std::path::Path::new(video_path)).await {
        Ok(audio_base64) => audio_base64,
        Err(message) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to extract audio from video: {message}"),
            )
        }
    };

    let result = match infer_client
        .speech2text_transcribe(
            Some(hef_path),
            audio_base64,
            Some(language.clone()),
            S2T_TIMEOUT_MS,
        )
        .await
    {
        Ok(result) => result,
        Err(error) => return infer_error(error),
    };

    if let Err(error) = save_transcript(&state, file_id, &result).await {
        return error_response(StatusCode::INTERNAL_SERVER_ERROR, error.to_string());
    }

    Json(json!({
        "status": "ok",
        "text": result.text,
        "segments": segments_json(&result.segments),
        "language": language,
    }))
    .into_response()
}

/// Persists a transcript the same way the batch runner does: two
/// `file_annotations` rows under `source = "hailo:s2t"` (`transcript` /
/// `transcript_segments`), matching the Python extension's shape so
/// `/api/s2t/transcript/{file_id}` reads either origin identically.
pub(crate) async fn save_transcript(
    state: &SharedState,
    file_id: i64,
    result: &S2tTranscription,
) -> Result<(), sqlx::Error> {
    let segments_json = serde_json::to_string(&segments_json(&result.segments))
        .unwrap_or_else(|_| "[]".to_string());
    let mut tx = state.db.begin().await?;
    for (key, value) in [
        ("transcript", result.text.as_str()),
        ("transcript_segments", segments_json.as_str()),
    ] {
        sqlx::query(
            "INSERT INTO file_annotations (file_id, source, key, value, confidence, created_at) \
             VALUES (?, ?, ?, ?, ?, unixepoch()) \
             ON CONFLICT(file_id, source, key) DO UPDATE SET \
                value=excluded.value, confidence=excluded.confidence, created_at=excluded.created_at",
        )
        .bind(file_id)
        .bind("hailo:s2t")
        .bind(key)
        .bind(value)
        .bind(Option::<f64>::None)
        .execute(&mut *tx)
        .await?;
    }
    tx.commit().await
}

// ── GET /ext/hailo-genai/api/s2t/transcript/{file_id} ──────────────────

pub async fn transcript(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let rows = match sqlx::query_as::<_, (String, String)>(
        "SELECT key, value FROM file_annotations WHERE file_id = ? AND source = 'hailo:s2t'",
    )
    .bind(file_id)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return error_response(StatusCode::INTERNAL_SERVER_ERROR, error.to_string()),
    };
    if rows.is_empty() {
        return Json(json!({
            "status": "not_found",
            "message": "No transcript found for this file",
        }))
        .into_response();
    }
    let mut result = json!({"status": "ok", "file_id": file_id});
    for (key, value) in rows {
        match key.as_str() {
            "transcript" => result["text"] = json!(value),
            "transcript_segments" => {
                result["segments"] = serde_json::from_str(&value).unwrap_or_else(|_| json!([]));
            }
            _ => {}
        }
    }
    Json(result).into_response()
}

// ── POST /ext/hailo-genai/v1/audio/transcriptions (OpenAI-compatible) ──

fn openai_error(message: impl Into<String>, code: &'static str, status: StatusCode) -> Response {
    (
        status,
        Json(json!({"error": {"message": message.into(), "type": "invalid_request_error", "code": code}})),
    )
        .into_response()
}

fn resolve_openai_model(model: &str) -> String {
    match model {
        "whisper-1" => DEFAULT_S2T_MODEL.to_string(),
        other => other.to_string(),
    }
}

pub async fn openai_transcriptions(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let Some(infer_client) = state.infer_client.as_ref() else {
        return openai_error(
            "Hailo speech2text sidecar is unavailable",
            "service_unavailable",
            StatusCode::SERVICE_UNAVAILABLE,
        );
    };
    let request = match parse_s2t_multipart(&headers, &body).await {
        Ok(request) => request,
        Err(response) => return response,
    };
    let model = resolve_openai_model(&request.model);
    if !super::hailo_model_registry::genai_models()
        .await
        .contains_key(&model)
    {
        return openai_error(
            format!("Model '{model}' not found"),
            "model_not_found",
            StatusCode::NOT_FOUND,
        );
    }
    let Some(hef_path) = hef_available(&model) else {
        return openai_error(
            format!("Model '{model}' not downloaded"),
            "model_not_found",
            StatusCode::NOT_FOUND,
        );
    };
    let audio_base64 = match audio_bytes_to_wav_base64(&request.bytes, &request.filename).await {
        Ok(audio_base64) => audio_base64,
        Err(message) => {
            return openai_error(
                format!("Audio conversion failed: {message}. Install ffmpeg or upload WAV format."),
                "invalid_request_error",
                StatusCode::BAD_REQUEST,
            )
        }
    };
    let result = match infer_client
        .speech2text_transcribe(
            Some(hef_path),
            audio_base64,
            Some(request.language.clone()),
            S2T_TIMEOUT_MS,
        )
        .await
    {
        Ok(result) => result,
        Err(error) => {
            return openai_error(
                format!("Transcription failed: {error}"),
                "server_error",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    };

    match request.response_format.as_deref() {
        Some("text") => (
            [(axum::http::header::CONTENT_TYPE, "text/plain")],
            result.text,
        )
            .into_response(),
        Some("verbose_json") => {
            let duration = result
                .segments
                .last()
                .map(|segment| segment.end)
                .unwrap_or(0.0);
            Json(json!({
                "task": "transcribe",
                "language": request.language,
                "duration": duration,
                "text": result.text,
                "segments": result.segments.iter().enumerate().map(|(index, segment)| {
                    json!({"id": index, "start": segment.start, "end": segment.end, "text": segment.text})
                }).collect::<Vec<_>>(),
            }))
            .into_response()
        }
        _ => Json(json!({"text": result.text})).into_response(),
    }
}

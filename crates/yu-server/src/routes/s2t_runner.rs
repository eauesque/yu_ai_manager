//! Background batch speech2text transcription for selected video files.
//! Mirrors `caption_runner.rs`'s shape (dedicated progress struct + SSE
//! `video_s2t.{start,progress,complete}` events, matching Python's
//! `event_bus.emit()` channel names so the existing UI keeps working
//! unmodified) rather than the generic `JobManager`, since -- like
//! captioning -- this is a single-purpose runner with its own status shape.

use std::{
    sync::atomic::{AtomicBool, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

use axum::{
    extract::{Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    sse::SseEvent,
    state::SharedState,
};

use super::{
    s2t::{ffmpeg_wav_base64, hef_available, save_transcript, DEFAULT_S2T_MODEL},
    vector_store::get_file_paths_by_ids,
};

#[derive(Debug, Clone)]
struct S2tProgress {
    running: bool,
    total: u64,
    processed: u64,
    errors: u64,
    started_at: u64,
    elapsed: f64,
}

pub struct S2tRunner {
    progress: tokio::sync::Mutex<S2tProgress>,
    stop_requested: AtomicBool,
}

impl S2tRunner {
    pub fn new() -> Self {
        Self {
            progress: tokio::sync::Mutex::new(S2tProgress {
                running: false,
                total: 0,
                processed: 0,
                errors: 0,
                started_at: 0,
                elapsed: 0.0,
            }),
            stop_requested: AtomicBool::new(false),
        }
    }

    async fn start(&self) -> Result<(), &'static str> {
        let mut progress = self.progress.lock().await;
        if progress.running {
            return Err("already_running");
        }
        self.stop_requested.store(false, Ordering::Release);
        *progress = S2tProgress {
            running: true,
            total: 0,
            processed: 0,
            errors: 0,
            started_at: now_epoch(),
            elapsed: 0.0,
        };
        Ok(())
    }

    async fn status(&self) -> Value {
        let mut progress = self.progress.lock().await;
        if progress.running && progress.started_at != 0 {
            progress.elapsed = rounded_elapsed(progress.started_at);
        }
        json!({"running": progress.running, "total": progress.total, "processed": progress.processed,
            "errors": progress.errors, "started_at": progress.started_at, "elapsed": progress.elapsed})
    }

    fn should_stop(&self) -> bool {
        self.stop_requested.load(Ordering::Acquire)
    }

    async fn update(&self, update: impl FnOnce(&mut S2tProgress)) {
        update(&mut *self.progress.lock().await);
    }

    #[cfg(test)]
    fn request_stop_for_test(&self) {
        self.stop_requested.store(true, Ordering::Release);
    }
}

impl Default for S2tRunner {
    fn default() -> Self {
        Self::new()
    }
}

fn admin_or_response(
    state: &SharedState,
    auth: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(
        state.config.pin_auth_enabled,
        auth.map(|extension| &extension.0),
    )
}

struct StartRequest {
    file_ids: Vec<i64>,
    model: String,
    language: String,
}

fn parse_start_value(value: &Value) -> Result<StartRequest, Response> {
    let file_ids: Vec<i64> = value
        .get("file_ids")
        .and_then(Value::as_array)
        .map(|ids| {
            ids.iter()
                .filter_map(Value::as_i64)
                .filter(|id| *id > 0)
                .collect()
        })
        .unwrap_or_default();
    if file_ids.is_empty() {
        return Err(bad_request("No valid file_ids"));
    }
    let model = value
        .get("model")
        .and_then(Value::as_str)
        .unwrap_or(DEFAULT_S2T_MODEL)
        .to_string();
    let language = value
        .get("language")
        .and_then(Value::as_str)
        .unwrap_or("en")
        .to_string();
    Ok(StartRequest {
        file_ids,
        model,
        language,
    })
}

fn bad_request(message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"status": "error", "message": message})),
    )
        .into_response()
}

pub async fn start_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let request = match parse_start_value(&body) {
        Ok(request) => request,
        Err(response) => return response,
    };
    if state.infer_client.is_none() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"status": "error", "message": "Hailo speech2text sidecar is unavailable"})),
        )
            .into_response();
    }
    let Some(_hef_path) = hef_available(&request.model) else {
        return bad_request(&format!("Model '{}' not downloaded yet", request.model));
    };
    if let Err(status) = state.s2t_runner.start().await {
        let mut value = state.s2t_runner.status().await;
        value["status"] = json!(status);
        return Json(value).into_response();
    }
    let total = request.file_ids.len();
    let task_state = state.clone();
    tokio::spawn(async move {
        run_worker(task_state, request).await;
    });
    Json(json!({"status": "started", "total": total})).into_response()
}

pub async fn status_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    Json(state.s2t_runner.status().await).into_response()
}

async fn run_worker(state: SharedState, request: StartRequest) {
    let total = request.file_ids.len() as u64;
    let hef_path = match hef_available(&request.model) {
        Some(path) => path,
        None => {
            finish(&state, "S2T init failed: model not downloaded", 0, 0, total).await;
            return;
        }
    };
    emit(
        &state,
        "video_s2t.start",
        json!({"total": total, "model": request.model}),
    );
    let paths = match get_file_paths_by_ids(&state.db_read, &request.file_ids).await {
        Ok(paths) => paths,
        Err(error) => {
            finish(&state, &format!("S2T init failed: {error}"), 0, 0, total).await;
            return;
        }
    };
    let mut processed = 0u64;
    let mut errors = 0u64;
    for file_id in request.file_ids {
        if state.s2t_runner.should_stop() {
            break;
        }
        let Some(video_path) = paths.get(&file_id) else {
            errors += 1;
            update_progress_and_emit(&state, processed, errors, total).await;
            continue;
        };
        let outcome =
            transcribe_one(&state, &hef_path, video_path, &request.language, file_id).await;
        match outcome {
            Ok(()) => processed += 1,
            Err(()) => errors += 1,
        }
        update_progress_and_emit(&state, processed, errors, total).await;
    }
    let reason = if state.s2t_runner.should_stop() {
        "stopped"
    } else {
        "complete"
    };
    finish(&state, reason, processed, errors, total).await;
}

async fn transcribe_one(
    state: &SharedState,
    hef_path: &str,
    video_path: &str,
    language: &str,
    file_id: i64,
) -> Result<(), ()> {
    let audio_base64 = ffmpeg_wav_base64(std::path::Path::new(video_path))
        .await
        .map_err(|_| ())?;
    let Some(infer_client) = state.infer_client.as_ref() else {
        return Err(());
    };
    let result = infer_client
        .speech2text_transcribe(
            Some(hef_path.to_string()),
            audio_base64,
            Some(language.to_string()),
            120_000,
        )
        .await
        .map_err(|_| ())?;
    save_transcript(state, file_id, &result)
        .await
        .map_err(|_| ())
}

async fn update_progress_and_emit(state: &SharedState, processed: u64, errors: u64, total: u64) {
    state
        .s2t_runner
        .update(|progress| {
            progress.processed = processed;
            progress.errors = errors;
        })
        .await;
    emit(
        state,
        "video_s2t.progress",
        progress_data(
            processed,
            errors,
            total,
            rounded_elapsed(now_started_at(state).await),
        ),
    );
}

async fn now_started_at(state: &SharedState) -> u64 {
    state.s2t_runner.progress.lock().await.started_at
}

async fn finish(state: &SharedState, reason: &str, processed: u64, errors: u64, total: u64) {
    let elapsed = rounded_elapsed(now_started_at(state).await);
    state
        .s2t_runner
        .update(|progress| {
            progress.running = false;
            progress.elapsed = elapsed;
        })
        .await;
    emit(
        state,
        "video_s2t.complete",
        complete_data(reason, processed, errors, total, elapsed),
    );
}

fn emit(state: &SharedState, event_type: &str, data: Value) {
    state.sse_hub.send(sse_event(event_type, data));
}

fn sse_event(event_type: &str, data: Value) -> SseEvent {
    SseEvent {
        event_type: event_type.to_string(),
        timestamp: now_secs_f64(),
        data,
        source: "video_s2t".to_string(),
    }
}

fn progress_data(processed: u64, errors: u64, total: u64, elapsed: f64) -> Value {
    json!({"processed": processed, "total": total, "errors": errors,
        "percent": percent(processed, errors, total), "elapsed": elapsed})
}

fn complete_data(reason: &str, processed: u64, errors: u64, total: u64, elapsed: f64) -> Value {
    json!({"reason": reason, "processed": processed, "errors": errors, "total": total,
        "elapsed_seconds": elapsed})
}

fn percent(processed: u64, errors: u64, total: u64) -> f64 {
    if total == 0 {
        0.0
    } else {
        round_one((processed + errors) as f64 / total as f64 * 100.0)
    }
}
fn now_epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn now_secs_f64() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
fn rounded_elapsed(started_at: u64) -> f64 {
    round_one(now_secs_f64() - started_at as f64)
}
fn round_one(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn start_filters_invalid_file_ids() {
        let request = parse_start_value(&json!({"file_ids": [1, 0, -1, "2", 3]})).unwrap();
        assert_eq!(request.file_ids, [1, 3]);
        assert!(parse_start_value(&json!({"file_ids": []})).is_err());
    }

    #[test]
    fn start_request_applies_defaults() {
        let defaults = parse_start_value(&json!({"file_ids": [1]})).unwrap();
        assert_eq!(defaults.model, DEFAULT_S2T_MODEL);
        assert_eq!(defaults.language, "en");
        let supplied =
            parse_start_value(&json!({"file_ids": [1], "model": "whisper-tiny", "language": "ja"}))
                .unwrap();
        assert_eq!(supplied.model, "whisper-tiny");
        assert_eq!(supplied.language, "ja");
    }

    #[test]
    fn percent_and_rounding_match_python() {
        assert_eq!(percent(0, 0, 0), 0.0);
        assert_eq!(percent(1, 1, 3), 66.7);
        assert_eq!(round_one(1.24), 1.2);
        assert_eq!(round_one(1.25), 1.3);
    }

    #[test]
    fn s2t_event_payloads_and_source_match_ui_contract() {
        let progress = progress_data(1, 2, 5, 3.0);
        assert!(progress.get("elapsed").is_some());
        assert!(progress.get("elapsed_seconds").is_none());
        let complete = complete_data("complete", 1, 2, 5, 3.0);
        assert!(complete.get("elapsed_seconds").is_some());
        assert!(complete.get("elapsed").is_none());
        assert_eq!(
            sse_event("video_s2t.progress", progress).source,
            "video_s2t"
        );
    }

    #[tokio::test]
    async fn stop_reflects_running_state() {
        let runner = S2tRunner::new();
        assert!(!runner.should_stop());
        runner.start().await.unwrap();
        runner.request_stop_for_test();
        assert!(runner.should_stop());
    }
}

//! Background, cursor-based CLIP image index construction.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use axum::{
    extract::{Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

use super::{
    clip_search::call_clip_image,
    vector_store::{self, DEFAULT_MODEL},
};

const DEFAULT_BATCH_SIZE: u16 = 32;
const MAX_BATCH_SIZE: u16 = 256;
const VIDEO_EXTENSIONS: &[&str] = &["webm", "mp4", "avi", "mov", "mkv", "m4v", "ogv"];

#[derive(Debug, Clone)]
struct IndexProgress {
    running: bool,
    total: u64,
    processed: u64,
    errors: u64,
    skipped_videos: u64,
    started_at: u64,
    message: String,
}

pub struct ClipIndexer {
    progress: tokio::sync::Mutex<IndexProgress>,
    stop_requested: AtomicBool,
}

impl ClipIndexer {
    pub fn new() -> Self {
        Self {
            progress: tokio::sync::Mutex::new(IndexProgress {
                running: false,
                total: 0,
                processed: 0,
                errors: 0,
                skipped_videos: 0,
                started_at: 0,
                message: String::new(),
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
        *progress = IndexProgress {
            running: true,
            total: 0,
            processed: 0,
            errors: 0,
            skipped_videos: 0,
            started_at: now_epoch(),
            message: "Initializing semantic indexer".to_string(),
        };
        Ok(())
    }

    async fn status(&self) -> Value {
        let progress = self.progress.lock().await.clone();
        json!({
            "running": progress.running, "total": progress.total, "processed": progress.processed,
            "errors": progress.errors, "skipped_videos": progress.skipped_videos,
            "started_at": progress.started_at, "elapsed": now_epoch().saturating_sub(progress.started_at),
            "message": progress.message, "indexed": progress.processed,
            "unindexed": progress.total.saturating_sub(progress.processed),
        })
    }

    async fn stop(&self) -> bool {
        let progress = self.progress.lock().await;
        if !progress.running {
            return false;
        }
        self.stop_requested.store(true, Ordering::Release);
        true
    }

    fn should_stop(&self) -> bool {
        self.stop_requested.load(Ordering::Acquire)
    }
    async fn update(&self, update: impl FnOnce(&mut IndexProgress)) {
        update(&mut *self.progress.lock().await);
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

pub async fn start_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Result<Json<Value>, axum::extract::rejection::JsonRejection>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let request = match parse_start_request(body) {
        Ok(request) => request,
        Err(response) => return response,
    };
    if request.distributed {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"status":"error", "message":"distributed indexing is not implemented"})),
        )
            .into_response();
    }
    if state.infer_client.is_none() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"status":"error", "message":"CLIP image sidecar is unavailable"})),
        )
            .into_response();
    }
    if let Err(status) = state.clip_indexer.start().await {
        return Json(json!({"status":status, "message":"Semantic indexing is already running"}))
            .into_response();
    }
    let state_for_task = state.clone();
    tokio::spawn(async move {
        run_worker(state_for_task, request.batch_size).await;
    });
    Json(json!({"status":"started", "total":0})).into_response()
}

pub async fn status_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    Json(state.clip_indexer.status().await).into_response()
}

pub async fn stop_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let status = if state.clip_indexer.stop().await {
        "stopping"
    } else {
        "not_running"
    };
    Json(json!({"status":status})).into_response()
}

pub async fn clear_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    if state.clip_indexer.stop().await {
        return (
            StatusCode::CONFLICT,
            Json(json!({"status":"error", "message":"indexing is stopping"})),
        )
            .into_response();
    }
    let deleted = match vector_store::delete_all_vectors(&state.vectors_db, DEFAULT_MODEL).await {
        Ok(count) => count,
        Err(error) => {
            tracing::error!(%error, "failed to clear CLIP vectors");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status":"error", "message":"Failed to clear vectors"})),
            )
                .into_response();
        }
    };
    if let Err(error) = state.clip_index.clear().await {
        tracing::error!(%error, "failed to clear CLIP ANN index");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"status":"error", "message":"Failed to clear index"})),
        )
            .into_response();
    }
    state.clip_runtime_cache.invalidate().await;
    Json(json!({"status":"ok", "deleted":deleted})).into_response()
}

struct StartRequest {
    batch_size: u16,
    distributed: bool,
}

/// Parse optional fields explicitly. This keeps malformed JSON, non-object
/// roots, type errors, and absent optional fields distinguishable instead of
/// hiding all of them behind serde defaults.
fn parse_start_request(
    body: Result<Json<Value>, axum::extract::rejection::JsonRejection>,
) -> Result<StartRequest, Response> {
    let value = body
        .map_err(|_| bad_request("Invalid JSON request body"))?
        .0;
    let object = value
        .as_object()
        .ok_or_else(|| bad_request("Request body must be a JSON object"))?;
    let batch_size = match object.get("batch_size") {
        None => DEFAULT_BATCH_SIZE,
        Some(Value::Number(value)) => value
            .as_u64()
            .and_then(|value| u16::try_from(value).ok())
            .filter(|value| (1..=MAX_BATCH_SIZE).contains(value))
            .ok_or_else(|| bad_request("batch_size must be an integer between 1 and 256"))?,
        Some(_) => return Err(bad_request("batch_size must be an integer")),
    };
    match object.get("backend") {
        None => {}
        Some(Value::String(value)) if matches!(value.as_str(), "auto" | "hailo" | "hailo-10h") => {}
        Some(Value::String(_)) => {
            return Err(bad_request("backend must be auto or hailo"));
        }
        Some(_) => return Err(bad_request("backend must be a string")),
    }
    let distributed = match object.get("distributed") {
        None => false,
        Some(Value::Bool(value)) => *value,
        Some(_) => return Err(bad_request("distributed must be a boolean")),
    };
    Ok(StartRequest {
        batch_size,
        distributed,
    })
}

async fn run_worker(state: SharedState, batch_size: u16) {
    let mut after_id = 0_i64;
    let mut reason = "complete";
    loop {
        if state.clip_indexer.should_stop() {
            reason = "stopped";
            break;
        }
        let file_ids = match vector_store::get_unindexed_file_ids_cursor(
            &state.db_read,
            &state.vectors_db_read,
            DEFAULT_MODEL,
            after_id,
            i64::from(batch_size),
        )
        .await
        {
            Ok(ids) => ids,
            Err(error) => {
                tracing::error!(%error, "CLIP index cursor failed");
                reason = "database error";
                break;
            }
        };
        let Some(last_id) = file_ids.last().copied() else {
            break;
        };
        after_id = last_id;
        state
            .clip_indexer
            .update(|progress| {
                progress.total += file_ids.len() as u64;
                progress.message = "Indexing images".to_string();
            })
            .await;
        let paths = match vector_store::get_file_paths_by_ids(&state.db_read, &file_ids).await {
            Ok(paths) => paths,
            Err(error) => {
                tracing::error!(%error, "CLIP path lookup failed");
                reason = "database error";
                break;
            }
        };
        let mut ids = Vec::new();
        let mut vectors = Vec::new();
        for file_id in file_ids {
            if state.clip_indexer.should_stop() {
                reason = "stopped";
                break;
            }
            let Some(path) = paths.get(&file_id) else {
                state
                    .clip_indexer
                    .update(|progress| progress.errors += 1)
                    .await;
                continue;
            };
            // Video keyframe embeddings are intentionally vN scope only.
            if is_video(path) {
                state
                    .clip_indexer
                    .update(|progress| progress.skipped_videos += 1)
                    .await;
                continue;
            }
            match call_clip_image(&state, std::path::Path::new(path)).await {
                Ok(vector) => {
                    ids.push(file_id);
                    vectors.push(vector);
                }
                Err(error) => {
                    tracing::debug!(?error, file_id, "CLIP image encoding skipped");
                    state
                        .clip_indexer
                        .update(|progress| progress.errors += 1)
                        .await;
                }
            }
        }
        if !ids.is_empty() {
            match vector_store::save_vectors_batch(&state.vectors_db, &ids, &vectors, DEFAULT_MODEL)
                .await
            {
                Ok(count) => {
                    state
                        .clip_indexer
                        .update(|progress| progress.processed += count as u64)
                        .await
                }
                Err(error) => {
                    tracing::error!(%error, "CLIP vector save failed");
                    reason = "vector write error";
                    break;
                }
            }
        }
        if reason == "stopped" {
            break;
        }
    }
    if reason == "complete" && !state.clip_indexer.should_stop() {
        if let Err(error) = state.clip_index.rebuild(&state.vectors_db_read, None).await {
            tracing::error!(%error, "CLIP index rebuild failed");
            reason = "index rebuild error";
        }
    }
    state
        .clip_indexer
        .update(|progress| {
            progress.running = false;
            progress.message = reason.to_string();
        })
        .await;
    state.clip_runtime_cache.invalidate().await;
}

fn is_video(path: &str) -> bool {
    let path = path.to_ascii_lowercase();
    VIDEO_EXTENSIONS
        .iter()
        .any(|extension| path.ends_with(&format!(".{extension}")))
}
fn now_epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn bad_request(message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"status":"error", "message":message})),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn start_body_validation_is_strict() {
        assert!(parse_start_request(Ok(Json(json!({"batch_size": 1})))).is_ok());
        assert!(parse_start_request(Ok(Json(json!({"batch_size": 257})))).is_err());
        assert!(parse_start_request(Ok(Json(json!({"batch_size": "32"})))).is_err());
        assert!(parse_start_request(Ok(Json(json!([])))).is_err());
        assert!(parse_start_request(Ok(Json(json!({"distributed": true})))).is_ok());
        assert!(parse_start_request(Ok(Json(json!({"backend": "onnx"})))).is_err());
    }
    #[test]
    fn excludes_video_extensions() {
        assert!(is_video("clip.MP4"));
        assert!(!is_video("clip.png"));
    }

    #[tokio::test]
    async fn index_routes_require_admin_scope() {
        let state = crate::state::semantic_test_state(true).await;
        assert_eq!(
            start_handler(State(state.clone()), None, Ok(Json(json!({}))))
                .await
                .status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            status_handler(State(state.clone()), None).await.status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            stop_handler(State(state.clone()), None).await.status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            clear_handler(State(state), None).await.status(),
            StatusCode::FORBIDDEN
        );
    }
}

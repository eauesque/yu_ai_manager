//! Background VLM caption generation for selected files.

use std::{
    collections::HashSet,
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

use super::{auto_stubs::model_name_to_hef_path, clip_search::read_image_as_base64, vector_store};

const DEFAULT_PROMPT: &str = "Describe this image in detail.";
const DEFAULT_MODEL: &str = "qwen2-vl-2b-instruct";

#[derive(Debug, Clone)]
struct CaptionProgress {
    running: bool,
    total: u64,
    processed: u64,
    errors: u64,
    started_at: u64,
    elapsed: f64,
    message: String,
}

pub struct CaptionRunner {
    progress: tokio::sync::Mutex<CaptionProgress>,
    stop_requested: AtomicBool,
}

impl CaptionRunner {
    pub fn new() -> Self {
        Self {
            progress: tokio::sync::Mutex::new(CaptionProgress {
                running: false,
                total: 0,
                processed: 0,
                errors: 0,
                started_at: 0,
                elapsed: 0.0,
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
        *progress = CaptionProgress {
            running: true,
            total: 0,
            processed: 0,
            errors: 0,
            started_at: now_epoch(),
            elapsed: 0.0,
            message: String::new(),
        };
        Ok(())
    }

    async fn status(&self) -> Value {
        let mut progress = self.progress.lock().await;
        if progress.running && progress.started_at != 0 {
            progress.elapsed = rounded_elapsed(progress.started_at);
        }
        json!({"running": progress.running, "total": progress.total, "processed": progress.processed,
            "errors": progress.errors, "started_at": progress.started_at, "elapsed": progress.elapsed,
            "message": progress.message})
    }

    async fn stop(&self) -> bool {
        if !self.progress.lock().await.running {
            return false;
        }
        self.stop_requested.store(true, Ordering::Release);
        true
    }

    fn should_stop(&self) -> bool {
        self.stop_requested.load(Ordering::Acquire)
    }

    #[cfg(test)]
    fn request_stop_for_test(&self) {
        self.stop_requested.store(true, Ordering::Release);
    }

    async fn update(&self, update: impl FnOnce(&mut CaptionProgress)) {
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
    if state.infer_client.is_none() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"status":"error", "message":"VLM sidecar is unavailable"})),
        )
            .into_response();
    }
    if let Err(status) = state.caption_runner.start().await {
        let mut value = state.caption_runner.status().await;
        value["status"] = json!(status);
        return Json(value).into_response();
    }
    let total = request.file_ids.len();
    let task_state = state.clone();
    tokio::spawn(async move {
        run_worker(task_state, request).await;
    });
    Json(json!({"status":"started", "total":total})).into_response()
}

pub async fn status_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    Json(state.caption_runner.status().await).into_response()
}

pub async fn stop_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    Json(json!({"status": if state.caption_runner.stop().await { "stopping" } else { "not_running" }})).into_response()
}

struct StartRequest {
    file_ids: Vec<i64>,
    prompt: String,
    model: String,
}

fn parse_start_request(
    body: Result<Json<Value>, axum::extract::rejection::JsonRejection>,
) -> Result<StartRequest, Response> {
    let value = body
        .map_err(|_| bad_request("Invalid JSON request body"))?
        .0;
    parse_start_value(value)
}

fn parse_start_value(value: Value) -> Result<StartRequest, Response> {
    let object = value
        .as_object()
        .ok_or_else(|| bad_request("Request body must be a JSON object"))?;
    let file_ids = object
        .get("file_ids")
        .and_then(Value::as_array)
        .map(|ids| {
            ids.iter()
                .filter_map(Value::as_i64)
                .filter(|id| *id > 0)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if file_ids.is_empty() {
        return Err(bad_request("No valid file_ids"));
    }
    let prompt = optional_string(object, "prompt", DEFAULT_PROMPT)?;
    let model = optional_string(object, "model", DEFAULT_MODEL)?;
    Ok(StartRequest {
        file_ids,
        prompt,
        model,
    })
}

fn optional_string(
    object: &serde_json::Map<String, Value>,
    key: &str,
    default: &str,
) -> Result<String, Response> {
    match object.get(key) {
        None => Ok(default.to_string()),
        Some(Value::String(value)) => Ok(value.clone()),
        Some(_) => Err(bad_request(&format!("{key} must be a string"))),
    }
}

async fn run_worker(state: SharedState, request: StartRequest) {
    let total = request.file_ids.len() as u64;
    let hef_path = match resolve_caption_hef(&request.model) {
        Ok(path) => path,
        Err(reason) => {
            finish(&state, &format!("VLM init failed: {reason}"), 0, 0, total).await;
            return;
        }
    };
    run_worker_with_hef(state, request, hef_path).await;
}

fn resolve_caption_hef(model: &str) -> Result<String, String> {
    validate_caption_hef(model, model_name_to_hef_path(model))
}

fn validate_caption_hef(model: &str, hef_path: String) -> Result<String, String> {
    std::path::Path::new(&hef_path)
        .exists()
        .then_some(hef_path)
        .ok_or_else(|| format!("model '{model}' is not downloaded"))
}

async fn run_worker_with_hef(state: SharedState, request: StartRequest, hef_path: String) {
    let total = request.file_ids.len() as u64;
    state
        .caption_runner
        .update(|progress| {
            progress.running = true;
            progress.processed = 0;
            progress.errors = 0;
            progress.total = total;
            progress.started_at = now_epoch();
            progress.elapsed = 0.0;
            progress.message.clear();
        })
        .await;
    emit(
        &state,
        "vlm_caption.start",
        json!({"total":total, "model":request.model}),
    );
    let paths = match vector_store::get_file_paths_by_ids(&state.db_read, &request.file_ids).await {
        Ok(paths) => paths,
        Err(error) => {
            finish(&state, &format!("VLM init failed: {error}"), 0, 0, total).await;
            return;
        }
    };
    let mut processed = 0;
    let mut errors = 0;
    let mut failed_ids = HashSet::new();
    for file_id in request.file_ids {
        if state.caption_runner.should_stop() {
            break;
        }
        let Some(path) = paths.get(&file_id) else {
            errors += 1;
            failed_ids.insert(file_id);
            continue;
        };
        if failed_ids.contains(&file_id) {
            continue;
        }
        let caption = match read_image_as_base64(&state, std::path::Path::new(path)).await {
            Ok(frame) => match state.infer_client.as_ref() {
                Some(client) => client
                    .vlm_generate(
                        hef_path.clone(),
                        request.prompt.clone(),
                        vec![frame],
                        crate::infer_client::DEFAULT_GENERATE_TIMEOUT_MS,
                    )
                    .await
                    .map_err(|error| error.to_string()),
                None => Err("VLM sidecar is unavailable".to_string()),
            },
            Err(error) => Err(format!("{error:?}")),
        };
        match caption {
            Ok(caption) if !caption.trim().is_empty() => {
                if let Err(error) = save_caption(&state, file_id, caption.trim()).await {
                    tracing::debug!(%error, file_id, "caption save failed");
                    errors += 1;
                    failed_ids.insert(file_id);
                } else {
                    processed += 1;
                }
            }
            Ok(_) | Err(_) => {
                errors += 1;
                failed_ids.insert(file_id);
            }
        }
        update_progress_and_emit(&state, processed, errors, total).await;
    }
    let reason = if state.caption_runner.should_stop() {
        "stopped"
    } else {
        "complete"
    };
    finish(&state, reason, processed, errors, total).await;
}

async fn update_progress_and_emit(state: &SharedState, processed: u64, errors: u64, total: u64) {
    state
        .caption_runner
        .update(|progress| {
            progress.processed = processed;
            progress.errors = errors;
        })
        .await;
    emit(
        state,
        "vlm_caption.progress",
        progress_data(
            processed,
            errors,
            total,
            rounded_elapsed(now_started_at(state).await),
        ),
    );
}

async fn now_started_at(state: &SharedState) -> u64 {
    state.caption_runner.progress.lock().await.started_at
}

async fn save_caption(state: &SharedState, file_id: i64, caption: &str) -> Result<(), sqlx::Error> {
    sqlx::query("INSERT INTO file_annotations (file_id, source, key, value, confidence, created_at) VALUES (?, ?, ?, ?, ?, unixepoch()) ON CONFLICT(file_id, source, key) DO UPDATE SET value=excluded.value, confidence=excluded.confidence, created_at=excluded.created_at")
        .bind(file_id).bind("hailo:vlm").bind("caption").bind(caption).bind(Option::<f64>::None).execute(&state.db).await?;
    Ok(())
}

async fn finish(state: &SharedState, reason: &str, processed: u64, errors: u64, total: u64) {
    let elapsed = rounded_elapsed(now_started_at(state).await);
    state
        .caption_runner
        .update(|progress| {
            progress.running = false;
            progress.elapsed = elapsed;
            progress.message = reason.to_string();
        })
        .await;
    emit(
        state,
        "vlm_caption.complete",
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
        source: "vlm_captioner".to_string(),
    }
}

fn progress_data(processed: u64, errors: u64, total: u64, elapsed: f64) -> Value {
    json!({"processed":processed, "total":total, "errors":errors,
        "percent": percent(processed, errors, total), "elapsed":elapsed})
}

fn complete_data(reason: &str, processed: u64, errors: u64, total: u64, elapsed: f64) -> Value {
    json!({"reason":reason, "processed":processed, "errors":errors, "total":total,
        "elapsed_seconds":elapsed})
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
    fn start_filters_invalid_file_ids() {
        let request =
            parse_start_request(Ok(Json(json!({"file_ids":[1, 0, -1, "2", 3]})))).unwrap();
        assert_eq!(request.file_ids, [1, 3]);
        assert!(parse_start_request(Ok(Json(json!({"file_ids":[]})))).is_err());
    }

    #[test]
    fn start_request_applies_defaults_and_accepts_strings() {
        let defaults = parse_start_value(json!({"file_ids":[1]})).unwrap();
        assert_eq!(defaults.prompt, DEFAULT_PROMPT);
        assert_eq!(defaults.model, DEFAULT_MODEL);
        let supplied =
            parse_start_value(json!({"file_ids":[1], "prompt":"brief", "model":"custom"})).unwrap();
        assert_eq!(supplied.prompt, "brief");
        assert_eq!(supplied.model, "custom");
    }

    #[test]
    fn start_request_rejects_invalid_bodies() {
        assert!(parse_start_value(json!([])).is_err());
        assert!(parse_start_value(json!({"file_ids":[1], "prompt":false})).is_err());
        assert!(parse_start_value(json!({"file_ids":[1], "model":7})).is_err());
    }

    #[tokio::test]
    async fn malformed_json_is_rejected() {
        use axum::{body::Body, http::Request, routing::post, Router};
        use tower::ServiceExt;

        let state = crate::state::semantic_test_state(false).await;
        let app = Router::new()
            .route("/", post(start_handler))
            .with_state(state);
        let response = app
            .oneshot(
                Request::post("/")
                    .header("content-type", "application/json")
                    .body(Body::from("{"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn status_has_exact_keys_and_updates_running_elapsed() {
        let runner = CaptionRunner::new();
        runner
            .update(|progress| {
                progress.running = true;
                progress.started_at = now_epoch().saturating_sub(2);
                progress.elapsed = 99.0;
            })
            .await;
        let status = runner.status().await;
        let keys: std::collections::BTreeSet<_> = status
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        assert_eq!(
            keys,
            [
                "elapsed",
                "errors",
                "message",
                "processed",
                "running",
                "started_at",
                "total"
            ]
            .into_iter()
            .collect()
        );
        assert!(status["elapsed"].as_f64().unwrap() >= 1.0);
        runner
            .update(|progress| {
                progress.running = false;
                progress.elapsed = 7.5;
            })
            .await;
        assert_eq!(runner.status().await["elapsed"], 7.5);
    }

    #[test]
    fn percent_and_rounding_match_python() {
        assert_eq!(percent(0, 0, 0), 0.0);
        assert_eq!(percent(1, 1, 3), 66.7);
        assert_eq!(round_one(1.24), 1.2);
        assert_eq!(round_one(1.25), 1.3);
    }

    #[tokio::test]
    async fn stop_reflects_running_state() {
        let runner = CaptionRunner::new();
        assert!(!runner.stop().await);
        runner.start().await.unwrap();
        assert!(runner.stop().await);
    }

    #[test]
    fn caption_event_payloads_and_source_match_ui_contract() {
        let progress = progress_data(1, 2, 5, 3.0);
        assert!(progress.get("elapsed").is_some());
        assert!(progress.get("elapsed_seconds").is_none());
        let complete = complete_data("complete", 1, 2, 5, 3.0);
        assert!(complete.get("elapsed_seconds").is_some());
        assert!(complete.get("elapsed").is_none());
        assert_eq!(
            sse_event("vlm_caption.progress", progress).source,
            "vlm_captioner"
        );
    }

    #[test]
    fn caption_hef_validation_requires_an_existing_file() {
        let temp = tempfile::NamedTempFile::new().unwrap();
        let path = temp.path().to_string_lossy().into_owned();
        assert_eq!(validate_caption_hef("test", path.clone()), Ok(path));
        assert_eq!(
            validate_caption_hef("missing", "definitely-missing.hef".to_string()),
            Err("model 'missing' is not downloaded".to_string())
        );
    }

    #[test]
    fn caption_routes_are_registered_to_native_handlers() {
        let source = include_str!("../main.rs")
            .lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n");
        for (path, handler) in [
            (
                "/ext/hailo-semantic/api/caption/start",
                "post(routes::caption_runner::start_handler)",
            ),
            (
                "/ext/hailo-semantic/api/caption/status",
                "get(routes::caption_runner::status_handler)",
            ),
            (
                "/ext/hailo-semantic/api/caption/stop",
                "post(routes::caption_runner::stop_handler)",
            ),
        ] {
            let route = source.split(path).nth(1).unwrap();
            assert!(route.contains(handler), "{path} must use {handler}");
        }
    }

    async fn worker_test_state(
        text: &'static str,
    ) -> (
        SharedState,
        tempfile::TempDir,
        String,
        std::sync::Arc<std::sync::atomic::AtomicUsize>,
        std::sync::Arc<tokio::sync::Mutex<Option<std::sync::Arc<CaptionRunner>>>>,
    ) {
        use axum::{routing::post, Json, Router};
        use std::sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        };

        let counter = Arc::new(AtomicUsize::new(0));
        let requests = counter.clone();
        let stop_target = Arc::new(tokio::sync::Mutex::new(None::<Arc<CaptionRunner>>));
        let handler_stop_target = stop_target.clone();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().route(
                    "/v1/infer/vlm/generate",
                    post(move || {
                        let requests = requests.clone();
                        let stop_target = handler_stop_target.clone();
                        async move {
                            if requests.fetch_add(1, Ordering::Relaxed) == 0 {
                                if let Some(runner) = stop_target.lock().await.as_ref() {
                                    runner.request_stop_for_test();
                                }
                            }
                            Json(
                                json!({"ok":true,"error":null,"data":{"hef_path":"x","text":text}}),
                            )
                        }
                    }),
                ),
            )
            .await
            .unwrap();
        });
        let dirs = crate::routes::wd_tagger::tests::test_dirs();
        let root = tempfile::tempdir().unwrap();
        let state = crate::routes::wd_tagger::tests::test_state_ex(
            &dirs,
            json!({"scan_roots":[{"path":root.path().to_string_lossy()}]}),
            Some(crate::infer_client::InferClient::new(
                format!("http://{address}"),
                String::new(),
            )),
            true,
            std::path::PathBuf::from("."),
        )
        .await;
        sqlx::query("CREATE TABLE file_annotations (file_id INTEGER, source TEXT, key TEXT, value TEXT, confidence REAL, created_at INTEGER, UNIQUE(file_id, source, key))").execute(&state.db).await.unwrap();
        let image = root.path().join("image.png");
        image::RgbImage::new(1, 1).save(&image).unwrap();
        let hef = root.path().join("model.hef");
        std::fs::write(&hef, []).unwrap();
        let hef_path = hef.to_string_lossy().into_owned();
        (state, root, hef_path, counter, stop_target)
    }

    #[tokio::test]
    async fn worker_persists_trimmed_caption_with_annotation_identity() {
        let (state, root, hef, _, _) = worker_test_state("  a caption  ").await;
        let image = root.path().join("image.png");
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (88, ?, 0)")
            .bind(image.to_string_lossy().as_ref())
            .execute(&state.db)
            .await
            .unwrap();
        let mut events = state.sse_hub.subscribe();
        run_worker_with_hef(
            state.clone(),
            StartRequest {
                file_ids: vec![88],
                prompt: DEFAULT_PROMPT.to_string(),
                model: DEFAULT_MODEL.to_string(),
            },
            hef,
        )
        .await;
        let row = sqlx::query_as::<_, (String, String, String, Option<f64>)>(
            "SELECT source, key, value, confidence FROM file_annotations WHERE file_id=88",
        )
        .fetch_one(&state.db)
        .await
        .unwrap();
        assert_eq!(
            row,
            (
                "hailo:vlm".to_string(),
                "caption".to_string(),
                "a caption".to_string(),
                None
            )
        );
        assert_eq!(state.caption_runner.status().await["message"], "complete");
    }

    #[tokio::test]
    async fn worker_rejects_empty_caption() {
        let (state, root, hef, _, _) = worker_test_state("  ").await;
        let image = root.path().join("image.png");
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (88, ?, 0)")
            .bind(image.to_string_lossy().as_ref())
            .execute(&state.db)
            .await
            .unwrap();
        run_worker_with_hef(
            state.clone(),
            StartRequest {
                file_ids: vec![88],
                prompt: DEFAULT_PROMPT.to_string(),
                model: DEFAULT_MODEL.to_string(),
            },
            hef,
        )
        .await;
        let status = state.caption_runner.status().await;
        assert_eq!(status["processed"], 0);
        assert_eq!(status["errors"], 1);
        assert_eq!(
            sqlx::query_scalar::<_, i64>("SELECT count(*) FROM file_annotations")
                .fetch_one(&state.db)
                .await
                .unwrap(),
            0
        );
    }

    #[tokio::test]
    async fn worker_does_not_retry_failed_duplicate_ids() {
        let (state, root, hef, requests, _) = worker_test_state("").await;
        let image = root.path().join("image.png");
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (88, ?, 0)")
            .bind(image.to_string_lossy().as_ref())
            .execute(&state.db)
            .await
            .unwrap();
        let mut events = state.sse_hub.subscribe();
        run_worker_with_hef(
            state.clone(),
            StartRequest {
                file_ids: vec![88, 88],
                prompt: DEFAULT_PROMPT.to_string(),
                model: DEFAULT_MODEL.to_string(),
            },
            hef,
        )
        .await;
        let status = state.caption_runner.status().await;
        assert_eq!(requests.load(std::sync::atomic::Ordering::Relaxed), 1);
        assert_eq!(status["errors"], 1);
        let event_types = [
            events.recv().await.unwrap().event_type.clone(),
            events.recv().await.unwrap().event_type.clone(),
            events.recv().await.unwrap().event_type.clone(),
        ];
        assert_eq!(
            event_types
                .iter()
                .filter(|event_type| event_type.as_str() == "vlm_caption.progress")
                .count(),
            1
        );
    }

    #[tokio::test]
    async fn missing_path_counts_without_a_sidecar_request_or_progress_event() {
        let (state, _root, hef, requests, _) = worker_test_state("a caption").await;
        let mut events = state.sse_hub.subscribe();
        run_worker_with_hef(
            state.clone(),
            StartRequest {
                file_ids: vec![99],
                prompt: DEFAULT_PROMPT.to_string(),
                model: DEFAULT_MODEL.to_string(),
            },
            hef,
        )
        .await;
        let status = state.caption_runner.status().await;
        assert_eq!(status["processed"], 0);
        assert_eq!(status["errors"], 0);
        assert_eq!(requests.load(std::sync::atomic::Ordering::Relaxed), 0);
        assert_eq!(
            sqlx::query_scalar::<_, i64>("SELECT count(*) FROM file_annotations")
                .fetch_one(&state.db)
                .await
                .unwrap(),
            0
        );
        assert_eq!(events.recv().await.unwrap().event_type, "vlm_caption.start");
        let complete = events.recv().await.unwrap();
        assert_eq!(complete.event_type, "vlm_caption.complete");
        assert_eq!(complete.data["processed"], 0);
        assert_eq!(complete.data["errors"], 1);
        assert!(events.try_recv().is_err());
    }

    #[tokio::test]
    async fn successful_path_emits_one_progress_event() {
        let (state, root, hef, _, _) = worker_test_state("a caption").await;
        let image = root.path().join("image.png");
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (88, ?, 0)")
            .bind(image.to_string_lossy().as_ref())
            .execute(&state.db)
            .await
            .unwrap();
        let mut events = state.sse_hub.subscribe();
        run_worker_with_hef(
            state,
            StartRequest {
                file_ids: vec![88],
                prompt: DEFAULT_PROMPT.to_string(),
                model: DEFAULT_MODEL.to_string(),
            },
            hef,
        )
        .await;
        assert_eq!(events.recv().await.unwrap().event_type, "vlm_caption.start");
        assert_eq!(
            events.recv().await.unwrap().event_type,
            "vlm_caption.progress"
        );
        assert_eq!(
            events.recv().await.unwrap().event_type,
            "vlm_caption.complete"
        );
    }

    #[tokio::test]
    async fn stop_halts_the_run_before_the_next_file() {
        let (state, root, hef, requests, stop_target) = worker_test_state("a caption").await;
        for id in [88, 89] {
            let image = root.path().join(format!("{id}.png"));
            image::RgbImage::new(1, 1).save(&image).unwrap();
            sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (?, ?, 0)")
                .bind(id)
                .bind(image.to_string_lossy().as_ref())
                .execute(&state.db)
                .await
                .unwrap();
        }
        *stop_target.lock().await = Some(state.caption_runner.clone());
        let mut events = state.sse_hub.subscribe();
        run_worker_with_hef(
            state.clone(),
            StartRequest {
                file_ids: vec![88, 89],
                prompt: DEFAULT_PROMPT.to_string(),
                model: DEFAULT_MODEL.to_string(),
            },
            hef,
        )
        .await;
        assert_eq!(requests.load(std::sync::atomic::Ordering::Relaxed), 1);
        assert_eq!(
            sqlx::query_scalar::<_, i64>("SELECT count(*) FROM file_annotations")
                .fetch_one(&state.db)
                .await
                .unwrap(),
            1
        );
        assert_eq!(events.recv().await.unwrap().event_type, "vlm_caption.start");
        assert_eq!(
            events.recv().await.unwrap().event_type,
            "vlm_caption.progress"
        );
        assert_eq!(events.recv().await.unwrap().data["reason"], "stopped");
    }

    #[tokio::test]
    async fn an_uninterrupted_run_reports_complete() {
        let (state, root, hef, requests, _) = worker_test_state("a caption").await;
        for id in [88, 89] {
            let image = root.path().join(format!("{id}.png"));
            image::RgbImage::new(1, 1).save(&image).unwrap();
            sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (?, ?, 0)")
                .bind(id)
                .bind(image.to_string_lossy().as_ref())
                .execute(&state.db)
                .await
                .unwrap();
        }
        let mut events = state.sse_hub.subscribe();
        run_worker_with_hef(
            state.clone(),
            StartRequest {
                file_ids: vec![88, 89],
                prompt: DEFAULT_PROMPT.to_string(),
                model: DEFAULT_MODEL.to_string(),
            },
            hef,
        )
        .await;
        assert_eq!(requests.load(std::sync::atomic::Ordering::Relaxed), 2);
        assert_eq!(
            sqlx::query_scalar::<_, i64>("SELECT count(*) FROM file_annotations")
                .fetch_one(&state.db)
                .await
                .unwrap(),
            2
        );
        let mut reason = None;
        for _ in 0..4 {
            let event = events.recv().await.unwrap();
            if event.event_type == "vlm_caption.complete" {
                reason = Some(event.data["reason"].clone());
            }
        }
        assert_eq!(reason, Some(json!("complete")));
    }

    #[tokio::test]
    async fn caption_routes_require_admin_scope() {
        let state = crate::state::semantic_test_state(true).await;
        assert_eq!(
            start_handler(
                State(state.clone()),
                None,
                Ok(Json(json!({"file_ids":[1]})))
            )
            .await
            .status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            status_handler(State(state.clone()), None).await.status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            stop_handler(State(state), None).await.status(),
            StatusCode::FORBIDDEN
        );
    }
}

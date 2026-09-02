use std::collections::HashSet;

use axum::{
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::{
    analysis_engines::{
        claude::ClaudeEngine, ollama::OllamaEngine, openai_compat::OpenAiCompatEngine,
        AnalysisEngine,
    },
    auth::{scope::require_admin_scope, AuthContext},
    jobs::StartOutcome,
    ocr::{
        media,
        router::{self, OcrServer},
        runner::spawn_guarded,
    },
    state::SharedState,
};

const OCR_JOB_ID: &str = "ocr";

fn api_error(status: StatusCode, error: &str) -> Response {
    (status, Json(json!({"ok": false, "error": error}))).into_response()
}

fn auth_error(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    if !state.config.pin_auth_enabled {
        return Some(api_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "pin_auth_not_configured",
        ));
    }
    if auth.is_none() {
        return Some(api_error(StatusCode::UNAUTHORIZED, "pin_auth_required"));
    }
    require_admin_scope(true, auth.map(|value| &value.0))
}

fn validate_task(task: &str) -> Result<(), &'static str> {
    match task {
        "ocr" | "ocr_document" | "ocr_manga" => Ok(()),
        _ => Err("Invalid task"),
    }
}

fn clamp_keyframe_count(value: Option<i64>) -> i64 {
    value.unwrap_or(4).clamp(1, 16)
}

fn clamp_dpi(value: Option<i64>) -> i64 {
    value.unwrap_or(200).clamp(72, 400)
}

fn parse_page_range(value: &str, page_count: usize) -> Result<Vec<usize>, &'static str> {
    if page_count == 0 {
        return Err("Invalid page range");
    }
    if value.trim().is_empty() {
        return Ok((0..page_count.min(50)).collect());
    }
    let mut pages = Vec::new();
    for part in value.split(',') {
        let (start, end) = match part.trim().split_once('-') {
            Some((start, end)) => (start, end),
            None => (part.trim(), part.trim()),
        };
        let start = start.parse::<usize>().map_err(|_| "Invalid page range")?;
        let end = end.parse::<usize>().map_err(|_| "Invalid page range")?;
        if start == 0 || start > end || end > page_count {
            return Err("Invalid page range");
        }
        pages.extend(start - 1..end);
    }
    pages.sort_unstable();
    pages.dedup();
    if pages.len() > 50 {
        return Err("Invalid page range");
    }
    Ok(pages)
}

fn dedupe_file_ids(file_ids: Vec<i64>) -> Vec<i64> {
    let mut seen = HashSet::new();
    file_ids.into_iter().filter(|id| seen.insert(*id)).collect()
}

fn validate_batch_size(size: usize) -> Result<(), &'static str> {
    if size <= 500 {
        Ok(())
    } else {
        Err("Max 500 files per batch")
    }
}

fn task_from(body: &Value, default: &'static str) -> Result<String, Response> {
    let task = body.get("task").and_then(Value::as_str).unwrap_or(default);
    validate_task(task).map_err(|error| api_error(StatusCode::BAD_REQUEST, error))?;
    Ok(task.to_string())
}

fn server_id_from(body: &Value) -> Result<Option<&str>, Response> {
    match body.get("server_id") {
        Some(Value::String(value)) if !value.is_empty() => Ok(Some(value)),
        Some(Value::String(_)) | None => Ok(None),
        Some(_) => Err(api_error(StatusCode::BAD_REQUEST, "Invalid server_id")),
    }
}

fn select_server(
    state: &SharedState,
    task: &str,
    server_id: Option<&str>,
) -> Result<Value, String> {
    if !state.config.pin_auth_enabled {
        return Err("PIN authentication is not configured".to_string());
    }
    let servers = state
        .config
        .app_config
        .get("ai_servers")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|server| {
            Some(OcrServer {
                id: server.get("id")?.as_str()?.to_string(),
                name: server
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                model: server
                    .get("config")
                    .and_then(|config| config.get("model"))
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                enabled: server
                    .get("enabled")
                    .and_then(Value::as_bool)
                    .unwrap_or(true),
                engine_kind: server
                    .get("type")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
            })
        })
        .collect::<Vec<_>>();
    let selected = router::select(&servers, task, server_id, &Default::default())?;
    state
        .config
        .app_config
        .get("ai_servers")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .find(|server| server.get("id").and_then(Value::as_str) == Some(selected.id.as_str()))
        .cloned()
        .ok_or_else(|| "selected server is missing".to_string())
}

fn make_engine(server: &Value, language: &str) -> Result<Box<dyn AnalysisEngine>, String> {
    let config = server.get("config").unwrap_or(&Value::Null);
    let model = config
        .get("model")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let kind = server.get("type").and_then(Value::as_str).unwrap_or("vlm");
    let url = config
        .get("base_url")
        .or_else(|| config.get("url"))
        .and_then(Value::as_str)
        .unwrap_or("http://localhost:11434")
        .to_string();
    match kind {
        "vlm" | "ollama" => Ok(Box::new(OllamaEngine {
            base_url: url,
            model,
            language: language.to_string(),
        })),
        "openai" | "openai_compat" => Ok(Box::new(OpenAiCompatEngine {
            base_url: Some(url),
            model,
            api_key: config
                .get("api_key")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            language: language.to_string(),
        })),
        "claude" | "claude_api" => Ok(Box::new(ClaudeEngine {
            model,
            api_key: config
                .get("api_key")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            language: language.to_string(),
        })),
        _ => Err(format!("unsupported OCR engine type: {kind}")),
    }
}

async fn file_exists(state: &SharedState, file_id: i64) -> bool {
    sqlx::query_scalar::<_, i64>("SELECT 1 FROM files WHERE id = ? AND is_deleted = 0")
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
        .ok()
        .flatten()
        .is_some()
}

fn submit<F, Fut>(state: SharedState, label: &'static str, body: F) -> Response
where
    F: FnOnce(tokio_util::sync::CancellationToken) -> Fut,
    Fut: std::future::Future<Output = Result<Value, String>> + Send + 'static,
{
    let run_id = uuid::Uuid::new_v4().to_string();
    match state
        .job_manager
        .start_or_current(OCR_JOB_ID, label, run_id)
    {
        StartOutcome::Busy(job) => (StatusCode::CONFLICT, Json(job)).into_response(),
        StartOutcome::Started(handle) => {
            let run_id = handle.run_id;
            spawn_guarded(state, OCR_JOB_ID, run_id.clone(), body(handle.token));
            (
                StatusCode::ACCEPTED,
                Json(json!({"job_id": OCR_JOB_ID, "run_id": run_id, "label": label})),
            )
                .into_response()
        }
    }
}

pub async fn ocr_single(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = auth_error(&state, auth.as_ref()) {
        return response;
    }
    let task = match task_from(&body, "ocr") {
        Ok(task) => task,
        Err(response) => return response,
    };
    let server_id = match server_id_from(&body) {
        Ok(server_id) => server_id,
        Err(response) => return response,
    };
    if !file_exists(&state, file_id).await {
        return api_error(StatusCode::NOT_FOUND, "File not found");
    }
    let server = match select_server(&state, &task, server_id) {
        Ok(server) => server,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    let language = body
        .get("language")
        .and_then(Value::as_str)
        .unwrap_or("auto")
        .to_string();
    let engine = match make_engine(&server, &language) {
        Ok(engine) => engine,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    submit(state.clone(), "ocr.single", move |token| async move {
        media::run_single(engine.as_ref(), &state, file_id, &task, &language, &token).await
    })
}

pub async fn ocr_batch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = auth_error(&state, auth.as_ref()) {
        return response;
    }
    let task = match task_from(&body, "ocr") {
        Ok(task) => task,
        Err(response) => return response,
    };
    let file_ids = match body.get("file_ids").and_then(Value::as_array) {
        Some(ids) => ids.iter().map(Value::as_i64).collect::<Option<Vec<_>>>(),
        None => None,
    };
    let Some(file_ids) = file_ids else {
        return api_error(StatusCode::BAD_REQUEST, "file_ids is required");
    };
    let file_ids = dedupe_file_ids(file_ids);
    if validate_batch_size(file_ids.len()).is_err() {
        return api_error(StatusCode::BAD_REQUEST, "Max 500 files per batch");
    }
    let server_id = match server_id_from(&body) {
        Ok(server_id) => server_id,
        Err(response) => return response,
    };
    for &file_id in &file_ids {
        if !file_exists(&state, file_id).await {
            return api_error(StatusCode::NOT_FOUND, "File not found");
        }
    }
    let server = match select_server(&state, &task, server_id) {
        Ok(server) => server,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    let language = body
        .get("language")
        .and_then(Value::as_str)
        .unwrap_or("auto")
        .to_string();
    let engine = match make_engine(&server, &language) {
        Ok(engine) => engine,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    submit(state.clone(), "ocr.batch", move |token| async move {
        media::run_batch(engine.as_ref(), &state, &file_ids, &task, &language, &token).await
    })
}

pub async fn ocr_video(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = auth_error(&state, auth.as_ref()) {
        return response;
    }
    let task = match task_from(&body, "ocr") {
        Ok(task) => task,
        Err(response) => return response,
    };
    let keyframe_count = body.get("keyframe_count").map(Value::as_i64);
    if keyframe_count.is_some_and(|value| value.is_none_or(|value| value < 0)) {
        return api_error(StatusCode::BAD_REQUEST, "Invalid keyframe_count");
    }
    // clamp_keyframe_count clamps to [1, 16].
    let keyframe_count = u32::try_from(clamp_keyframe_count(keyframe_count.flatten())).unwrap_or(4);
    let server_id = match server_id_from(&body) {
        Ok(server_id) => server_id,
        Err(response) => return response,
    };
    if !file_exists(&state, file_id).await {
        return api_error(StatusCode::NOT_FOUND, "File not found");
    }
    let server = match select_server(&state, &task, server_id) {
        Ok(server) => server,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    let language = body
        .get("language")
        .and_then(Value::as_str)
        .unwrap_or("auto")
        .to_string();
    let engine = match make_engine(&server, &language) {
        Ok(engine) => engine,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    submit(state.clone(), "ocr.video", move |token| async move {
        media::run_video(
            engine.as_ref(),
            &state,
            file_id,
            &task,
            &language,
            keyframe_count,
            &token,
        )
        .await
    })
}

pub async fn ocr_pdf(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = auth_error(&state, auth.as_ref()) {
        return response;
    }
    let task = match task_from(&body, "ocr_document") {
        Ok(task) => task,
        Err(response) => return response,
    };
    let dpi = body.get("dpi").map(Value::as_i64);
    if dpi.is_some() && dpi.flatten().is_none() {
        return api_error(StatusCode::BAD_REQUEST, "Invalid dpi");
    }
    // clamp_dpi clamps to [72, 400].
    let dpi = u32::try_from(clamp_dpi(dpi.flatten())).unwrap_or(200);
    let page_range = match body.get("page_range") {
        Some(Value::String(value)) => value.as_str(),
        None => "",
        Some(_) => return api_error(StatusCode::BAD_REQUEST, "Invalid page range"),
    };
    let server_id = match server_id_from(&body) {
        Ok(server_id) => server_id,
        Err(response) => return response,
    };
    if !file_exists(&state, file_id).await {
        return api_error(StatusCode::NOT_FOUND, "File not found");
    }
    let server = match select_server(&state, &task, server_id) {
        Ok(server) => server,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    let language = body
        .get("language")
        .and_then(Value::as_str)
        .unwrap_or("auto")
        .to_string();
    let engine = match make_engine(&server, &language) {
        Ok(engine) => engine,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    let pdf = match media::file_path(&state, file_id).await {
        Ok(path) => path,
        Err(_) => return api_error(StatusCode::NOT_FOUND, "File not found"),
    };
    let library_dir = state.config.project_root.join("vendor/pdfium/linux-x64");
    let page_count = match crate::ocr::pdf::page_count(&pdf, &library_dir, false) {
        Ok(count) => count,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    let pages = match parse_page_range(page_range, page_count) {
        Ok(pages) => pages,
        Err(_) => return api_error(StatusCode::BAD_REQUEST, "Invalid page range"),
    };
    submit(state.clone(), "ocr.pdf", move |token| async move {
        media::run_pdf(
            engine.as_ref(),
            &state,
            file_id,
            &task,
            &language,
            &pages,
            dpi,
            &library_dir,
            false,
            &token,
        )
        .await
    })
}

pub async fn ocr_cancel(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = auth_error(&state, auth.as_ref()) {
        return response;
    }
    let Some(run_id) = body
        .get("run_id")
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty())
    else {
        return api_error(StatusCode::BAD_REQUEST, "run_id is required");
    };
    let Some(job) = state.job_manager.get_job(OCR_JOB_ID) else {
        return api_error(
            StatusCode::CONFLICT,
            "run_id does not match the current OCR job",
        );
    };
    if !job.running || job.detail.as_deref() != Some(run_id) {
        return api_error(
            StatusCode::CONFLICT,
            "run_id does not match the current OCR job",
        );
    }
    if state.job_manager.cancel_job(OCR_JOB_ID) {
        Json(json!({"status": "cancelling"})).into_response()
    } else {
        api_error(
            StatusCode::CONFLICT,
            "run_id does not match the current OCR job",
        )
    }
}

pub async fn ocr_benchmark(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = auth_error(&state, auth.as_ref()) {
        return response;
    }
    let task = match task_from(&body, "ocr") {
        Ok(task) => task,
        Err(response) => return response,
    };
    let server_id = match server_id_from(&body) {
        Ok(server_id) => server_id,
        Err(response) => return response,
    };
    let server = match select_server(&state, &task, server_id) {
        Ok(server) => server,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    let engine = match make_engine(&server, "auto") {
        Ok(engine) => engine,
        Err(error) => return api_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    };
    submit(state.clone(), "ocr.benchmark", move |token| async move {
        media::run_benchmark(engine.as_ref(), &state, Some(&task), &token).await
    })
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use super::*;
    use axum::{
        body::{to_bytes, Body},
        http::{Request, StatusCode},
        routing::post as axum_post,
        Router,
    };
    use serde_json::json;
    use tower::ServiceExt;

    async fn build_test_state(pin_auth_enabled: bool) -> SharedState {
        let dirs = Box::leak(Box::new(crate::routes::wd_tagger::tests::test_dirs()));
        let mut state = crate::routes::wd_tagger::tests::test_state(
            dirs,
            json!({
                "ai_servers": [{
                    "id": "test-vlm",
                    "name": "Test VLM",
                    "type": "vlm",
                    "enabled": true,
                    "config": {"model": "qwen2.5vl"}
                }]
            }),
        )
        .await;
        Arc::get_mut(&mut state)
            .expect("test state must be uniquely owned")
            .config
            .pin_auth_enabled = pin_auth_enabled;
        state
    }

    fn build_test_router(state: SharedState) -> Router {
        Router::new()
            .route("/api/ocr/{file_id}", axum_post(ocr_single))
            .route("/api/ocr/batch", axum_post(ocr_batch))
            .route("/api/ocr/video/{file_id}", axum_post(ocr_video))
            .route("/api/ocr/pdf/{file_id}", axum_post(ocr_pdf))
            .route("/api/ocr/benchmark", axum_post(ocr_benchmark))
            .route("/api/ocr/cancel", axum_post(ocr_cancel))
            .with_state(state)
    }

    fn request(path: &str, body: &str, authenticated: bool) -> Request<Body> {
        let mut request = Request::post(path)
            .header("content-type", "application/json")
            .body(Body::from(body.to_owned()))
            .unwrap();
        if authenticated {
            request.extensions_mut().insert(AuthContext {
                reason: "pin_session".to_owned(),
                scopes: None,
            });
        }
        request
    }

    async fn post(
        app: &Router,
        path: &str,
        body: &str,
        authenticated: bool,
    ) -> axum::response::Response {
        app.clone()
            .oneshot(request(path, body, authenticated))
            .await
            .unwrap()
    }

    async fn response_json(response: axum::response::Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    async fn submit_ok(app: &Router, path: &str) -> axum::response::Response {
        post(app, path, r#"{"task":"ocr"}"#, true).await
    }

    async fn await_job_finished(state: &SharedState) {
        for _ in 0..20 {
            if !state.job_manager.is_running(OCR_JOB_ID) {
                return;
            }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        panic!("OCR job did not finish");
    }

    fn ocr_routes() -> [(&'static str, &'static str); 5] {
        [
            ("/api/ocr/1", r#"{"task":"ocr"}"#),
            ("/api/ocr/batch", r#"{"task":"ocr","file_ids":[1]}"#),
            ("/api/ocr/video/1", r#"{"task":"ocr"}"#),
            ("/api/ocr/pdf/1", r#"{"task":"ocr_document"}"#),
            ("/api/ocr/benchmark", r#"{"task":"ocr"}"#),
        ]
    }

    #[test]
    fn task_allowlist_covers_all_five_routes() {
        for task in ["ocr", "ocr_document", "ocr_manga"] {
            assert!(validate_task(task).is_ok(), "{task} must be accepted");
        }
        assert!(validate_task("../etc/passwd").is_err());
        assert!(validate_task("").is_err());
    }

    #[test]
    fn keyframe_count_is_clamped_not_crashed() {
        assert_eq!(clamp_keyframe_count(Some(0)), 1);
        assert_eq!(clamp_keyframe_count(Some(99)), 16);
        assert_eq!(clamp_keyframe_count(None), 4);
    }

    #[test]
    fn dpi_is_clamped() {
        assert_eq!(clamp_dpi(Some(10)), 72);
        assert_eq!(clamp_dpi(Some(9999)), 400);
        assert_eq!(clamp_dpi(None), 200);
    }

    #[test]
    fn page_range_rejects_reversed_instead_of_falling_back_to_all() {
        assert!(parse_page_range("5-1", 10).is_err());
        assert!(parse_page_range("99-100", 10).is_err());
        assert_eq!(parse_page_range("1-3", 10).unwrap(), vec![0, 1, 2]);
    }

    #[test]
    fn batch_file_ids_are_deduped_at_submit() {
        assert_eq!(dedupe_file_ids(vec![1, 2, 1, 3, 2]), vec![1, 2, 3]);
    }

    #[test]
    fn batch_rejects_more_than_five_hundred() {
        assert!(validate_batch_size(500).is_ok());
        assert!(validate_batch_size(501).is_err());
    }

    #[tokio::test]
    async fn pin_is_required_on_all_five_routes() {
        let app = build_test_router(build_test_state(true).await);
        for (path, body) in ocr_routes() {
            let response = post(&app, path, body, false).await;
            assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "{path}");
        }
    }

    #[tokio::test]
    async fn validation_runs_before_the_busy_check() {
        let state = build_test_state(true).await;
        let app = build_test_router(state);
        assert_eq!(
            submit_ok(&app, "/api/ocr/1").await.status(),
            StatusCode::ACCEPTED
        );
        let response = post(&app, "/api/ocr/1", r#"{"task":"../etc/passwd"}"#, true).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn missing_file_is_404_before_engine_resolution() {
        let app = build_test_router(build_test_state(true).await);
        let response = post(&app, "/api/ocr/999999", r#"{"task":"ocr"}"#, true).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn accepted_body_carries_job_id_run_id_and_label() {
        let app = build_test_router(build_test_state(true).await);
        let response = submit_ok(&app, "/api/ocr/1").await;
        assert_eq!(response.status(), StatusCode::ACCEPTED);
        let body = response_json(response).await;
        assert_eq!(body["job_id"], OCR_JOB_ID);
        assert_eq!(body["label"], "ocr.single");
        assert!(body["run_id"].as_str().is_some_and(|id| !id.is_empty()));
    }

    #[tokio::test]
    async fn second_submit_returns_409_describing_the_incumbent() {
        // The second submit must come from a *different* route. An earlier
        // version submitted /api/ocr/1 then /api/ocr/2 — both "ocr.single" —
        // so a handler that echoed the caller's own label instead of the
        // running job's produced the identical body and the test stayed green.
        //
        // The incumbent is registered directly rather than by submitting
        // /api/ocr/1: that submit spawns the work, and the spawned job can
        // finish before the second request arrives, in which case the busy
        // check is simply never reached and the assertion below fails for a
        // reason that has nothing to do with the handler. That race made this
        // test fail roughly one full-suite run in two. "/api/ocr/1 answers 202
        // with label ocr.single" is already pinned by
        // accepted_body_carries_job_id_run_id_and_label, so nothing is lost.
        let state = build_test_state(true).await;
        assert!(
            matches!(
                state
                    .job_manager
                    .start_or_current(OCR_JOB_ID, "ocr.single", "run-incumbent"),
                crate::jobs::StartOutcome::Started(_)
            ),
            "the incumbent must actually take the slot"
        );
        assert!(state.job_manager.is_running(OCR_JOB_ID));
        let app = build_test_router(state);
        // /api/ocr/batch, not /api/ocr/pdf: pdf defaults to task
        // "ocr_document", which the test registry cannot resolve an engine
        // for, so it would answer 503 at the engine step and never reach
        // the busy check.
        let response = post(
            &app,
            "/api/ocr/batch",
            r#"{"file_ids":[1],"task":"ocr"}"#,
            true,
        )
        .await;
        assert_eq!(response.status(), StatusCode::CONFLICT);
        let body = response_json(response).await;
        assert_eq!(
            body["label"], "ocr.single",
            "the 409 must describe the running job, not the rejected request"
        );
        assert_ne!(
            body["label"], "ocr.batch",
            "echoing the caller's label tells the caller nothing it did not already know"
        );
        assert_eq!(body["running"], true);
    }

    #[tokio::test]
    async fn non_integer_keyframe_count_is_400_not_a_silent_default() {
        let app = build_test_router(build_test_state(true).await);
        for body in [
            r#"{"task":"ocr","keyframe_count":"4"}"#,
            r#"{"task":"ocr","keyframe_count":4.5}"#,
            r#"{"task":"ocr","keyframe_count":-1}"#,
        ] {
            let response = post(&app, "/api/ocr/video/1", body, true).await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{body}");
        }
    }

    #[tokio::test]
    async fn a_finished_job_frees_the_slot_for_the_next_submit() {
        let state = build_test_state(true).await;
        let app = build_test_router(state.clone());
        assert_eq!(
            submit_ok(&app, "/api/ocr/1").await.status(),
            StatusCode::ACCEPTED
        );
        await_job_finished(&state).await;
        assert_eq!(
            submit_ok(&app, "/api/ocr/1").await.status(),
            StatusCode::ACCEPTED
        );
    }

    #[tokio::test]
    async fn all_five_routes_are_503_when_no_pin_is_configured() {
        let app = build_test_router(build_test_state(false).await);
        for (path, body) in ocr_routes() {
            let response = post(&app, path, body, true).await;
            assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE, "{path}");
        }
    }

    #[tokio::test]
    async fn cancel_requires_the_current_run_id() {
        let state = build_test_state(true).await;
        let app = build_test_router(state.clone());
        assert_eq!(
            submit_ok(&app, "/api/ocr/1").await.status(),
            StatusCode::ACCEPTED
        );
        let run_id = state
            .job_manager
            .get_job(OCR_JOB_ID)
            .and_then(|job| job.detail)
            .unwrap();

        let stale = post(&app, "/api/ocr/cancel", r#"{"run_id":"not-the-one"}"#, true).await;
        assert_eq!(stale.status(), StatusCode::CONFLICT);

        let body = format!(r#"{{"run_id":"{run_id}"}}"#);
        let current = post(&app, "/api/ocr/cancel", &body, true).await;
        assert_eq!(current.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn cancel_without_a_run_id_is_400_not_a_blanket_cancel() {
        let state = build_test_state(true).await;
        let app = build_test_router(state.clone());
        assert_eq!(
            submit_ok(&app, "/api/ocr/1").await.status(),
            StatusCode::ACCEPTED
        );
        let response = post(&app, "/api/ocr/cancel", "{}", true).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(state.job_manager.is_running(OCR_JOB_ID));
    }
}

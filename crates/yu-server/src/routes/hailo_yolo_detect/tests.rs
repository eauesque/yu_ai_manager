use std::sync::Arc;

use axum::{
    body::to_bytes,
    extract::{Path as AxumPath, Query, State},
    http::StatusCode,
    routing::post,
    Json, Router,
};
use std::collections::HashMap;
use tokio::sync::Notify;

use super::*;

async fn build_test_state() -> SharedState {
    let dirs = Box::leak(Box::new(crate::routes::wd_tagger::tests::test_dirs()));
    let state = crate::routes::wd_tagger::tests::test_state(dirs, json!({})).await;
    sqlx::query(
        "CREATE TABLE file_annotations (\
            id INTEGER PRIMARY KEY, file_id INTEGER, source TEXT, key TEXT, value BLOB, \
            confidence REAL, created_at INTEGER, UNIQUE(file_id, source, key)\
        )",
    )
    .execute(&state.db)
    .await
    .unwrap();
    state
}

async fn response_json(response: Response) -> Value {
    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&body).unwrap()
}

async fn insert_detection(
    state: &SharedState,
    file_id: i64,
    source: &str,
    detections: Value,
    confidence: Option<f64>,
) {
    sqlx::query(
        "INSERT INTO file_annotations (file_id, source, key, value, confidence) \
         VALUES (?, ?, 'detections', ?, ?)",
    )
    .bind(file_id)
    .bind(source)
    .bind(detections.to_string())
    .bind(confidence)
    .execute(&state.db)
    .await
    .unwrap();
}

#[tokio::test]
async fn labels_handler_returns_plain_status_and_labels_payload() {
    let state = build_test_state().await;

    let response = labels_handler(State(state), None).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = response_json(response).await;
    assert_eq!(body["status"], "ok");
    assert_eq!(body["labels"].as_array().unwrap().len(), 80);
}

#[tokio::test]
async fn detect_start_handler_returns_started_when_no_targets_exist() {
    let state = build_test_state().await;
    insert_detection(&state, 1, "hailo:yolov8n", json!([]), None).await;
    insert_detection(&state, 2, "hailo:yolov8n", json!([]), None).await;

    let response = detect_start_handler(State(state), None, None).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response_json(response).await,
        json!({"status": "started", "total": 0})
    );
}

#[tokio::test]
async fn detect_start_handler_rejects_unknown_model() {
    let state = build_test_state().await;

    let response = detect_start_handler(
        State(state),
        None,
        Some(Json(json!({"model": "not-a-real-model"}))),
    )
    .await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let body = response_json(response).await;
    assert_eq!(body["status"], "error");
    assert_eq!(body["message"], "Unknown model: not-a-real-model");
}

#[tokio::test]
async fn detect_start_handler_rejects_archive_true() {
    // Archive-member (zip-nested) detection is out of scope for phase1;
    // silently ignoring `archive: true` would process ordinary files under
    // the wrong semantics instead of Python's separate archive path.
    let state = build_test_state().await;

    let response =
        detect_start_handler(State(state), None, Some(Json(json!({"archive": true})))).await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let body = response_json(response).await;
    assert_eq!(body["status"], "error");
    assert!(body["message"]
        .as_str()
        .unwrap()
        .contains("archive detection is not supported"));
}

#[tokio::test]
async fn detect_status_handler_includes_job_and_detection_counts() {
    let state = build_test_state().await;
    insert_detection(
        &state,
        1,
        "hailo:yolov8n",
        json!([{ "class_name": "person", "confidence": 0.9 }]),
        Some(0.9),
    )
    .await;
    state
        .job_manager
        .start(HAILO_YOLO_JOB_ID, "Hailo YOLO detection");
    state
        .job_manager
        .update_progress(HAILO_YOLO_JOB_ID, 1, 2, Some("detecting".to_string()));

    let response = detect_status_handler(State(state), None).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = response_json(response).await;
    assert_eq!(body["running"], true);
    assert_eq!(body["total"], 2);
    assert_eq!(body["processed"], 1);
    assert_eq!(body["detected"], 1);
    assert_eq!(body["undetected"], 1);
    assert!(body["elapsed"].is_number());
}

#[tokio::test]
async fn detect_stop_handler_returns_not_running_without_a_job() {
    let state = build_test_state().await;

    let response = detect_stop_handler(State(state), None).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response_json(response).await,
        json!({"status": "not_running"})
    );
}

#[tokio::test]
async fn detect_search_handler_filters_and_returns_plain_payload() {
    let state = build_test_state().await;
    insert_detection(
        &state,
        1,
        "hailo:yolov8n",
        json!([
            {"class_name": "person", "confidence": 0.9},
            {"class_name": "person", "confidence": 0.4},
            {"class_name": "cat", "confidence": 0.99}
        ]),
        Some(0.75),
    )
    .await;
    let params = HashMap::from([
        ("class_name".to_string(), "person".to_string()),
        ("min_confidence".to_string(), "0.5".to_string()),
    ]);

    let response = detect_search_handler(State(state), None, Query(params)).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = response_json(response).await;
    assert_eq!(body["status"], "ok");
    assert_eq!(body["total"], 1);
    assert_eq!(body["results"][0]["filename"], "a.png");
    assert_eq!(body["results"][0]["match_count"], 1);
    assert_eq!(body["results"][0]["detection"]["confidence"], 0.9);
}

#[tokio::test]
async fn detect_search_handler_requires_a_nonempty_class_name() {
    let state = build_test_state().await;

    let response = detect_search_handler(State(state), None, Query(HashMap::new())).await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({"status": "error", "message": "class_name parameter is required"})
    );
}

#[tokio::test]
async fn detect_clear_handler_deletes_yolo_annotations_only() {
    let state = build_test_state().await;
    insert_detection(&state, 1, "hailo:yolov8n", json!([]), None).await;
    insert_detection(&state, 2, "other:detector", json!([]), None).await;

    let response = detect_clear_handler(State(state.clone()), None).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response_json(response).await,
        json!({"status": "ok", "deleted": 1})
    );
    let remaining: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM file_annotations")
        .fetch_one(&state.db)
        .await
        .unwrap();
    assert_eq!(remaining, 1);
}

#[tokio::test]
async fn detect_results_handler_returns_empty_payload_without_annotations() {
    let state = build_test_state().await;

    let response = detect_results_handler(State(state), None, AxumPath(1)).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response_json(response).await,
        json!({"status": "ok", "detections": [], "source": null})
    );
}

#[tokio::test]
async fn runtime_handler_reports_known_models_and_hailo_backend() {
    // Regression: an empty `models`/`available_backends` list silently
    // disables the model dropdown in the frontend
    // (extensions/builtin_hailo_yolo_detect/templates/hailo_yolo_detect/_yolo_script.html
    // collectSupportedModels()/updateModelOptions()), even when the Hailo
    // device and HEFs are actually available.
    let state = build_test_state().await;
    insert_detection(&state, 1, "hailo:yolov8n", json!([]), None).await;

    let response = runtime_handler(State(state), None).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = response_json(response).await;
    assert_eq!(body["status"], "ok");
    assert!(body["models"]["yolov8n"].is_object());
    assert!(body["models"]["yolov11n"].is_object());
    assert!(body["models"]["yolov5m"].is_object());
    let backends = body["available_backends"].as_array().unwrap();
    assert_eq!(backends.len(), 1);
    assert_eq!(backends[0]["name"], "hailo");
    let supported = backends[0]["supported_models"].as_array().unwrap();
    assert!(supported.iter().any(|value| value == "yolov8n"));
    assert!(supported.iter().any(|value| value == "yolov5m"));
    assert_eq!(body["detected_count"], 1);
    assert_eq!(body["undetected_count"], 1);
    assert_eq!(body["config"]["batch_size"], 16);
}

#[tokio::test]
async fn resolve_targets_excludes_existing_detections_and_deleted_files() {
    let state = build_test_state().await;
    sqlx::query(
        "INSERT INTO file_annotations (file_id, source, key, value) \
         VALUES (1, 'hailo:yolov8n', 'detections', '[]')",
    )
    .execute(&state.db)
    .await
    .unwrap();

    assert_eq!(
        resolve_targets(&state, "yolov8n", "all").await.unwrap(),
        vec![2]
    );
}

#[tokio::test]
async fn start_batch_job_reports_no_targets_and_running_job() {
    let state = build_test_state().await;
    sqlx::query(
        "INSERT INTO file_annotations (file_id, source, key, value) VALUES \
         (1, 'hailo:yolov8n', 'detections', '[]'), \
         (2, 'hailo:yolov8n', 'detections', '[]')",
    )
    .execute(&state.db)
    .await
    .unwrap();
    assert!(matches!(
        start_batch_job(
            state.clone(),
            "yolov8n".to_string(),
            0.25,
            "all".to_string(),
        )
        .await
        .unwrap(),
        StartResult::NoTargets
    ));

    sqlx::query("DELETE FROM file_annotations")
        .execute(&state.db)
        .await
        .unwrap();
    state
        .job_manager
        .start(HAILO_YOLO_JOB_ID, "Hailo YOLO detection");
    assert!(matches!(
        start_batch_job(state, "yolov8n".to_string(), 0.25, "all".to_string())
            .await
            .unwrap(),
        StartResult::AlreadyRunning
    ));
}

#[tokio::test]
async fn start_batch_job_no_targets_still_registers_a_completed_job() {
    // Python's start_detection always spawns its worker thread (preflight=False),
    // so a subsequent detect/status observes a job that started and finished
    // near-instantly rather than "never ran". Match that: NoTargets must not
    // skip job registration entirely.
    let state = build_test_state().await;
    insert_detection(&state, 1, "hailo:yolov8n", json!([]), None).await;
    insert_detection(&state, 2, "hailo:yolov8n", json!([]), None).await;

    assert!(matches!(
        start_batch_job(
            state.clone(),
            "yolov8n".to_string(),
            0.25,
            "all".to_string()
        )
        .await
        .unwrap(),
        StartResult::NoTargets
    ));

    let job = state.job_manager.get_job(HAILO_YOLO_JOB_ID).unwrap();
    assert_eq!(job.phase.as_deref(), Some("complete"));
    assert_eq!(job.result.unwrap()["total"], 0);
}

#[test]
fn hailo_yolo_hef_path_uses_env_default_resolution_for_default_model() {
    // Passing None for the default model preserves yu-infer's own
    // env_or_default_path("HAILO_YOLO_HEF", "yolov8n.hef") resolution.
    assert_eq!(hailo_yolo_hef_path("yolov8n"), None);
    assert_eq!(hailo_yolo_hef_path(""), None);
}

#[test]
fn hailo_yolo_hef_path_resolves_non_default_models_explicitly() {
    let path = hailo_yolo_hef_path("yolov11n").unwrap();
    assert!(path.ends_with("hailo_models/yolov11n.hef"), "{path}");
}

#[test]
fn hailo_yolo_hef_path_uses_special_filename_for_yolov5m() {
    // Python's YOLO_MODELS table maps "yolov5m" to "yolov5m_wo_spp.hef"
    // (a variant compiled without the SPP layer), not "yolov5m.hef".
    let path = hailo_yolo_hef_path("yolov5m").unwrap();
    assert!(path.ends_with("hailo_models/yolov5m_wo_spp.hef"), "{path}");
}

#[test]
fn hailo_yolo_hef_path_falls_back_to_default_for_unknown_model() {
    // An unknown model name resolves to None (the default HEF) rather than
    // constructing a path that can never exist on disk.
    assert_eq!(hailo_yolo_hef_path("not-a-real-model"), None);
}

#[test]
fn media_extensions_all_excludes_video_extensions() {
    // Video keyframe detection is out of scope for phase1; "all" must not
    // silently select video files as batch targets (run_detect_worker
    // cannot process them).
    let extensions = media_extensions("all");
    assert!(extensions.contains(&".png".to_string()));
    assert!(!extensions.contains(&".mp4".to_string()));
}

#[test]
fn is_video_path_detects_known_video_extensions() {
    assert!(is_video_path("/scratch/clip.mp4"));
    assert!(is_video_path("/scratch/CLIP.MOV"));
    assert!(!is_video_path("/scratch/photo.png"));
}

#[derive(Clone)]
struct InferenceGate {
    started: Arc<Notify>,
    release: Arc<Notify>,
}

async fn stalled_detect(State(gate): State<InferenceGate>) -> Json<Value> {
    gate.started.notify_one();
    gate.release.notified().await;
    // This test exercises cancellation timing, not postprocessing.
    Json(json!({"detections": []}))
}

#[tokio::test]
async fn run_detect_worker_stops_at_file_boundary_when_cancelled() {
    let gate = InferenceGate {
        started: Arc::new(Notify::new()),
        release: Arc::new(Notify::new()),
    };
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server_gate = gate.clone();
    let server = tokio::spawn(async move {
        axum::serve(
            listener,
            Router::new()
                .route("/v1/infer/yolo/detect", post(stalled_detect))
                .with_state(server_gate),
        )
        .await
        .unwrap();
    });

    let dirs = Box::leak(Box::new(crate::routes::wd_tagger::tests::test_dirs()));
    let state = crate::routes::wd_tagger::tests::test_state_ex(
        dirs,
        json!({}),
        Some(crate::infer_client::InferClient::new(
            format!("http://{address}"),
            "test-token".to_string(),
        )),
        true,
        dirs.root.join("cache"),
    )
    .await;
    sqlx::query(
        "CREATE TABLE file_annotations (\
            id INTEGER PRIMARY KEY, file_id INTEGER, source TEXT, key TEXT, value BLOB, \
            confidence REAL, created_at INTEGER, UNIQUE(file_id, source, key)\
        )",
    )
    .execute(&state.db)
    .await
    .unwrap();
    let first = dirs.root.join("first.png");
    let second = dirs.root.join("second.png");
    image::RgbImage::new(1, 1).save(&first).unwrap();
    image::RgbImage::new(1, 1).save(&second).unwrap();
    sqlx::query("UPDATE files SET path = ? WHERE id = 1")
        .bind(first.to_string_lossy().to_string())
        .execute(&state.db)
        .await
        .unwrap();
    sqlx::query("UPDATE files SET path = ? WHERE id = 2")
        .bind(second.to_string_lossy().to_string())
        .execute(&state.db)
        .await
        .unwrap();

    let cancel = state
        .job_manager
        .start(HAILO_YOLO_JOB_ID, "Hailo YOLO detection");
    let worker = tokio::spawn(run_detect_worker(
        state.clone(),
        HAILO_YOLO_JOB_ID.to_string(),
        vec![1, 2],
        "yolov8n".to_string(),
        0.25,
        cancel,
    ));
    // A watchdog, not a performance assertion: it exists so a worker that never
    // starts fails the test instead of hanging the suite. One second is roughly
    // the time a healthy run takes under load, so it fired on healthy runs
    // (2026-08-13: one in six full-suite runs). A hung worker never starts at
    // all, so a wide budget still catches it.
    tokio::time::timeout(std::time::Duration::from_secs(30), gate.started.notified())
        .await
        .expect("first inference should start");
    assert!(state.job_manager.cancel_job(HAILO_YOLO_JOB_ID));
    gate.release.notify_one();
    worker.await.unwrap();
    server.abort();

    let job = state.job_manager.get_job(HAILO_YOLO_JOB_ID).unwrap();
    assert_eq!(job.phase.as_deref(), Some("cancelled"));
    let result = job.result.unwrap();
    assert_eq!(result["processed"], 1);
    assert_eq!(result["skipped"], 0);
    assert_eq!(result["errors"], 0);
    assert_eq!(result["total"], 2);
}

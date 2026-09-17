use super::*;

pub(crate) async fn labels_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }
    Json(json!({"status": "ok", "labels": &COCO_LABELS[..]})).into_response()
}

/// Starts the native batch worker using the same deliberately permissive JSON
/// defaults as the Python endpoint.
pub(crate) async fn detect_start_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<Value>>,
) -> Response {
    // Deliberate deviation from Python parity: the Python route has no auth
    // check here (an apparent oversight), but this handler starts a
    // resource-intensive background job, so admin scope is required.
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }
    let body = body.map(|Json(value)| value).unwrap_or(Value::Null);
    // Archive-member (e.g. zip-nested) detection is out of scope for
    // phase1: resolve_targets/run_detect_worker only handle regular files,
    // so silently accepting `archive: true` would process and permanently
    // mark ordinary files as "detected" under the wrong semantics instead
    // of running Python's separate `start_archive_detection` path. Reject
    // explicitly rather than silently diverging.
    if body
        .get("archive")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "status": "error",
                "message": "archive detection is not supported by the native Hailo YOLO detector",
            })),
        )
            .into_response();
    }
    let model_name = body
        .get("model")
        .and_then(Value::as_str)
        .unwrap_or("yolov8n")
        .to_string();
    if !crate::routes::hailo_model_download::YOLO_MODELS.contains_key(&model_name) {
        let mut available = crate::routes::hailo_model_download::YOLO_MODELS
            .keys()
            .cloned()
            .collect::<Vec<_>>();
        available.sort_unstable();
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "status": "error",
                "message": format!("Unknown model: {model_name}"),
                "available": available,
            })),
        )
            .into_response();
    }
    let confidence_threshold = body
        .get("confidence_threshold")
        .and_then(Value::as_f64)
        .unwrap_or(0.25);
    let media_filter = body
        .get("media_filter")
        .and_then(Value::as_str)
        .unwrap_or("all")
        .to_string();

    match start_batch_job(state, model_name, confidence_threshold, media_filter).await {
        Ok(StartResult::AlreadyRunning) => {
            Json(json!({"status": "already_running"})).into_response()
        }
        // Python calls start_detection with preflight=False and therefore says
        // "started" even when no targets exist. Keep its response contract,
        // while start_batch_job safely avoids spawning an empty worker.
        Ok(StartResult::Started | StartResult::NoTargets) => {
            Json(json!({"status": "started", "total": 0})).into_response()
        }
        Err(error) => database_error(error, "failed to start Hailo YOLO detection"),
    }
}

pub(crate) async fn detect_status_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }

    let (detected, undetected) = match detection_counts(&state).await {
        Ok(counts) => counts,
        Err(error) => return database_error(error, "failed to count Hailo YOLO detections"),
    };
    let job = state.job_manager.get_job(HAILO_YOLO_JOB_ID);
    let running = job.as_ref().is_some_and(|job| job.running);
    let response = json!({
        "running": running,
        "total": job.as_ref().and_then(|job| job.total).unwrap_or(0),
        "processed": job.as_ref().and_then(|job| job.current).unwrap_or(0),
        "errors": job
            .as_ref()
            .and_then(|job| job.result.as_ref())
            .and_then(|result| result.get("errors"))
            .and_then(Value::as_u64)
            .unwrap_or(0),
        // JobDict intentionally does not expose its internal SystemTime.
        "started_at": Value::Null,
        "message": job.as_ref().and_then(|job| job.message.clone()),
        "elapsed": if running {
            json!(job.as_ref().map(|job| job.elapsed_seconds).unwrap_or_default())
        } else {
            Value::Null
        },
        "detected": detected,
        "undetected": undetected,
    });
    Json(response).into_response()
}

pub(crate) async fn detect_stop_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    // Deliberate deviation from Python parity: see detect_start_handler.
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }
    let status = if state.job_manager.cancel_job(HAILO_YOLO_JOB_ID) {
        "stopping"
    } else {
        "not_running"
    };
    Json(json!({"status": status})).into_response()
}

pub(crate) async fn detect_search_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }
    let class_name = params
        .get("class_name")
        .map(|value| value.trim().to_ascii_lowercase())
        .filter(|value| !value.is_empty());
    let Some(class_name) = class_name else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "status": "error",
                "message": "class_name parameter is required",
            })),
        )
            .into_response();
    };
    let min_confidence = params
        .get("min_confidence")
        .and_then(|value| value.parse::<f64>().ok())
        .unwrap_or(0.0);
    let limit = params
        .get("limit")
        .and_then(|value| value.parse::<i64>().ok())
        .unwrap_or(50)
        .min(200);
    let offset = params
        .get("offset")
        .and_then(|value| value.parse::<i64>().ok())
        .unwrap_or(0);
    let candidate_limit = limit.saturating_add(offset).max(0);
    let search_pattern = format!("%\"class_name\": \"{class_name}\"%");
    let compact_search_pattern = format!("%\"class_name\":\"{class_name}\"%");

    let rows = match sqlx::query(
        "SELECT a.file_id, a.value, a.source, f.path \
         FROM file_annotations a \
         JOIN files f ON a.file_id = f.id \
         WHERE f.is_deleted = 0 AND a.key = 'detections' \
           AND a.source LIKE '%:yolo%' \
           AND (a.value LIKE ? OR a.value LIKE ?) \
         ORDER BY a.confidence DESC LIMIT ? OFFSET 0",
    )
    .bind(search_pattern)
    .bind(compact_search_pattern)
    .bind(candidate_limit)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return database_error(error, "failed to search Hailo YOLO detections"),
    };

    let mut results = Vec::new();
    for row in rows {
        let raw_value = row
            .try_get::<Vec<u8>, _>("value")
            .or_else(|_| row.try_get::<String, _>("value").map(String::into_bytes))
            .unwrap_or_default();
        let Ok(detections) = serde_json::from_slice::<Value>(&raw_value) else {
            continue;
        };
        let Some(detections) = detections.as_array() else {
            continue;
        };
        let matching = detections
            .iter()
            .filter(|detection| {
                detection
                    .get("class_name")
                    .and_then(Value::as_str)
                    .is_some_and(|name| name.eq_ignore_ascii_case(&class_name))
                    && detection
                        .get("confidence")
                        .and_then(Value::as_f64)
                        .is_some_and(|confidence| confidence >= min_confidence)
            })
            .collect::<Vec<_>>();
        let Some(best) = matching.iter().max_by(|left, right| {
            let left_confidence = left
                .get("confidence")
                .and_then(Value::as_f64)
                .unwrap_or(f64::NEG_INFINITY);
            let right_confidence = right
                .get("confidence")
                .and_then(Value::as_f64)
                .unwrap_or(f64::NEG_INFINITY);
            left_confidence
                .partial_cmp(&right_confidence)
                .unwrap_or(std::cmp::Ordering::Equal)
        }) else {
            continue;
        };
        let filepath: String = row.try_get("path").unwrap_or_default();
        let filename = Path::new(&filepath)
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("");
        results.push(json!({
            "file_id": row.try_get::<i64, _>("file_id").unwrap_or_default(),
            "filepath": filepath,
            "filename": filename,
            "source": row.try_get::<String, _>("source").unwrap_or_default(),
            "detection": *best,
            "match_count": matching.len(),
        }));
    }

    let total = results.len();
    let paged = results
        .into_iter()
        .skip(usize::try_from(offset.max(0)).unwrap_or(0))
        .take(usize::try_from(limit.max(0)).unwrap_or(0))
        .collect::<Vec<_>>();
    Json(json!({
        "status": "ok",
        "results": paged,
        "total": total,
        "class_name": class_name,
        "min_confidence": min_confidence,
        "limit": limit,
        "offset": offset,
    }))
    .into_response()
}

pub(crate) async fn detect_clear_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    // Deliberate deviation from Python parity: see detect_start_handler.
    // This handler is destructive (deletes annotations), so admin scope is
    // required even though Python's route has no auth check.
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }
    match sqlx::query(
        "DELETE FROM file_annotations WHERE source LIKE '%:yolo%' AND key = 'detections'",
    )
    .execute(&state.db)
    .await
    {
        Ok(result) => {
            Json(json!({"status": "ok", "deleted": result.rows_affected()})).into_response()
        }
        Err(error) => database_error(error, "failed to clear Hailo YOLO detections"),
    }
}

pub(crate) async fn detect_results_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }
    let row = match sqlx::query(
        "SELECT value, source, confidence FROM file_annotations \
         WHERE file_id = ? AND source LIKE '%:yolo%' AND key = 'detections' LIMIT 1",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(row) => row,
        Err(error) => return database_error(error, "failed to get Hailo YOLO detections"),
    };
    let Some(row) = row else {
        return Json(json!({"status": "ok", "detections": [], "source": Value::Null}))
            .into_response();
    };
    let raw_value = row
        .try_get::<Vec<u8>, _>("value")
        .or_else(|_| row.try_get::<String, _>("value").map(String::into_bytes))
        .unwrap_or_default();
    let detections = serde_json::from_slice::<Value>(&raw_value).unwrap_or_else(|_| json!([]));
    Json(json!({
        "status": "ok",
        "detections": detections,
        "source": row.try_get::<String, _>("source").unwrap_or_default(),
        "confidence": row.try_get::<Option<f64>, _>("confidence").unwrap_or(None),
    }))
    .into_response()
}

pub(crate) async fn runtime_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }
    let mut supported_models = crate::routes::hailo_model_download::YOLO_MODELS
        .keys()
        .cloned()
        .collect::<Vec<_>>();
    supported_models.sort_unstable();
    match detection_counts(&state).await {
        Ok((detected_count, undetected_count)) => Json(json!({
            "status": "ok",
            "models": crate::routes::hailo_model_download::get_yolo_model_status(
                &crate::routes::hailo_model_download::default_hef_dir(),
            ),
            "detected_count": detected_count,
            "undetected_count": undetected_count,
            "detection_running": state.job_manager.is_running(HAILO_YOLO_JOB_ID),
            "auto_detect_on_scan": false,
            "config": {
                "backend": "auto",
                "model": "yolov8n",
                "confidence_threshold": 0.25,
                "batch_size": 16,
                "video_frame_interval": 2.0,
            },
            "available_backends": [{
                "name": "hailo",
                "priority": 100,
                "supported_models": supported_models,
            }],
        }))
        .into_response(),
        Err(error) => database_error(error, "failed to count Hailo YOLO detections"),
    }
}

async fn detection_counts(state: &SharedState) -> Result<(i64, i64), sqlx::Error> {
    let detected = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(DISTINCT a.file_id) FROM file_annotations a \
         JOIN files f ON a.file_id = f.id \
         WHERE f.is_deleted = 0 AND a.source = ? AND a.key = 'detections'",
    )
    .bind(annotation_source("yolov8n"))
    .fetch_one(&state.db_read)
    .await?;
    let undetected = resolve_targets(state, "yolov8n", "all")
        .await
        .map_err(|error| match error {
            DetectError::Db(error) => error,
        })?
        .len() as i64;
    Ok((detected, undetected))
}

fn database_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{message}");
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"status": "error", "message": message})),
    )
        .into_response()
}

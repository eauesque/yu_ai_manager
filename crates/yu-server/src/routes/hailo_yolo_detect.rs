//! Native Hailo YOLO batch target resolution and detection worker.

use axum::{
    extract::{Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use futures_util::FutureExt;
use serde_json::{json, Value};
use sqlx::Row;
use std::{collections::HashMap, path::Path};

use super::hailo_yolo_labels::{annotation_source, COCO_LABELS};
use super::hailo_yolo_postprocess::write_detections;
use super::hailo_yolo_preprocess::letterbox_resize;
use crate::{auth::AuthContext, state::SharedState};

mod handlers;
mod model_handlers;
pub(crate) use handlers::*;
pub(crate) use model_handlers::*;

pub(crate) const HAILO_YOLO_JOB_ID: &str = "hailo_yolo_detect";

const IMAGE_EXTENSIONS: &[&str] = &[
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif",
];
const VIDEO_EXTENSIONS: &[&str] = &[".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv"];

#[derive(Debug, thiserror::Error)]
pub(crate) enum DetectError {
    #[error("database error: {0}")]
    Db(#[from] sqlx::Error),
}

/// Outcome of starting a Hailo YOLO detection batch.
pub(crate) enum StartResult {
    Started,
    NoTargets,
    AlreadyRunning,
}

/// Finds active files without a `detections` annotation for this model.
pub(crate) async fn resolve_targets(
    state: &SharedState,
    model_name: &str,
    media_filter: &str,
) -> Result<Vec<i64>, DetectError> {
    let extensions = media_extensions(media_filter);
    let mut sql = String::from(
        "SELECT f.id FROM files f \
         WHERE f.is_deleted = 0 \
         AND NOT EXISTS ( \
             SELECT 1 FROM file_annotations a \
             WHERE a.file_id = f.id AND a.source = ? AND a.key = 'detections' \
         )",
    );
    if !extensions.is_empty() {
        let filters = (0..extensions.len())
            .map(|_| "LOWER(f.path) LIKE ?")
            .collect::<Vec<_>>()
            .join(" OR ");
        sql.push_str(" AND (");
        sql.push_str(&filters);
        sql.push(')');
    }

    let mut query = sqlx::query_scalar::<_, i64>(&sql).bind(annotation_source(model_name));
    for extension in extensions {
        query = query.bind(format!("%{extension}"));
    }
    Ok(query.fetch_all(&state.db_read).await?)
}

/// Starts a Hailo YOLO detection batch (or, for zero targets, a job that
/// completes immediately) unless one is already running. The Hailo job id
/// is deliberately independent from the WD-Tagger job id, so both workers
/// may run at once.
///
/// Python's `start_detection` always spawns its background thread (even for
/// zero undetected files, since it calls `preflight=False`), so
/// `detect/status` observes a job that starts and finishes near-instantly.
/// Skipping job creation entirely for `NoTargets` would make an immediate
/// status check after "started" incorrectly report not-running (or a
/// stale prior job); registering and immediately finishing the job here
/// keeps `detect/start`+`detect/status` consistent with that real behavior.
pub(crate) async fn start_batch_job(
    state: SharedState,
    model_name: String,
    conf_threshold: f64,
    media_filter: String,
) -> Result<StartResult, DetectError> {
    let targets = resolve_targets(&state, &model_name, &media_filter).await?;

    let cancel = match state
        .job_manager
        .start_if_idle(HAILO_YOLO_JOB_ID, "Hailo YOLO detection")
    {
        Some(token) => token,
        None => return Ok(StartResult::AlreadyRunning),
    };

    if targets.is_empty() {
        state
            .job_manager
            .finish(HAILO_YOLO_JOB_ID, Some(result_json(0, 0, 0, 0)), None);
        return Ok(StartResult::NoTargets);
    }

    let worker_state = state.clone();
    tokio::spawn(async move {
        let result = std::panic::AssertUnwindSafe(run_detect_worker(
            worker_state.clone(),
            HAILO_YOLO_JOB_ID.to_string(),
            targets,
            model_name,
            conf_threshold,
            cancel,
        ))
        .catch_unwind()
        .await;
        if result.is_err() {
            worker_state.job_manager.finish(
                HAILO_YOLO_JOB_ID,
                None,
                Some("internal panic during batch worker".to_string()),
            );
        }
    });

    Ok(StartResult::Started)
}

/// Runs detection sequentially. Cancellation is deliberately observed only
/// at file boundaries, so an inference that has already started can finish.
pub(crate) async fn run_detect_worker(
    state: SharedState,
    job_id: String,
    targets: Vec<i64>,
    model_name: String,
    conf_threshold: f64,
    cancel: tokio_util::sync::CancellationToken,
) {
    let total = targets.len() as u64;
    let mut processed = 0_u64;
    let mut skipped = 0_u64;
    let mut errors = 0_u64;
    let source = annotation_source(&model_name);

    for (index, file_id) in targets.into_iter().enumerate() {
        if cancel.is_cancelled() {
            break;
        }

        let path = match sqlx::query_scalar::<_, String>(
            "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
        )
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
        {
            Ok(Some(path)) => path,
            Ok(None) => {
                skipped += 1;
                update_progress(&state, &job_id, index, total);
                continue;
            }
            Err(error) => {
                errors += 1;
                tracing::warn!(?error, file_id, "hailo yolo: file lookup failed");
                update_progress(&state, &job_id, index, total);
                continue;
            }
        };

        if is_video_path(&path) {
            // Video keyframe detection is out of scope for phase1; leave the
            // file unannotated (no `write_detections` call) so it remains a
            // valid target once video support lands, instead of being
            // permanently marked "detected" with an empty result.
            tracing::debug!(
                file_id,
                path,
                "hailo yolo: skipping video file (out of scope)"
            );
            skipped += 1;
            update_progress(&state, &job_id, index, total);
            continue;
        }

        let image = match image::open(&path) {
            Ok(image) => image,
            Err(error) => {
                tracing::warn!(?error, file_id, path, "hailo yolo: image load failed");
                match write_detections(&state.db, file_id, &source, &[]).await {
                    Ok(()) => skipped += 1,
                    Err(error) => {
                        errors += 1;
                        tracing::warn!(?error, file_id, "hailo yolo: failed to record skip");
                    }
                }
                update_progress(&state, &job_id, index, total);
                continue;
            }
        };

        let (input, scale_info) = letterbox_resize(&image, 640);
        let Some(infer_client) = state.infer_client.as_ref() else {
            finish_fatal(
                &state,
                &job_id,
                processed,
                skipped,
                total,
                errors + 1,
                "Hailo inference unavailable".to_string(),
            );
            return;
        };
        let response = match infer_client
            .infer_yolo_detect(
                hailo_yolo_hef_path(&model_name),
                STANDARD.encode(input),
                conf_threshold,
                0.45,
                80,
                640,
                scale_info.orig_w,
                scale_info.orig_h,
                scale_info.scale,
                scale_info.pad_x,
                scale_info.pad_y,
            )
            .await
        {
            Ok(response) => response,
            Err(error) => {
                finish_fatal(
                    &state,
                    &job_id,
                    processed,
                    skipped,
                    total,
                    errors + 1,
                    error.to_string(),
                );
                return;
            }
        };
        match write_detections(&state.db, file_id, &source, &response).await {
            Ok(()) => processed += 1,
            Err(error) => {
                errors += 1;
                tracing::warn!(?error, file_id, "hailo yolo: detection write failed");
            }
        }
        update_progress(&state, &job_id, index, total);
    }

    let result = Some(result_json(processed, skipped, total, errors));
    if cancel.is_cancelled() {
        state.job_manager.finish_cancelled(&job_id, result);
    } else {
        state.job_manager.finish(&job_id, result, None);
    }
}

fn is_video_path(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    VIDEO_EXTENSIONS
        .iter()
        .any(|extension| lower.ends_with(extension))
}

/// Resolves `model_name` to the HEF path yu-infer should load, mirroring
/// Python's `get_hef_path()` (`$HAILO_HEF_DIR` or `~/hailo_models/` +
/// the shared YOLO model registry filename).
///
/// For the default model (`yolov8n`) with neither `HAILO_HEF_DIR` nor
/// `HAILO_YOLO_HEF` set, this returns `None` so yu-infer falls through to
/// its own `env_or_default_path("HAILO_YOLO_HEF", "yolov8n.hef")`
/// resolution (`crates/yu-infer/src/router.rs`) -- preserving the
/// `HAILO_YOLO_HEF` full-path override used by local/smoke-test setups,
/// which `HAILO_HEF_DIR` (a directory, not a path) cannot express. If
/// `HAILO_HEF_DIR` *is* set, it is honored even for the default model, to
/// match Python's single `HAILO_HEF_DIR` override applying to every model.
/// Any other known model is always resolved explicitly so its own HEF (not
/// the default) is actually loaded. An unknown model name also resolves to
/// `None` (falls back to the default HEF) rather than constructing a path
/// that can never exist -- the caller-facing model list is validated at
/// the API layer.
pub(crate) fn hailo_yolo_hef_path(model_name: &str) -> Option<String> {
    let info = crate::routes::hailo_model_download::YOLO_MODELS.get(model_name)?;
    if model_name == "yolov8n" && std::env::var_os("HAILO_HEF_DIR").is_none() {
        return None;
    }
    Some(
        crate::routes::hailo_model_download::get_hef_path(
            &info.hef_filename,
            &crate::routes::hailo_model_download::default_hef_dir(),
        )
        .to_string_lossy()
        .into_owned(),
    )
}

/// Phase1 scope note: video keyframe detection is out of scope (matching
/// the WD-Tagger native migration precedent), so "all"/"" resolves to
/// images-only rather than Python's unfiltered set -- a video file must
/// never be silently selected as a batch target, since `run_detect_worker`
/// cannot process it and would otherwise mark it "detected" with an empty
/// result forever.
fn media_extensions(media_filter: &str) -> Vec<String> {
    match media_filter {
        "all" | "" | "image" => IMAGE_EXTENSIONS
            .iter()
            .map(|extension| (*extension).to_string())
            .collect(),
        "video" => VIDEO_EXTENSIONS
            .iter()
            .map(|extension| (*extension).to_string())
            .collect(),
        _ => media_filter
            .split(',')
            .map(str::trim)
            .filter(|extension| !extension.is_empty())
            .map(str::to_ascii_lowercase)
            .map(|extension| {
                if extension.starts_with('.') {
                    extension
                } else {
                    format!(".{extension}")
                }
            })
            .collect(),
    }
}

fn update_progress(state: &SharedState, job_id: &str, index: usize, total: u64) {
    state
        .job_manager
        .update_progress(job_id, (index + 1) as u64, total, None);
}

fn finish_fatal(
    state: &SharedState,
    job_id: &str,
    processed: u64,
    skipped: u64,
    total: u64,
    errors: u64,
    message: String,
) {
    tracing::error!(job_id, %message, "hailo yolo: fatal batch error");
    state.job_manager.finish(
        job_id,
        Some(result_json(processed, skipped, total, errors)),
        Some(message),
    );
}

fn result_json(processed: u64, skipped: u64, total: u64, errors: u64) -> Value {
    json!({
        "processed": processed,
        "skipped": skipped,
        "total": total,
        "errors": errors,
    })
}

#[cfg(test)]
#[path = "hailo_yolo_detect/tests.rs"]
mod tests;

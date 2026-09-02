use axum::{
    body::Bytes,
    extract::{Extension, State},
    http::StatusCode,
    response::Response,
};
use futures_util::{future::BoxFuture, FutureExt};
use serde_json::{json, Value};

use crate::auth::AuthContext;
use crate::routes::wd_tagger::{
    admin_scope_error, api_error_code, api_result, configured_model_id_string,
    resolve_configured_model_id, set_active_model_id, tag_file_native_core, FatalReason,
    TagOutcome,
};
use crate::state::SharedState;

const MAX_LIMIT: i64 = 500;
const DEFAULT_LIMIT: i64 = 100;
pub(crate) const WD_TAGGER_JOB_ID: &str = "wd_tagger";

#[derive(Debug)]
pub(crate) enum BatchError {
    InvalidValue(&'static str),
}

#[derive(Debug)]
pub(crate) struct BatchRequest {
    pub file_ids: Option<Vec<i64>>,
    pub scan_root: Option<String>,
    pub limit: i64,
    pub force: bool,
}

/// POST /api/wd-tagger/batch
///
/// This deliberately accepts raw bytes instead of `Json<BatchRequest>` so
/// malformed or absent JSON follows the legacy Python route's permissive
/// default-request behavior. Individual fields are then validated to avoid
/// silently replacing a type-invalid request with the default request.
pub(crate) async fn batch_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth.as_ref()) {
        return response;
    }

    let payload = serde_json::from_slice::<Value>(&body).unwrap_or(json!({}));
    if !payload.is_object() {
        return api_error_code(
            "request body must be a JSON object",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    }

    let file_ids = match payload.get("file_ids") {
        None | Some(Value::Null) => None,
        Some(Value::Array(file_ids)) => {
            if file_ids.len() > usize::try_from(MAX_LIMIT).unwrap_or(usize::MAX) {
                return api_error_code(
                    "file_ids max 500",
                    StatusCode::BAD_REQUEST,
                    "batch_too_large",
                );
            }
            let file_ids = match file_ids
                .iter()
                .map(Value::as_i64)
                .collect::<Option<Vec<_>>>()
            {
                Some(file_ids) => file_ids,
                None => {
                    return api_error_code(
                        "file_ids must be a list",
                        StatusCode::BAD_REQUEST,
                        "invalid_input",
                    );
                }
            };
            Some(file_ids)
        }
        Some(_) => {
            return api_error_code(
                "file_ids must be a list",
                StatusCode::BAD_REQUEST,
                "invalid_input",
            );
        }
    };

    let limit = match payload.get("limit") {
        None => DEFAULT_LIMIT,
        Some(value) => match value.as_i64() {
            Some(limit) if (0..=MAX_LIMIT).contains(&limit) => limit,
            Some(_) => {
                return api_error_code(
                    "limit must be between 0 and 500",
                    StatusCode::BAD_REQUEST,
                    "invalid_value",
                );
            }
            None => {
                return api_error_code(
                    "limit must be an integer",
                    StatusCode::BAD_REQUEST,
                    "invalid_value",
                );
            }
        },
    };

    let force = match payload.get("force") {
        None => false,
        Some(value) => match value.as_bool() {
            Some(force) => force,
            None => {
                return api_error_code(
                    "force must be a boolean",
                    StatusCode::BAD_REQUEST,
                    "invalid_value",
                );
            }
        },
    };

    let scan_root = match payload.get("scan_root") {
        Some(Value::String(scan_root)) => Some(scan_root.clone()),
        _ => None,
    };
    let request = BatchRequest {
        file_ids,
        scan_root,
        limit,
        force,
    };

    match start_batch_job(state, request).await {
        Ok(StartResult::Started) => {
            api_result(json!({"started": true, "job_id": WD_TAGGER_JOB_ID}))
        }
        Ok(StartResult::NoTargets) => api_result(json!({"started": false, "reason": "no_targets"})),
        Ok(StartResult::AlreadyRunning) => api_error_code(
            "WD-Tagger retag job already running",
            StatusCode::CONFLICT,
            "job_running",
        ),
        Err(BatchError::InvalidValue(_)) => api_error_code(
            "limit must be between 0 and 500",
            StatusCode::BAD_REQUEST,
            "invalid_value",
        ),
    }
}

/// POST /api/wd-tagger/batch/cancel
pub(crate) async fn batch_cancel_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth.as_ref()) {
        return response;
    }
    if !state.job_manager.cancel_job(WD_TAGGER_JOB_ID) {
        return api_error_code(
            "No running batch tagging job",
            StatusCode::NOT_FOUND,
            "job_not_running",
        );
    }

    api_result(json!({
        "status": "cancelling",
        "message": "Batch tagging cancel requested",
    }))
}

/// Resolves the WD-Tagger batch/backfill target file ids.
///
/// `file_ids` (when present) always wins over `scan_root`, even if both are
/// supplied — this mirrors the Python `wd_tagger_batch_routes.py` behavior
/// verbatim, including not treating the combination as an error.
pub(crate) async fn resolve_targets(
    state: &SharedState,
    req: &BatchRequest,
) -> Result<(Vec<i64>, &'static str), BatchError> {
    if req.limit < 0 || req.limit > MAX_LIMIT {
        return Err(BatchError::InvalidValue("limit"));
    }

    if let Some(file_ids) = &req.file_ids {
        // filter is_deleted=0 first (preserving input order), THEN apply
        // limit. Reversing this order would drop live files whenever a
        // deleted id sorts earlier in the input, under-counting relative to
        // the Python implementation.
        let active_ids = filter_active_in_order(&state.db_read, file_ids).await;
        let limited = if req.limit > 0 {
            active_ids
                .into_iter()
                .take(usize::try_from(req.limit).unwrap_or(0))
                .collect()
        } else {
            active_ids
        };
        Ok((limited, "batch"))
    } else {
        let scan_root = req.scan_root.clone().unwrap_or_default();
        let ids = query_backfill_targets(state, &scan_root, req.limit, req.force, None).await;
        Ok((ids, "backfill"))
    }
}

pub(crate) async fn filter_active_in_order(db: &sqlx::SqlitePool, file_ids: &[i64]) -> Vec<i64> {
    if file_ids.is_empty() {
        return Vec::new();
    }
    let placeholders: Vec<String> = (0..file_ids.len()).map(|i| format!("?{}", i + 1)).collect();
    let sql = format!(
        "SELECT id FROM files WHERE is_deleted = 0 AND id IN ({})",
        placeholders.join(",")
    );
    let mut query = sqlx::query_scalar::<_, i64>(&sql);
    for id in file_ids {
        query = query.bind(id);
    }
    let active: std::collections::HashSet<i64> = query
        .fetch_all(db)
        .await
        .map(|rows| rows.into_iter().collect())
        .unwrap_or_default();
    file_ids
        .iter()
        .copied()
        .filter(|id| active.contains(id))
        .collect()
}

pub(crate) async fn query_backfill_targets(
    state: &SharedState,
    scan_root: &str,
    limit: i64,
    force: bool,
    model_id: Option<i64>,
) -> Vec<i64> {
    // Deliberately NOT using the kv_state-derived active_model_id/
    // active_model_db_id/count_untagged path (wd_tagger.rs) here: that path
    // tracks a separately-set "active model" concept that can diverge from
    // the model tag_file_native_core actually infers with. We must resolve
    // the same model id that tagging will use, so the backfill target list
    // and the model that ends up writing file_wd_tags always agree.
    let model_id = model_id.or(resolve_configured_model_id(state).await);

    let mut clauses = vec!["is_deleted = 0".to_string()];
    let mut like_binds: Vec<String> = Vec::new();

    if !scan_root.trim_end_matches(['/', '\\']).is_empty() {
        clauses.push("(path LIKE ? ESCAPE '~' OR path LIKE ? ESCAPE '~')".to_string());
        let (p1, p2) = scan_root_like_patterns(scan_root);
        like_binds.push(p1);
        like_binds.push(p2);
    }

    if !force {
        clauses.push(
            "NOT EXISTS (SELECT 1 FROM file_wd_tags fwt WHERE fwt.file_id = files.id AND fwt.model_id = ?)"
                .to_string(),
        );
    }

    let where_sql = clauses.join(" AND ");
    let sql = format!("SELECT id FROM files WHERE {where_sql}");
    let mut query = sqlx::query_scalar::<_, i64>(&sql);
    for bind in &like_binds {
        query = query.bind(bind);
    }
    if !force {
        query = query.bind(model_id);
    }

    let mut rows = query.fetch_all(&state.db_read).await.unwrap_or_default();
    // limit is applied on the Rust side, after filtering — no SQL LIMIT
    // clause is used (matches the design spec's decision).
    if limit > 0 {
        rows.truncate(usize::try_from(limit).unwrap_or(0));
    }
    rows
}

/// Mirrors the Python `_scan_root_like_patterns`: escapes LIKE wildcards
/// with `~` and generates forward-slash and backslash path patterns so a
/// scan root matches regardless of path separator style stored in `files.path`.
fn scan_root_like_patterns(scan_root: &str) -> (String, String) {
    let root = scan_root.trim_end_matches(&['/', '\\'][..]);
    let forward_root = root.replace('\\', "/");
    let backward_root = root.replace('/', "\\");
    let like_escape = |value: &str| {
        value
            .replace('~', "~~")
            .replace('%', "~%")
            .replace('_', "~_")
    };
    let forward = format!("{}/%", like_escape(forward_root.trim_end_matches('/')));
    let backward = format!("{}\\%", like_escape(backward_root.trim_end_matches('\\')));
    (forward, backward)
}

/// Outcome of a `start_batch_job` call: whether a new batch job was started,
/// there were no targets to process, or a job was already running.
pub(crate) enum StartResult {
    Started,
    NoTargets,
    AlreadyRunning,
}

/// Starts a WD-Tagger batch/backfill job. Only one `WD_TAGGER_JOB_ID` job may
/// run at a time.
pub(crate) async fn start_batch_job(
    state: SharedState,
    req: BatchRequest,
) -> Result<StartResult, BatchError> {
    let (targets, _scope) = resolve_targets(&state, &req).await?;
    if targets.is_empty() {
        return Ok(StartResult::NoTargets);
    }

    let cancel = match state
        .job_manager
        .start_if_idle(WD_TAGGER_JOB_ID, "WD-Tagger batch")
    {
        Some(token) => token,
        None => return Ok(StartResult::AlreadyRunning),
    };
    let force = req.force;
    let worker_state = state.clone();
    tokio::spawn(async move {
        let result = std::panic::AssertUnwindSafe(run_batch_worker(
            worker_state.clone(),
            WD_TAGGER_JOB_ID.to_string(),
            targets,
            force,
            cancel,
        ))
        .catch_unwind()
        .await;
        if result.is_err() {
            // Defense in depth: if the worker body itself panics, make sure
            // JobManager still transitions the job to a finished state so it
            // never appears stuck as "running" forever.
            worker_state.job_manager.finish(
                WD_TAGGER_JOB_ID,
                None,
                Some("internal panic during batch worker".to_string()),
            );
        }
    });

    Ok(StartResult::Started)
}

/// Processes `targets` sequentially, tagging each file via
/// `tag_file_native_core`. The cancellation token is only checked at file
/// boundaries -- a file that has already started tagging is always allowed
/// to finish. `TagOutcome::Fallback` and `TagOutcome::Rejected` are treated
/// as per-file skips (the batch path never falls back to Python), while
/// `TagOutcome::Fatal` aborts the whole job immediately.
async fn run_batch_worker(
    state: SharedState,
    job_id: String,
    targets: Vec<i64>,
    force: bool,
    cancel: tokio_util::sync::CancellationToken,
) {
    run_batch_worker_with_tagger(
        state,
        job_id,
        targets,
        force,
        cancel,
        |state, file_id, force| Box::pin(tag_file_native_core(state, file_id, force)),
    )
    .await;
}

pub(crate) async fn run_batch_worker_with_tagger<F>(
    state: SharedState,
    job_id: String,
    targets: Vec<i64>,
    force: bool,
    cancel: tokio_util::sync::CancellationToken,
    tag_file: F,
) where
    F: for<'a> Fn(&'a SharedState, i64, bool) -> BoxFuture<'a, TagOutcome>,
{
    let total = targets.len() as u64;
    let mut processed: u64 = 0;
    let mut skipped: u64 = 0;
    let mut errors: u64 = 0;

    for (idx, file_id) in targets.into_iter().enumerate() {
        if cancel.is_cancelled() {
            break;
        }
        match tag_file(&state, file_id, force).await {
            TagOutcome::Tagged(_) => {
                processed += 1;
            }
            TagOutcome::Skipped(_) => {
                skipped += 1;
            }
            TagOutcome::Fallback => {
                errors += 1;
                tracing::warn!(
                    file_id,
                    "wd-tagger batch: unsupported/rejected file, skipping"
                );
            }
            TagOutcome::Rejected(body) => {
                errors += 1;
                tracing::warn!(
                    file_id,
                    ?body,
                    "wd-tagger batch: file-specific error, skipping"
                );
            }
            TagOutcome::Fatal(reason) => {
                tracing::error!(
                    file_id,
                    ?reason,
                    "wd-tagger batch: fatal error, aborting batch"
                );
                state.job_manager.finish(
                    &job_id,
                    Some(json!({
                        "processed": processed,
                        "skipped": skipped,
                        "total": total,
                        "errors": errors + 1,
                    })),
                    Some(fatal_reason_label(&reason)),
                );
                return;
            }
        }
        state
            .job_manager
            .update_progress(&job_id, (idx + 1) as u64, total, None);
    }

    if processed > 0 {
        // This is the exact sanitized model identifier passed to both
        // call_wd_infer and write_wd_tags, rather than the wd_model_dict
        // integer foreign key used by backfill queries.
        let model_id = configured_model_id_string(&state);
        if let Err(error) = set_active_model_id(&state.db, Some(&model_id)).await {
            tracing::error!(?error, "wd-tagger batch: failed to sync active model");
        }
    }

    let result = Some(json!({
        "processed": processed,
        "skipped": skipped,
        "total": total,
        "errors": errors,
    }));
    if cancel.is_cancelled() {
        state.job_manager.finish_cancelled(&job_id, result);
    } else {
        state.job_manager.finish(&job_id, result, None);
    }
}

fn fatal_reason_label(reason: &FatalReason) -> String {
    format!("{reason:?}")
}

#[cfg(test)]
#[path = "wd_tagger_batch/test_helpers.rs"]
mod test_helpers;
#[cfg(test)]
#[path = "wd_tagger_batch/tests_handlers.rs"]
mod tests_handlers;
#[cfg(test)]
#[path = "wd_tagger_batch/tests_resolve.rs"]
mod tests_resolve;
#[cfg(test)]
#[path = "wd_tagger_batch/tests_worker.rs"]
mod tests_worker;

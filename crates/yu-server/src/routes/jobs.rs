use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::jobs::model::StatusResult;
use crate::state::SharedState;

/// GET `/api/jobs/status`
pub async fn status(State(state): State<SharedState>) -> Response {
    let rust = state.job_manager.get_status();
    Json(with_envelope(&rust)).into_response()
}

/// Wrap a bare `StatusResult` in the Python `api_result` envelope so the shape is
/// identical whether or not a Python backend is present.
fn with_envelope(status: &StatusResult) -> Value {
    json!({
        "ok": true,
        "error": null,
        "data": null,
        "has_active": status.has_active,
        "active": status.active,
        "recent": status.recent,
    })
}

/// GET `/api/jobs/{job_id}`
pub async fn get_job(
    State(state): State<SharedState>,
    Path(job_id): Path<String>,
) -> impl IntoResponse {
    match state.job_manager.get_job(&job_id) {
        Some(job) => (StatusCode::OK, Json(json!(job))).into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "job not found"})),
        )
            .into_response(),
    }
}

/// POST `/api/jobs/{job_id}/cancel`
pub async fn cancel(
    State(state): State<SharedState>,
    Path(job_id): Path<String>,
) -> impl IntoResponse {
    if state.job_manager.cancel_job(&job_id) {
        (StatusCode::OK, Json(json!({"ok": true}))).into_response()
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "job not found or not running"})),
        )
            .into_response()
    }
}

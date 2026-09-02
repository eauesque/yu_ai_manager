//! `/api/scheduler/*` — GET handlers use native SchedulerState when standalone;
//! non-standalone forwards to Python.

use axum::{
    body::Bytes,
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    scheduler::history,
    state::SharedState,
};

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn fwd_get(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "python_backend_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .get(&url)
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
        .send()
        .await
    {
        Ok(resp) => {
            let status =
                StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            match resp.bytes().await {
                Ok(b) => (status, b).into_response(),
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
        Err(e) => {
            tracing::warn!(%url, ?e, "scheduler python GET forward error");
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({"ok": false, "error": "python_backend_unavailable"})),
            )
                .into_response()
        }
    }
}

async fn fwd_post(state: &SharedState, path: &str, body: Bytes) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "python_backend_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
        .body(body)
        .send()
        .await
    {
        Ok(resp) => {
            let status =
                StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            match resp.bytes().await {
                Ok(b) => (status, b).into_response(),
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
        Err(e) => {
            tracing::warn!(%url, ?e, "scheduler python POST forward error");
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({"ok": false, "error": "python_backend_unavailable"})),
            )
                .into_response()
        }
    }
}

async fn fwd_delete(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "python_backend_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .delete(&url)
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
        .send()
        .await
    {
        Ok(resp) => {
            let status =
                StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            match resp.bytes().await {
                Ok(b) => (status, b).into_response(),
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
        Err(e) => {
            tracing::warn!(%url, ?e, "scheduler python DELETE forward error");
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({"ok": false, "error": "python_backend_unavailable"})),
            )
                .into_response()
        }
    }
}

/// GET /api/scheduler/status
pub async fn scheduler_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let Some(ss) = state.scheduler_state.get() else {
        return Json(json!({
            "ok": true,
            "error": null,
            "data": {"status": {"running": false, "job_count": 0, "jobs": []}}
        }))
        .into_response();
    };

    let (job_ids_owned, metas) = {
        let registry = ss.registry.lock().unwrap();
        let ids: Vec<String> = registry.keys().cloned().collect();
        let metas: Vec<(String, String, String, bool)> = registry
            .values()
            .map(|m| {
                (
                    m.job_id.clone(),
                    m.name.clone(),
                    m.trigger_repr.clone(),
                    m.paused,
                )
            })
            .collect();
        (ids, metas)
    };
    let job_ids: Vec<&str> = job_ids_owned.iter().map(|s| s.as_str()).collect();

    let last_map = history::get_last_for_jobs(&state.db_read, &job_ids)
        .await
        .unwrap_or_default();

    let jobs: Vec<Value> = metas
        .iter()
        .map(|(job_id, name, trigger, paused)| {
            let last = last_map.get(job_id.as_str());
            json!({
                "id": job_id,
                "name": name,
                "next_run_time": null,
                "paused": paused,
                "trigger": trigger,
                "last_success": last.map(|r| r.success),
                "last_time": last.map(|r| r.timestamp),
                "last_summary": last.and_then(|r| r.result_summary.clone().or_else(|| r.error.clone())),
            })
        })
        .collect();

    Json(json!({
        "ok": true,
        "error": null,
        "data": {
            "status": {
                "running": true,
                "job_count": jobs.len(),
                "jobs": jobs,
            }
        }
    }))
    .into_response()
}

/// GET /api/scheduler/jobs
pub async fn scheduler_jobs(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let Some(ss) = state.scheduler_state.get() else {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    };

    let registry = ss.registry.lock().unwrap();
    let jobs: Vec<Value> = registry
        .values()
        .map(|m| {
            json!({
                "id": m.job_id,
                "name": m.name,
                "next_run_time": null,
                "paused": m.paused,
                "trigger": m.trigger_repr,
            })
        })
        .collect();
    drop(registry);

    Json(json!({"ok": true, "error": null, "data": {"jobs": jobs}})).into_response()
}

/// GET /api/scheduler/history
pub async fn scheduler_history(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.scheduler_state.get().is_none() {
        return Json(json!({
            "ok": true,
            "error": null,
            "data": {"history": []}
        }))
        .into_response();
    }
    let records = history::get_recent_history(&state.db_read, 100)
        .await
        .unwrap_or_default();

    let hist: Vec<Value> = records
        .iter()
        .map(|r| {
            json!({
                "job_id": r.job_id,
                "timestamp": r.timestamp,
                "duration_ms": r.duration_ms,
                "success": r.success,
                "error": r.error,
                "result_summary": r.result_summary,
            })
        })
        .collect();

    Json(json!({"ok": true, "error": null, "data": {"history": hist}})).into_response()
}

/// POST /api/scheduler/jobs
pub async fn scheduler_add_job(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.scheduler_state.get().is_none() {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    }
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "scheduler_unavailable"})),
    )
        .into_response()
}

/// DELETE /api/scheduler/jobs/:job_id
pub async fn scheduler_remove_job(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(job_id): Path<String>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.scheduler_state.get().is_none() {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    }
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "scheduler_unavailable"})),
    )
        .into_response()
}

/// POST /api/scheduler/jobs/:job_id/pause
pub async fn scheduler_pause_job(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(job_id): Path<String>,
    body: Bytes,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.scheduler_state.get().is_none() {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    }
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "scheduler_unavailable"})),
    )
        .into_response()
}

/// POST /api/scheduler/jobs/:job_id/resume
pub async fn scheduler_resume_job(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(job_id): Path<String>,
    body: Bytes,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.scheduler_state.get().is_none() {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    }
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "scheduler_unavailable"})),
    )
        .into_response()
}

/// POST /api/scheduler/jobs/:job_id/trigger
pub async fn scheduler_trigger_job(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(job_id): Path<String>,
    body: Bytes,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.scheduler_state.get().is_none() {
        return (
            StatusCode::NOT_IMPLEMENTED,
            Json(json!({"ok": false, "error": "not implemented"})),
        )
            .into_response();
    }
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "scheduler_unavailable"})),
    )
        .into_response()
}

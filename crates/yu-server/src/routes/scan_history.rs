use std::path::PathBuf;

use axum::{
    extract::{Extension, Query, State},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

#[derive(Deserialize)]
pub struct HistoryParams {
    limit: Option<usize>,
}

fn history_file_path(state: &SharedState) -> PathBuf {
    // scan_history.json lives in the same directory as the DB file (data/)
    PathBuf::from(&state.config.db_path)
        .parent()
        .unwrap_or_else(|| std::path::Path::new("."))
        .join("scan_history.json")
}

pub async fn scan_history_clear(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let path = history_file_path(&state);
    if path.exists() {
        if let Err(e) = std::fs::write(&path, b"[]") {
            tracing::error!(?e, "scan_history_clear: failed to write file");
            return Json(json!({"ok": false, "error": "io_error"})).into_response();
        }
    }
    Json(json!({"ok": true, "error": null, "data": {"status": "cleared"}})).into_response()
}

pub async fn scan_history(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HistoryParams>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }

    let limit = params.limit.unwrap_or(50).min(100);
    let path = history_file_path(&state);

    let entries: Vec<Value> = if path.exists() {
        match std::fs::read_to_string(&path) {
            Ok(text) => match serde_json::from_str::<Vec<Value>>(&text) {
                Ok(mut all) => {
                    all.reverse();
                    all.truncate(limit);
                    all
                }
                Err(_) => vec![],
            },
            Err(_) => vec![],
        }
    } else {
        vec![]
    };

    Json(json!({
        "ok": true,
        "error": null,
        "data": null,
        "entries": entries,
        "limit": limit,
    }))
    .into_response()
}

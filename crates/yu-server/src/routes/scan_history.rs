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
    Json(json!({"ok": true, "error": null, "data": null, "status": "cleared"})).into_response()
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

#[cfg(test)]
mod tests {
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use serde_json::Value;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use super::*;
    use crate::state::{AppState, Config};

    async fn test_state(root: &tempfile::TempDir) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(
            AppState::new(
                Config {
                    db_path: root
                        .path()
                        .join("history.db")
                        .to_string_lossy()
                        .into_owned(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,
                    pin_boss_login_ui: false,
                    trusted_ips: HashSet::new(),
                    trusted_peer_ips: HashSet::new(),
                    rate_limit_trusted_proxies: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: root.path().join("config.json"),
                    project_root: root.path().to_path_buf(),
                    app_config: json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                    wd_tagger_root: PathBuf::from("."),
                    clip_model_dir: PathBuf::from("."),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    #[tokio::test]
    async fn clear_returns_python_envelope() {
        let root = tempfile::tempdir().unwrap();
        let response = scan_history_clear(State(test_state(&root).await), None).await;
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&body).unwrap(),
            json!({"ok": true, "error": null, "data": null, "status": "cleared"})
        );
    }
}

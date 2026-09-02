//! Native groups-index routes; Python source: routes/files_routes_groups.py and core/group_api/responses.py.

use std::collections::HashMap;

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    groups_index::{build_container_thumb_ids_response, parse_thumb_limit},
    state::SharedState,
};

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn internal_error(message: &str) -> Response {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"error": message})),
    )
        .into_response()
}

pub async fn groups_index(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match state.groups_index_cache.get(&state.db_read).await {
        Ok(index) => Json(index).into_response(),
        Err(error) => {
            tracing::error!(?error, "groups index failed");
            internal_error("Failed to get groups index")
        }
    }
}

pub async fn groups_index_warm(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match state.groups_index_cache.get(&state.db_read).await {
        Ok(_) => Json(json!({"ok": true})).into_response(),
        Err(error) => {
            tracing::error!(?error, "groups index warm failed");
            internal_error("Failed to warm groups index")
        }
    }
}

pub async fn group_members(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let key = params.get("key").map(|value| value.trim()).unwrap_or("");
    if key.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ids": [], "error": "missing key"})),
        )
            .into_response();
    }
    match state.groups_index_cache.get(&state.db_read).await {
        Ok(index) => {
            if let Some(entry) = index.folders.get(key).or_else(|| index.zips.get(key)) {
                Json(json!({"ids": entry.ids, "key": key})).into_response()
            } else {
                Json(json!({"ids": [], "key": key})).into_response()
            }
        }
        Err(error) => {
            tracing::error!(?error, "group members failed");
            internal_error("Failed to get group members")
        }
    }
}

pub async fn container_thumb_ids(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let limit = parse_thumb_limit(params.get("limit").map(String::as_str));
    match build_container_thumb_ids_response(&state.db_read, &state.groups_index_cache, limit).await
    {
        Ok(payload) => Json(payload).into_response(),
        Err(error) => {
            tracing::error!(?error, "container thumb ids failed");
            internal_error("Failed to get container thumbnail ids")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{body::to_bytes, extract::State};
    use serde_json::{json, Value};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tempfile::TempDir;

    use crate::state::{AppState, Config, SharedState};

    async fn test_state(seed: &str) -> (SharedState, TempDir) {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT,
               mtime,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );",
        )
        .execute(&pool)
        .await
        .unwrap();
        if !seed.is_empty() {
            sqlx::raw_sql(seed).execute(&pool).await.unwrap();
        }
        let temp = TempDir::new().unwrap();
        let state = Arc::new(
            AppState::new(
                Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: HashSet::new(),
                    trusted_peer_ips: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("config.json"),
                    project_root: PathBuf::from("."),
                    app_config: json!({}),
                    cache_dir: temp.path().to_path_buf(),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        );
        (state, temp)
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn group_members_returns_missing_and_unknown_shapes() {
        let (state, _temp) = test_state("").await;

        let missing =
            json_body(group_members(State(Arc::clone(&state)), None, Query(HashMap::new())).await)
                .await;
        let unknown = json_body(
            group_members(
                State(state),
                None,
                Query(HashMap::from([(
                    "key".to_string(),
                    " folder:x ".to_string(),
                )])),
            )
            .await,
        )
        .await;

        assert_eq!(missing, json!({"ids": [], "error": "missing key"}));
        assert_eq!(unknown, json!({"ids": [], "key": "folder:x"}));
    }
}

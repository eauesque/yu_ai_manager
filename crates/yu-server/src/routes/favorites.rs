use std::collections::HashMap;

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_bad_request(message: &'static str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": message})),
    )
        .into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": "internal_server_error"})),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

/// The clamp on the same expression is what makes the cast exact: the value is
/// already inside `i64`'s range by the time it is narrowed, so nothing can be
/// lost. Saturating is the intended behaviour for an id that overflowed.
#[allow(clippy::cast_possible_truncation)]
fn clamp_sqlite_int(value: i128) -> i64 {
    value.clamp(i64::MIN as i128, i64::MAX as i128) as i64
}

fn parse_i64(raw: &str) -> Option<i64> {
    raw.trim().parse::<i128>().ok().map(clamp_sqlite_int)
}

fn parse_check_ids(raw: Option<&String>) -> Result<Option<Vec<i64>>, &'static str> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    if raw.is_empty() {
        return Ok(None);
    }
    let mut ids = Vec::new();
    for part in raw.split(',') {
        if part.trim().is_empty() {
            continue;
        }
        let Some(id) = parse_i64(part) else {
            return Err("invalid ids");
        };
        ids.push(id);
    }
    if ids.is_empty() {
        Ok(None)
    } else {
        Ok(Some(ids))
    }
}

fn parse_optional_i64(
    raw: Option<&String>,
    message: &'static str,
) -> Result<Option<i64>, &'static str> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    if raw.is_empty() {
        return Ok(None);
    }
    parse_i64(raw).map(Some).ok_or(message)
}

async fn favorite_ids(
    pool: &SqlitePool,
    ids: &[i64],
    collection_id: Option<i64>,
) -> Result<Vec<i64>, sqlx::Error> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let mut query = QueryBuilder::<Sqlite>::new("SELECT ");
    if collection_id.is_none() {
        query.push("DISTINCT ");
    }
    query.push("file_id FROM favorites WHERE file_id IN (");
    let mut separated = query.separated(", ");
    for id in ids {
        separated.push_bind(id);
    }
    separated.push_unseparated(")");
    if let Some(collection_id) = collection_id {
        query.push(" AND collection_id = ");
        query.push_bind(collection_id);
    }
    let rows = query.build().fetch_all(pool).await?;
    let found = rows
        .into_iter()
        .map(|row| row.get::<i64, _>(0))
        .collect::<std::collections::HashSet<_>>();
    Ok(ids
        .iter()
        .copied()
        .filter(|id| found.contains(id))
        .collect())
}

pub async fn check(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let ids = match parse_check_ids(params.get("ids")) {
        Ok(Some(ids)) => ids,
        Ok(None) => return api_result(json!({"favorites": []})),
        Err(message) => return api_bad_request(message),
    };
    let collection_id =
        match parse_optional_i64(params.get("collection_id"), "invalid collection_id") {
            Ok(value) => value,
            Err(message) => return api_bad_request(message),
        };
    match favorite_ids(&state.db_read, &ids, collection_id).await {
        Ok(ids) => api_result(json!({"favorites": ids})),
        Err(error) => internal_error(error, "failed to check favorites"),
    }
}

pub async fn check_collections(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let file_id = match parse_optional_i64(params.get("file_id"), "invalid file_id") {
        Ok(Some(file_id)) => file_id,
        Ok(None) => return api_result(json!({"collections": []})),
        Err(message) => return api_bad_request(message),
    };
    match sqlx::query("SELECT collection_id FROM favorites WHERE file_id=? ORDER BY collection_id")
        .bind(file_id)
        .fetch_all(&state.db_read)
        .await
    {
        Ok(rows) => api_result(json!({
            "collections": rows.into_iter().map(|row| row.get::<i64, _>(0)).collect::<Vec<_>>()
        })),
        Err(error) => internal_error(error, "failed to check favorite collections"),
    }
}

pub async fn list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let collection_id =
        match parse_optional_i64(params.get("collection_id"), "invalid collection_id") {
            Ok(value) => value,
            Err(message) => return api_bad_request(message),
        };
    let rows = if let Some(collection_id) = collection_id {
        sqlx::query(
            "SELECT fav.file_id FROM favorites fav
             JOIN files f ON f.id=fav.file_id AND f.is_deleted=0
             WHERE fav.collection_id=?
             ORDER BY fav.added_at DESC, fav.file_id DESC",
        )
        .bind(collection_id)
        .fetch_all(&state.db_read)
        .await
    } else {
        sqlx::query(
            "SELECT fav.file_id, MAX(fav.added_at) AS added_at FROM favorites fav
             JOIN files f ON f.id=fav.file_id AND f.is_deleted=0
             GROUP BY fav.file_id
             ORDER BY added_at DESC, fav.file_id DESC",
        )
        .fetch_all(&state.db_read)
        .await
    };
    match rows {
        Ok(rows) => api_result(json!({
            "ids": rows.into_iter().map(|row| row.get::<i64, _>(0)).collect::<Vec<_>>()
        })),
        Err(error) => internal_error(error, "failed to list favorites"),
    }
}

#[derive(serde::Deserialize)]
struct ToggleRequest {
    file_id: Option<Value>,
    collection_id: Option<i64>,
}

fn parse_positive_file_id(value: Option<Value>) -> Option<i64> {
    let value = value?;
    match value {
        Value::Number(number) => number.as_i64().filter(|id| *id > 0),
        _ => None,
    }
}

pub async fn toggle(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if !body.is_object() {
        return api_bad_request("JSON object required");
    }
    let request: ToggleRequest = match serde_json::from_value(body) {
        Ok(request) => request,
        Err(_) => return api_bad_request("JSON object required"),
    };
    let Some(file_id) = parse_positive_file_id(request.file_id) else {
        return api_bad_request("file_id required");
    };
    let collection_id = request.collection_id.unwrap_or(1);

    let exists =
        match sqlx::query("SELECT file_id FROM favorites WHERE file_id=? AND collection_id=?")
            .bind(file_id)
            .bind(collection_id)
            .fetch_optional(&state.db_read)
            .await
        {
            Ok(row) => row.is_some(),
            Err(error) => return internal_error(error, "failed to check favorite before toggle"),
        };

    let result = if exists {
        sqlx::query("DELETE FROM favorites WHERE file_id=? AND collection_id=?")
            .bind(file_id)
            .bind(collection_id)
            .execute(&state.db)
            .await
            .map(|_| false)
    } else {
        sqlx::query(
            "INSERT INTO favorites (file_id, collection_id, added_at) VALUES (?, ?, unixepoch())",
        )
        .bind(file_id)
        .bind(collection_id)
        .execute(&state.db)
        .await
        .map(|_| true)
    };

    match result {
        Ok(favorited) => api_result(json!({
            "file_id": file_id,
            "collection_id": collection_id,
            "favorited": favorited
        })),
        Err(error) => internal_error(error, "failed to toggle favorite"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    async fn test_state() -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );
             CREATE TABLE favorites (
               file_id INTEGER NOT NULL,
               collection_id INTEGER NOT NULL DEFAULT 1,
               added_at INTEGER,
               PRIMARY KEY(file_id, collection_id)
             );
             INSERT INTO files(id, path, is_deleted) VALUES
               (1, '/home/pi/a.png', 0),
               (2, '/home/pi/nested/b.png', 0),
               (3, '/home/pi/deleted.png', 1),
               (4, '/other/c.png', 0);
             INSERT INTO favorites(file_id, collection_id, added_at) VALUES
               (1, 1, 100),
               (1, 2, 350),
               (2, 2, 200),
               (4, 1, 300),
               (10, 1, 0);",
        )
        .execute(&pool)
        .await
        .unwrap();

        Arc::new(
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
                    cache_dir: PathBuf::from("."),
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
        )
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn check_returns_requested_favorite_ids_in_request_order() {
        let response = check(
            State(test_state().await),
            None,
            Query(HashMap::from([("ids".to_string(), "4,2,1".to_string())])),
        )
        .await;
        let value = json_body(response).await;
        assert_eq!(value["favorites"], json!([4, 2, 1]));
    }

    #[tokio::test]
    async fn check_rejects_invalid_ids_like_python() {
        let response = check(
            State(test_state().await),
            None,
            Query(HashMap::from([("ids".to_string(), "bad".to_string())])),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value, json!({"ok": false, "error": "invalid ids"}));
    }

    #[tokio::test]
    async fn check_collections_returns_collection_ids_for_file() {
        let response = check_collections(
            State(test_state().await),
            None,
            Query(HashMap::from([("file_id".to_string(), "2".to_string())])),
        )
        .await;
        let value = json_body(response).await;
        assert_eq!(value["collections"], json!([2]));
    }

    #[tokio::test]
    async fn list_returns_non_deleted_ids_newest_first() {
        let response = list(State(test_state().await), None, Query(HashMap::new())).await;
        let value = json_body(response).await;
        assert_eq!(value["ids"], json!([1, 4, 2]));
    }

    #[tokio::test]
    async fn list_deduplicates_files_in_multiple_collections_by_latest_added_at() {
        let response = list(State(test_state().await), None, Query(HashMap::new())).await;
        let value = json_body(response).await;
        assert_eq!(value["ids"], json!([1, 4, 2]));
        assert_eq!(
            value["ids"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|id| **id == json!(1))
                .count(),
            1
        );
    }

    #[tokio::test]
    async fn favorites_toggle_inserts_when_absent() {
        let state = test_state().await;
        let response = toggle(
            State(Arc::clone(&state)),
            None,
            Json(json!({"file_id": 7, "collection_id": 1})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["file_id"], 7);
        assert_eq!(value["collection_id"], 1);
        assert_eq!(value["favorited"], true);

        let count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM favorites WHERE file_id = 7 AND collection_id = 1",
        )
        .fetch_one(&state.db_read)
        .await
        .unwrap();
        assert_eq!(count, 1);
    }

    #[tokio::test]
    async fn favorites_toggle_deletes_when_present() {
        let state = test_state().await;
        let response = toggle(
            State(Arc::clone(&state)),
            None,
            Json(json!({"file_id": 10, "collection_id": 1})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["favorited"], false);

        let count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM favorites WHERE file_id = 10 AND collection_id = 1",
        )
        .fetch_one(&state.db_read)
        .await
        .unwrap();
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn favorites_toggle_rejects_missing_file_id() {
        let response = toggle(
            State(test_state().await),
            None,
            Json(json!({"collection_id": 1})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let value = json_body(response).await;
        assert_eq!(value, json!({"ok": false, "error": "file_id required"}));
    }

    #[tokio::test]
    async fn favorites_toggle_uses_default_collection_id_1() {
        let state = test_state().await;
        let response = toggle(State(Arc::clone(&state)), None, Json(json!({"file_id": 8}))).await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["collection_id"], 1);
        assert_eq!(value["favorited"], true);

        let count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM favorites WHERE file_id = 8 AND collection_id = 1",
        )
        .fetch_one(&state.db_read)
        .await
        .unwrap();
        assert_eq!(count, 1);
    }
}

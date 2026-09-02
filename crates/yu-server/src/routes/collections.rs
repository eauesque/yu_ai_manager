#![allow(clippy::result_large_err)]

use axum::{
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
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

#[derive(Deserialize)]
struct CreateRequest {
    name: Option<Value>,
    query_json: Option<String>,
}

#[derive(Deserialize)]
struct UpdateRequest {
    name: Option<Value>,
}

#[derive(Deserialize)]
struct ReorderRequest {
    ids: Option<Vec<i64>>,
}

#[derive(Deserialize)]
struct BatchFileIdsRequest {
    file_ids: Option<Vec<Value>>,
}

fn extract_name(raw: Option<Value>) -> Option<String> {
    raw?.as_str()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

fn api_err(msg: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": msg})),
    )
        .into_response()
}

fn api_err_with_code(msg: &str, code: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": msg, "code": code})),
    )
        .into_response()
}

fn parse_object<T: for<'de> Deserialize<'de>>(body: Value) -> Result<T, &'static str> {
    if !body.is_object() {
        return Err("JSON object required");
    }
    serde_json::from_value(body).map_err(|_| "JSON object required")
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

async fn table_exists(db: &SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

async fn build_list_response(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "collections").await? {
        return Ok(json!({"collections": []}));
    }
    let rows = sqlx::query(
        "SELECT c.id, c.name, c.sort_order, c.created_at,
                COUNT(fav.file_id) AS count, c.query_json
         FROM collections c
         LEFT JOIN favorites fav ON fav.collection_id=c.id
         GROUP BY c.id ORDER BY c.sort_order, c.id",
    )
    .fetch_all(pool)
    .await?;
    let collections = rows
        .into_iter()
        .map(|row| {
            let query_json = row
                .try_get::<Option<String>, _>("query_json")
                .ok()
                .flatten();
            json!({
                "id": row.get::<i64, _>("id"),
                "name": row.get::<String, _>("name"),
                "sort_order": row.get::<i64, _>("sort_order"),
                "created_at": row.try_get::<Option<i64>, _>("created_at").ok().flatten(),
                "count": row.get::<i64, _>("count"),
                "is_smart": query_json.is_some(),
                "query_json": query_json,
            })
        })
        .collect::<Vec<_>>();
    Ok(json!({"collections": collections}))
}

pub async fn list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_list_response(&state.db_read).await {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "failed to list collections"),
    }
}

pub async fn create(State(state): State<SharedState>, Json(body): Json<Value>) -> Response {
    let body: CreateRequest = match parse_object(body) {
        Ok(body) => body,
        Err(message) => return api_err(message),
    };
    let Some(name) = extract_name(body.name) else {
        return api_err("name required");
    };

    let next_order =
        match sqlx::query_scalar::<_, i64>("SELECT COALESCE(MAX(sort_order),0)+1 FROM collections")
            .fetch_one(&state.db)
            .await
        {
            Ok(next_order) => next_order,
            Err(error) => return internal_error(error, "failed to get next collection sort order"),
        };

    let result = match sqlx::query(
        "INSERT INTO collections (name, sort_order, created_at, query_json)
         VALUES (?, ?, unixepoch(), ?)",
    )
    .bind(&name)
    .bind(next_order)
    .bind(&body.query_json)
    .execute(&state.db)
    .await
    {
        Ok(result) => result,
        Err(error) => return internal_error(error, "failed to create collection"),
    };

    (
        StatusCode::CREATED,
        Json(json!({
            "ok": true,
            "error": null,
            "data": null,
            "id": result.last_insert_rowid(),
            "name": name,
            "is_smart": body.query_json.is_some(),
        })),
    )
        .into_response()
}

pub async fn update(
    State(state): State<SharedState>,
    Path(id): Path<i64>,
    Json(body): Json<Value>,
) -> Response {
    let body: UpdateRequest = match parse_object(body) {
        Ok(body) => body,
        Err(message) => return api_err(message),
    };
    let Some(name) = extract_name(body.name) else {
        return api_err("name required");
    };

    if let Err(error) = sqlx::query("UPDATE collections SET name=? WHERE id=?")
        .bind(&name)
        .bind(id)
        .execute(&state.db)
        .await
    {
        return internal_error(error, "failed to update collection");
    }

    api_result(json!({"id": id, "name": name}))
}

pub async fn delete(State(state): State<SharedState>, Path(id): Path<i64>) -> Response {
    if id == 1 {
        return api_err("Collection could not be deleted");
    }

    if let Err(error) = sqlx::query("DELETE FROM favorites WHERE collection_id=?")
        .bind(id)
        .execute(&state.db)
        .await
    {
        return internal_error(error, "failed to delete collection favorites");
    }
    if let Err(error) = sqlx::query("DELETE FROM collections WHERE id=?")
        .bind(id)
        .execute(&state.db)
        .await
    {
        return internal_error(error, "failed to delete collection");
    }

    api_result(json!({"deleted": id}))
}

pub async fn reorder(State(state): State<SharedState>, Json(body): Json<Value>) -> Response {
    let body: ReorderRequest = match parse_object(body) {
        Ok(body) => body,
        Err(message) => return api_err(message),
    };
    let Some(ids) = body.ids.filter(|ids| !ids.is_empty()) else {
        return api_err("ids list required");
    };

    for (sort_order, id) in ids.into_iter().enumerate() {
        if let Err(error) = sqlx::query("UPDATE collections SET sort_order=? WHERE id=?")
            .bind(sort_order as i64)
            .bind(id)
            .execute(&state.db)
            .await
        {
            return internal_error(error, "failed to reorder collection");
        }
    }

    api_result(json!({}))
}

fn valid_file_id(value: &Value) -> Option<i64> {
    value.as_i64().filter(|id| *id > 0)
}

fn batch_size_error(len: usize) -> Option<Response> {
    if len > 500 {
        Some(api_err_with_code(
            &format!("Batch size {len} exceeds maximum of 500"),
            "batch_too_large",
        ))
    } else {
        None
    }
}

async fn existing_file_ids(pool: &SqlitePool, ids: &[i64]) -> Result<Vec<i64>, sqlx::Error> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let mut builder: QueryBuilder<Sqlite> = QueryBuilder::new("SELECT id FROM files WHERE id IN (");
    let mut separated = builder.separated(", ");
    for id in ids {
        separated.push_bind(id);
    }
    separated.push_unseparated(") AND is_deleted=0");
    builder.build_query_scalar::<i64>().fetch_all(pool).await
}

async fn favorite_file_ids(
    pool: &SqlitePool,
    collection_id: i64,
    ids: &[i64],
) -> Result<Vec<i64>, sqlx::Error> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let mut builder: QueryBuilder<Sqlite> =
        QueryBuilder::new("SELECT file_id FROM favorites WHERE file_id IN (");
    let mut separated = builder.separated(", ");
    for id in ids {
        separated.push_bind(id);
    }
    separated.push_unseparated(") AND collection_id=");
    separated.push_bind_unseparated(collection_id);
    builder.build_query_scalar::<i64>().fetch_all(pool).await
}

pub async fn batch_add(
    State(state): State<SharedState>,
    Path(id): Path<i64>,
    Json(body): Json<Value>,
) -> Response {
    let body: BatchFileIdsRequest = match parse_object(body) {
        Ok(body) => body,
        Err(message) => return api_err(message),
    };
    let Some(file_ids) = body.file_ids.filter(|ids| !ids.is_empty()) else {
        return api_err_with_code("file_ids array required", "batch_empty");
    };
    if let Some(response) = batch_size_error(file_ids.len()) {
        return response;
    }

    let collection_exists =
        match sqlx::query_scalar::<_, i64>("SELECT id FROM collections WHERE id=?")
            .bind(id)
            .fetch_optional(&state.db_read)
            .await
        {
            Ok(found) => found.is_some(),
            Err(error) => return internal_error(error, "failed to check collection existence"),
        };
    if !collection_exists {
        let errors = file_ids
            .into_iter()
            .map(|file_id| {
                json!({
                    "file_id": file_id,
                    "code": "collection_not_found",
                    "error": "Collection not found",
                })
            })
            .collect::<Vec<_>>();
        return api_result(json!({
            "data": {
                "total": errors.len(),
                "succeeded": 0,
                "failed": errors.len(),
                "errors": errors,
            }
        }));
    }

    let candidate_ids = file_ids
        .iter()
        .filter_map(valid_file_id)
        .collect::<Vec<_>>();
    let existing_ids = match existing_file_ids(&state.db_read, &candidate_ids).await {
        Ok(ids) => ids.into_iter().collect::<std::collections::HashSet<_>>(),
        Err(error) => return internal_error(error, "failed to check file existence"),
    };
    let favorite_ids = match favorite_file_ids(&state.db_read, id, &candidate_ids).await {
        Ok(ids) => ids.into_iter().collect::<std::collections::HashSet<_>>(),
        Err(error) => return internal_error(error, "failed to check collection favorites"),
    };

    let mut succeeded = 0_usize;
    let mut errors = Vec::new();
    let mut inserts = Vec::new();
    for file_id in &file_ids {
        let Some(file_id_int) = valid_file_id(file_id) else {
            errors.push(json!({
                "file_id": file_id,
                "code": "invalid_value",
                "error": "file_id must be a positive integer",
            }));
            continue;
        };
        if !existing_ids.contains(&file_id_int) {
            errors.push(json!({
                "file_id": file_id_int,
                "code": "not_found",
                "error": "File not found",
            }));
            continue;
        }
        succeeded += 1;
        if !favorite_ids.contains(&file_id_int) {
            inserts.push(file_id_int);
        }
    }

    for file_id in inserts {
        if let Err(error) = sqlx::query(
            "INSERT INTO favorites (file_id, collection_id, added_at)
             VALUES (?, ?, unixepoch())",
        )
        .bind(file_id)
        .bind(id)
        .execute(&state.db)
        .await
        {
            return internal_error(error, "failed to add collection favorite");
        }
    }

    api_result(json!({
        "data": {
            "total": file_ids.len(),
            "succeeded": succeeded,
            "failed": errors.len(),
            "errors": errors,
        }
    }))
}

pub async fn batch_remove(
    State(state): State<SharedState>,
    Path(id): Path<i64>,
    Json(body): Json<Value>,
) -> Response {
    let body: BatchFileIdsRequest = match parse_object(body) {
        Ok(body) => body,
        Err(message) => return api_err(message),
    };
    let Some(file_ids) = body.file_ids.filter(|ids| !ids.is_empty()) else {
        return api_err_with_code("file_ids array required", "batch_empty");
    };
    if let Some(response) = batch_size_error(file_ids.len()) {
        return response;
    }

    let valid_ids = file_ids
        .iter()
        .filter_map(valid_file_id)
        .collect::<Vec<_>>();
    let mut removed = 0_u64;
    for chunk in valid_ids.chunks(500) {
        if chunk.is_empty() {
            continue;
        }
        let mut builder: QueryBuilder<Sqlite> =
            QueryBuilder::new("DELETE FROM favorites WHERE file_id IN (");
        let mut separated = builder.separated(", ");
        for file_id in chunk {
            separated.push_bind(file_id);
        }
        separated.push_unseparated(") AND collection_id=");
        separated.push_bind_unseparated(id);
        match builder.build().execute(&state.db).await {
            Ok(result) => removed += result.rows_affected(),
            Err(error) => return internal_error(error, "failed to remove collection favorites"),
        }
    }

    api_result(json!({"data": {"removed": removed}}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_state(seed: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE collections (
               id INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               sort_order INTEGER NOT NULL DEFAULT 0,
               created_at INTEGER,
               query_json TEXT
             );
             CREATE TABLE favorites (
               file_id INTEGER NOT NULL,
               collection_id INTEGER NOT NULL,
               added_at INTEGER
             );
             CREATE TABLE IF NOT EXISTS files (
               id INTEGER PRIMARY KEY,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );",
        )
        .execute(&pool)
        .await
        .unwrap();
        sqlx::raw_sql(
            "INSERT INTO files(id, is_deleted) VALUES (10, 0), (20, 0);
             INSERT INTO favorites(file_id, collection_id) VALUES (10, 1);",
        )
        .execute(&pool)
        .await
        .unwrap();
        if !seed.is_empty() {
            sqlx::raw_sql(seed).execute(&pool).await.unwrap();
        }
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
    async fn collections_list_returns_empty_collection_array() {
        let value = json_body(list(State(test_state("").await), None).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["collections"], json!([]));
    }

    #[tokio::test]
    async fn collections_list_returns_counts_and_smart_flags() {
        let state = test_state(
            "INSERT INTO collections(id, name, sort_order, created_at, query_json) VALUES
               (2, 'plain', 1, 100, NULL),
               (1, 'smart', 0, 90, '{\"q\":\"tag\"}');
             INSERT INTO favorites(file_id, collection_id) VALUES
               (10, 2), (11, 2), (12, 1);",
        )
        .await;

        let value = json_body(list(State(state), None).await).await;

        assert_eq!(value["collections"][0]["id"], 1);
        assert_eq!(value["collections"][0]["count"], 2);
        assert_eq!(value["collections"][0]["is_smart"], true);
        assert_eq!(value["collections"][0]["query_json"], "{\"q\":\"tag\"}");
        assert_eq!(value["collections"][1]["id"], 2);
        assert_eq!(value["collections"][1]["count"], 2);
        assert_eq!(value["collections"][1]["is_smart"], false);
        assert!(value["collections"][1]["query_json"].is_null());
    }

    #[tokio::test]
    async fn collections_create_returns_201_with_id() {
        let response = create(
            State(test_state("").await),
            Json(json!({"name": "My Collection", "query_json": null})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::CREATED);

        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["id"], 1);
        assert_eq!(value["name"], "My Collection");
        assert_eq!(value["is_smart"], false);
    }

    #[tokio::test]
    async fn collections_create_rejects_blank_name() {
        let response = create(State(test_state("").await), Json(json!({"name": "  "}))).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let value = json_body(response).await;
        assert_eq!(value, json!({"ok": false, "error": "name required"}));
    }

    #[tokio::test]
    async fn collections_update_returns_200_with_id_and_name() {
        let response = update(
            State(
                test_state("INSERT INTO collections(id, name, sort_order) VALUES (5, 'old', 1);")
                    .await,
            ),
            axum::extract::Path(5_i64),
            Json(json!({"name": "New Name"})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["id"], 5);
        assert_eq!(value["name"], "New Name");
    }

    #[tokio::test]
    async fn collections_update_rejects_blank_name() {
        let response = update(
            State(test_state("").await),
            axum::extract::Path(5_i64),
            Json(json!({"name": ""})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let value = json_body(response).await;
        assert_eq!(value, json!({"ok": false, "error": "name required"}));
    }

    #[tokio::test]
    async fn collections_delete_id1_returns_400() {
        let response = delete(State(test_state("").await), axum::extract::Path(1_i64)).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let value = json_body(response).await;
        assert_eq!(
            value,
            json!({"ok": false, "error": "Collection could not be deleted"})
        );
    }

    #[tokio::test]
    async fn collections_delete_returns_deleted_id() {
        let response = delete(
            State(
                test_state("INSERT INTO collections(id, name, sort_order) VALUES (5, 'old', 1);")
                    .await,
            ),
            axum::extract::Path(5_i64),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["deleted"], 5);
    }

    #[tokio::test]
    async fn collections_reorder_updates_sort_order() {
        let state = test_state(
            "INSERT INTO collections(id, name, sort_order) VALUES
               (1, 'one', 5), (2, 'two', 6), (3, 'three', 7);",
        )
        .await;

        let response = reorder(State(Arc::clone(&state)), Json(json!({"ids": [3, 1, 2]}))).await;
        assert_eq!(response.status(), StatusCode::OK);

        let orders: Vec<(i64, i64)> =
            sqlx::query_as("SELECT id, sort_order FROM collections ORDER BY sort_order")
                .fetch_all(&state.db_read)
                .await
                .unwrap();
        assert_eq!(orders, vec![(3, 0), (1, 1), (2, 2)]);
    }

    #[tokio::test]
    async fn collections_batch_add_skips_nonexistent_files() {
        let response = batch_add(
            State(
                test_state(
                    "INSERT INTO collections(id, name, sort_order) VALUES (1, 'default', 1);",
                )
                .await,
            ),
            axum::extract::Path(1_i64),
            Json(json!({"file_ids": [20, 99]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["data"]["total"], 2);
        assert_eq!(value["data"]["succeeded"], 1);
        assert_eq!(value["data"]["failed"], 1);
        assert_eq!(value["data"]["errors"][0]["file_id"], 99);
        assert_eq!(value["data"]["errors"][0]["code"], "not_found");
    }

    #[tokio::test]
    async fn collections_batch_add_idempotent_for_already_present() {
        let response = batch_add(
            State(
                test_state(
                    "INSERT INTO collections(id, name, sort_order) VALUES (1, 'default', 1);",
                )
                .await,
            ),
            axum::extract::Path(1_i64),
            Json(json!({"file_ids": [10]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["data"]["total"], 1);
        assert_eq!(value["data"]["succeeded"], 1);
        assert_eq!(value["data"]["failed"], 0);
        assert_eq!(value["data"]["errors"], json!([]));
    }

    #[tokio::test]
    async fn collections_batch_remove_returns_removed_count() {
        let response = batch_remove(
            State(
                test_state(
                    "INSERT INTO collections(id, name, sort_order) VALUES (1, 'default', 1);",
                )
                .await,
            ),
            axum::extract::Path(1_i64),
            Json(json!({"file_ids": [10, 20]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(
            value,
            json!({"ok": true, "error": null, "data": {"removed": 1}})
        );
    }

    #[tokio::test]
    async fn collections_batch_add_collection_not_found_returns_errors() {
        let response = batch_add(
            State(test_state("").await),
            axum::extract::Path(99_i64),
            Json(json!({"file_ids": [10, 20, 99]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["data"]["total"], 3);
        assert_eq!(value["data"]["succeeded"], 0);
        assert_eq!(value["data"]["failed"], 3);
        assert_eq!(value["data"]["errors"][0]["code"], "collection_not_found");
        assert_eq!(value["data"]["errors"][1]["code"], "collection_not_found");
        assert_eq!(value["data"]["errors"][2]["code"], "collection_not_found");
    }
}

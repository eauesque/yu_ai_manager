#![allow(clippy::result_large_err)]
//! `/ext/lora-dataset` projects and tag-presets CRUD.
//!
//! Native port of `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py`
//! and `api_presets.py` (backed by `store.py` / `lora_dataset_write_service.py`).
//!
//! `/projects/{id}/tags` and `/projects/{id}/caption-preview` (which delegate to
//! `caption_builder.py`) and the `export`/`train` endpoints are out of scope —
//! see the migration plan for this feature.

use axum::{
    extract::{rejection::JsonRejection, Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Map, Value};
use sqlx::{QueryBuilder, Row, Sqlite, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const PROJECT_COLUMNS: [&str; 12] = [
    "id",
    "name",
    "concept",
    "repeat",
    "base_model",
    "model_scope",
    "tag_exclude",
    "tag_preset",
    "search_query",
    "file_ids",
    "created_at",
    "updated_at",
];

fn api_success(payload: Value, status: StatusCode, data: Option<Value>) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => Map::from_iter([("data".to_string(), other)]),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string())
        .or_insert(data.unwrap_or(Value::Null));
    (status, Json(Value::Object(body))).into_response()
}

fn api_error(message: &str, status: StatusCode, code: Option<&str>) -> Response {
    let mut body = json!({"ok": false, "error": message});
    if let Some(code) = code {
        body["code"] = json!(code);
    }
    (status, Json(body)).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    api_error(
        "internal_server_error",
        StatusCode::INTERNAL_SERVER_ERROR,
        None,
    )
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn require_json(body: Result<Json<Value>, JsonRejection>) -> Value {
    match body {
        Ok(Json(v)) => v,
        Err(_) => json!({}),
    }
}

fn now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

async fn ensure_tables(pool: &SqlitePool) -> Result<(), sqlx::Error> {
    sqlx::raw_sql(
        "
        CREATE TABLE IF NOT EXISTS lora_projects (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            concept      TEXT NOT NULL,
            repeat       INTEGER DEFAULT 10,
            base_model   TEXT DEFAULT 'sdxl',
            tag_exclude  TEXT DEFAULT '[]',
            tag_preset   TEXT DEFAULT '',
            search_query TEXT DEFAULT '',
            file_ids     TEXT DEFAULT '[]',
            model_scope  TEXT NOT NULL DEFAULT 'all',
            created_at   INTEGER,
            updated_at   INTEGER
        );
        CREATE TABLE IF NOT EXISTS lora_tag_presets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            tags       TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER,
            updated_at INTEGER
        );",
    )
    .execute(pool)
    .await?;

    // A `lora_projects` table created by Python schema migration v1 (before v2's
    // `ALTER TABLE ... ADD COLUMN model_scope`) lacks this column; CREATE TABLE IF
    // NOT EXISTS above is a no-op against it. Add it here too, mirroring Python's
    // `migrate.py` v2 step, so PROJECT_COLUMNS's unconditional SELECT never 500s.
    let has_model_scope: bool = sqlx::query_scalar(
        "SELECT COUNT(*) > 0 FROM pragma_table_info('lora_projects') WHERE name = 'model_scope'",
    )
    .fetch_one(pool)
    .await?;
    if !has_model_scope {
        sqlx::raw_sql(
            "ALTER TABLE lora_projects ADD COLUMN model_scope TEXT NOT NULL DEFAULT 'all'",
        )
        .execute(pool)
        .await?;
    }

    Ok(())
}

async fn ensure_tables_or_response(state: &SharedState) -> Option<Response> {
    ensure_tables(&state.db)
        .await
        .err()
        .map(|error| internal_error(error, "failed to initialize lora_dataset tables"))
}

fn project_from_row(row: &sqlx::sqlite::SqliteRow) -> Value {
    let tag_exclude: String = row.try_get("tag_exclude").unwrap_or_default();
    let tag_exclude = serde_json::from_str::<Value>(&tag_exclude)
        .ok()
        .filter(Value::is_array)
        .unwrap_or_else(|| json!([]));
    let file_ids: String = row.try_get("file_ids").unwrap_or_default();
    let file_ids = serde_json::from_str::<Value>(&file_ids)
        .ok()
        .filter(Value::is_array)
        .unwrap_or_else(|| json!([]));
    let file_count = file_ids.as_array().map(Vec::len).unwrap_or(0);
    json!({
        "id": row.get::<i64, _>("id"),
        "name": row.get::<String, _>("name"),
        "concept": row.get::<String, _>("concept"),
        "repeat": row.get::<i64, _>("repeat"),
        "base_model": row.get::<String, _>("base_model"),
        "model_scope": row.try_get::<String, _>("model_scope").unwrap_or_else(|_| "all".to_string()),
        "tag_exclude": tag_exclude,
        "tag_preset": row.get::<String, _>("tag_preset"),
        "search_query": row.get::<String, _>("search_query"),
        "file_ids": file_ids,
        "file_count": file_count,
        "created_at": row.try_get::<Option<i64>, _>("created_at").unwrap_or(None),
        "updated_at": row.try_get::<Option<i64>, _>("updated_at").unwrap_or(None),
    })
}

async fn get_project_value(pool: &SqlitePool, pid: i64) -> Result<Option<Value>, sqlx::Error> {
    let cols = PROJECT_COLUMNS.join(", ");
    let row = sqlx::query(&format!("SELECT {cols} FROM lora_projects WHERE id=?"))
        .bind(pid)
        .fetch_optional(pool)
        .await?;
    Ok(row.as_ref().map(project_from_row))
}

/// Normalizes the `model_scope` field per the Python handler: absent/null ->
/// `"active"`, non-empty string -> trimmed, empty-after-trim -> `"active"`,
/// any other JSON type -> validation error.
fn normalize_model_scope(raw: Option<&Value>) -> Result<String, Response> {
    match raw {
        None | Some(Value::Null) => Ok("active".to_string()),
        Some(Value::String(s)) => {
            let trimmed = s.trim();
            Ok(if trimmed.is_empty() {
                "active".to_string()
            } else {
                trimmed.to_string()
            })
        }
        Some(_) => Err(api_error(
            "model_scope must be a string",
            StatusCode::BAD_REQUEST,
            None,
        )),
    }
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

pub async fn list_projects(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let cols = PROJECT_COLUMNS.join(", ");
    match sqlx::query(&format!(
        "SELECT {cols} FROM lora_projects ORDER BY updated_at DESC"
    ))
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => {
            let projects: Vec<Value> = rows.iter().map(project_from_row).collect();
            api_success(
                json!({"projects": projects, "total": projects.len()}),
                StatusCode::OK,
                None,
            )
        }
        Err(error) => internal_error(error, "failed to list lora projects"),
    }
}

pub async fn create_project(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let data = require_json(body);

    let name = data
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if name.is_empty() {
        return api_error("name is required", StatusCode::BAD_REQUEST, None);
    }
    let concept = data
        .get("concept")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if concept.is_empty() {
        return api_error("concept is required", StatusCode::BAD_REQUEST, None);
    }
    // Python: `base_model = data.get("base_model", "sdxl")` then rejects if not in
    // ("sd15", "sdxl") — an explicit non-string/null value is rejected too, only an
    // *absent* key defaults to "sdxl".
    let base_model = match data.get("base_model") {
        None => "sdxl",
        Some(Value::String(s)) if s == "sd15" || s == "sdxl" => s.as_str(),
        _ => {
            return api_error(
                "base_model must be 'sd15' or 'sdxl'",
                StatusCode::BAD_REQUEST,
                None,
            );
        }
    };
    let repeat = data.get("repeat").and_then(Value::as_i64).unwrap_or(10);
    if !(1..=999).contains(&repeat) {
        return api_error("repeat must be 1-999", StatusCode::BAD_REQUEST, None);
    }
    let model_scope = match normalize_model_scope(data.get("model_scope")) {
        Ok(v) => v,
        Err(response) => return response,
    };

    let ts = now();
    let result = sqlx::query(
        "INSERT INTO lora_projects (name, concept, repeat, base_model, model_scope, created_at, updated_at) \
         VALUES (?, ?, ?, ?, ?, ?, ?)",
    )
    .bind(name)
    .bind(concept)
    .bind(repeat)
    .bind(base_model)
    .bind(&model_scope)
    .bind(ts)
    .bind(ts)
    .execute(&state.db)
    .await;

    match result {
        Ok(result) => {
            let pid = result.last_insert_rowid();
            match get_project_value(&state.db_read, pid).await {
                Ok(Some(project)) => api_success(project, StatusCode::CREATED, None),
                Ok(None) => {
                    internal_error("missing after insert", "failed to load created project")
                }
                Err(error) => internal_error(error, "failed to load created project"),
            }
        }
        Err(error) => internal_error(error, "failed to create lora project"),
    }
}

pub async fn get_project(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(pid): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    match get_project_value(&state.db_read, pid).await {
        Ok(Some(project)) => api_success(project, StatusCode::OK, None),
        Ok(None) => api_error("Project not found", StatusCode::NOT_FOUND, None),
        Err(error) => internal_error(error, "failed to get lora project"),
    }
}

pub async fn update_project(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(pid): AxumPath<i64>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    if get_project_value(&state.db_read, pid)
        .await
        .ok()
        .flatten()
        .is_none()
    {
        return api_error("Project not found", StatusCode::NOT_FOUND, None);
    }
    let data = require_json(body);

    let mut query = QueryBuilder::<Sqlite>::new("UPDATE lora_projects SET ");
    let mut separated = query.separated(", ");
    let mut has_update = false;

    if let Some(v) = data.get("name").and_then(Value::as_str) {
        has_update = true;
        separated
            .push("name")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if let Some(v) = data.get("concept").and_then(Value::as_str) {
        has_update = true;
        separated
            .push("concept")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if let Some(v) = data.get("repeat").and_then(Value::as_i64) {
        has_update = true;
        separated
            .push("repeat")
            .push_unseparated("=")
            .push_bind_unseparated(v);
    }
    if let Some(v) = data.get("base_model").and_then(Value::as_str) {
        has_update = true;
        separated
            .push("base_model")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if let Some(v) = data.get("tag_preset").and_then(Value::as_str) {
        has_update = true;
        separated
            .push("tag_preset")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if let Some(v) = data.get("search_query").and_then(Value::as_str) {
        has_update = true;
        separated
            .push("search_query")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if let Some(v) = data.get("tag_exclude").filter(|v| v.is_array()) {
        has_update = true;
        separated
            .push("tag_exclude")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if let Some(v) = data.get("file_ids").filter(|v| v.is_array()) {
        has_update = true;
        separated
            .push("file_ids")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if data.get("model_scope").is_some() {
        match normalize_model_scope(data.get("model_scope")) {
            Ok(v) => {
                has_update = true;
                separated
                    .push("model_scope")
                    .push_unseparated("=")
                    .push_bind_unseparated(v);
            }
            Err(response) => return response,
        }
    }

    if !has_update {
        // Mirrors store.update_project: no recognized fields -> no-op, return current state.
        return match get_project_value(&state.db_read, pid).await {
            Ok(Some(project)) => api_success(project, StatusCode::OK, None),
            Ok(None) => api_error("Project not found", StatusCode::NOT_FOUND, None),
            Err(error) => internal_error(error, "failed to load lora project"),
        };
    }

    separated
        .push("updated_at")
        .push_unseparated("=")
        .push_bind_unseparated(now());
    query.push(" WHERE id=").push_bind(pid);

    match query.build().execute(&state.db).await {
        Ok(_) => match get_project_value(&state.db_read, pid).await {
            Ok(Some(project)) => api_success(project, StatusCode::OK, None),
            Ok(None) => api_error("Project not found", StatusCode::NOT_FOUND, None),
            Err(error) => internal_error(error, "failed to load updated lora project"),
        },
        Err(error) => internal_error(error, "failed to update lora project"),
    }
}

pub async fn delete_project(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(pid): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    match sqlx::query("DELETE FROM lora_projects WHERE id=?")
        .bind(pid)
        .execute(&state.db)
        .await
    {
        Ok(result) if result.rows_affected() > 0 => {
            api_success(json!({"deleted": true}), StatusCode::OK, None)
        }
        Ok(_) => api_error("Project not found", StatusCode::NOT_FOUND, None),
        Err(error) => internal_error(error, "failed to delete lora project"),
    }
}

// ---------------------------------------------------------------------------
// Tag presets
// ---------------------------------------------------------------------------

fn preset_from_row(row: &sqlx::sqlite::SqliteRow) -> Value {
    let tags: String = row.try_get("tags").unwrap_or_default();
    let tags = serde_json::from_str::<Value>(&tags)
        .ok()
        .filter(Value::is_array)
        .unwrap_or_else(|| json!([]));
    json!({
        "id": row.get::<i64, _>("id"),
        "name": row.get::<String, _>("name"),
        "tags": tags,
        "created_at": row.try_get::<Option<i64>, _>("created_at").unwrap_or(None),
        "updated_at": row.try_get::<Option<i64>, _>("updated_at").unwrap_or(None),
    })
}

async fn get_preset_value(pool: &SqlitePool, preset_id: i64) -> Result<Option<Value>, sqlx::Error> {
    let row = sqlx::query(
        "SELECT id, name, tags, created_at, updated_at FROM lora_tag_presets WHERE id=?",
    )
    .bind(preset_id)
    .fetch_optional(pool)
    .await?;
    Ok(row.as_ref().map(preset_from_row))
}

pub async fn list_presets(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    match sqlx::query(
        "SELECT id, name, tags, created_at, updated_at FROM lora_tag_presets ORDER BY name",
    )
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => {
            let presets: Vec<Value> = rows.iter().map(preset_from_row).collect();
            api_success(
                json!({"presets": presets, "total": presets.len()}),
                StatusCode::OK,
                None,
            )
        }
        Err(error) => internal_error(error, "failed to list lora tag presets"),
    }
}

pub async fn create_preset(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let data = require_json(body);

    let name = data
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if name.is_empty() {
        return api_error("name is required", StatusCode::BAD_REQUEST, None);
    }
    let Some(tags) = data.get("tags").filter(|v| v.is_array()).or_else(|| {
        if data.get("tags").is_none() {
            Some(&Value::Null)
        } else {
            None
        }
    }) else {
        return api_error("tags must be an array", StatusCode::BAD_REQUEST, None);
    };
    let tags_json = if tags.is_null() {
        "[]".to_string()
    } else {
        tags.to_string()
    };

    let ts = now();
    let result = sqlx::query(
        "INSERT INTO lora_tag_presets (name, tags, created_at, updated_at) VALUES (?, ?, ?, ?)",
    )
    .bind(name)
    .bind(&tags_json)
    .bind(ts)
    .bind(ts)
    .execute(&state.db)
    .await;

    match result {
        Ok(result) => {
            let preset_id = result.last_insert_rowid();
            match get_preset_value(&state.db_read, preset_id).await {
                Ok(Some(preset)) => api_success(preset, StatusCode::CREATED, None),
                Ok(None) => internal_error("missing after insert", "failed to load created preset"),
                Err(error) => internal_error(error, "failed to load created preset"),
            }
        }
        // SQLite UNIQUE constraint violation on lora_tag_presets.name.
        Err(sqlx::Error::Database(db_err)) if db_err.is_unique_violation() => api_error(
            &format!("Preset '{name}' already exists"),
            StatusCode::CONFLICT,
            None,
        ),
        Err(error) => internal_error(error, "failed to create lora tag preset"),
    }
}

pub async fn update_preset(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(preset_id): AxumPath<i64>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let data = require_json(body);

    let mut query = QueryBuilder::<Sqlite>::new("UPDATE lora_tag_presets SET ");
    let mut separated = query.separated(", ");
    let mut has_update = false;

    if let Some(v) = data.get("name").and_then(Value::as_str) {
        has_update = true;
        separated
            .push("name")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }
    if let Some(v) = data.get("tags").filter(|v| v.is_array()) {
        has_update = true;
        separated
            .push("tags")
            .push_unseparated("=")
            .push_bind_unseparated(v.to_string());
    }

    if !has_update {
        return match get_preset_value(&state.db_read, preset_id).await {
            Ok(Some(preset)) => api_success(preset, StatusCode::OK, None),
            Ok(None) => api_error("Preset not found", StatusCode::NOT_FOUND, None),
            Err(error) => internal_error(error, "failed to load lora tag preset"),
        };
    }

    separated
        .push("updated_at")
        .push_unseparated("=")
        .push_bind_unseparated(now());
    query.push(" WHERE id=").push_bind(preset_id);

    match query.build().execute(&state.db).await {
        Ok(result) if result.rows_affected() > 0 => {
            match get_preset_value(&state.db_read, preset_id).await {
                Ok(Some(preset)) => api_success(preset, StatusCode::OK, None),
                Ok(None) => api_error("Preset not found", StatusCode::NOT_FOUND, None),
                Err(error) => internal_error(error, "failed to load updated lora tag preset"),
            }
        }
        Ok(_) => api_error("Preset not found", StatusCode::NOT_FOUND, None),
        Err(sqlx::Error::Database(db_err)) if db_err.is_unique_violation() => {
            api_error("Preset name already exists", StatusCode::CONFLICT, None)
        }
        Err(error) => internal_error(error, "failed to update lora tag preset"),
    }
}

pub async fn delete_preset(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(preset_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    match sqlx::query("DELETE FROM lora_tag_presets WHERE id=?")
        .bind(preset_id)
        .execute(&state.db)
        .await
    {
        Ok(result) if result.rows_affected() > 0 => {
            api_success(json!({"deleted": true}), StatusCode::OK, None)
        }
        Ok(_) => api_error("Preset not found", StatusCode::NOT_FOUND, None),
        Err(error) => internal_error(error, "failed to delete lora tag preset"),
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

    async fn create_test_project(state: SharedState, name: &str) -> Value {
        let response = create_project(
            State(state),
            None,
            Ok(Json(json!({"name": name, "concept": "test concept"}))),
        )
        .await;
        json_body(response).await
    }

    // -- Projects --

    #[tokio::test]
    async fn create_list_and_get_project_round_trip() {
        let state = test_state().await;
        let created = create_test_project(state.clone(), "Project A").await;
        assert_eq!(created["ok"], json!(true));
        assert_eq!(created["name"], json!("Project A"));
        assert_eq!(created["concept"], json!("test concept"));
        assert_eq!(created["base_model"], json!("sdxl"));
        assert_eq!(created["repeat"], json!(10));
        assert_eq!(created["model_scope"], json!("active"));
        assert_eq!(created["file_count"], json!(0));
        let pid = created["id"].as_i64().unwrap();

        let list_resp = list_projects(State(state.clone()), None).await;
        let list_body = json_body(list_resp).await;
        assert_eq!(list_body["total"], json!(1));

        let get_resp = get_project(State(state), None, AxumPath(pid)).await;
        let get_body = json_body(get_resp).await;
        assert_eq!(get_body["id"], json!(pid));
    }

    #[tokio::test]
    async fn create_project_requires_name_and_concept() {
        let state = test_state().await;
        let resp = create_project(
            State(state.clone()),
            None,
            Ok(Json(json!({"concept": "c"}))),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);

        let resp = create_project(State(state), None, Ok(Json(json!({"name": "n"})))).await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn create_project_validates_base_model_and_repeat() {
        let state = test_state().await;
        let resp = create_project(
            State(state.clone()),
            None,
            Ok(Json(
                json!({"name": "n", "concept": "c", "base_model": "sd21"}),
            )),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);

        let resp = create_project(
            State(state.clone()),
            None,
            Ok(Json(json!({"name": "n", "concept": "c", "repeat": 0}))),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);

        // An explicitly-present but non-string/null base_model is rejected too —
        // only an *absent* key defaults to "sdxl" (parity with the Python handler).
        let resp = create_project(
            State(state),
            None,
            Ok(Json(
                json!({"name": "n", "concept": "c", "base_model": null}),
            )),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn ensure_tables_adds_model_scope_to_a_legacy_v1_lora_projects_table() {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        // Pre-create a v1-shaped table (Python schema migration v1, before v2's
        // ALTER TABLE ADD COLUMN model_scope).
        sqlx::raw_sql(
            "CREATE TABLE lora_projects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                concept      TEXT NOT NULL,
                repeat       INTEGER DEFAULT 10,
                base_model   TEXT DEFAULT 'sdxl',
                tag_exclude  TEXT DEFAULT '[]',
                tag_preset   TEXT DEFAULT '',
                search_query TEXT DEFAULT '',
                file_ids     TEXT DEFAULT '[]',
                created_at   INTEGER,
                updated_at   INTEGER
            );
            INSERT INTO lora_projects (id, name, concept) VALUES (1, 'Legacy', 'c');",
        )
        .execute(&pool)
        .await
        .unwrap();

        ensure_tables(&pool).await.unwrap();

        let project = get_project_value(&pool, 1).await.unwrap().unwrap();
        assert_eq!(project["model_scope"], json!("all"));
    }

    #[tokio::test]
    async fn create_project_model_scope_defaults_and_rejects_non_string() {
        let state = test_state().await;
        // Explicit null and empty string both normalize to "active".
        let created = create_project(
            State(state.clone()),
            None,
            Ok(Json(
                json!({"name": "n", "concept": "c", "model_scope": null}),
            )),
        )
        .await;
        assert_eq!(json_body(created).await["model_scope"], json!("active"));

        let resp = create_project(
            State(state),
            None,
            Ok(Json(
                json!({"name": "n2", "concept": "c", "model_scope": 5}),
            )),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn update_project_changes_fields_and_no_op_returns_current_state() {
        let state = test_state().await;
        let created = create_test_project(state.clone(), "Original").await;
        let pid = created["id"].as_i64().unwrap();

        let updated = update_project(
            State(state.clone()),
            None,
            AxumPath(pid),
            Ok(Json(json!({"name": "Renamed", "file_ids": [1, 2, 3]}))),
        )
        .await;
        let updated_body = json_body(updated).await;
        assert_eq!(updated_body["name"], json!("Renamed"));
        assert_eq!(updated_body["file_count"], json!(3));

        // No recognized fields -> no-op, current state returned unchanged.
        let noop = update_project(
            State(state),
            None,
            AxumPath(pid),
            Ok(Json(json!({"bogus": 1}))),
        )
        .await;
        assert_eq!(json_body(noop).await["name"], json!("Renamed"));
    }

    #[tokio::test]
    async fn update_and_delete_project_not_found_return_404() {
        let state = test_state().await;
        let resp = update_project(
            State(state.clone()),
            None,
            AxumPath(999),
            Ok(Json(json!({"name": "x"}))),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);

        let resp = delete_project(State(state), None, AxumPath(999)).await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn delete_project_then_get_returns_404() {
        let state = test_state().await;
        let created = create_test_project(state.clone(), "ToDelete").await;
        let pid = created["id"].as_i64().unwrap();

        let deleted = delete_project(State(state.clone()), None, AxumPath(pid)).await;
        assert_eq!(json_body(deleted).await["deleted"], json!(true));

        let resp = get_project(State(state), None, AxumPath(pid)).await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    // -- Tag presets --

    #[tokio::test]
    async fn create_and_list_presets_round_trip() {
        let state = test_state().await;
        let created = create_preset(
            State(state.clone()),
            None,
            Ok(Json(json!({"name": "Preset A", "tags": ["a", "b"]}))),
        )
        .await;
        let created_body = json_body(created).await;
        assert_eq!(created_body["name"], json!("Preset A"));
        assert_eq!(created_body["tags"], json!(["a", "b"]));

        let list_resp = list_presets(State(state), None).await;
        assert_eq!(json_body(list_resp).await["total"], json!(1));
    }

    #[tokio::test]
    async fn create_preset_requires_name_and_array_tags() {
        let state = test_state().await;
        let resp = create_preset(State(state.clone()), None, Ok(Json(json!({"tags": []})))).await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);

        let resp = create_preset(
            State(state),
            None,
            Ok(Json(json!({"name": "n", "tags": "not-an-array"}))),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn create_preset_duplicate_name_returns_409() {
        let state = test_state().await;
        let first = create_preset(
            State(state.clone()),
            None,
            Ok(Json(json!({"name": "Dup", "tags": []}))),
        )
        .await;
        assert_eq!(first.status(), StatusCode::CREATED);

        let second = create_preset(
            State(state),
            None,
            Ok(Json(json!({"name": "Dup", "tags": []}))),
        )
        .await;
        assert_eq!(second.status(), StatusCode::CONFLICT);
    }

    #[tokio::test]
    async fn update_preset_partial_fields_and_not_found() {
        let state = test_state().await;
        let created = create_preset(
            State(state.clone()),
            None,
            Ok(Json(json!({"name": "Original", "tags": ["x"]}))),
        )
        .await;
        let preset_id = json_body(created).await["id"].as_i64().unwrap();

        let updated = update_preset(
            State(state.clone()),
            None,
            AxumPath(preset_id),
            Ok(Json(json!({"tags": ["y", "z"]}))),
        )
        .await;
        let updated_body = json_body(updated).await;
        assert_eq!(updated_body["name"], json!("Original"));
        assert_eq!(updated_body["tags"], json!(["y", "z"]));

        let resp = update_preset(
            State(state),
            None,
            AxumPath(999),
            Ok(Json(json!({"name": "x"}))),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn delete_preset_then_list_is_empty_and_repeat_delete_is_404() {
        let state = test_state().await;
        let created = create_preset(
            State(state.clone()),
            None,
            Ok(Json(json!({"name": "ToDelete", "tags": []}))),
        )
        .await;
        let preset_id = json_body(created).await["id"].as_i64().unwrap();

        let deleted = delete_preset(State(state.clone()), None, AxumPath(preset_id)).await;
        assert_eq!(json_body(deleted).await["deleted"], json!(true));

        let resp = delete_preset(State(state), None, AxumPath(preset_id)).await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }
}

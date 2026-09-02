use std::collections::HashMap;

use axum::{
    extract::{rejection::JsonRejection, Extension, Path as AxumPath, Query, State},
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

const COLUMNS: [&str; 14] = [
    "id",
    "title",
    "positive",
    "negative",
    "seed",
    "steps",
    "sampler",
    "cfg_scale",
    "model_name",
    "memo",
    "source_file_id",
    "characters_json",
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

fn require_json(body: Result<Json<Value>, JsonRejection>) -> Result<Value, Response> {
    match body {
        Ok(Json(Value::Object(map))) => Ok(Value::Object(map)),
        Ok(_) => Err(api_error(
            "JSON object body is required",
            StatusCode::BAD_REQUEST,
            None,
        )),
        Err(error) if error.body_text().contains("Content-Type") => Err(api_error(
            "JSON body is required",
            StatusCode::BAD_REQUEST,
            None,
        )),
        Err(_) => Err(api_error(
            "Invalid JSON body",
            StatusCode::BAD_REQUEST,
            None,
        )),
    }
}

fn now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

fn fts5_phrase(q: &str) -> String {
    format!("\"{}\"", q.replace('"', "\"\""))
}

fn characters_json(value: Option<&Value>) -> String {
    let Some(Value::Array(items)) = value else {
        return String::new();
    };
    let chars = items
        .iter()
        .filter(|item| {
            item.get("prompt")
                .is_some_and(|v| v.as_str().is_some_and(|s| !s.is_empty()))
        })
        .cloned()
        .collect::<Vec<_>>();
    if chars.is_empty() {
        String::new()
    } else {
        serde_json::to_string(&chars).unwrap_or_default()
    }
}

async fn ensure_tables(pool: &SqlitePool) -> Result<(), sqlx::Error> {
    sqlx::raw_sql(
        "
        CREATE TABLE IF NOT EXISTS prompt_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            positive TEXT NOT NULL DEFAULT '',
            negative TEXT NOT NULL DEFAULT '',
            seed TEXT NOT NULL DEFAULT '',
            steps TEXT NOT NULL DEFAULT '',
            sampler TEXT NOT NULL DEFAULT '',
            cfg_scale TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL DEFAULT '',
            memo TEXT NOT NULL DEFAULT '',
            source_file_id INTEGER,
            characters_json TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prompt_library_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prompt_library_folder_items (
            prompt_id INTEGER NOT NULL,
            folder_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (prompt_id, folder_id)
        );
        CREATE TABLE IF NOT EXISTS prompt_library_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS prompt_library_tag_map (
            prompt_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (prompt_id, tag_id)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS prompt_library_fts
            USING fts5(title, positive, negative, memo, content=prompt_library, content_rowid=id);
        CREATE TRIGGER IF NOT EXISTS prompt_library_fts_ai
        AFTER INSERT ON prompt_library BEGIN
            INSERT INTO prompt_library_fts(rowid, title, positive, negative, memo)
            VALUES (new.id, new.title, new.positive, new.negative, new.memo);
        END;
        CREATE TRIGGER IF NOT EXISTS prompt_library_fts_ad
        AFTER DELETE ON prompt_library BEGIN
            INSERT INTO prompt_library_fts(prompt_library_fts, rowid, title, positive, negative, memo)
            VALUES ('delete', old.id, old.title, old.positive, old.negative, old.memo);
        END;
        CREATE TRIGGER IF NOT EXISTS prompt_library_fts_au
        AFTER UPDATE ON prompt_library BEGIN
            INSERT INTO prompt_library_fts(prompt_library_fts, rowid, title, positive, negative, memo)
            VALUES ('delete', old.id, old.title, old.positive, old.negative, old.memo);
            INSERT INTO prompt_library_fts(rowid, title, positive, negative, memo)
            VALUES (new.id, new.title, new.positive, new.negative, new.memo);
        END;",
    )
    .execute(pool)
    .await?;
    Ok(())
}

async fn ensure_tables_or_response(state: &SharedState) -> Option<Response> {
    ensure_tables(&state.db)
        .await
        .err()
        .map(|error| internal_error(error, "failed to initialize prompt library"))
}

fn prompt_from_row(row: &sqlx::sqlite::SqliteRow) -> Value {
    let raw_chars: String = row.try_get("characters_json").unwrap_or_default();
    let chars = serde_json::from_str::<Value>(&raw_chars)
        .ok()
        .filter(Value::is_array)
        .unwrap_or_else(|| json!([]));
    json!({
        "id": row.get::<i64, _>("id"),
        "title": row.get::<String, _>("title"),
        "positive": row.get::<String, _>("positive"),
        "negative": row.get::<String, _>("negative"),
        "seed": row.get::<String, _>("seed"),
        "steps": row.get::<String, _>("steps"),
        "sampler": row.get::<String, _>("sampler"),
        "cfg_scale": row.get::<String, _>("cfg_scale"),
        "model_name": row.get::<String, _>("model_name"),
        "memo": row.get::<String, _>("memo"),
        "source_file_id": row.try_get::<Option<i64>, _>("source_file_id").unwrap_or(None),
        "characters": chars,
        "created_at": row.get::<i64, _>("created_at"),
        "updated_at": row.get::<i64, _>("updated_at"),
    })
}

async fn get_prompt_value(pool: &SqlitePool, prompt_id: i64) -> Result<Option<Value>, sqlx::Error> {
    let select_cols = COLUMNS.join(", ");
    let Some(row) = sqlx::query(&format!(
        "SELECT {select_cols} FROM prompt_library WHERE id=?"
    ))
    .bind(prompt_id)
    .fetch_optional(pool)
    .await?
    else {
        return Ok(None);
    };
    let mut prompt = prompt_from_row(&row);
    let folders =
        sqlx::query("SELECT folder_id FROM prompt_library_folder_items WHERE prompt_id=?")
            .bind(prompt_id)
            .fetch_all(pool)
            .await?
            .into_iter()
            .map(|row| row.get::<i64, _>(0))
            .collect::<Vec<_>>();
    let tags = sqlx::query(
        "SELECT t.id, t.name FROM prompt_library_tags t
         JOIN prompt_library_tag_map tm ON tm.tag_id=t.id
         WHERE tm.prompt_id=?",
    )
    .bind(prompt_id)
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|row| json!({"id": row.get::<i64, _>(0), "name": row.get::<String, _>(1)}))
    .collect::<Vec<_>>();
    prompt["folder_ids"] = json!(folders);
    prompt["tags"] = json!(tags);
    Ok(Some(prompt))
}

pub async fn info() -> Response {
    Json(json!({"name": "builtin-prompt-library", "version": "1.0.0"})).into_response()
}

pub async fn list_prompts(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let sort = match params.get("sort").map(String::as_str) {
        Some("created_at") => "created_at",
        Some("title") => "title",
        _ => "updated_at",
    };
    let order = if params
        .get("order")
        .is_some_and(|v| v.eq_ignore_ascii_case("asc"))
    {
        "asc"
    } else {
        "desc"
    };
    let limit = params
        .get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .filter(|v| (1..=200).contains(v))
        .unwrap_or(50);
    let offset = params
        .get("offset")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(0)
        .max(0);
    let folder_id = params.get("folder_id").and_then(|v| v.parse::<i64>().ok());
    let tag_id = params.get("tag_id").and_then(|v| v.parse::<i64>().ok());
    let q = params.get("q").map(|v| v.trim()).filter(|v| !v.is_empty());

    let mut base = " FROM prompt_library p".to_string();
    let mut wheres = Vec::new();
    if folder_id.is_some() {
        base.push_str(" JOIN prompt_library_folder_items fi ON fi.prompt_id=p.id");
        wheres.push("fi.folder_id=?");
    }
    if tag_id.is_some() {
        base.push_str(" JOIN prompt_library_tag_map tm ON tm.prompt_id=p.id");
        wheres.push("tm.tag_id=?");
    }
    if q.is_some() {
        wheres.push(
            "p.id IN (SELECT rowid FROM prompt_library_fts WHERE prompt_library_fts MATCH ?)",
        );
    }
    let where_clause = if wheres.is_empty() {
        String::new()
    } else {
        format!(" WHERE {}", wheres.join(" AND "))
    };
    let count_sql = format!("SELECT COUNT(DISTINCT p.id){base}{where_clause}");
    let mut count_query = sqlx::query_scalar::<_, i64>(&count_sql);
    if let Some(value) = folder_id {
        count_query = count_query.bind(value);
    }
    if let Some(value) = tag_id {
        count_query = count_query.bind(value);
    }
    if let Some(value) = q {
        count_query = count_query.bind(fts5_phrase(value));
    }
    let total = match count_query.fetch_one(&state.db_read).await {
        Ok(total) => total,
        Err(error) => return internal_error(error, "failed to count prompt library"),
    };
    let select_cols = COLUMNS
        .iter()
        .map(|col| format!("p.{col}"))
        .collect::<Vec<_>>()
        .join(", ");
    let rows_sql =
        format!("SELECT DISTINCT {select_cols}{base}{where_clause} ORDER BY p.{sort} {order} LIMIT ? OFFSET ?");
    let mut rows_query = sqlx::query(&rows_sql);
    if let Some(value) = folder_id {
        rows_query = rows_query.bind(value);
    }
    if let Some(value) = tag_id {
        rows_query = rows_query.bind(value);
    }
    if let Some(value) = q {
        rows_query = rows_query.bind(fts5_phrase(value));
    }
    let rows = match rows_query
        .bind(limit)
        .bind(offset)
        .fetch_all(&state.db_read)
        .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list prompt library"),
    };
    let items = rows.iter().map(prompt_from_row).collect::<Vec<_>>();
    let payload = json!({"items": items, "total": total});
    api_success(payload.clone(), StatusCode::OK, Some(payload))
}

pub async fn get_prompt(
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
    match get_prompt_value(&state.db_read, pid).await {
        Ok(Some(prompt)) => api_success(json!({"prompt": prompt}), StatusCode::OK, None),
        Ok(None) => api_error("Prompt not found", StatusCode::NOT_FOUND, Some("not_found")),
        Err(error) => internal_error(error, "failed to get prompt"),
    }
}

pub async fn create_prompt(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let title = data
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if title.is_empty() {
        return api_error(
            "title is required",
            StatusCode::BAD_REQUEST,
            Some("missing_title"),
        );
    }
    match insert_prompt(
        &state.db,
        &data,
        title,
        data.get("source_file_id").and_then(Value::as_i64),
    )
    .await
    {
        Ok(prompt) => api_success(json!({"prompt": prompt}), StatusCode::CREATED, None),
        Err(error) => internal_error(error, "failed to create prompt"),
    }
}

async fn insert_prompt(
    pool: &SqlitePool,
    data: &Value,
    title: &str,
    source_file_id: Option<i64>,
) -> Result<Value, sqlx::Error> {
    let now = now();
    let chars_json = characters_json(data.get("characters"));
    let result = sqlx::query(
        "INSERT INTO prompt_library
         (title, positive, negative, seed, steps, sampler, cfg_scale, model_name, memo, source_file_id, characters_json, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )
    .bind(title)
    .bind(data.get("positive").and_then(Value::as_str).unwrap_or("").trim())
    .bind(data.get("negative").and_then(Value::as_str).unwrap_or("").trim())
    .bind(value_as_string(data.get("seed")))
    .bind(value_as_string(data.get("steps")))
    .bind(data.get("sampler").and_then(Value::as_str).unwrap_or("").trim())
    .bind(value_as_string(data.get("cfg_scale")))
    .bind(data.get("model_name").and_then(Value::as_str).unwrap_or("").trim())
    .bind(data.get("memo").and_then(Value::as_str).unwrap_or("").trim())
    .bind(source_file_id)
    .bind(chars_json.clone())
    .bind(now)
    .bind(now)
    .execute(pool)
    .await?;
    let id = result.last_insert_rowid();
    Ok(json!({
        "id": id,
        "title": title,
        "positive": data.get("positive").and_then(Value::as_str).unwrap_or("").trim(),
        "negative": data.get("negative").and_then(Value::as_str).unwrap_or("").trim(),
        "seed": value_as_string(data.get("seed")),
        "steps": value_as_string(data.get("steps")),
        "sampler": data.get("sampler").and_then(Value::as_str).unwrap_or("").trim(),
        "cfg_scale": value_as_string(data.get("cfg_scale")),
        "model_name": data.get("model_name").and_then(Value::as_str).unwrap_or("").trim(),
        "memo": data.get("memo").and_then(Value::as_str).unwrap_or("").trim(),
        "source_file_id": source_file_id,
        "characters": serde_json::from_str::<Value>(&chars_json).unwrap_or_else(|_| json!([])),
        "created_at": now,
        "updated_at": now,
    }))
}

fn value_as_string(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(s)) => s.trim().to_string(),
        Some(Value::Null) | None => String::new(),
        Some(other) => other.to_string().trim_matches('"').to_string(),
    }
}

pub async fn update_prompt(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let mut query = QueryBuilder::<Sqlite>::new("UPDATE prompt_library SET ");
    let mut separated = query.separated(", ");
    let mut has_update = false;
    for key in [
        "title",
        "positive",
        "negative",
        "seed",
        "steps",
        "sampler",
        "cfg_scale",
        "model_name",
        "memo",
    ] {
        if data.get(key).is_some() {
            has_update = true;
            separated
                .push(key)
                .push_unseparated("=")
                .push_bind_unseparated(value_as_string(data.get(key)));
        }
    }
    if data.get("characters").is_some_and(Value::is_array) {
        has_update = true;
        separated
            .push("characters_json")
            .push_unseparated("=")
            .push_bind_unseparated(characters_json(data.get("characters")));
    }
    if !has_update {
        return api_error("Prompt not found", StatusCode::NOT_FOUND, Some("not_found"));
    }
    separated
        .push("updated_at")
        .push_unseparated("=")
        .push_bind_unseparated(now());
    query.push(" WHERE id=").push_bind(pid);
    match query.build().execute(&state.db).await {
        Ok(result) if result.rows_affected() > 0 => {
            match get_prompt_value(&state.db_read, pid).await {
                Ok(Some(prompt)) => api_success(json!({"prompt": prompt}), StatusCode::OK, None),
                Ok(None) => api_error("Prompt not found", StatusCode::NOT_FOUND, Some("not_found")),
                Err(error) => internal_error(error, "failed to load updated prompt"),
            }
        }
        Ok(_) => api_error("Prompt not found", StatusCode::NOT_FOUND, Some("not_found")),
        Err(error) => internal_error(error, "failed to update prompt"),
    }
}

pub async fn delete_prompt(
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
    match sqlx::query("DELETE FROM prompt_library WHERE id=?")
        .bind(pid)
        .execute(&state.db)
        .await
    {
        Ok(result) if result.rows_affected() > 0 => {
            api_success(json!({"deleted": pid}), StatusCode::OK, None)
        }
        Ok(_) => api_error("Prompt not found", StatusCode::NOT_FOUND, Some("not_found")),
        Err(error) => internal_error(error, "failed to delete prompt"),
    }
}

pub async fn folders(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let folders = match list_folder_values(&state.db_read).await {
        Ok(folders) => folders,
        Err(error) => return internal_error(error, "failed to list folders"),
    };
    let tree = build_folder_tree(&folders);
    api_success(
        json!({"folders": folders, "tree": tree}),
        StatusCode::OK,
        None,
    )
}

async fn list_folder_values(pool: &SqlitePool) -> Result<Vec<Value>, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT f.id, f.name, f.parent_id, f.sort_order, f.created_at, COUNT(fi.prompt_id) AS count
         FROM prompt_library_folders f
         LEFT JOIN prompt_library_folder_items fi ON fi.folder_id=f.id
         GROUP BY f.id ORDER BY f.sort_order, f.id",
    )
    .fetch_all(pool)
    .await?;
    Ok(rows
        .into_iter()
        .map(|r| {
            json!({
                "id": r.get::<i64, _>("id"),
                "name": r.get::<String, _>("name"),
                "parent_id": r.try_get::<Option<i64>, _>("parent_id").unwrap_or(None),
                "sort_order": r.get::<i64, _>("sort_order"),
                "created_at": r.get::<i64, _>("created_at"),
                "count": r.get::<i64, _>("count"),
            })
        })
        .collect())
}

fn build_folder_tree(folders: &[Value]) -> Value {
    let mut roots = Vec::new();
    for folder in folders {
        if folder.get("parent_id").is_none_or(Value::is_null) {
            let mut node = folder.clone();
            node["children"] = json!(children_for(
                folders,
                folder["id"].as_i64().unwrap_or_default()
            ));
            roots.push(node);
        }
    }
    json!(roots)
}

fn children_for(folders: &[Value], parent_id: i64) -> Vec<Value> {
    folders
        .iter()
        .filter(|folder| folder["parent_id"].as_i64() == Some(parent_id))
        .map(|folder| {
            let mut node = folder.clone();
            node["children"] = json!(children_for(
                folders,
                folder["id"].as_i64().unwrap_or_default()
            ));
            node
        })
        .collect()
}

pub async fn create_folder(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let name = data
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if name.is_empty() {
        return api_error(
            "name is required",
            StatusCode::BAD_REQUEST,
            Some("missing_name"),
        );
    }
    let now = now();
    let next_order: i64 = match sqlx::query_scalar(
        "SELECT COALESCE(MAX(sort_order),0)+1 FROM prompt_library_folders",
    )
    .fetch_one(&state.db)
    .await
    {
        Ok(value) => value,
        Err(error) => return internal_error(error, "failed to get folder sort order"),
    };
    let parent_id = data.get("parent_id").and_then(Value::as_i64);
    match sqlx::query("INSERT INTO prompt_library_folders (name, parent_id, sort_order, created_at) VALUES (?, ?, ?, ?)")
        .bind(name)
        .bind(parent_id)
        .bind(next_order)
        .bind(now)
        .execute(&state.db)
        .await
    {
        Ok(result) => api_success(json!({"folder": {"id": result.last_insert_rowid(), "name": name, "parent_id": parent_id, "sort_order": next_order, "created_at": now, "count": 0}}), StatusCode::CREATED, None),
        Err(error) => internal_error(error, "failed to create folder"),
    }
}

pub async fn update_folder(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(fid): AxumPath<i64>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let mut query = QueryBuilder::<Sqlite>::new("UPDATE prompt_library_folders SET ");
    let mut separated = query.separated(", ");
    let mut changed = false;
    if data.get("name").is_some() {
        changed = true;
        separated
            .push("name")
            .push_unseparated("=")
            .push_bind_unseparated(
                data.get("name")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .trim(),
            );
    }
    if data.get("parent_id").is_some() {
        changed = true;
        separated
            .push("parent_id")
            .push_unseparated("=")
            .push_bind_unseparated(data.get("parent_id").and_then(Value::as_i64));
    }
    if !changed {
        return api_error("Folder not found", StatusCode::NOT_FOUND, Some("not_found"));
    }
    query.push(" WHERE id=").push_bind(fid);
    match query.build().execute(&state.db).await {
        Ok(result) if result.rows_affected() > 0 => {
            let row = sqlx::query("SELECT id, name, parent_id, sort_order, created_at FROM prompt_library_folders WHERE id=?")
                .bind(fid)
                .fetch_one(&state.db_read)
                .await;
            match row {
                Ok(r) => api_success(
                    json!({"folder": {"id": r.get::<i64, _>("id"), "name": r.get::<String, _>("name"), "parent_id": r.try_get::<Option<i64>, _>("parent_id").unwrap_or(None), "sort_order": r.get::<i64, _>("sort_order"), "created_at": r.get::<i64, _>("created_at")}}),
                    StatusCode::OK,
                    None,
                ),
                Err(error) => internal_error(error, "failed to load updated folder"),
            }
        }
        Ok(_) => api_error("Folder not found", StatusCode::NOT_FOUND, Some("not_found")),
        Err(error) => internal_error(error, "failed to update folder"),
    }
}

pub async fn delete_folder(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(fid): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let parent = sqlx::query_scalar::<_, Option<i64>>(
        "SELECT parent_id FROM prompt_library_folders WHERE id=?",
    )
    .bind(fid)
    .fetch_optional(&state.db_read)
    .await
    .ok()
    .flatten()
    .flatten();
    let mut tx = match state.db.begin().await {
        Ok(tx) => tx,
        Err(error) => return internal_error(error, "failed to begin delete folder"),
    };
    if let Err(error) =
        sqlx::query("UPDATE prompt_library_folders SET parent_id=? WHERE parent_id=?")
            .bind(parent)
            .bind(fid)
            .execute(&mut *tx)
            .await
    {
        return internal_error(error, "failed to reparent folders");
    }
    let _ = sqlx::query("DELETE FROM prompt_library_folder_items WHERE folder_id=?")
        .bind(fid)
        .execute(&mut *tx)
        .await;
    let deleted = match sqlx::query("DELETE FROM prompt_library_folders WHERE id=?")
        .bind(fid)
        .execute(&mut *tx)
        .await
    {
        Ok(result) => result.rows_affected(),
        Err(error) => return internal_error(error, "failed to delete folder"),
    };
    if let Err(error) = tx.commit().await {
        return internal_error(error, "failed to commit delete folder");
    }
    if deleted == 0 {
        api_error("Folder not found", StatusCode::NOT_FOUND, Some("not_found"))
    } else {
        api_success(json!({"deleted": fid}), StatusCode::OK, None)
    }
}

pub async fn assign_folder(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(folder_id) = data.get("folder_id").and_then(Value::as_i64) else {
        return api_error("folder_id is required", StatusCode::BAD_REQUEST, None);
    };
    match sqlx::query("INSERT OR IGNORE INTO prompt_library_folder_items (prompt_id, folder_id, sort_order) VALUES (?, ?, 0)")
        .bind(pid)
        .bind(folder_id)
        .execute(&state.db)
        .await
    {
        Ok(_) => api_success(json!({}), StatusCode::OK, None),
        Err(error) => internal_error(error, "failed to assign folder"),
    }
}

pub async fn remove_folder(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(folder_id) = data.get("folder_id").and_then(Value::as_i64) else {
        return api_error("folder_id is required", StatusCode::BAD_REQUEST, None);
    };
    match sqlx::query("DELETE FROM prompt_library_folder_items WHERE prompt_id=? AND folder_id=?")
        .bind(pid)
        .bind(folder_id)
        .execute(&state.db)
        .await
    {
        Ok(_) => api_success(json!({}), StatusCode::OK, None),
        Err(error) => internal_error(error, "failed to remove folder"),
    }
}

pub async fn tags(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let rows = match sqlx::query(
        "SELECT t.id, t.name, COUNT(tm.prompt_id) AS count
         FROM prompt_library_tags t
         LEFT JOIN prompt_library_tag_map tm ON tm.tag_id=t.id
         GROUP BY t.id ORDER BY t.name",
    )
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list tags"),
    };
    let tags = rows
        .into_iter()
        .map(|r| json!({"id": r.get::<i64, _>("id"), "name": r.get::<String, _>("name"), "count": r.get::<i64, _>("count")}))
        .collect::<Vec<_>>();
    api_success(json!({"tags": tags}), StatusCode::OK, None)
}

pub async fn create_tag(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let name = data
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if name.is_empty() {
        return api_error(
            "name is required",
            StatusCode::BAD_REQUEST,
            Some("missing_name"),
        );
    }
    match sqlx::query("INSERT INTO prompt_library_tags (name) VALUES (?)")
        .bind(name)
        .execute(&state.db)
        .await
    {
        Ok(result) => api_success(
            json!({"tag": {"id": result.last_insert_rowid(), "name": name, "count": 0}}),
            StatusCode::CREATED,
            None,
        ),
        Err(sqlx::Error::Database(_)) => api_error(
            "Tag already exists",
            StatusCode::BAD_REQUEST,
            Some("duplicate_tag"),
        ),
        Err(error) => internal_error(error, "failed to create tag"),
    }
}

pub async fn delete_tag(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(tid): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let mut tx = match state.db.begin().await {
        Ok(tx) => tx,
        Err(error) => return internal_error(error, "failed to begin delete tag"),
    };
    let _ = sqlx::query("DELETE FROM prompt_library_tag_map WHERE tag_id=?")
        .bind(tid)
        .execute(&mut *tx)
        .await;
    let deleted = match sqlx::query("DELETE FROM prompt_library_tags WHERE id=?")
        .bind(tid)
        .execute(&mut *tx)
        .await
    {
        Ok(result) => result.rows_affected(),
        Err(error) => return internal_error(error, "failed to delete tag"),
    };
    let _ = tx.commit().await;
    if deleted == 0 {
        api_error("Tag not found", StatusCode::NOT_FOUND, Some("not_found"))
    } else {
        api_success(json!({"deleted": tid}), StatusCode::OK, None)
    }
}

pub async fn set_tags(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(tag_ids) = data.get("tag_ids").and_then(Value::as_array) else {
        return api_error("tag_ids must be a list", StatusCode::BAD_REQUEST, None);
    };
    let mut tx = match state.db.begin().await {
        Ok(tx) => tx,
        Err(error) => return internal_error(error, "failed to begin set tags"),
    };
    if let Err(error) = sqlx::query("DELETE FROM prompt_library_tag_map WHERE prompt_id=?")
        .bind(pid)
        .execute(&mut *tx)
        .await
    {
        return internal_error(error, "failed to clear prompt tags");
    }
    for tid in tag_ids.iter().filter_map(Value::as_i64) {
        if let Err(error) = sqlx::query(
            "INSERT OR IGNORE INTO prompt_library_tag_map (prompt_id, tag_id) VALUES (?, ?)",
        )
        .bind(pid)
        .bind(tid)
        .execute(&mut *tx)
        .await
        {
            return internal_error(error, "failed to insert prompt tag");
        }
    }
    if let Err(error) = tx.commit().await {
        return internal_error(error, "failed to commit set tags");
    }
    let tags = match prompt_tags(&state.db_read, pid).await {
        Ok(tags) => tags,
        Err(error) => return internal_error(error, "failed to load prompt tags"),
    };
    api_success(json!({"tags": tags}), StatusCode::OK, None)
}

async fn prompt_tags(pool: &SqlitePool, pid: i64) -> Result<Vec<Value>, sqlx::Error> {
    Ok(sqlx::query(
        "SELECT t.id, t.name FROM prompt_library_tags t
         JOIN prompt_library_tag_map tm ON tm.tag_id=t.id
         WHERE tm.prompt_id=? ORDER BY t.name",
    )
    .bind(pid)
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|r| json!({"id": r.get::<i64, _>("id"), "name": r.get::<String, _>("name")}))
    .collect())
}

pub async fn bulk_delete(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(ids) = data
        .get("ids")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty())
    else {
        return api_error("ids list is required", StatusCode::BAD_REQUEST, None);
    };
    let deleted = match delete_ids(&state.db, "prompt_library", "id", ids).await {
        Ok(value) => value,
        Err(error) => return internal_error(error, "failed to bulk delete prompts"),
    };
    api_success(json!({"deleted": deleted}), StatusCode::OK, None)
}

async fn delete_ids(
    pool: &SqlitePool,
    table: &str,
    column: &str,
    ids: &[Value],
) -> Result<u64, sqlx::Error> {
    let mut query = QueryBuilder::<Sqlite>::new(format!("DELETE FROM {table} WHERE {column} IN ("));
    let mut separated = query.separated(",");
    for id in ids.iter().filter_map(Value::as_i64) {
        separated.push_bind(id);
    }
    separated.push_unseparated(")");
    Ok(query.build().execute(pool).await?.rows_affected())
}

pub async fn bulk_move(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(ids) = data
        .get("ids")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty())
    else {
        return api_error("ids list is required", StatusCode::BAD_REQUEST, None);
    };
    let Some(folder_id) = data.get("folder_id").and_then(Value::as_i64) else {
        return api_error("folder_id is required", StatusCode::BAD_REQUEST, None);
    };
    let prompt_ids = ids.iter().filter_map(Value::as_i64).collect::<Vec<_>>();
    let mut tx = match state.db.begin().await {
        Ok(tx) => tx,
        Err(error) => return internal_error(error, "failed to begin bulk move"),
    };
    for pid in &prompt_ids {
        let _ = sqlx::query("DELETE FROM prompt_library_folder_items WHERE prompt_id=?")
            .bind(pid)
            .execute(&mut *tx)
            .await;
        let _ = sqlx::query("INSERT OR IGNORE INTO prompt_library_folder_items (prompt_id, folder_id, sort_order) VALUES (?, ?, 0)")
            .bind(pid)
            .bind(folder_id)
            .execute(&mut *tx)
            .await;
    }
    let _ = tx.commit().await;
    api_success(json!({"moved": prompt_ids.len()}), StatusCode::OK, None)
}

pub async fn bulk_tag(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(ids) = data
        .get("ids")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty())
    else {
        return api_error("ids list is required", StatusCode::BAD_REQUEST, None);
    };
    let Some(tag_ids) = data
        .get("tag_ids")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty())
    else {
        return api_error("tag_ids list is required", StatusCode::BAD_REQUEST, None);
    };
    let prompt_ids = ids.iter().filter_map(Value::as_i64).collect::<Vec<_>>();
    let tag_ids = tag_ids.iter().filter_map(Value::as_i64).collect::<Vec<_>>();
    let mut tx = match state.db.begin().await {
        Ok(tx) => tx,
        Err(error) => return internal_error(error, "failed to begin bulk tag"),
    };
    for pid in &prompt_ids {
        for tid in &tag_ids {
            let _ = sqlx::query(
                "INSERT OR IGNORE INTO prompt_library_tag_map (prompt_id, tag_id) VALUES (?, ?)",
            )
            .bind(pid)
            .bind(tid)
            .execute(&mut *tx)
            .await;
        }
    }
    let _ = tx.commit().await;
    api_success(json!({"tagged": prompt_ids.len()}), StatusCode::OK, None)
}

pub async fn export_library(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Some(response) = ensure_tables_or_response(&state).await {
        return response;
    }
    let folder_id = params.get("folder_id").and_then(|v| v.parse::<i64>().ok());
    match export_library_value(&state.db_read, folder_id).await {
        Ok(value) => api_success(value.clone(), StatusCode::OK, Some(value)),
        Err(error) => internal_error(error, "failed to export prompt library"),
    }
}

async fn export_library_value(
    pool: &SqlitePool,
    folder_id: Option<i64>,
) -> Result<Value, sqlx::Error> {
    let rows = if let Some(folder_id) = folder_id {
        sqlx::query(
            "SELECT p.id, p.title, p.positive, p.negative, p.seed, p.steps, p.sampler, p.cfg_scale, p.model_name, p.memo, p.characters_json, p.created_at, p.updated_at
             FROM prompt_library p JOIN prompt_library_folder_items fi ON fi.prompt_id=p.id
             WHERE fi.folder_id=? ORDER BY p.updated_at DESC",
        )
        .bind(folder_id)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT id, title, positive, negative, seed, steps, sampler, cfg_scale, model_name, memo, characters_json, created_at, updated_at
             FROM prompt_library ORDER BY updated_at DESC",
        )
        .fetch_all(pool)
        .await?
    };
    let mut prompts = Vec::new();
    for r in rows {
        let pid = r.get::<i64, _>(0);
        let mut entry = json!({
            "title": r.get::<String, _>(1),
            "positive": r.get::<String, _>(2),
            "negative": r.get::<String, _>(3),
            "seed": r.get::<String, _>(4),
            "steps": r.get::<String, _>(5),
            "sampler": r.get::<String, _>(6),
            "cfg_scale": r.get::<String, _>(7),
            "model_name": r.get::<String, _>(8),
            "memo": r.get::<String, _>(9),
            "created_at": r.get::<i64, _>(11),
            "updated_at": r.get::<i64, _>(12),
            "tags": export_tag_names(pool, pid).await?,
            "folders": export_folder_names(pool, pid).await?,
        });
        let chars_raw: String = r.get(10);
        if let Ok(chars) = serde_json::from_str::<Value>(&chars_raw) {
            if chars.as_array().is_some_and(|items| !items.is_empty()) {
                entry["characters"] = chars;
            }
        }
        prompts.push(entry);
    }
    Ok(json!({"version": 1, "exported_at": now(), "count": prompts.len(), "prompts": prompts}))
}

async fn export_tag_names(pool: &SqlitePool, pid: i64) -> Result<Vec<String>, sqlx::Error> {
    Ok(sqlx::query(
        "SELECT t.name FROM prompt_library_tags t
         JOIN prompt_library_tag_map tm ON tm.tag_id=t.id
         WHERE tm.prompt_id=? ORDER BY t.name",
    )
    .bind(pid)
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|r| r.get::<String, _>(0))
    .collect())
}

async fn export_folder_names(pool: &SqlitePool, pid: i64) -> Result<Vec<String>, sqlx::Error> {
    Ok(sqlx::query(
        "SELECT f.name FROM prompt_library_folders f
         JOIN prompt_library_folder_items fi ON fi.folder_id=f.id
         WHERE fi.prompt_id=? ORDER BY f.name",
    )
    .bind(pid)
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|r| r.get::<String, _>(0))
    .collect())
}

pub async fn import_library(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(prompts) = data.get("prompts").and_then(Value::as_array) else {
        return api_error(
            "Invalid import format: 'prompts' key missing",
            StatusCode::BAD_REQUEST,
            None,
        );
    };
    let mut imported = 0;
    let mut skipped = 0;
    for prompt in prompts {
        let title = prompt
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim();
        if title.is_empty() {
            skipped += 1;
            continue;
        }
        let inserted = match insert_prompt(&state.db, prompt, title, None).await {
            Ok(value) => value,
            Err(error) => return internal_error(error, "failed to import prompt"),
        };
        let pid = inserted["id"].as_i64().unwrap_or_default();
        for tag_name in prompt
            .get("tags")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
        {
            if let Err(error) = ensure_tag_name(&state.db, pid, tag_name.trim()).await {
                return internal_error(error, "failed to import prompt tag");
            }
        }
        for folder_name in prompt
            .get("folders")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
        {
            if let Err(error) = ensure_folder_name(&state.db, pid, folder_name.trim()).await {
                return internal_error(error, "failed to import prompt folder");
            }
        }
        imported += 1;
    }
    api_success(
        json!({"imported": imported, "skipped": skipped}),
        StatusCode::OK,
        Some(json!({"imported": imported, "skipped": skipped})),
    )
}

async fn ensure_tag_name(pool: &SqlitePool, pid: i64, name: &str) -> Result<(), sqlx::Error> {
    if name.is_empty() {
        return Ok(());
    }
    sqlx::query("INSERT OR IGNORE INTO prompt_library_tags (name) VALUES (?)")
        .bind(name)
        .execute(pool)
        .await?;
    let tid: i64 = sqlx::query_scalar("SELECT id FROM prompt_library_tags WHERE name=?")
        .bind(name)
        .fetch_one(pool)
        .await?;
    sqlx::query("INSERT OR IGNORE INTO prompt_library_tag_map (prompt_id, tag_id) VALUES (?, ?)")
        .bind(pid)
        .bind(tid)
        .execute(pool)
        .await?;
    Ok(())
}

async fn ensure_folder_name(pool: &SqlitePool, pid: i64, name: &str) -> Result<(), sqlx::Error> {
    if name.is_empty() {
        return Ok(());
    }
    let existing: Option<i64> =
        sqlx::query_scalar("SELECT id FROM prompt_library_folders WHERE name=?")
            .bind(name)
            .fetch_optional(pool)
            .await?;
    let fid = if let Some(fid) = existing {
        fid
    } else {
        sqlx::query(
            "INSERT INTO prompt_library_folders (name, parent_id, sort_order, created_at) VALUES (?, NULL, 0, ?)",
        )
        .bind(name)
        .bind(now())
        .execute(pool)
        .await?
        .last_insert_rowid()
    };
    sqlx::query("INSERT OR IGNORE INTO prompt_library_folder_items (prompt_id, folder_id, sort_order) VALUES (?, ?, 0)")
        .bind(pid)
        .bind(fid)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn from_file(
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
    let data = match require_json(body) {
        Ok(data) => data,
        Err(response) => return response,
    };
    let Some(file_id) = data
        .get("file_id")
        .and_then(Value::as_i64)
        .filter(|v| *v > 0)
    else {
        return api_error(
            "file_id is required",
            StatusCode::BAD_REQUEST,
            Some("missing_file_id"),
        );
    };
    let row = match sqlx::query(
        "SELECT f.id, f.path, f.meta_source, tm.raw_prompt, tm.raw_negative, tm.raw_meta_json, tm.model_name
         FROM files f LEFT JOIN templates tm ON tm.file_id=f.id
         WHERE f.id=? AND f.is_deleted=0",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(Some(row)) => row,
        Ok(None) => return api_error("File not found", StatusCode::NOT_FOUND, Some("file_not_found")),
        Err(error) => return internal_error(error, "failed to read file metadata for prompt"),
    };
    let path: String = row.get("path");
    let raw_prompt: String = row
        .try_get::<Option<String>, _>("raw_prompt")
        .unwrap_or(None)
        .unwrap_or_default();
    let raw_negative: String = row
        .try_get::<Option<String>, _>("raw_negative")
        .unwrap_or(None)
        .unwrap_or_default();
    let raw_meta_json: Option<String> = row.try_get("raw_meta_json").unwrap_or(None);
    let model_name: String = row
        .try_get::<Option<String>, _>("model_name")
        .unwrap_or(None)
        .unwrap_or_default();
    let params = parse_params_from_metadata(&raw_prompt, raw_meta_json.as_deref());
    let title = data
        .get("title")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| {
            std::path::Path::new(&path)
                .file_stem()
                .and_then(|v| v.to_str())
                .unwrap_or("Imported")
                .chars()
                .take(80)
                .collect()
        });
    let create_data = json!({
        "title": title,
        "positive": params.get("positive").and_then(Value::as_str).unwrap_or(&raw_prompt),
        "negative": if raw_negative.is_empty() { params.get("negative").and_then(Value::as_str).unwrap_or("") } else { &raw_negative },
        "seed": params.get("Seed").and_then(Value::as_str).unwrap_or(""),
        "steps": params.get("Steps").and_then(Value::as_str).unwrap_or(""),
        "sampler": params.get("Sampler").and_then(Value::as_str).unwrap_or(""),
        "cfg_scale": params.get("CFG scale").and_then(Value::as_str).unwrap_or(""),
        "model_name": if model_name.is_empty() { params.get("Model").and_then(Value::as_str).unwrap_or("") } else { &model_name },
        "memo": data.get("memo").and_then(Value::as_str).unwrap_or(""),
        "characters": extract_novelai_characters(raw_meta_json.as_deref()),
    });
    match insert_prompt(
        &state.db,
        &create_data,
        create_data["title"].as_str().unwrap_or("Imported"),
        Some(file_id),
    )
    .await
    {
        Ok(prompt) => api_success(json!({"prompt": prompt}), StatusCode::CREATED, None),
        Err(error) => internal_error(error, "failed to create prompt from file"),
    }
}

fn parse_params_from_metadata(raw_prompt: &str, raw_meta_json: Option<&str>) -> Map<String, Value> {
    if let Some(raw) = raw_meta_json {
        if let Ok(Value::Object(obj)) = serde_json::from_str::<Value>(raw) {
            if let Some(Value::Object(params)) = obj.get("parameters") {
                return params.clone();
            }
            if obj.contains_key("Seed") || obj.contains_key("Steps") {
                return obj;
            }
        }
    }
    let mut result = Map::new();
    let mut positive = raw_prompt.to_string();
    let mut negative = String::new();
    if let Some(idx) = raw_prompt.find("Negative prompt:") {
        positive = raw_prompt[..idx].trim().to_string();
        let rest = &raw_prompt[idx + "Negative prompt:".len()..];
        if let Some(steps_idx) = rest.find("Steps:") {
            negative = rest[..steps_idx].trim().trim_end_matches(',').to_string();
        } else {
            negative = rest.trim().to_string();
        }
    }
    if let Some(steps_idx) = raw_prompt.rfind("Steps:") {
        for part in raw_prompt[steps_idx..].split(',') {
            if let Some((key, value)) = part.split_once(':') {
                result.insert(key.trim().to_string(), json!(value.trim()));
            }
        }
    }
    result.insert("positive".to_string(), json!(positive));
    result.insert("negative".to_string(), json!(negative));
    result
}

fn extract_novelai_characters(raw_meta_json: Option<&str>) -> Value {
    let Some(raw) = raw_meta_json else {
        return json!([]);
    };
    let Ok(value) = serde_json::from_str::<Value>(raw) else {
        return json!([]);
    };
    let data = value.get("novelai_v4_data").unwrap_or(&value);
    let prompts = data
        .get("character_prompts")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let negatives = data
        .get("negative_characters")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let chars = prompts
        .into_iter()
        .enumerate()
        .filter_map(|(idx, prompt)| {
            let prompt_text = prompt.get("prompt").and_then(Value::as_str).unwrap_or("");
            if prompt_text.is_empty() {
                return None;
            }
            let negative = negatives
                .get(idx)
                .and_then(|v| v.get("prompt"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let center = prompt
                .get("positions")
                .and_then(Value::as_array)
                .and_then(|items| items.first())
                .map(|pos| json!({"x": pos.get("x").and_then(Value::as_f64).unwrap_or(0.5), "y": pos.get("y").and_then(Value::as_f64).unwrap_or(0.5)}));
            Some(json!({"prompt": prompt_text, "negative": negative, "center": center}))
        })
        .collect::<Vec<_>>();
    json!(chars)
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
               meta_source TEXT,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );
             CREATE TABLE templates (
               file_id INTEGER PRIMARY KEY,
               raw_prompt TEXT,
               raw_negative TEXT,
               raw_meta_json TEXT,
               model_name TEXT
             );
             INSERT INTO files(id, path, meta_source, is_deleted) VALUES
               (10, '/tmp/source-image.png', 'a1111_png', 0),
               (11, '/tmp/deleted.png', 'a1111_png', 1);
             INSERT INTO templates(file_id, raw_prompt, raw_negative, raw_meta_json, model_name) VALUES
               (10, 'cat prompt
Negative prompt: blurry
Steps: 20, Sampler: Euler, CFG scale: 7, Seed: 123, Model: test-model', '', NULL, '');",
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

    async fn create_test_prompt(state: SharedState, title: &str) -> Value {
        let response = create_prompt(
            State(state),
            None,
            Ok(Json(json!({
                "title": title,
                "positive": "sunlit forest",
                "negative": "noise",
                "seed": 42,
                "steps": 28,
                "sampler": "Euler",
                "cfg_scale": 7,
                "model_name": "model-a",
                "memo": "memo text",
                "characters": [{"prompt": "hero", "negative": "villain"}]
            }))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::CREATED);
        json_body(response).await["prompt"].clone()
    }

    #[tokio::test]
    async fn prompt_library_prompt_crud_round_trip() {
        let state = test_state().await;
        let created = create_test_prompt(Arc::clone(&state), "Alpha Prompt").await;
        let pid = created["id"].as_i64().unwrap();

        let fetched =
            json_body(get_prompt(State(Arc::clone(&state)), None, AxumPath(pid)).await).await;
        assert_eq!(fetched["prompt"]["title"], "Alpha Prompt");
        assert_eq!(fetched["prompt"]["characters"][0]["prompt"], "hero");

        let updated = json_body(
            update_prompt(
                State(Arc::clone(&state)),
                None,
                AxumPath(pid),
                Ok(Json(json!({"title": "Beta Prompt", "positive": "ocean"}))),
            )
            .await,
        )
        .await;
        assert_eq!(updated["prompt"]["title"], "Beta Prompt");
        assert_eq!(updated["prompt"]["positive"], "ocean");

        let listed = json_body(
            list_prompts(
                State(Arc::clone(&state)),
                None,
                Query(HashMap::from([
                    ("q".to_string(), "ocean".to_string()),
                    ("sort".to_string(), "title".to_string()),
                    ("order".to_string(), "asc".to_string()),
                ])),
            )
            .await,
        )
        .await;
        assert_eq!(listed["total"], 1);
        assert_eq!(listed["items"][0]["id"], pid);

        let deleted =
            json_body(delete_prompt(State(Arc::clone(&state)), None, AxumPath(pid)).await).await;
        assert_eq!(deleted["deleted"], pid);

        let missing = get_prompt(State(state), None, AxumPath(pid)).await;
        assert_eq!(missing.status(), StatusCode::NOT_FOUND);
        assert_eq!(json_body(missing).await["code"], "not_found");
    }

    #[tokio::test]
    async fn prompt_library_folders_tags_bulk_and_export_import_round_trip() {
        let state = test_state().await;
        let p1 = create_test_prompt(Arc::clone(&state), "Bulk One").await;
        let p2 = create_test_prompt(Arc::clone(&state), "Bulk Two").await;
        let p1_id = p1["id"].as_i64().unwrap();
        let p2_id = p2["id"].as_i64().unwrap();

        let folder = json_body(
            create_folder(
                State(Arc::clone(&state)),
                None,
                Ok(Json(json!({"name": "Inbox"}))),
            )
            .await,
        )
        .await["folder"]
            .clone();
        let folder_id = folder["id"].as_i64().unwrap();

        let updated_folder = json_body(
            update_folder(
                State(Arc::clone(&state)),
                None,
                AxumPath(folder_id),
                Ok(Json(json!({"name": "Archive"}))),
            )
            .await,
        )
        .await;
        assert_eq!(updated_folder["folder"]["name"], "Archive");

        let folders_value = json_body(folders(State(Arc::clone(&state)), None).await).await;
        assert_eq!(folders_value["folders"][0]["name"], "Archive");

        let tag = json_body(
            create_tag(
                State(Arc::clone(&state)),
                None,
                Ok(Json(json!({"name": "favorite"}))),
            )
            .await,
        )
        .await["tag"]
            .clone();
        let tag_id = tag["id"].as_i64().unwrap();

        let tags_value = json_body(tags(State(Arc::clone(&state)), None).await).await;
        assert_eq!(tags_value["tags"][0]["name"], "favorite");

        let moved = json_body(
            bulk_move(
                State(Arc::clone(&state)),
                None,
                Ok(Json(json!({"ids": [p1_id, p2_id], "folder_id": folder_id}))),
            )
            .await,
        )
        .await;
        assert_eq!(moved["moved"], 2);

        let tagged = json_body(
            bulk_tag(
                State(Arc::clone(&state)),
                None,
                Ok(Json(json!({"ids": [p1_id, p2_id], "tag_ids": [tag_id]}))),
            )
            .await,
        )
        .await;
        assert_eq!(tagged["tagged"], 2);

        let filtered = json_body(
            list_prompts(
                State(Arc::clone(&state)),
                None,
                Query(HashMap::from([
                    ("folder_id".to_string(), folder_id.to_string()),
                    ("tag_id".to_string(), tag_id.to_string()),
                ])),
            )
            .await,
        )
        .await;
        assert_eq!(filtered["total"], 2);

        let exported =
            json_body(export_library(State(Arc::clone(&state)), None, Query(HashMap::new())).await)
                .await;
        assert_eq!(exported["count"], 2);
        assert_eq!(exported["prompts"][0]["tags"][0], "favorite");

        let deleted = json_body(
            bulk_delete(
                State(Arc::clone(&state)),
                None,
                Ok(Json(json!({"ids": [p1_id, p2_id]}))),
            )
            .await,
        )
        .await;
        assert_eq!(deleted["deleted"], 2);

        let imported = json_body(
            import_library(State(Arc::clone(&state)), None, Ok(Json(exported.clone()))).await,
        )
        .await;
        assert_eq!(imported["imported"], 2);
        assert_eq!(imported["skipped"], 0);

        let after_import =
            json_body(list_prompts(State(Arc::clone(&state)), None, Query(HashMap::new())).await)
                .await;
        assert_eq!(after_import["total"], 2);

        let removed_tag =
            json_body(delete_tag(State(Arc::clone(&state)), None, AxumPath(tag_id)).await).await;
        assert_eq!(removed_tag["deleted"], tag_id);

        let removed_folder =
            json_body(delete_folder(State(state), None, AxumPath(folder_id)).await).await;
        assert_eq!(removed_folder["deleted"], folder_id);
    }

    #[tokio::test]
    async fn prompt_library_from_file_imports_metadata_and_reports_missing_file_id() {
        let state = test_state().await;

        let missing = from_file(State(Arc::clone(&state)), None, Ok(Json(json!({})))).await;
        assert_eq!(missing.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(missing).await["code"], "missing_file_id");

        let imported = from_file(
            State(Arc::clone(&state)),
            None,
            Ok(Json(json!({"file_id": 10, "memo": "from file"}))),
        )
        .await;
        assert_eq!(imported.status(), StatusCode::CREATED);
        let value = json_body(imported).await;
        assert_eq!(value["prompt"]["title"], "source-image");
        assert_eq!(value["prompt"]["positive"], "cat prompt");
        assert_eq!(value["prompt"]["negative"], "blurry");
        assert_eq!(value["prompt"]["seed"], "123");
        assert_eq!(value["prompt"]["source_file_id"], 10);
    }

    #[tokio::test]
    async fn prompt_library_json_validation_errors_do_not_include_codes() {
        let value =
            json_body(create_prompt(State(test_state().await), None, Ok(Json(json!([])))).await)
                .await;

        assert_eq!(
            value,
            json!({"ok": false, "error": "JSON object body is required"})
        );
    }
}

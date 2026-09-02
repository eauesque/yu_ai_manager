use std::collections::HashMap;

use axum::{
    extract::{rejection::JsonRejection, Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use regex::Regex;
use serde_json::{json, Value};
use sqlx::{
    sqlite::SqliteValueRef, Decode, QueryBuilder, Row, Sqlite, SqlitePool, Value as SqlxValue,
    ValueRef,
};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const BATCH_SET_MAX: usize = 500;
const MAX_VALUE_LEN: usize = 65_536;
const ZSTD_MAGIC: &[u8; 4] = b"\x28\xb5\x2f\xfd";

fn api_success(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_error(message: &str, status: StatusCode, code: Option<&str>) -> Response {
    let mut body = json!({"ok": false, "error": message});
    if let Some(code) = code {
        body["code"] = json!(code);
    }
    (status, Json(body)).into_response()
}

fn require_json_object(body: Result<Json<Value>, JsonRejection>) -> Result<Value, Response> {
    match body {
        Ok(Json(value @ Value::Object(_))) => Ok(value),
        Ok(_) | Err(_) => Err(api_error(
            "JSON object required",
            StatusCode::BAD_REQUEST,
            Some("invalid_json"),
        )),
    }
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

fn decode_annotation_value(value: SqliteValueRef<'_>) -> Result<String, sqlx::Error> {
    if value.is_null() {
        return Ok(String::new());
    }
    let owned = value.to_owned();
    if let Ok(text) = <String as Decode<Sqlite>>::decode(owned.as_ref()) {
        return Ok(text);
    }
    let bytes = <Vec<u8> as Decode<Sqlite>>::decode(owned.as_ref()).map_err(sqlx::Error::Decode)?;
    if bytes.starts_with(ZSTD_MAGIC) {
        let decoded = zstd::stream::decode_all(bytes.as_slice())
            .map_err(|err| sqlx::Error::Decode(err.into()))?;
        return Ok(String::from_utf8_lossy(&decoded).into_owned());
    }
    Ok(String::from_utf8_lossy(&bytes).into_owned())
}

fn annotation_row(row: sqlx::sqlite::SqliteRow) -> Result<Value, sqlx::Error> {
    Ok(json!({
        "id": row.get::<i64, _>("id"),
        "file_id": row.get::<i64, _>("file_id"),
        "source": row.get::<String, _>("source"),
        "key": row.get::<String, _>("key"),
        "value": decode_annotation_value(row.try_get_raw("value")?)?,
        "confidence": row.try_get::<Option<f64>, _>("confidence")?,
        "created_at": row.get::<i64, _>("created_at"),
    }))
}

fn parse_limit(params: &HashMap<String, String>, default: i64, max: i64) -> i64 {
    params
        .get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(default)
        .clamp(1, max)
}

fn parse_offset(params: &HashMap<String, String>) -> i64 {
    params
        .get("offset")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(0)
        .max(0)
}

fn valid_source(value: &str) -> bool {
    Regex::new(r"^[a-z0-9_.:-]{1,64}$").unwrap().is_match(value)
}

fn valid_key(value: &str) -> bool {
    Regex::new(r"^[a-z0-9_.:-]{1,128}$")
        .unwrap()
        .is_match(value)
}

async fn existing_file_ids(
    pool: &SqlitePool,
    ids: &[i64],
) -> Result<std::collections::HashSet<i64>, sqlx::Error> {
    let mut found = std::collections::HashSet::new();
    if ids.is_empty() {
        return Ok(found);
    }
    let mut query = QueryBuilder::<Sqlite>::new("SELECT id FROM files WHERE id IN (");
    let mut separated = query.separated(",");
    for id in ids {
        separated.push_bind(id);
    }
    separated.push_unseparated(") AND is_deleted=0");
    for row in query.build().fetch_all(pool).await? {
        found.insert(row.get::<i64, _>("id"));
    }
    Ok(found)
}

pub async fn notes(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    notes_data(State(state), auth_context, Query(params)).await
}

pub async fn notes_data(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let q = params
        .get("q")
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty());
    let limit = parse_limit(&params, 50, 200);
    let offset = parse_offset(&params);

    // Python 互換: LEFT JOIN files to include path, filter by path LIKE (not value)
    let join = " FROM file_annotations a LEFT JOIN files f ON a.file_id = f.id \
                 WHERE a.source='user' AND a.key='note'";

    let mut count = QueryBuilder::<Sqlite>::new("SELECT COUNT(*)");
    count.push(join);
    let mut rows =
        QueryBuilder::<Sqlite>::new("SELECT a.id, a.file_id, f.path, a.value, a.created_at");
    rows.push(join);

    if let Some(ref q) = q {
        let like = format!("%{q}%");
        count.push(" AND f.path LIKE ").push_bind(like.clone());
        rows.push(" AND f.path LIKE ").push_bind(like);
    }
    rows.push(" ORDER BY a.created_at DESC LIMIT ")
        .push_bind(limit)
        .push(" OFFSET ")
        .push_bind(offset);

    let total: i64 = match count.build_query_scalar().fetch_one(&state.db_read).await {
        Ok(total) => total,
        Err(error) => return internal_error(error, "failed to count annotations notes"),
    };
    let rows = match rows.build().fetch_all(&state.db_read).await {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list annotations notes"),
    };
    let mut notes: Vec<Value> = Vec::with_capacity(rows.len());
    for row in rows {
        let id: i64 = row.try_get("id").unwrap_or(0);
        let file_id: i64 = row.try_get("file_id").unwrap_or(0);
        let path: Option<String> = row.try_get("path").unwrap_or(None);
        let raw: Vec<u8> = row.try_get("value").unwrap_or_default();
        let created_at: Option<String> = row.try_get("created_at").unwrap_or(None);
        let value = decompress_note_value(&raw);
        notes.push(json!({
            "id": id,
            "file_id": file_id,
            "path": path.unwrap_or_default(),
            "value": value,
            "created_at": created_at,
        }));
    }
    api_success(json!({"notes": notes, "total": total, "limit": limit, "offset": offset}))
}

fn decompress_note_value(raw: &[u8]) -> Value {
    if raw.is_empty() {
        return Value::Null;
    }
    // Attempt Zstd decompress; fall back to UTF-8 string if not compressed
    let decompressed: Vec<u8> = zstd::stream::decode_all(raw).unwrap_or_else(|_| raw.to_vec());
    match serde_json::from_slice::<Value>(&decompressed) {
        Ok(v) => v,
        Err(_) => Value::String(String::from_utf8_lossy(&decompressed).into_owned()),
    }
}

pub async fn get_file_annotations(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let mut query = QueryBuilder::<Sqlite>::new(
        "SELECT id, file_id, source, key, value, confidence, created_at FROM file_annotations WHERE file_id=",
    );
    query.push_bind(file_id);
    if let Some(source) = params.get("source").filter(|v| !v.is_empty()) {
        query.push(" AND source=").push_bind(source);
    }
    if let Some(key) = params.get("key").filter(|v| !v.is_empty()) {
        query.push(" AND key=").push_bind(key);
    }
    query.push(" ORDER BY created_at DESC");
    let rows = match query.build().fetch_all(&state.db_read).await {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to get annotations"),
    };
    let annotations = match rows
        .into_iter()
        .map(annotation_row)
        .collect::<Result<Vec<_>, _>>()
    {
        Ok(items) => items,
        Err(error) => return internal_error(error, "failed to decode annotations"),
    };
    api_success(json!({"annotations": annotations}))
}

pub async fn s2t_transcript(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    // Python 互換: builtin_speech_to_text/s2t_routes.py::api_s2t_transcript
    // source='s2t' 優先、無ケレバ旧 source='hailo:s2t' ヲ後方互換トシテ参照ス
    let mut rows = match sqlx::query(
        "SELECT key, value FROM file_annotations WHERE file_id=? AND source='s2t'",
    )
    .bind(file_id)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to get s2t transcript"),
    };
    if rows.is_empty() {
        rows = match sqlx::query(
            "SELECT key, value FROM file_annotations WHERE file_id=? AND source='hailo:s2t'",
        )
        .bind(file_id)
        .fetch_all(&state.db_read)
        .await
        {
            Ok(rows) => rows,
            Err(error) => return internal_error(error, "failed to get s2t transcript"),
        };
    }
    if rows.is_empty() {
        return Json(json!({
            "status": "not_found",
            "message": "No transcript for this file",
        }))
        .into_response();
    }

    let mut result = json!({"status": "ok", "file_id": file_id});
    for row in rows {
        let key: String = row.get("key");
        let value = match decode_annotation_value(row.try_get_raw("value").unwrap()) {
            Ok(value) => value,
            Err(error) => return internal_error(error, "failed to decode s2t transcript"),
        };
        match key.as_str() {
            "transcript" => result["text"] = json!(value),
            "transcript_segments" => {
                result["segments"] = serde_json::from_str(&value).unwrap_or(json!([]));
            }
            "transcript_backend" => result["backend"] = json!(value),
            _ => {}
        }
    }
    Json(result).into_response()
}

pub async fn search(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let limit = parse_limit(&params, 100, 2000);
    let offset = parse_offset(&params);
    let min_confidence = params
        .get("min_confidence")
        .and_then(|v| v.parse::<f64>().ok());
    let max_confidence = params
        .get("max_confidence")
        .and_then(|v| v.parse::<f64>().ok());

    let mut count = QueryBuilder::<Sqlite>::new("SELECT COUNT(*) FROM file_annotations a");
    let mut rows = QueryBuilder::<Sqlite>::new(
        "SELECT a.id, a.file_id, a.source, a.key, a.value, a.confidence, a.created_at FROM file_annotations a",
    );
    let mut conditions: Vec<(&str, Value)> = Vec::new();
    if let Some(source) = params.get("source").filter(|v| !v.is_empty()) {
        conditions.push(("a.source=", json!(source)));
    }
    if let Some(key) = params.get("key").filter(|v| !v.is_empty()) {
        conditions.push(("a.key=", json!(key)));
    }
    if let Some(value) = min_confidence {
        conditions.push(("a.confidence >= ", json!(value)));
    }
    if let Some(value) = max_confidence {
        conditions.push(("a.confidence <= ", json!(value)));
    }
    for (idx, (sql, value)) in conditions.iter().enumerate() {
        let prefix = if idx == 0 { " WHERE " } else { " AND " };
        count.push(prefix).push(*sql);
        rows.push(prefix).push(*sql);
        if let Some(s) = value.as_str() {
            count.push_bind(s.to_string());
            rows.push_bind(s.to_string());
        } else if let Some(f) = value.as_f64() {
            count.push_bind(f);
            rows.push_bind(f);
        }
    }
    rows.push(" ORDER BY a.created_at DESC LIMIT ")
        .push_bind(limit)
        .push(" OFFSET ")
        .push_bind(offset);

    let total: i64 = match count.build_query_scalar().fetch_one(&state.db_read).await {
        Ok(total) => total,
        Err(error) => return internal_error(error, "failed to count annotations search"),
    };
    let rows = match rows.build().fetch_all(&state.db_read).await {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to search annotations"),
    };
    let annotations = match rows
        .into_iter()
        .map(annotation_row)
        .collect::<Result<Vec<_>, _>>()
    {
        Ok(items) => items,
        Err(error) => return internal_error(error, "failed to decode annotations search"),
    };
    api_success(
        json!({"annotations": annotations, "total": total, "limit": limit, "offset": offset}),
    )
}

pub async fn batch_set(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let body = match require_json_object(body) {
        Ok(body) => body,
        Err(response) => return response,
    };
    let Some(items) = body.get("items").and_then(Value::as_array) else {
        return api_error(
            "items array required",
            StatusCode::BAD_REQUEST,
            Some("batch_empty"),
        );
    };
    if items.is_empty() {
        return api_error(
            "items array required",
            StatusCode::BAD_REQUEST,
            Some("batch_empty"),
        );
    }
    if items.len() > BATCH_SET_MAX {
        return api_error(
            &format!(
                "Batch size {} exceeds maximum of {BATCH_SET_MAX}",
                items.len()
            ),
            StatusCode::BAD_REQUEST,
            Some("batch_too_large"),
        );
    }
    let candidate_ids = items
        .iter()
        .filter_map(|item| {
            item.get("file_id")
                .and_then(Value::as_i64)
                .filter(|id| *id > 0)
        })
        .collect::<Vec<_>>();
    let existing = match existing_file_ids(&state.db_read, &candidate_ids).await {
        Ok(existing) => existing,
        Err(error) => return internal_error(error, "failed to validate annotation file ids"),
    };
    let mut valid = Vec::new();
    let mut errors = Vec::new();
    for item in items {
        let file_id = item.get("file_id").and_then(Value::as_i64);
        let source = item.get("source").and_then(Value::as_str).map(str::trim);
        let key = item.get("key").and_then(Value::as_str).map(str::trim);
        let value = item.get("value").and_then(Value::as_str);
        let confidence = item
            .get("confidence")
            .filter(|v| !v.is_null())
            .and_then(Value::as_f64);
        let raw_file_id = item.get("file_id").cloned().unwrap_or(Value::Null);
        let Some(file_id) = file_id.filter(|id| *id > 0) else {
            errors.push(json!({"file_id": raw_file_id, "code": "invalid_value", "error": "file_id must be a positive integer"}));
            continue;
        };
        let Some(source) = source.filter(|v| !v.is_empty()) else {
            errors.push(
                json!({"file_id": file_id, "code": "invalid_value", "error": "source is required"}),
            );
            continue;
        };
        if !valid_source(source) {
            errors.push(json!({"file_id": file_id, "code": "invalid_value", "error": "source must match ^[a-z0-9_.:-]{1,64}$"}));
            continue;
        }
        let Some(key) = key.filter(|v| !v.is_empty()) else {
            errors.push(
                json!({"file_id": file_id, "code": "invalid_value", "error": "key is required"}),
            );
            continue;
        };
        if !valid_key(key) {
            errors.push(json!({"file_id": file_id, "code": "invalid_value", "error": "key must match ^[a-z0-9_.:-]{1,128}$"}));
            continue;
        }
        let Some(value) = value else {
            errors.push(json!({"file_id": file_id, "code": "invalid_value", "error": "value must be a string"}));
            continue;
        };
        if value.len() > MAX_VALUE_LEN {
            errors.push(json!({"file_id": file_id, "code": "invalid_value", "error": format!("value exceeds {MAX_VALUE_LEN} characters")}));
            continue;
        }
        if item.get("confidence").is_some_and(|v| !v.is_null()) && confidence.is_none() {
            errors.push(json!({"file_id": file_id, "code": "invalid_value", "error": "confidence must be a number or null"}));
            continue;
        }
        if confidence.is_some_and(|c| !(0.0..=1.0).contains(&c)) {
            errors.push(json!({"file_id": file_id, "code": "invalid_value", "error": "confidence must be 0.0-1.0"}));
            continue;
        }
        if !existing.contains(&file_id) {
            errors
                .push(json!({"file_id": file_id, "code": "not_found", "error": "File not found"}));
            continue;
        }
        valid.push((
            file_id,
            source.to_string(),
            key.to_string(),
            value.to_string(),
            confidence,
        ));
    }
    let mut tx = match state.db.begin().await {
        Ok(tx) => tx,
        Err(error) => return internal_error(error, "failed to begin annotations batch set"),
    };
    for (file_id, source, key, value, confidence) in &valid {
        if let Err(error) = sqlx::query(
            "INSERT INTO file_annotations (file_id, source, key, value, confidence, created_at)
             VALUES (?, ?, ?, ?, ?, unixepoch())
             ON CONFLICT(file_id, source, key) DO UPDATE SET
                value=excluded.value, confidence=excluded.confidence, created_at=excluded.created_at",
        )
        .bind(file_id)
        .bind(source)
        .bind(key)
        .bind(value)
        .bind(confidence)
        .execute(&mut *tx)
        .await
        {
            return internal_error(error, "failed to upsert annotation");
        }
    }
    if let Err(error) = tx.commit().await {
        return internal_error(error, "failed to commit annotations batch set");
    }
    api_success(
        json!({"data": {"total": items.len(), "succeeded": valid.len(), "failed": errors.len(), "errors": errors}}),
    )
}

pub async fn batch_delete(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let body = match require_json_object(body) {
        Ok(body) => body,
        Err(response) => return response,
    };
    let Some(source) = body
        .get("source")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
    else {
        return api_error(
            "source is required",
            StatusCode::BAD_REQUEST,
            Some("invalid_value"),
        );
    };
    let Some(file_ids) = body
        .get("file_ids")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty())
    else {
        return api_error(
            "file_ids is required (non-empty list)",
            StatusCode::BAD_REQUEST,
            Some("invalid_value"),
        );
    };
    if file_ids.len() > 500 {
        return api_error(
            "file_ids too large (max 500)",
            StatusCode::BAD_REQUEST,
            Some("batch_too_large"),
        );
    }
    let ids = file_ids
        .iter()
        .filter_map(Value::as_i64)
        .collect::<Vec<_>>();
    let key = body
        .get("key")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty());
    let mut query = QueryBuilder::<Sqlite>::new("DELETE FROM file_annotations WHERE source=");
    query.push_bind(source);
    query.push(" AND file_id IN (");
    let mut separated = query.separated(",");
    for id in &ids {
        separated.push_bind(id);
    }
    separated.push_unseparated(")");
    if let Some(key) = key {
        query.push(" AND key=").push_bind(key);
    }
    let deleted = match query.build().execute(&state.db).await {
        Ok(result) => result.rows_affected(),
        Err(error) => return internal_error(error, "failed to delete annotations"),
    };
    api_success(json!({"data": {"deleted": deleted}}))
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
             CREATE TABLE file_annotations (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               file_id INTEGER NOT NULL,
               source TEXT NOT NULL,
               key TEXT NOT NULL,
               value BLOB NOT NULL,
               confidence REAL,
               created_at INTEGER NOT NULL,
               UNIQUE(file_id, source, key)
             );
             INSERT INTO files(id, path, is_deleted) VALUES
               (1, '/tmp/a.png', 0),
               (2, '/tmp/b.png', 0),
               (3, '/tmp/deleted.png', 1);",
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
    async fn annotations_batch_set_read_search_and_delete_round_trip() {
        let state = test_state().await;

        let set_value = json_body(
            batch_set(
                State(Arc::clone(&state)),
                None,
                Ok(Json(json!({
                    "items": [
                        {"file_id": 1, "source": "user", "key": "note", "value": "first note", "confidence": 0.9},
                        {"file_id": 2, "source": "agent", "key": "label", "value": "second label", "confidence": 0.5}
                    ]
                }))),
            )
            .await,
        )
        .await;
        assert_eq!(set_value["ok"], true);
        assert_eq!(set_value["data"]["succeeded"], 2);

        // `q` filters by file **path**, not by the note value — Python-compatible
        // semantics, documented at `notes_data`'s LEFT JOIN. `/tmp/a.png` is the
        // file carrying the note set above.
        let notes_value = json_body(
            notes_data(
                State(Arc::clone(&state)),
                None,
                Query(HashMap::from([("q".to_string(), "a.png".to_string())])),
            )
            .await,
        )
        .await;
        assert_eq!(notes_value["total"], 1);
        assert_eq!(notes_value["notes"][0]["value"], "first note");

        let file_value = json_body(
            get_file_annotations(
                State(Arc::clone(&state)),
                None,
                AxumPath(1),
                Query(HashMap::new()),
            )
            .await,
        )
        .await;
        assert_eq!(file_value["annotations"][0]["source"], "user");
        assert_eq!(file_value["annotations"][0]["key"], "note");

        let search_value = json_body(
            search(
                State(Arc::clone(&state)),
                None,
                Query(HashMap::from([
                    ("source".to_string(), "agent".to_string()),
                    ("min_confidence".to_string(), "0.4".to_string()),
                ])),
            )
            .await,
        )
        .await;
        assert_eq!(search_value["total"], 1);
        assert_eq!(search_value["annotations"][0]["value"], "second label");

        let delete_value = json_body(
            batch_delete(
                State(Arc::clone(&state)),
                None,
                Ok(Json(
                    json!({"source": "user", "file_ids": [1], "key": "note"}),
                )),
            )
            .await,
        )
        .await;
        assert_eq!(delete_value["data"]["deleted"], 1);

        let cleared_value = json_body(
            get_file_annotations(State(state), None, AxumPath(1), Query(HashMap::new())).await,
        )
        .await;
        assert_eq!(cleared_value["annotations"].as_array().unwrap().len(), 0);
    }

    #[tokio::test]
    async fn annotations_batch_set_rejects_empty_items_with_api_error_shape() {
        let value = json_body(
            batch_set(
                State(test_state().await),
                None,
                Ok(Json(json!({"items": []}))),
            )
            .await,
        )
        .await;

        assert_eq!(
            value,
            json!({"ok": false, "error": "items array required", "code": "batch_empty"})
        );
    }

    #[tokio::test]
    async fn annotations_post_rejects_non_object_json_with_python_error_shape() {
        let value =
            json_body(batch_set(State(test_state().await), None, Ok(Json(json!([])))).await).await;

        assert_eq!(
            value,
            json!({"ok": false, "error": "JSON object required", "code": "invalid_json"})
        );
    }
}

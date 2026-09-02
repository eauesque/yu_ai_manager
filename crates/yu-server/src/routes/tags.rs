use axum::{
    extract::{Extension, Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

#[derive(Debug, Serialize, sqlx::FromRow)]
pub struct FileTag {
    pub id: i64,
    pub tag: String,
    pub namespace: Option<String>,
    pub weight: f64,
}

#[derive(Debug, Deserialize)]
pub struct AddTagRequest {
    pub tag: String,
    pub namespace: Option<String>,
    pub weight: f64,
}

#[derive(Deserialize)]
pub struct SuggestParams {
    q: Option<String>,
    limit: Option<i64>,
}

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

fn internal_server_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(serde_json::json!({
            "error": "internal_server_error",
        })),
    )
        .into_response()
}

pub async fn list_tags(State(state): State<SharedState>, Path(file_id): Path<i64>) -> Response {
    match sqlx::query_as::<_, FileTag>(
        "SELECT t.id, t.tag, t.namespace, ft.weight
         FROM file_tags ft
         JOIN tags t ON t.id = ft.tag_id
         WHERE ft.file_id = ?
         ORDER BY t.tag",
    )
    .bind(file_id)
    .fetch_all(&state.db)
    .await
    {
        Ok(tags) => Json(tags).into_response(),
        Err(error) => internal_server_error(error, "failed to list file tags"),
    }
}

pub async fn add_tag(
    State(state): State<SharedState>,
    Path(file_id): Path<i64>,
    Json(body): Json<Value>,
) -> Response {
    let request: AddTagRequest = match serde_json::from_value(body) {
        Ok(request) => request,
        Err(error) => return internal_server_error(error, "failed to parse add tag request"),
    };

    let tag_id = match tagdb_core::db::tag::upsert_tag(
        &state.db,
        request.namespace.as_deref(),
        &request.tag,
        None,
    )
    .await
    {
        Ok(tag_id) => tag_id,
        Err(error) => return internal_server_error(error, "failed to upsert tag"),
    };

    match tagdb_core::db::tag::insert_file_tag(&state.db, file_id, tag_id, request.weight).await {
        Ok(()) => StatusCode::OK.into_response(),
        Err(error) => internal_server_error(error, "failed to insert file tag"),
    }
}

pub async fn delete_tag(
    State(state): State<SharedState>,
    Path((file_id, tag_id)): Path<(i64, i64)>,
) -> Response {
    match sqlx::query("DELETE FROM file_tags WHERE file_id = ? AND tag_id = ?")
        .bind(file_id)
        .bind(tag_id)
        .execute(&state.db)
        .await
    {
        Ok(_) => Json(json!({"ok": true})).into_response(),
        Err(error) => internal_server_error(error, "failed to delete file tag"),
    }
}

pub async fn batch_set(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(err) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return err;
    }
    let items = match body.get("items").and_then(Value::as_array) {
        Some(a) if !a.is_empty() => a.clone(),
        Some(_) | None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"ok":false,"error":"batch_empty","detail":"items array required"})),
            )
                .into_response();
        }
    };
    const BATCH_MAX: usize = 500;
    if items.len() > BATCH_MAX {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok":false,"error":"batch_too_large",
                "detail":format!("Batch size {} exceeds maximum of {}", items.len(), BATCH_MAX)})),
        )
            .into_response();
    }

    let candidate_ids: Vec<i64> = items
        .iter()
        .filter_map(|it| it.get("file_id")?.as_i64().filter(|&id| id > 0))
        .collect();

    let existing_ids: std::collections::HashSet<i64> = if candidate_ids.is_empty() {
        Default::default()
    } else {
        let ph = candidate_ids
            .iter()
            .map(|_| "?")
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!("SELECT id FROM files WHERE id IN ({ph}) AND is_deleted=0");
        let mut q = sqlx::query(&sql);
        for id in &candidate_ids {
            q = q.bind(id);
        }
        q.fetch_all(&state.db)
            .await
            .map(|rows| rows.iter().map(|r| r.get::<i64, _>("id")).collect())
            .unwrap_or_default()
    };

    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;

    let mut succeeded: usize = 0;
    let mut errors: Vec<Value> = Vec::new();

    for item in &items {
        let file_id = match item
            .get("file_id")
            .and_then(Value::as_i64)
            .filter(|&id| id > 0)
        {
            Some(id) => id,
            None => {
                errors.push(
                    json!({"file_id": item.get("file_id"), "code":"invalid_value",
                    "error":"file_id must be a positive integer"}),
                );
                continue;
            }
        };
        let add_tags = item
            .get("add")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let remove_tags = item
            .get("remove")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        if add_tags.is_empty() && remove_tags.is_empty() {
            errors.push(json!({"file_id":file_id,"code":"invalid_value",
                "error":"at least one of add or remove is required"}));
            continue;
        }
        if !existing_ids.contains(&file_id) {
            errors.push(json!({"file_id":file_id,"code":"not_found","error":"File not found"}));
            continue;
        }

        let mut ok = true;
        'add: for tag_val in &add_tags {
            let Some(key) = tag_val.as_str().map(str::trim).filter(|s| !s.is_empty()) else {
                continue;
            };
            let tag_id =
                match tagdb_core::db::tag::upsert_tag(&state.db, None, key, Some(now)).await {
                    Ok(id) => id,
                    Err(e) => {
                        tracing::error!(?e, "batch_set: upsert_tag failed");
                        ok = false;
                        break 'add;
                    }
                };
            if let Err(e) = sqlx::query(
                "INSERT INTO file_tags(file_id,tag_id,weight,source) VALUES(?,?,1.0,'user')
                 ON CONFLICT(file_id,tag_id) DO UPDATE SET weight=excluded.weight",
            )
            .bind(file_id)
            .bind(tag_id)
            .execute(&state.db)
            .await
            {
                tracing::error!(?e, "batch_set: insert_file_tag failed");
                ok = false;
                break 'add;
            }
        }
        if ok {
            for tag_val in &remove_tags {
                let Some(key) = tag_val.as_str().map(str::trim).filter(|s| !s.is_empty()) else {
                    continue;
                };
                let row: Option<i64> =
                    sqlx::query_scalar("SELECT id FROM tags WHERE tag=? AND namespace IS NULL")
                        .bind(key)
                        .fetch_optional(&state.db)
                        .await
                        .unwrap_or(None);
                if let Some(tag_id) = row {
                    let _ = sqlx::query(
                        "DELETE FROM file_tags WHERE file_id=? AND tag_id=? AND source='user'",
                    )
                    .bind(file_id)
                    .bind(tag_id)
                    .execute(&state.db)
                    .await;
                    let refs: Option<i64> =
                        sqlx::query_scalar("SELECT 1 FROM file_tags WHERE tag_id=? LIMIT 1")
                            .bind(tag_id)
                            .fetch_optional(&state.db)
                            .await
                            .unwrap_or(None);
                    if refs.is_none() {
                        let _ = sqlx::query("DELETE FROM tags WHERE id=?")
                            .bind(tag_id)
                            .execute(&state.db)
                            .await;
                    }
                }
            }
        }

        if ok {
            succeeded += 1;
        } else {
            errors
                .push(json!({"file_id":file_id,"code":"internal_error","error":"Internal error"}));
        }
    }

    Json(json!({
        "ok": true, "error": null,
        "data": {
            "total": items.len(),
            "succeeded": succeeded,
            "failed": errors.len(),
            "errors": errors,
        }
    }))
    .into_response()
}

pub async fn suggest(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<SuggestParams>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(q) = params.q.as_deref().map(str::trim).filter(|q| !q.is_empty()) else {
        return api_result(json!([]));
    };
    let limit = params.limit.unwrap_or(20).clamp(0, 100);
    let pattern = format!("%{q}%");

    match sqlx::query(
        "SELECT t.id, t.tag, t.namespace, COUNT(ft.file_id) AS file_count
         FROM tags t
         LEFT JOIN file_tags ft ON ft.tag_id = t.id
         WHERE t.tag LIKE ?
         GROUP BY t.id
         ORDER BY file_count DESC
         LIMIT ?",
    )
    .bind(pattern)
    .bind(limit)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => api_result(json!(rows
            .into_iter()
            .map(|row| json!({
                "id": row.get::<i64, _>("id"),
                "tag": row.get::<String, _>("tag"),
                "namespace": row.get::<Option<String>, _>("namespace"),
                "file_count": row.get::<i64, _>("file_count"),
            }))
            .collect::<Vec<_>>())),
        Err(error) => internal_error(error, "failed to suggest tags"),
    }
}

fn dedup_tags(tags: Vec<String>, keep_last: bool) -> Vec<String> {
    let mut seen = std::collections::HashSet::new();
    if keep_last {
        let mut out: Vec<String> = tags
            .into_iter()
            .rev()
            .filter(|t| seen.insert(t.to_lowercase()))
            .collect();
        out.reverse();
        out
    } else {
        tags.into_iter()
            .filter(|t| seen.insert(t.to_lowercase()))
            .collect()
    }
}

pub async fn dedup(Json(body): Json<Value>) -> Response {
    let keep_last = body.get("keep").and_then(Value::as_str) == Some("last");
    let tags: Vec<String> = match body.get("tags") {
        Some(Value::String(s)) => s
            .split(',')
            .map(|t| t.trim().to_string())
            .filter(|t| !t.is_empty())
            .collect(),
        Some(Value::Array(arr)) => arr
            .iter()
            .filter_map(Value::as_str)
            .map(|t| t.trim().to_string())
            .filter(|t| !t.is_empty())
            .collect(),
        _ => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"ok": false, "error": "tags is required (string or array)"})),
            )
                .into_response()
        }
    };
    let total = tags.len();
    let deduped = dedup_tags(tags, keep_last);
    let removed = total - deduped.len();
    api_result(json!({
        "tags": deduped,
        "string": deduped.join(", "),
        "removed": removed,
    }))
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
            "CREATE TABLE tags (
               id INTEGER PRIMARY KEY,
               tag TEXT NOT NULL,
               namespace TEXT,
               first_seen_mtime INTEGER,
               UNIQUE(tag, namespace)
             );
             CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL UNIQUE,
               mtime INTEGER NOT NULL,
               size INTEGER NOT NULL
             );
             CREATE TABLE file_tags (
               file_id INTEGER NOT NULL,
               tag_id INTEGER NOT NULL,
               weight REAL NOT NULL DEFAULT 1.0,
               source TEXT NOT NULL DEFAULT 'meta',
               UNIQUE(file_id, tag_id)
             );
             INSERT INTO files(id, path, mtime, size) VALUES (1, '/a.png', 100, 0);
             INSERT INTO tags(id, tag, namespace) VALUES
               (1, 'zeta', NULL),
               (2, 'alpha', 'meta'),
               (3, 'nature', NULL),
               (4, 'natural', NULL),
               (5, 'cat', NULL);
             INSERT INTO file_tags(file_id, tag_id, weight) VALUES
               (1, 1, 0.5),
               (1, 2, 1.0),
               (2, 3, 1.0),
               (3, 3, 1.0),
               (4, 4, 1.0);",
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
                    app_config: serde_json::json!({}),
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

    #[test]
    fn dedup_tags_keep_first() {
        let tags = vec!["a", "b", "A", "c", "b"]
            .into_iter()
            .map(String::from)
            .collect();
        assert_eq!(dedup_tags(tags, false), ["a", "b", "c"]);
    }

    #[test]
    fn dedup_tags_keep_last() {
        let tags = vec!["a", "b", "A", "c", "b"]
            .into_iter()
            .map(String::from)
            .collect();
        // keep last: "A" and last "b" survive
        assert_eq!(dedup_tags(tags, true), ["A", "c", "b"]);
    }

    #[tokio::test]
    async fn list_tags_returns_tags_ordered_by_tag() {
        let response = list_tags(State(test_state().await), Path(1)).await;
        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let tags: serde_json::Value = serde_json::from_slice(&body).unwrap();

        assert_eq!(tags[0]["id"], 2);
        assert_eq!(tags[0]["tag"], "alpha");
        assert_eq!(tags[0]["namespace"], "meta");
        assert_eq!(tags[0]["weight"], 1.0);
        assert_eq!(tags[1]["tag"], "zeta");
    }

    #[tokio::test]
    async fn add_tag_inserts_file_tag() {
        let state = test_state().await;
        let response = add_tag(
            State(Arc::clone(&state)),
            Path(1),
            Json(serde_json::json!({
                "tag": "new_tag",
                "namespace": null,
                "weight": 0.75
            })),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let weight: f64 = sqlx::query_scalar(
            "SELECT ft.weight
             FROM file_tags ft
             JOIN tags t ON t.id = ft.tag_id
             WHERE ft.file_id = 1 AND t.tag = 'new_tag'",
        )
        .fetch_one(&state.db)
        .await
        .unwrap();
        assert!((weight - 0.75).abs() < 1e-9);
    }

    #[tokio::test]
    async fn delete_tag_removes_file_tag() {
        let state = test_state().await;
        let response = delete_tag(State(Arc::clone(&state)), Path((1, 1))).await;
        // 200 + `{"ok": true}`, not 204 — changed deliberately in 197ba88ef for
        // parity-schema conformance; this assertion was left behind.
        assert_eq!(response.status(), StatusCode::OK);

        let count: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM file_tags WHERE file_id = 1 AND tag_id = 1")
                .fetch_one(&state.db)
                .await
                .unwrap();
        assert_eq!(count, 0);
    }

    async fn json_body(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn tags_suggest_returns_matches_sorted_by_count() {
        let response = suggest(
            State(test_state().await),
            None,
            axum::extract::Query(SuggestParams {
                q: Some("nat".to_string()),
                limit: None,
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["data"][0]["tag"], "nature");
        assert_eq!(value["data"][0]["file_count"], 2);
        assert_eq!(value["data"][1]["tag"], "natural");
        assert_eq!(value["data"][1]["file_count"], 1);
    }

    #[tokio::test]
    async fn tags_suggest_empty_q_returns_empty_list() {
        let response = suggest(
            State(test_state().await),
            None,
            axum::extract::Query(SuggestParams {
                q: Some(" ".to_string()),
                limit: Some(5),
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["data"], serde_json::json!([]));
    }

    #[tokio::test]
    async fn tags_suggest_respects_limit() {
        let response = suggest(
            State(test_state().await),
            None,
            axum::extract::Query(SuggestParams {
                q: Some("a".to_string()),
                limit: Some(1),
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["data"].as_array().unwrap().len(), 1);
    }
}

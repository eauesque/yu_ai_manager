//! Native tag read routes; Python sources: wd_tagger_tag_routes.py and tagger_servers.py.

use std::collections::HashMap;

use axum::{
    extract::{Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{Row, Sqlite, SqlitePool, Transaction};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

fn include_all_flag(raw: Option<&str>) -> bool {
    matches!(
        raw.unwrap_or("").to_lowercase().as_str(),
        "1" | "true" | "yes"
    )
}

#[cfg(test)]
fn effective_model(
    include_all: bool,
    query_model: Option<String>,
    active_model: Option<String>,
) -> Option<String> {
    if include_all {
        None
    } else {
        query_model.or(active_model)
    }
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

fn api_error(message: &str, status: StatusCode) -> Response {
    (
        status,
        Json(json!({
            "ok": false,
            "error": message,
        })),
    )
        .into_response()
}

fn api_error_code(message: &str, status: StatusCode, code: &str) -> Response {
    (
        status,
        Json(json!({
            "ok": false,
            "error": message,
            "code": code,
        })),
    )
        .into_response()
}

pub(crate) async fn active_model(pool: &SqlitePool) -> Option<String> {
    let result = sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM kv_state WHERE key = 'wd_active_model_id'",
    )
    .fetch_optional(pool)
    .await;
    match result {
        Ok(Some(Some(value))) if !value.is_empty() => Some(value),
        _ => None,
    }
}

pub(crate) async fn resolve_model_id_readonly(
    pool: &SqlitePool,
    model: &str,
) -> Result<Option<i64>, sqlx::Error> {
    sqlx::query_scalar("SELECT id FROM wd_model_dict WHERE model=?")
        .bind(model)
        .fetch_optional(pool)
        .await
}

pub(crate) async fn build_wd_tags(
    pool: &SqlitePool,
    file_id: i64,
    model: Option<String>,
    include_all: bool,
) -> Result<Vec<Value>, sqlx::Error> {
    let model = if include_all || model.as_deref() == Some("") {
        None
    } else if model.is_some() {
        model
    } else {
        active_model(pool).await
    };
    let rows = if let Some(model) = model {
        let Some(model_id) = resolve_model_id_readonly(pool, &model).await? else {
            return Ok(Vec::new());
        };
        sqlx::query(
            "SELECT td.tag_name, fwt.confidence_milli / 1000.0 AS confidence,
                    cd.category, md.model, fwt.created_at
             FROM file_wd_tags fwt
             JOIN wd_tag_dict td ON td.id = fwt.tag_id
             JOIN wd_category_dict cd ON cd.id = fwt.category_id
             JOIN wd_model_dict md ON md.id = fwt.model_id
             WHERE fwt.file_id = ? AND fwt.model_id = ?
             ORDER BY fwt.confidence_milli DESC, fwt.id",
        )
        .bind(file_id)
        .bind(model_id)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT td.tag_name, fwt.confidence_milli / 1000.0 AS confidence,
                    cd.category, md.model, fwt.created_at
             FROM file_wd_tags fwt
             JOIN wd_tag_dict td ON td.id = fwt.tag_id
             JOIN wd_category_dict cd ON cd.id = fwt.category_id
             JOIN wd_model_dict md ON md.id = fwt.model_id
             WHERE fwt.file_id = ?
             ORDER BY fwt.confidence_milli DESC, fwt.id",
        )
        .bind(file_id)
        .fetch_all(pool)
        .await?
    };
    Ok(rows
        .into_iter()
        .map(|row| {
            json!({
                "tag_name": row.get::<String, _>("tag_name"),
                "confidence": row.get::<f64, _>("confidence"),
                "category": row.get::<String, _>("category"),
                "model": row.get::<String, _>("model"),
                "created_at": row.try_get::<Option<i64>, _>("created_at").ok().flatten(),
            })
        })
        .collect())
}

async fn build_tagger_server_tags(
    pool: &SqlitePool,
    file_id: i64,
) -> Result<Vec<Value>, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT tag_name, confidence, source, created_at
         FROM file_hailo_tags WHERE file_id = ?
         ORDER BY confidence DESC, id",
    )
    .bind(file_id)
    .fetch_all(pool)
    .await?;
    Ok(rows
        .into_iter()
        .map(|row| {
            json!({
                "tag_name": row.get::<String, _>("tag_name"),
                "confidence": row.get::<f64, _>("confidence"),
                "source": row.get::<String, _>("source"),
                "created_at": row.try_get::<Option<i64>, _>("created_at").ok().flatten(),
            })
        })
        .collect())
}

pub async fn wd_tags(
    State(state): State<SharedState>,
    AxumPath(file_id): AxumPath<i64>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let include_all = include_all_flag(params.get("all").map(String::as_str));
    let model = if include_all {
        None
    } else {
        params.get("model").cloned()
    };
    match build_wd_tags(&state.db_read, file_id, model, include_all).await {
        Ok(tags) => api_result(json!({"file_id": file_id, "tags": tags})),
        Err(error) => {
            tracing::error!(?error, file_id, "wd tags read failed");
            api_error("Failed to get WD tags", StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// トランザクション内でWD tagsをDELETEする共有ヘルパー。
/// 呼出側がトランザクションの開始・commit/rollbackを制御する
/// (単一トランザクション内でDELETE+INSERTを行いたい呼出元向け)。
pub(crate) async fn delete_wd_tags_for_files_tx(
    tx: &mut Transaction<'_, Sqlite>,
    file_ids: &[i64],
    effective_model: Option<&str>,
) -> Result<(i64, i64), sqlx::Error> {
    if file_ids.is_empty() {
        return Ok((0, 0));
    }
    let model_id = if let Some(model) = effective_model {
        sqlx::query_scalar::<_, i64>("SELECT id FROM wd_model_dict WHERE model=?")
            .bind(model)
            .fetch_optional(&mut **tx)
            .await?
    } else {
        None
    };
    let mut deleted_files = 0_i64;
    let mut deleted_tags = 0_i64;
    for file_id in file_ids {
        let result = if let Some(model_id) = model_id {
            sqlx::query("DELETE FROM file_wd_tags WHERE file_id = ? AND model_id = ?")
                .bind(file_id)
                .bind(model_id)
                .execute(&mut **tx)
                .await?
        } else {
            sqlx::query("DELETE FROM file_wd_tags WHERE file_id = ?")
                .bind(file_id)
                .execute(&mut **tx)
                .await?
        };
        let rows = result.rows_affected() as i64;
        if rows > 0 {
            deleted_files += 1;
            deleted_tags += rows;
        }
    }
    Ok((deleted_files, deleted_tags))
}

pub(crate) async fn delete_wd_tags_for_files(
    pool: &SqlitePool,
    file_ids: &[i64],
    model: Option<&str>,
    use_active_when_missing: bool,
) -> Result<(i64, i64), sqlx::Error> {
    if file_ids.is_empty() {
        return Ok((0, 0));
    }
    let effective_model = if let Some(model) = model.filter(|model| !model.is_empty()) {
        Some(model.to_string())
    } else if use_active_when_missing {
        active_model(pool).await
    } else {
        None
    };
    let mut tx = pool.begin().await?;
    let result = delete_wd_tags_for_files_tx(&mut tx, file_ids, effective_model.as_deref()).await?;
    tx.commit().await?;
    Ok(result)
}

pub async fn delete_wd_tags(
    State(state): State<SharedState>,
    AxumPath(file_id): AxumPath<i64>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let model = params.get("model").map(String::as_str);
    match delete_wd_tags_for_files(&state.db, &[file_id], model, true).await {
        Ok((_, deleted)) => api_result(json!({"file_id": file_id, "deleted": deleted})),
        Err(error) => {
            tracing::error!(?error, file_id, "wd tags delete failed");
            api_error(
                "Failed to delete WD tags",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

pub async fn delete_wd_tags_batch(
    State(state): State<SharedState>,
    Json(body): Json<Value>,
) -> Response {
    let Some(file_ids_value) = body.get("file_ids") else {
        return api_error_code(
            "file_ids must be a list",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    let Some(file_ids_raw) = file_ids_value.as_array() else {
        return api_error_code(
            "file_ids must be a list",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    if file_ids_raw.len() > 500 {
        return api_error_code(
            "file_ids max 500",
            StatusCode::BAD_REQUEST,
            "batch_too_large",
        );
    }
    let file_ids = file_ids_raw
        .iter()
        .filter_map(Value::as_i64)
        .collect::<Vec<_>>();
    let model = body.get("model").and_then(Value::as_str);
    match delete_wd_tags_for_files(&state.db, &file_ids, model, false).await {
        Ok((deleted_files, deleted_tags)) => {
            api_result(json!({"deleted_files": deleted_files, "deleted_tags": deleted_tags}))
        }
        Err(error) => {
            tracing::error!(?error, "wd tags batch delete failed");
            api_error(
                "Failed to delete WD tags",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

pub async fn tagger_server_tags(
    State(state): State<SharedState>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    match build_tagger_server_tags(&state.db_read, file_id).await {
        Ok(tags) => api_result(json!({"file_id": file_id, "tags": tags})),
        Err(error) => {
            tracing::error!(?error, file_id, "tagger server tags read failed");
            api_error(
                "Failed to get tagger server tags",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

pub async fn delete_tagger_server_tags(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    match sqlx::query("DELETE FROM file_hailo_tags WHERE file_id = ?")
        .bind(file_id)
        .execute(&state.db)
        .await
    {
        Ok(r) => api_result(json!({"file_id": file_id, "deleted": r.rows_affected() as i64})),
        Err(error) => {
            tracing::error!(?error, file_id, "delete tagger server tags failed");
            api_error(
                "Failed to delete tagger server tags",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use axum::extract::{Path as AxumPath, Query, State};
    use axum::http::StatusCode;
    use axum::Json;
    use std::str::FromStr;

    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    async fn test_pool(seed: &str) -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE kv_state (key TEXT PRIMARY KEY, value TEXT);
             CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL);
             CREATE TABLE wd_category_dict (id INTEGER PRIMARY KEY, category TEXT NOT NULL);
             CREATE TABLE wd_tag_dict (id INTEGER PRIMARY KEY, tag_name TEXT NOT NULL);
             CREATE TABLE file_wd_tags (
               id INTEGER PRIMARY KEY,
               file_id INTEGER NOT NULL,
               tag_id INTEGER NOT NULL,
               category_id INTEGER NOT NULL,
               model_id INTEGER NOT NULL,
               confidence_milli INTEGER NOT NULL,
               created_at INTEGER
             );",
        )
        .execute(&pool)
        .await
        .unwrap();
        if !seed.is_empty() {
            sqlx::raw_sql(seed).execute(&pool).await.unwrap();
        }
        pool
    }

    #[test]
    fn include_all_accepts_python_truthy_values() {
        assert!(include_all_flag(Some("1")));
        assert!(include_all_flag(Some("TRUE")));
        assert!(include_all_flag(Some("yes")));
        assert!(!include_all_flag(Some("0")));
    }

    #[test]
    fn effective_model_prefers_include_all_then_query_then_active() {
        assert_eq!(
            effective_model(true, Some("query".to_string()), Some("active".to_string())),
            None
        );
        assert_eq!(
            effective_model(false, Some("query".to_string()), Some("active".to_string())),
            Some("query".to_string())
        );
        assert_eq!(
            effective_model(false, None, Some("active".to_string())),
            Some("active".to_string())
        );
    }

    #[tokio::test]
    async fn wd_tags_resolves_query_active_unknown_and_include_all_models() {
        let pool = test_pool(
            "INSERT INTO kv_state(key, value) VALUES ('wd_active_model_id', 'model-a');
             INSERT INTO wd_model_dict(id, model) VALUES (1, 'model-a'), (2, 'model-b');
             INSERT INTO wd_category_dict(id, category) VALUES (1, 'general');
             INSERT INTO wd_tag_dict(id, tag_name) VALUES (1, 'alpha'), (2, 'beta');
             INSERT INTO file_wd_tags(id, file_id, tag_id, category_id, model_id, confidence_milli, created_at) VALUES
             (1, 7, 1, 1, 1, 500, 10),
             (2, 7, 2, 1, 2, 900, 11);",
        )
        .await;

        let active = build_wd_tags(&pool, 7, None, false).await.unwrap();
        assert_eq!(active.len(), 1);
        assert_eq!(active[0]["model"], json!("model-a"));

        let queried = build_wd_tags(&pool, 7, Some("model-b".to_string()), false)
            .await
            .unwrap();
        assert_eq!(queried.len(), 1);
        assert_eq!(queried[0]["tag_name"], json!("beta"));

        let unknown = build_wd_tags(&pool, 7, Some("missing".to_string()), false)
            .await
            .unwrap();
        assert!(unknown.is_empty());

        let empty_model = build_wd_tags(&pool, 7, Some(String::new()), false)
            .await
            .unwrap();
        assert_eq!(empty_model.len(), 2);
        assert_eq!(empty_model[0]["tag_name"], json!("beta"));
        assert_eq!(empty_model[1]["tag_name"], json!("alpha"));

        let all = build_wd_tags(&pool, 7, Some("missing".to_string()), true)
            .await
            .unwrap();
        assert_eq!(all.len(), 2);
        assert_eq!(all[0]["tag_name"], json!("beta"));
        assert_eq!(all[1]["tag_name"], json!("alpha"));
    }

    #[tokio::test]
    async fn delete_wd_tags_removes_active_model_tags_and_returns_count() {
        let pool = test_pool(
            "INSERT INTO kv_state(key, value) VALUES ('wd_active_model_id', 'model-a');
             INSERT INTO wd_model_dict(id, model) VALUES (1, 'model-a'), (2, 'model-b');
             INSERT INTO wd_category_dict(id, category) VALUES (1, 'general');
             INSERT INTO wd_tag_dict(id, tag_name) VALUES (1, 'alpha'), (2, 'beta');
             INSERT INTO file_wd_tags(id, file_id, tag_id, category_id, model_id, confidence_milli, created_at) VALUES
             (1, 7, 1, 1, 1, 500, 10),
             (2, 7, 2, 1, 2, 900, 11);",
        )
        .await;
        let state = std::sync::Arc::new(
            crate::state::AppState::new(
                crate::state::Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: std::collections::HashSet::new(),
                    trusted_peer_ips: std::collections::HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: std::path::PathBuf::from("config.json"),
                    project_root: std::path::PathBuf::from("."),
                    app_config: json!({}),
                    cache_dir: std::path::PathBuf::from("."),
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
                pool.clone(),
                std::sync::Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        );

        let response = delete_wd_tags(State(state), AxumPath(7), Query(HashMap::new())).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let value: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(value["file_id"], json!(7));
        assert_eq!(value["deleted"], json!(1));

        let remaining = build_wd_tags(&pool, 7, None, true).await.unwrap();
        assert_eq!(remaining.len(), 1);
        assert_eq!(remaining[0]["model"], json!("model-b"));
    }

    #[tokio::test]
    async fn delete_wd_tags_batch_rejects_large_batches_and_deletes_transactionally() {
        let pool = test_pool(
            "INSERT INTO wd_model_dict(id, model) VALUES (1, 'model-a');
             INSERT INTO wd_category_dict(id, category) VALUES (1, 'general');
             INSERT INTO wd_tag_dict(id, tag_name) VALUES (1, 'alpha');
             INSERT INTO file_wd_tags(id, file_id, tag_id, category_id, model_id, confidence_milli, created_at) VALUES
             (1, 7, 1, 1, 1, 500, 10),
             (2, 8, 1, 1, 1, 900, 11);",
        )
        .await;
        let state = std::sync::Arc::new(
            crate::state::AppState::new(
                crate::state::Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: std::collections::HashSet::new(),
                    trusted_peer_ips: std::collections::HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: std::path::PathBuf::from("config.json"),
                    project_root: std::path::PathBuf::from("."),
                    app_config: json!({}),
                    cache_dir: std::path::PathBuf::from("."),
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
                pool.clone(),
                std::sync::Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        );

        let too_large = delete_wd_tags_batch(
            State(std::sync::Arc::clone(&state)),
            Json(json!({"file_ids": (0..501).collect::<Vec<i64>>()})),
        )
        .await;
        assert_eq!(too_large.status(), StatusCode::BAD_REQUEST);

        let response = delete_wd_tags_batch(
            State(state),
            Json(json!({"file_ids": [7, 8], "model": "model-a"})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let value: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(value["deleted_files"], json!(2));
        assert_eq!(value["deleted_tags"], json!(2));
    }
}

use axum::{
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

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

pub async fn enabled() -> Response {
    api_result(
        json!({"enabled": std::env::var("YU_DEBUG_MODE").unwrap_or_else(|_| "0".to_string()) == "1"}),
    )
}

fn api_error(message: &str, code: &str, status: StatusCode) -> Response {
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

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn preview_text(raw: Option<String>) -> String {
    raw.unwrap_or_default().chars().take(200).collect()
}

async fn build_model_check(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    let with_model: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM templates WHERE model_name IS NOT NULL AND model_name != ''",
    )
    .fetch_one(pool)
    .await?;
    let total: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM templates")
        .fetch_one(pool)
        .await?;
    let samples_with = sqlx::query(
        "SELECT file_id, model_name, model_hash, format
         FROM templates
         WHERE model_name IS NOT NULL AND model_name != ''
         ORDER BY file_id
         LIMIT 10",
    )
    .fetch_all(pool)
    .await?;
    let samples_without = sqlx::query(
        "SELECT file_id, model_name, format, raw_meta_json
         FROM templates
         WHERE (model_name IS NULL OR model_name = '')
         ORDER BY file_id
         LIMIT 5",
    )
    .fetch_all(pool)
    .await?;

    Ok(json!({
        "total_templates": total,
        "with_model_name": with_model,
        "without_model_name": total - with_model,
        "samples_with_model": samples_with.into_iter().map(|row| json!({
            "file_id": row.get::<i64, _>("file_id"),
            "model_name": row.try_get::<Option<String>, _>("model_name").ok().flatten(),
            "model_hash": row.try_get::<Option<String>, _>("model_hash").ok().flatten(),
            "format": row.try_get::<Option<String>, _>("format").ok().flatten(),
        })).collect::<Vec<_>>(),
        "samples_without_model": samples_without.into_iter().map(|row| json!({
            "file_id": row.get::<i64, _>("file_id"),
            "model_name": row.try_get::<Option<String>, _>("model_name").ok().flatten(),
            "format": row.try_get::<Option<String>, _>("format").ok().flatten(),
            "raw_meta_json_preview": preview_text(row.try_get::<Option<String>, _>("raw_meta_json").ok().flatten()),
        })).collect::<Vec<_>>(),
    }))
}

/// GET /api/debug/file-meta/{file_id}
pub async fn file_meta(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
) -> Response {
    if let Some(resp) = admin_scope_error(&state, auth_context.as_ref()) {
        return resp;
    }
    let row = sqlx::query(
        "SELECT f.id, f.path, f.meta_source, f.parser_version, \
         tm.raw_prompt, tm.raw_negative, tm.raw_meta_json, tm.model_name, tm.format \
         FROM files f LEFT JOIN templates tm ON f.id=tm.file_id \
         WHERE f.id=?",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await;

    match row {
        Err(e) => {
            tracing::error!(?e, "file_meta query failed");
            api_error("DB error", "db_error", StatusCode::INTERNAL_SERVER_ERROR)
        }
        Ok(None) => api_error("file not found", "file_not_found", StatusCode::NOT_FOUND),
        Ok(Some(row)) => {
            let raw_prompt: Option<String> = row.try_get("raw_prompt").ok().flatten();
            let raw_negative: Option<String> = row.try_get("raw_negative").ok().flatten();
            let raw_meta: Option<String> = row.try_get("raw_meta_json").ok().flatten();
            let raw_meta_ref = raw_meta.as_deref().unwrap_or("");
            api_result(json!({
                "id": row.get::<i64, _>("id"),
                "path": row.try_get::<Option<String>, _>("path").ok().flatten(),
                "meta_source": row.try_get::<Option<String>, _>("meta_source").ok().flatten(),
                "parser_version": row.try_get::<Option<i64>, _>("parser_version").ok().flatten(),
                "format": row.try_get::<Option<String>, _>("format").ok().flatten(),
                "model_name": row.try_get::<Option<String>, _>("model_name").ok().flatten(),
                "raw_prompt_length": raw_prompt.as_deref().unwrap_or("").len(),
                "raw_prompt_preview": &raw_prompt.as_deref().unwrap_or("")[..raw_prompt.as_deref().unwrap_or("").len().min(300)],
                "raw_negative_preview": &raw_negative.as_deref().unwrap_or("")[..raw_negative.as_deref().unwrap_or("").len().min(300)],
                "raw_meta_json_length": raw_meta_ref.len(),
                "raw_meta_json_preview": &raw_meta_ref[..raw_meta_ref.len().min(500)],
                "has_v4_prompt": raw_meta_ref.contains("v4_prompt"),
                "has_comment": raw_meta_ref.contains("Comment"),
            }))
        }
    }
}

pub async fn model_check(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_model_check(&state.db_read).await {
        Ok(value) => api_result(value),
        Err(error) => {
            tracing::error!(?error, "model check failed");
            api_error(
                "Failed to check model metadata",
                "model_check_failed",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    async fn test_state(seed: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE templates (
               file_id INTEGER,
               model_name TEXT,
               model_hash TEXT,
               format TEXT,
               raw_meta_json TEXT
             );",
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

    #[tokio::test]
    async fn enabled_reads_environment_flag() {
        std::env::set_var("YU_DEBUG_MODE", "1");
        let value = json_body(enabled().await).await;
        std::env::remove_var("YU_DEBUG_MODE");
        assert_eq!(value["enabled"], true);
    }

    #[tokio::test]
    async fn model_check_returns_counts_samples_and_char_safe_preview() {
        let long_preview = format!("{}tail", "あ".repeat(201));
        let state = test_state(&format!(
            "INSERT INTO templates(file_id, model_name, model_hash, format, raw_meta_json) VALUES
               (2, 'Model B', 'hash-b', 'fmt-b', NULL),
               (1, 'Model A', 'hash-a', 'fmt-a', NULL),
               (4, '', NULL, 'fmt-empty', '{long_preview}'),
               (3, NULL, NULL, 'fmt-null', NULL);"
        ))
        .await;

        let value = json_body(model_check(State(state), None).await).await;

        assert_eq!(value["total_templates"], 4);
        assert_eq!(value["with_model_name"], 2);
        assert_eq!(value["without_model_name"], 2);
        assert_eq!(value["samples_with_model"][0]["file_id"], 1);
        assert_eq!(value["samples_with_model"][1]["file_id"], 2);
        assert_eq!(value["samples_without_model"][0]["file_id"], 3);
        assert_eq!(
            value["samples_without_model"][1]["raw_meta_json_preview"],
            "あ".repeat(200)
        );
    }
}

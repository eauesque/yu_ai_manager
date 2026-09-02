use std::fs;

use axum::{
    extract::{Extension, State},
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

fn parse_page_size(value: &str) -> Result<i64, std::num::ParseIntError> {
    value.parse::<i64>()
}

async fn page_size(pool: &SqlitePool) -> Result<i64, sqlx::Error> {
    match sqlx::query_scalar::<_, i64>("PRAGMA page_size")
        .fetch_one(pool)
        .await
    {
        Ok(value) => Ok(value),
        Err(sqlx::Error::ColumnDecode { .. }) => {
            // SQLCipher's page_size pragma hook returns TEXT.
            let raw: String = sqlx::query_scalar("PRAGMA page_size")
                .fetch_one(pool)
                .await?;
            parse_page_size(&raw).map_err(|error| sqlx::Error::Decode(Box::new(error)))
        }
        Err(error) => Err(error),
    }
}

pub async fn db_stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let stats = async {
        let page_count: i64 = sqlx::query_scalar("PRAGMA page_count")
            .fetch_one(&state.db_read)
            .await?;
        let freelist_count: i64 = sqlx::query_scalar("PRAGMA freelist_count")
            .fetch_one(&state.db_read)
            .await?;
        let page_size = page_size(&state.db_read).await?;
        let free_ratio = if page_count == 0 {
            0.0
        } else {
            ((freelist_count as f64 / page_count as f64) * 10000.0).round() / 10000.0
        };
        let size_mb = fs::metadata(&state.config.db_path)
            .map(|metadata| ((metadata.len() as f64 / (1024.0 * 1024.0)) * 100.0).round() / 100.0)
            .unwrap_or(0.0);
        Ok::<_, sqlx::Error>(json!({
            "page_count": page_count,
            "freelist_count": freelist_count,
            "page_size": page_size,
            "free_ratio": free_ratio,
            "size_mb": size_mb,
        }))
    }
    .await;
    match stats {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "failed to build DB stats"),
    }
}

pub async fn scan_error_stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match sqlx::query(
        "SELECT error_type, COUNT(*) as c FROM scan_errors WHERE resolved=0
         GROUP BY error_type ORDER BY c DESC LIMIT 10",
    )
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => api_result(json!({
            "errors": rows.into_iter().map(|row| json!({
                "error_type": row.get::<String, _>(0),
                "count": row.get::<i64, _>(1),
            })).collect::<Vec<_>>()
        })),
        Err(error) => internal_error(error, "failed to build scan error stats"),
    }
}

pub async fn vacuum(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let result = async {
        let size_before = fs::metadata(&state.config.db_path)
            .map(|m| m.len())
            .unwrap_or(0);
        sqlx::query("VACUUM").execute(&state.db).await?;
        let size_after = fs::metadata(&state.config.db_path)
            .map(|m| m.len())
            .unwrap_or(0);
        let to_mb = |b: u64| ((b as f64 / (1024.0 * 1024.0)) * 100.0).round() / 100.0;
        Ok::<_, sqlx::Error>(json!({
            "size_before_mb": to_mb(size_before),
            "size_after_mb": to_mb(size_after),
            "saved_mb": to_mb(size_before.saturating_sub(size_after)),
        }))
    }
    .await;
    match result {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "VACUUM failed"),
    }
}

pub async fn analyze(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match sqlx::query("ANALYZE").execute(&state.db).await {
        Ok(_) => api_result(json!({"message": "ANALYZE complete"})),
        Err(error) => internal_error(error, "ANALYZE failed"),
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
            "CREATE TABLE scan_errors (
               error_type TEXT NOT NULL,
               resolved INTEGER NOT NULL DEFAULT 0
             );
             INSERT INTO scan_errors(error_type, resolved) VALUES
               ('decode', 0), ('decode', 0), ('io', 0), ('old', 1);",
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
    async fn db_stats_reports_pragma_shape() {
        let response = db_stats(State(test_state().await), None).await;
        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert!(value["page_count"].as_i64().unwrap() > 0);
        assert!(value["page_size"].as_i64().unwrap() > 0);
        assert_eq!(value["free_ratio"], 0.0);
    }

    #[test]
    fn parse_page_size_accepts_sqlcipher_text_pragma() {
        assert_eq!(parse_page_size("4096").unwrap(), 4096);
    }

    #[test]
    fn parse_page_size_rejects_non_numeric_text() {
        assert!(parse_page_size("not-a-number").is_err());
    }

    #[tokio::test]
    async fn scan_error_stats_groups_open_errors() {
        let response = scan_error_stats(State(test_state().await), None).await;
        let value = json_body(response).await;
        assert_eq!(
            value["errors"],
            json!([
                {"error_type": "decode", "count": 2},
                {"error_type": "io", "count": 1}
            ])
        );
    }
}

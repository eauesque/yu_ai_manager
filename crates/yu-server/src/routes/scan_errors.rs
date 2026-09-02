//! Native GET /api/scan-errors; Python source: routes/scan.py and core/scan_core/scan_errors.py.

use std::collections::HashMap;

use axum::{
    extract::{Extension, Path, Query, State},
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

fn parse_encodings(raw: Option<String>) -> serde_json::Value {
    raw.and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .filter(Value::is_array)
        .unwrap_or_else(|| json!([]))
}

fn clamp_scan_error_limit(limit: i64) -> i64 {
    if (1..=1000).contains(&limit) {
        limit
    } else {
        200
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

async fn table_exists(db: &SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

async fn build_scan_errors(
    pool: &SqlitePool,
    error_type: Option<&str>,
    resolved: Option<i64>,
    limit: i64,
) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "scan_errors").await? {
        return Ok(json!({"errors": [], "total_unresolved": 0}));
    }
    let mut clauses = Vec::new();
    if error_type.is_some() {
        clauses.push("error_type = ?");
    }
    if resolved.is_some() {
        clauses.push("resolved = ?");
    }
    let where_sql = if clauses.is_empty() {
        String::new()
    } else {
        format!(" WHERE {}", clauses.join(" AND "))
    };
    let sql = format!(
        "SELECT id, path, error_type, error_detail, encodings_tried, created_at, resolved
         FROM scan_errors{where_sql} ORDER BY created_at DESC, id DESC LIMIT ?"
    );
    let mut query = sqlx::query(&sql);
    if let Some(error_type) = error_type {
        query = query.bind(error_type);
    }
    if let Some(resolved) = resolved {
        query = query.bind(resolved);
    }
    query = query.bind(limit);
    let rows = query.fetch_all(pool).await?;
    let errors = rows
        .into_iter()
        .map(|row| {
            json!({
                "id": row.get::<i64, _>("id"),
                "path": row.get::<String, _>("path"),
                "error_type": row.get::<String, _>("error_type"),
                "error_detail": row.try_get::<Option<String>, _>("error_detail").ok().flatten(),
                "encodings_tried": parse_encodings(row.try_get::<Option<String>, _>("encodings_tried").ok().flatten()),
                "created_at": row.get::<String, _>("created_at"),
                "resolved": row.get::<i64, _>("resolved"),
            })
        })
        .collect::<Vec<_>>();
    let unresolved_count: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM scan_errors WHERE resolved=0")
            .fetch_one(pool)
            .await?;
    Ok(json!({
        "errors": errors,
        "total": errors.len(),
        "unresolved_count": unresolved_count,
    }))
}

pub async fn list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let error_type = params
        .get("error_type")
        .map(String::as_str)
        .filter(|value| !value.is_empty());
    let resolved = match params.get("resolved").map(String::as_str) {
        Some("true") => Some(1),
        Some("false") => Some(0),
        _ => None,
    };
    let limit_raw = params.get("limit").map(String::as_str).unwrap_or("200");
    let limit = match limit_raw.parse::<i64>() {
        Ok(value) => clamp_scan_error_limit(value),
        Err(error) => {
            tracing::error!(?error, "scan errors limit parse failed");
            // Python raises before api_result for this edge case; goldens only cover valid limits.
            return api_error(
                "Failed to list scan errors",
                "internal_error",
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    };
    match build_scan_errors(&state.db_read, error_type, resolved, limit).await {
        Ok(value) => api_result(value),
        Err(error) => {
            tracing::error!(?error, "scan errors list failed");
            api_error(
                "Failed to list scan errors",
                "internal_error",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

pub async fn resolve_scan_error(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(error_id): Path<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if error_id < 1 {
        return api_error("Invalid error_id", "invalid_id", StatusCode::BAD_REQUEST);
    }
    match sqlx::query("UPDATE scan_errors SET resolved=1 WHERE id=? AND resolved=0")
        .bind(error_id)
        .execute(&state.db)
        .await
    {
        Ok(result) if result.rows_affected() > 0 => {
            api_result(json!({"resolved": true, "id": error_id}))
        }
        Ok(_) => api_error(
            "Error not found or already resolved",
            "not_found",
            StatusCode::NOT_FOUND,
        ),
        Err(error) => {
            tracing::error!(?error, "resolve_scan_error failed");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "internal_server_error"})),
            )
                .into_response()
        }
    }
}

pub async fn clear_resolved_scan_errors(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match sqlx::query("DELETE FROM scan_errors WHERE resolved=1")
        .execute(&state.db)
        .await
    {
        Ok(result) => api_result(json!({"deleted": result.rows_affected()})),
        Err(error) => {
            tracing::error!(?error, "clear_resolved_scan_errors failed");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "internal_server_error"})),
            )
                .into_response()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use axum::extract::Path;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_pool(seed: &str) -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE scan_errors (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL,
               error_type TEXT NOT NULL,
               error_detail TEXT,
               encodings_tried TEXT,
               created_at TEXT NOT NULL,
               resolved INTEGER NOT NULL
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

    async fn test_state(seed: &str) -> SharedState {
        let pool = test_pool(seed).await;
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

    #[test]
    fn clamps_invalid_limits_to_python_default() {
        assert_eq!(clamp_scan_error_limit(0), 200);
        assert_eq!(clamp_scan_error_limit(1001), 200);
        assert_eq!(clamp_scan_error_limit(1000), 1000);
    }

    #[test]
    fn parses_encodings_tried_json_arrays_only() {
        assert_eq!(
            parse_encodings(Some(r#"["utf-8","cp932"]"#.to_string())),
            json!(["utf-8", "cp932"])
        );
        assert_eq!(parse_encodings(Some("not-json".to_string())), json!([]));
        assert_eq!(parse_encodings(Some(r#"{"x":1}"#.to_string())), json!([]));
    }

    #[tokio::test]
    async fn scan_errors_filters_clamps_and_orders_ties() {
        let pool = test_pool(
            "INSERT INTO scan_errors(id, path, error_type, error_detail, encodings_tried, created_at, resolved) VALUES
             (1, '/a', 'encoding', 'a', '[\"utf-8\"]', '2026-01-01T00:00:00', 0),
             (2, '/b', 'encoding', 'b', 'bad-json', '2026-01-01T00:00:00', 0),
             (3, '/c', 'timeout', 'c', '[\"cp932\"]', '2025-01-01T00:00:00', 1);",
        )
        .await;
        let payload = build_scan_errors(
            &pool,
            Some("encoding"),
            Some(0),
            clamp_scan_error_limit(5000),
        )
        .await
        .unwrap();
        assert_eq!(payload["unresolved_count"], json!(2));
        assert_eq!(payload["total"], json!(2));
        assert_eq!(payload["errors"][0]["id"], json!(2));
        assert_eq!(payload["errors"][0]["encodings_tried"], json!([]));
        assert_eq!(payload["errors"][1]["id"], json!(1));
        assert_eq!(payload["errors"][1]["encodings_tried"], json!(["utf-8"]));
    }

    #[tokio::test]
    async fn scan_errors_preserves_null_error_detail() {
        let pool = test_pool(
            "INSERT INTO scan_errors(id, path, error_type, error_detail, encodings_tried, created_at, resolved) VALUES
             (1, '/a', 'encoding', NULL, '[]', '2026-01-01T00:00:00', 0);",
        )
        .await;
        let payload = build_scan_errors(&pool, None, None, 200).await.unwrap();
        assert_eq!(payload["errors"][0]["error_detail"], Value::Null);
    }

    #[tokio::test]
    async fn resolve_sets_resolved_flag() {
        let state = test_state(
            "INSERT INTO scan_errors(id, path, error_type, error_detail, encodings_tried, created_at, resolved) VALUES
             (7, '/a', 'encoding', NULL, '[]', '2026-01-01T00:00:00', 0);",
        )
        .await;
        let value = json_body(resolve_scan_error(State(state.clone()), None, Path(7)).await).await;

        assert_eq!(value["resolved"], json!(true));
        assert_eq!(value["id"], json!(7));
        let resolved: i64 = sqlx::query_scalar("SELECT resolved FROM scan_errors WHERE id=7")
            .fetch_one(&state.db)
            .await
            .unwrap();
        assert_eq!(resolved, 1);
    }

    #[tokio::test]
    async fn resolve_returns_404_for_already_resolved() {
        let state = test_state(
            "INSERT INTO scan_errors(id, path, error_type, error_detail, encodings_tried, created_at, resolved) VALUES
             (1, '/a', 'encoding', NULL, '[]', '2026-01-01T00:00:00', 1);",
        )
        .await;
        let response = resolve_scan_error(State(state), None, Path(1)).await;

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(json_body(response).await["code"], json!("not_found"));
    }

    #[tokio::test]
    async fn resolve_returns_400_for_invalid_id() {
        let state = test_state("").await;
        let response = resolve_scan_error(State(state), None, Path(0)).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(response).await["code"], json!("invalid_id"));
    }

    #[tokio::test]
    async fn clear_deletes_resolved_rows() {
        let state = test_state(
            "INSERT INTO scan_errors(id, path, error_type, error_detail, encodings_tried, created_at, resolved) VALUES
             (1, '/a', 'encoding', NULL, '[]', '2026-01-01T00:00:00', 1),
             (2, '/b', 'encoding', NULL, '[]', '2026-01-01T00:00:01', 1),
             (3, '/c', 'encoding', NULL, '[]', '2026-01-01T00:00:02', 0);",
        )
        .await;
        let value = json_body(clear_resolved_scan_errors(State(state.clone()), None).await).await;

        assert_eq!(value["deleted"], json!(2));
        let remaining: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM scan_errors")
            .fetch_one(&state.db)
            .await
            .unwrap();
        assert_eq!(remaining, 1);
    }
}

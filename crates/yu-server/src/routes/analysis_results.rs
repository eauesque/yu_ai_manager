use axum::{
    extract::{Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{sqlite::SqliteValueRef, Decode, Row, Sqlite, SqlitePool, Value as SqlxValue, ValueRef};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

pub(crate) const ZSTD_MAGIC: &[u8; 4] = b"\x28\xb5\x2f\xfd";

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

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

pub(crate) fn decompress_blob(value: SqliteValueRef<'_>) -> Result<Value, sqlx::Error> {
    if value.is_null() {
        return Ok(Value::Null);
    }
    let owned = value.to_owned();
    if let Ok(text) = <String as Decode<Sqlite>>::decode(owned.as_ref()) {
        return Ok(Value::String(text.to_string()));
    }
    let bytes = <Vec<u8> as Decode<Sqlite>>::decode(owned.as_ref()).map_err(sqlx::Error::Decode)?;
    if bytes.starts_with(ZSTD_MAGIC) {
        let decoded = zstd_decompress(&bytes)?;
        return Ok(Value::String(decoded));
    }
    Ok(Value::String(String::from_utf8_lossy(&bytes).into_owned()))
}

pub(crate) fn zstd_decompress(bytes: &[u8]) -> Result<String, sqlx::Error> {
    let out = zstd::stream::decode_all(bytes).map_err(|err| sqlx::Error::Decode(err.into()))?;
    Ok(String::from_utf8_lossy(&out).into_owned())
}

#[cfg(test)]
fn zstd_compress_for_test(text: &str) -> Vec<u8> {
    zstd::stream::encode_all(text.as_bytes(), 3).expect("zstd test fixture compression")
}

fn parse_json_array(raw: Option<String>) -> Value {
    raw.and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .filter(Value::is_array)
        .unwrap_or_else(|| json!([]))
}

async fn build_analysis_result(pool: &SqlitePool, file_id: i64) -> Result<Value, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT file_id, engine, analyzed_at, tags_json, quality_score, quality_notes, description,
                style, composition, mood, color_palette_json, prompt_suggestion
         FROM analysis
         WHERE file_id=?
         ORDER BY analyzed_at DESC, engine ASC",
    )
    .bind(file_id)
    .fetch_all(pool)
    .await?;
    if rows.is_empty() {
        return Ok(json!({"found": false}));
    }
    let mut results = Vec::with_capacity(rows.len());
    for row in rows {
        results.push(json!({
            "file_id": row.get::<i64, _>("file_id"),
            "engine": row.get::<String, _>("engine"),
            "analyzed_at": row.get::<i64, _>("analyzed_at"),
            "tags": parse_json_array(row.try_get::<Option<String>, _>("tags_json").ok().flatten()),
            "quality_score": row.try_get::<Option<f64>, _>("quality_score").ok().flatten(),
            "quality_notes": decompress_blob(row.try_get_raw("quality_notes")?)?,
            "description": row.try_get::<Option<String>, _>("description").ok().flatten().unwrap_or_default(),
            "style": row.try_get::<Option<String>, _>("style").ok().flatten(),
            "composition": row.try_get::<Option<String>, _>("composition").ok().flatten(),
            "mood": row.try_get::<Option<String>, _>("mood").ok().flatten(),
            "color_palette": parse_json_array(row.try_get::<Option<String>, _>("color_palette_json").ok().flatten()),
            "prompt_suggestion": decompress_blob(row.try_get_raw("prompt_suggestion")?)?,
        }));
    }
    Ok(json!({"found": true, "result": results[0], "results": results}))
}

async fn build_analysis_stats(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    let total_analyzed: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM analysis")
        .fetch_one(pool)
        .await?;
    let total_files: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM files WHERE is_deleted=0")
        .fetch_one(pool)
        .await?;
    let style_rows = sqlx::query(
        "SELECT style, COUNT(*) as cnt FROM analysis
         WHERE style IS NOT NULL AND style != ''
         GROUP BY style ORDER BY cnt DESC, style ASC LIMIT 10",
    )
    .fetch_all(pool)
    .await?;
    let quality_rows = sqlx::query(
        "SELECT
             CASE
                 WHEN quality_score >= 8 THEN 'excellent'
                 WHEN quality_score >= 6 THEN 'good'
                 WHEN quality_score >= 4 THEN 'average'
                 ELSE 'low'
             END as tier,
             COUNT(*) as cnt,
             ROUND(AVG(quality_score), 1) as avg_score
         FROM analysis
         WHERE quality_score > 0
         GROUP BY tier
         ORDER BY tier",
    )
    .fetch_all(pool)
    .await?;
    Ok(json!({
        "total_analyzed": total_analyzed,
        "total_files": total_files,
        "styles": style_rows.into_iter().map(|row| json!({
            "style": row.get::<String, _>(0),
            "count": row.get::<i64, _>(1),
        })).collect::<Vec<_>>(),
        "quality_distribution": quality_rows.into_iter().map(|row| json!({
            "tier": row.get::<String, _>(0),
            "count": row.get::<i64, _>(1),
            "avg_score": row.get::<f64, _>(2),
        })).collect::<Vec<_>>(),
    }))
}

pub async fn result(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_analysis_result(&state.db_read, file_id).await {
        Ok(value) => api_result(value),
        Err(error) => {
            tracing::error!(?error, file_id, "analysis.result error");
            api_error(
                "Failed to get analysis result",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

pub async fn stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let fallback = json!({
        "total_analyzed": 0,
        "total_files": 0,
        "styles": [],
        "quality_distribution": [],
    });
    api_result(
        build_analysis_stats(&state.db_read)
            .await
            .unwrap_or(fallback),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_state(schema: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        if !schema.is_empty() {
            sqlx::raw_sql(schema).execute(&pool).await.unwrap();
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

    fn analysis_schema() -> &'static str {
        "CREATE TABLE files(id INTEGER PRIMARY KEY, is_deleted INTEGER NOT NULL DEFAULT 0);
         CREATE TABLE analysis (
           id INTEGER PRIMARY KEY,
           file_id INTEGER NOT NULL,
           engine TEXT NOT NULL,
           analyzed_at INTEGER NOT NULL,
           tags_json TEXT,
           quality_score REAL,
           quality_notes BLOB,
           description TEXT,
           style TEXT,
           composition TEXT,
           mood TEXT,
           color_palette_json TEXT,
           prompt_suggestion BLOB,
           raw_response BLOB
         );"
    }

    #[tokio::test]
    async fn analysis_result_empty_returns_found_false() {
        let state = test_state(analysis_schema()).await;

        let value = json_body(result(State(state), None, AxumPath(1)).await).await;

        assert_eq!(value["found"], false);
    }

    #[tokio::test]
    async fn analysis_result_decodes_text_blob_zstd_and_tiebreaks() {
        let state = test_state(analysis_schema()).await;
        let zstd_notes = zstd_compress_for_test("compressed notes");
        sqlx::query(
            "INSERT INTO analysis(file_id, engine, analyzed_at, tags_json, quality_score, quality_notes,
             description, style, composition, mood, color_palette_json, prompt_suggestion, raw_response)
             VALUES(1, 'b-engine', 100, '[\"b\"]', 7.5, ?, NULL, 'anime', 'center', 'calm',
                    '[\"red\"]', 'legacy prompt', X'00'),
                   (1, 'a-engine', 100, '[\"a\"]', 8.5, 'legacy notes', 'desc', 'anime', NULL, NULL,
                    '[\"blue\"]', ?, X'00')",
        )
        .bind(&zstd_notes)
        .bind(&zstd_notes)
        .execute(&state.db)
        .await
        .unwrap();

        let value = json_body(result(State(state), None, AxumPath(1)).await).await;

        assert_eq!(value["found"], true);
        assert_eq!(value["result"]["engine"], "a-engine");
        assert_eq!(value["result"]["quality_notes"], "legacy notes");
        assert_eq!(value["result"]["prompt_suggestion"], "compressed notes");
        assert_eq!(value["results"][1]["description"], "");
        assert_eq!(value["results"][1]["quality_notes"], "compressed notes");
        assert_eq!(value["results"][1]["prompt_suggestion"], "legacy prompt");
    }

    #[tokio::test]
    async fn analysis_stats_returns_seeded_counts_and_ordering() {
        let state = test_state(&format!(
            "{}{}",
            analysis_schema(),
            "INSERT INTO files(id, is_deleted) VALUES(1,0),(2,0),(3,1);
             INSERT INTO analysis(file_id, engine, analyzed_at, style, quality_score) VALUES
               (1, 'a', 1, 'z', 8.0),
               (1, 'b', 2, 'a', 6.0),
               (2, 'c', 3, 'a', 3.0),
               (2, 'd', 4, 'z', 4.0);"
        ))
        .await;

        let value = json_body(stats(State(state), None).await).await;

        assert_eq!(value["total_analyzed"], 4);
        assert_eq!(value["total_files"], 2);
        assert_eq!(
            value["styles"],
            json!([{"style": "a", "count": 2}, {"style": "z", "count": 2}])
        );
        assert_eq!(value["quality_distribution"][0]["tier"], "average");
        assert_eq!(value["quality_distribution"][1]["tier"], "excellent");
        assert_eq!(value["quality_distribution"][2]["tier"], "good");
        assert_eq!(value["quality_distribution"][3]["tier"], "low");
    }

    #[tokio::test]
    async fn analysis_stats_returns_zero_fallback_on_missing_tables() {
        let value = json_body(stats(State(test_state("").await), None).await).await;

        assert_eq!(
            value,
            json!({
                "ok": true,
                "error": null,
                "data": null,
                "total_analyzed": 0,
                "total_files": 0,
                "styles": [],
                "quality_distribution": [],
            })
        );
    }
}

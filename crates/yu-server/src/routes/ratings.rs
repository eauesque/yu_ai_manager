#![allow(clippy::result_large_err)]

use std::collections::{HashMap, HashSet};

use axum::{
    extract::{rejection::JsonRejection, Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

#[derive(Deserialize)]
struct SetRatingRequest {
    file_id: i64,
    rating: i64,
}

#[derive(Deserialize)]
struct BatchRequest {
    file_ids: Vec<i64>,
}

#[derive(Deserialize)]
struct BatchSetItem {
    file_id: i64,
    rating: i64,
}

#[derive(Deserialize)]
struct BatchSetRequest {
    items: Vec<BatchSetItem>,
}

pub async fn ratings_get(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let Some(raw_file_id) = params.get("file_id") else {
        return api_validation_error("file_id: Field required");
    };
    let Ok(file_id) = raw_file_id.parse::<i64>() else {
        return api_validation_error(
            "file_id: Input should be a valid integer, unable to parse string as an integer",
        );
    };
    if file_id <= 0 {
        return api_validation_error("file_id: Input should be greater than 0");
    }

    match sqlx::query_scalar::<_, Option<i64>>("SELECT rating FROM file_ratings WHERE file_id=?")
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
    {
        Ok(rating) => {
            api_result(json!({"file_id": file_id, "rating": rating.flatten().unwrap_or(0)}))
        }
        Err(error) => internal_error(error, "failed to get rating"),
    }
}

pub async fn ratings_stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    match sqlx::query(
        "SELECT rating, COUNT(*) AS count FROM file_ratings GROUP BY rating ORDER BY rating",
    )
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => {
            let mut distribution = serde_json::Map::new();
            let mut total = 0_i64;
            for row in rows {
                let rating: i64 = row.get(0);
                let count: i64 = row.get(1);
                total += count;
                distribution.insert(rating.to_string(), json!(count));
            }
            api_result(json!({"total_rated": total, "distribution": distribution}))
        }
        Err(error) => internal_error(error, "failed to get rating stats"),
    }
}

pub async fn ratings_set(
    State(state): State<SharedState>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    let request = match parse_set_rating_request(body) {
        Ok(request) => request,
        Err(response) => return response,
    };

    let result = if request.rating == 0 {
        sqlx::query("DELETE FROM file_ratings WHERE file_id=?")
            .bind(request.file_id)
            .execute(&state.db)
            .await
    } else {
        sqlx::query(
            "INSERT INTO file_ratings (file_id, rating, rated_at, updated_at)
             VALUES (?, ?, unixepoch(), unixepoch())
             ON CONFLICT(file_id) DO UPDATE SET rating=excluded.rating, updated_at=excluded.updated_at",
        )
        .bind(request.file_id)
        .bind(request.rating)
        .execute(&state.db)
        .await
    };

    match result {
        Ok(_) => api_result(json!({"file_id": request.file_id, "rating": request.rating})),
        Err(error) => internal_error(error, "failed to set rating"),
    }
}

pub async fn ratings_batch(
    State(state): State<SharedState>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    let request = match parse_batch_request(body) {
        Ok(request) => request,
        Err(response) => return response,
    };

    let mut ratings = serde_json::Map::new();
    for chunk in request.file_ids.chunks(500) {
        if chunk.is_empty() {
            continue;
        }
        let mut builder = QueryBuilder::<Sqlite>::new(
            "SELECT file_id, rating FROM file_ratings WHERE file_id IN (",
        );
        let mut separated = builder.separated(", ");
        for file_id in chunk {
            separated.push_bind(file_id);
        }
        separated.push_unseparated(")");

        match builder.build().fetch_all(&state.db_read).await {
            Ok(rows) => {
                for row in rows {
                    let file_id: i64 = row.get(0);
                    let rating: i64 = row.get(1);
                    ratings.insert(file_id.to_string(), json!(rating));
                }
            }
            Err(error) => return internal_error(error, "failed to get rating batch"),
        }
    }

    api_result(json!({"ratings": ratings}))
}

pub async fn ratings_batch_set(
    State(state): State<SharedState>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    let request = match parse_batch_set_request(body) {
        Ok(request) => request,
        Err(response) => return response,
    };

    let mut candidate_ids = Vec::new();
    for item in &request.items {
        if item.file_id > 0 {
            candidate_ids.push(item.file_id);
        }
    }

    let existing_ids = match load_existing_file_ids(&state, &candidate_ids).await {
        Ok(ids) => ids,
        Err(response) => return response,
    };

    let mut errors = Vec::new();
    let mut valid_items = Vec::new();
    for item in request.items {
        if item.file_id <= 0 {
            errors.push(json!({
                "file_id": item.file_id,
                "code": "invalid_value",
                "error": "file_id must be a positive integer",
            }));
        } else if !(0..=5).contains(&item.rating) {
            errors.push(json!({
                "file_id": item.file_id,
                "code": "invalid_value",
                "error": "rating must be 0-5",
            }));
        } else if !existing_ids.contains(&item.file_id) {
            errors.push(json!({
                "file_id": item.file_id,
                "code": "not_found",
                "error": "File not found",
            }));
        } else {
            valid_items.push(item);
        }
    }

    let succeeded = valid_items.len();
    let total = succeeded + errors.len();
    let failed = errors.len();

    if let Err(error) = write_rating_items(&state, &valid_items).await {
        return internal_error(error, "failed to set rating batch");
    }

    api_result(json!({
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors,
    }))
}

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return Json(json!({"ok": true, "error": null, "data": other})).into_response();
        }
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

// The shape lives in `routes::api_validation` -- it existed in three places, in
// three states of correctness. One copy, used by every caller.
use crate::routes::api_validation::{api_validation_error, api_validation_errors};

/// Unknown keys are a 400 on the Python side, not a courtesy: every request
/// model derives from `ApiModel`, whose config is `extra="forbid"`
/// (`core/infra_core/api_models.py`). Rust used to ignore them, so a client
/// that misspelled a field got a 400 from Python and a silent success from
/// Rust -- the two implementations disagreed on what a valid request even is,
/// and a typo'd field was dropped without a word.
///
/// One fidelity limit, stated rather than hidden: serde_json orders object keys
/// (BTreeMap), pydantic reports them in input order, so with two or more
/// unknown keys the "; "-joined order can differ. Single unknown key -- the
/// common typo -- matches exactly.
fn unknown_field_errors(value: &Value, known: &[&str]) -> Vec<String> {
    let Some(map) = value.as_object() else {
        return Vec::new();
    };
    map.keys()
        .filter(|key| !known.contains(&key.as_str()))
        .map(|key| format!("{key}: Extra inputs are not permitted"))
        .collect()
}

/// Combine field errors with unknown-key errors the way pydantic does: declared
/// fields first, extras after.
fn finish_parse<T>(parsed: Result<T, Vec<String>>, extra: Vec<String>) -> Result<T, Response> {
    match parsed {
        Ok(value) if extra.is_empty() => Ok(value),
        Ok(_) => Err(api_validation_errors(&extra)),
        Err(mut errors) => {
            errors.extend(extra);
            Err(api_validation_errors(&errors))
        }
    }
}

fn parse_set_rating_request(
    body: Result<Json<Value>, JsonRejection>,
) -> Result<SetRatingRequest, Response> {
    let value = json_value(body)?;
    let extra = unknown_field_errors(&value, &["file_id", "rating"]);
    finish_parse(set_rating_fields(&value), extra)
}

fn set_rating_fields(value: &Value) -> Result<SetRatingRequest, Vec<String>> {
    let file_id = required_i64_field(value, "file_id")?;
    if file_id <= 0 {
        return Err(vec!["file_id: Input should be greater than 0".to_string()]);
    }
    let rating = required_i64_field(value, "rating")?;
    if rating < 0 {
        return Err(vec![
            "rating: Input should be greater than or equal to 0".to_string()
        ]);
    }
    if rating > 5 {
        return Err(vec![
            "rating: Input should be less than or equal to 5".to_string()
        ]);
    }
    Ok(SetRatingRequest { file_id, rating })
}

fn parse_batch_request(body: Result<Json<Value>, JsonRejection>) -> Result<BatchRequest, Response> {
    let value = json_value(body)?;
    let extra = unknown_field_errors(&value, &["file_ids"]);
    finish_parse(batch_fields(&value), extra)
}

fn batch_fields(value: &Value) -> Result<BatchRequest, Vec<String>> {
    let Some(file_ids) = value.get("file_ids") else {
        return Err(vec!["file_ids: Field required".to_string()]);
    };
    let Some(items) = file_ids.as_array() else {
        return Err(vec!["file_ids: Input should be a valid list".to_string()]);
    };
    let mut parsed = Vec::with_capacity(items.len());
    for item in items {
        let Some(file_id) = item.as_i64() else {
            return Err(vec!["file_ids: Input should be a valid integer".to_string()]);
        };
        if file_id <= 0 {
            return Err(vec!["file_ids: Input should be greater than 0".to_string()]);
        }
        parsed.push(file_id);
    }
    Ok(BatchRequest { file_ids: parsed })
}

fn parse_batch_set_request(
    body: Result<Json<Value>, JsonRejection>,
) -> Result<BatchSetRequest, Response> {
    let value = json_value(body)?;
    let extra = unknown_field_errors(&value, &["items"]);
    finish_parse(batch_set_fields(&value), extra)
}

fn batch_set_fields(value: &Value) -> Result<BatchSetRequest, Vec<String>> {
    let Some(items_value) = value.get("items") else {
        return Err(vec!["items: Field required".to_string()]);
    };
    let Some(items) = items_value.as_array() else {
        return Err(vec!["items: Input should be a valid list".to_string()]);
    };
    if items.is_empty() {
        return Err(vec![
            "items: List should have at least 1 item after validation, not 0".to_string(),
        ]);
    }
    if items.len() > 500 {
        return Err(vec![
            "items: List should have at most 500 items after validation".to_string(),
        ]);
    }

    // BatchSetItem derives from ApiModel too, so unknown keys inside each item
    // are a 400 on the Python side as well.
    let mut item_errors = Vec::new();
    for (index, item) in items.iter().enumerate() {
        for message in unknown_field_errors(item, &["file_id", "rating"]) {
            item_errors.push(format!("items.{index}.{message}"));
        }
    }
    if !item_errors.is_empty() {
        return Err(item_errors);
    }

    let mut parsed = Vec::with_capacity(items.len());
    for item in items {
        let file_id = item.get("file_id").and_then(Value::as_i64).unwrap_or(0);
        let rating = item.get("rating").and_then(Value::as_i64).unwrap_or(-1);
        parsed.push(BatchSetItem { file_id, rating });
    }
    Ok(BatchSetRequest { items: parsed })
}

fn json_value(body: Result<Json<Value>, JsonRejection>) -> Result<Value, Response> {
    match body {
        Ok(Json(value)) if value.is_object() => Ok(value),
        Ok(_) => Err(api_validation_error(
            "body: Input should be a valid dictionary",
        )),
        Err(_) => Err(api_validation_error("body: Input should be valid JSON")),
    }
}

fn required_i64(value: &Value, field: &str) -> Result<i64, Response> {
    required_i64_field(value, field).map_err(|errors| api_validation_errors(&errors))
}

fn required_i64_field(value: &Value, field: &str) -> Result<i64, Vec<String>> {
    let Some(raw) = value.get(field) else {
        return Err(vec![format!("{field}: Field required")]);
    };
    raw.as_i64().ok_or_else(|| {
        vec![format!(
            "{field}: Input should be a valid integer, unable to parse string as an integer"
        )]
    })
}

async fn load_existing_file_ids(
    state: &SharedState,
    file_ids: &[i64],
) -> Result<HashSet<i64>, Response> {
    let mut existing_ids = HashSet::new();
    for chunk in file_ids.chunks(500) {
        if chunk.is_empty() {
            continue;
        }
        let mut builder =
            QueryBuilder::<Sqlite>::new("SELECT id FROM files WHERE is_deleted=0 AND id IN (");
        let mut separated = builder.separated(", ");
        for file_id in chunk {
            separated.push_bind(file_id);
        }
        separated.push_unseparated(")");

        match builder.build().fetch_all(&state.db_read).await {
            Ok(rows) => {
                for row in rows {
                    existing_ids.insert(row.get::<i64, _>(0));
                }
            }
            Err(error) => return Err(internal_error(error, "failed to check file existence")),
        }
    }
    Ok(existing_ids)
}

async fn write_rating_items(
    state: &SharedState,
    items: &[BatchSetItem],
) -> Result<(), sqlx::Error> {
    let mut tx = state.db.begin().await?;
    for item in items {
        if item.rating == 0 {
            sqlx::query("DELETE FROM file_ratings WHERE file_id=?")
                .bind(item.file_id)
                .execute(&mut *tx)
                .await?;
        } else {
            sqlx::query(
                "INSERT INTO file_ratings (file_id, rating, rated_at, updated_at)
                 VALUES (?, ?, unixepoch(), unixepoch())
                 ON CONFLICT(file_id) DO UPDATE SET rating=excluded.rating, updated_at=excluded.updated_at",
            )
            .bind(item.file_id)
            .bind(item.rating)
            .execute(&mut *tx)
            .await?;
        }
    }
    tx.commit().await
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": "internal_server_error"})),
    )
        .into_response()
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
            "CREATE TABLE file_ratings (
                file_id INTEGER PRIMARY KEY,
                rating INTEGER NOT NULL,
                rated_at INTEGER,
                updated_at INTEGER
             );
             CREATE TABLE files (id INTEGER PRIMARY KEY, is_deleted INTEGER NOT NULL DEFAULT 0);
             INSERT INTO files(id, is_deleted) VALUES (7, 0), (8, 0);
             INSERT INTO file_ratings(file_id, rating) VALUES (7, 5), (8, 3);",
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
                    rate_limit_trusted_proxies: HashSet::new(),
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
                    wd_tagger_root: std::path::PathBuf::from("."),
                    clip_model_dir: std::path::PathBuf::from("."),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    async fn json_body(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn ratings_get_missing_file_id_matches_validation_error_shape() {
        let response = ratings_get(State(test_state().await), None, Query(HashMap::new())).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["code"], "validation_error");
        assert_eq!(value["detail"], "1 validation error(s)");
        assert_eq!(value["error"], "file_id: Field required");
    }

    #[tokio::test]
    async fn ratings_get_invalid_file_id_matches_validation_error_shape() {
        let response = ratings_get(
            State(test_state().await),
            None,
            Query(HashMap::from([(
                "file_id".to_string(),
                "not-an-int".to_string(),
            )])),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["code"], "validation_error");
        assert_eq!(value["detail"], "1 validation error(s)");
        assert_eq!(
            value["error"],
            "file_id: Input should be a valid integer, unable to parse string as an integer"
        );
    }

    #[tokio::test]
    async fn ratings_get_returns_rating_or_zero() {
        let response = ratings_get(
            State(test_state().await),
            None,
            Query(HashMap::from([("file_id".to_string(), "7".to_string())])),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["data"], serde_json::Value::Null);
        assert_eq!(value["file_id"], 7);
        assert_eq!(value["rating"], 5);
    }

    #[tokio::test]
    async fn ratings_stats_returns_distribution_and_total() {
        let response = ratings_stats(State(test_state().await), None).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["data"], serde_json::Value::Null);
        assert_eq!(value["total_rated"], 2);
        assert_eq!(value["distribution"]["3"], 1);
        assert_eq!(value["distribution"]["5"], 1);
    }

    #[tokio::test]
    async fn ratings_set_missing_file_id_returns_validation_error() {
        let response = ratings_set(State(test_state().await), Ok(Json(json!({"rating": 3})))).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["code"], "validation_error");
        assert_eq!(value["detail"], "1 validation error(s)");
        assert_eq!(value["error"], "file_id: Field required");
    }

    #[tokio::test]
    async fn ratings_set_invalid_rating_returns_validation_error() {
        let response = ratings_set(
            State(test_state().await),
            Ok(Json(json!({"file_id": 7, "rating": 6}))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(
            value["error"],
            "rating: Input should be less than or equal to 5"
        );
    }

    #[tokio::test]
    async fn ratings_set_upserts_and_clears_on_zero() {
        let state = test_state().await;
        let response = ratings_set(
            State(Arc::clone(&state)),
            Ok(Json(json!({"file_id": 7, "rating": 4}))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["file_id"], 7);
        assert_eq!(value["rating"], 4);

        let rating: i64 = sqlx::query_scalar("SELECT rating FROM file_ratings WHERE file_id=7")
            .fetch_one(&state.db_read)
            .await
            .unwrap();
        assert_eq!(rating, 4);

        let response =
            ratings_set(State(state), Ok(Json(json!({"file_id": 7, "rating": 0})))).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["rating"], 0);
    }

    #[tokio::test]
    async fn ratings_batch_empty_returns_empty_map() {
        let response =
            ratings_batch(State(test_state().await), Ok(Json(json!({"file_ids": []})))).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["ratings"], json!({}));
    }

    #[tokio::test]
    async fn ratings_batch_returns_ratings_for_known_ids() {
        let response = ratings_batch(
            State(test_state().await),
            Ok(Json(json!({"file_ids": [7, 8, 99]}))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["ratings"]["7"], 5);
        assert_eq!(value["ratings"]["8"], 3);
        assert!(value["ratings"].get("99").is_none());
    }

    #[tokio::test]
    async fn ratings_batch_set_skips_nonexistent_file_ids() {
        let response = ratings_batch_set(
            State(test_state().await),
            Ok(Json(json!({"items": [{"file_id": 999, "rating": 3}]}))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["total"], 1);
        assert_eq!(value["succeeded"], 0);
        assert_eq!(value["failed"], 1);
        assert_eq!(value["errors"][0]["code"], "not_found");
    }

    #[tokio::test]
    async fn ratings_batch_set_upserts_valid_items() {
        let state = test_state().await;
        let response = ratings_batch_set(
            State(Arc::clone(&state)),
            Ok(Json(
                json!({"items": [{"file_id": 7, "rating": 2}, {"file_id": 8, "rating": 0}]}),
            )),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["total"], 2);
        assert_eq!(value["succeeded"], 2);
        assert_eq!(value["failed"], 0);

        let rating: i64 = sqlx::query_scalar("SELECT rating FROM file_ratings WHERE file_id=7")
            .fetch_one(&state.db_read)
            .await
            .unwrap();
        let cleared: Option<i64> =
            sqlx::query_scalar("SELECT rating FROM file_ratings WHERE file_id=8")
                .fetch_optional(&state.db_read)
                .await
                .unwrap();
        assert_eq!(rating, 2);
        assert_eq!(cleared, None);
    }

    /// The Python side rejects unknown fields (`ApiModel`'s `extra="forbid"`)
    /// and counts the errors. Rust used to ignore unknown keys entirely, so a
    /// misspelled field was a 400 there and a silent success here.
    #[test]
    fn an_unknown_field_is_rejected_the_way_pydantic_rejects_it() {
        let response = parse_batch_set_request(Ok(Json(json!({"ratings": []}))))
            .err()
            .expect("an unknown field plus a missing one must not parse");
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[test]
    fn validation_errors_are_joined_and_counted_like_pydantic() {
        // Both problems at once: `items` missing, `ratings` not permitted.
        let messages = batch_set_fields(&json!({"ratings": []}))
            .err()
            .map(|mut errors| {
                errors.extend(unknown_field_errors(&json!({"ratings": []}), &["items"]));
                errors
            })
            .expect("must report the missing field");
        assert_eq!(
            messages,
            vec![
                "items: Field required".to_string(),
                "ratings: Extra inputs are not permitted".to_string(),
            ]
        );
        // `detail` used to be hardcoded to "1 validation error(s)", which was
        // false for exactly this input.
        let response = api_validation_errors(&messages);
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[test]
    fn a_known_field_is_still_accepted() {
        let request =
            parse_batch_set_request(Ok(Json(json!({"items": [{"file_id": 1, "rating": 3}]}))))
                .expect("a well-formed request must still parse");
        assert_eq!(request.items.len(), 1);
        assert_eq!(request.items[0].file_id, 1);
    }

    #[test]
    fn an_unknown_field_inside_an_item_is_rejected_too() {
        // BatchSetItem derives from ApiModel as well.
        parse_batch_set_request(Ok(Json(
            json!({"items": [{"file_id": 1, "rating": 3, "starz": 9}]}),
        )))
        .err()
        .expect("an unknown key inside an item must not parse");
    }
}

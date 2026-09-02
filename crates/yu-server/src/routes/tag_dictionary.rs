use std::collections::{HashMap, HashSet};

use axum::{
    body::Body,
    extract::Extension,
    extract::{rejection::JsonRejection, Query, Request, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use futures_util::StreamExt;
use serde_json::{json, Map, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const MAX_CSV_UPLOAD_BYTES: usize = 16 * 1024 * 1024;
const IMPORT_BATCH_SIZE: usize = 1000;

fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => Map::from_iter([("data".to_string(), other)]),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{message}");
    api_error("internal_server_error", StatusCode::INTERNAL_SERVER_ERROR)
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn ensure_table(state: &SharedState) -> Result<(), sqlx::Error> {
    sqlx::raw_sql(
        "CREATE TABLE IF NOT EXISTS tag_dictionary (
            id INTEGER PRIMARY KEY,
            tag_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            category INTEGER NOT NULL DEFAULT 0,
            post_count INTEGER NOT NULL DEFAULT 0,
            aliases TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_tag_dict_name ON tag_dictionary(tag_name COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_tag_dict_post_count ON tag_dictionary(post_count DESC);",
    )
    .execute(&state.db)
    .await?;
    Ok(())
}

fn like_escape(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('%', "\\%")
        .replace('_', "\\_")
}

fn row_to_tag(row: &sqlx::sqlite::SqliteRow, match_type: &str) -> Value {
    json!({
        "tag_name": row.get::<String, _>("tag_name"),
        "category": row.get::<i64, _>("category"),
        "post_count": row.get::<i64, _>("post_count"),
        "aliases": row.try_get::<String, _>("aliases").unwrap_or_default(),
        "match_type": match_type,
    })
}

pub async fn search(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Err(error) = ensure_table(&state).await {
        return internal_error(error, "failed to initialize tag dictionary");
    }
    let q = params.get("q").map(String::as_str).unwrap_or("").trim();
    if q.is_empty() {
        return Json(json!({"results": []})).into_response();
    }
    let limit = params
        .get("limit")
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(20)
        .min(100);
    let use_fuzzy = params
        .get("fuzzy")
        .is_some_and(|v| matches!(v.to_lowercase().as_str(), "1" | "true"));
    let mut results = match search_tags(&state, q, limit).await {
        Ok(results) => results,
        Err(error) => return internal_error(error, "failed to search tag dictionary"),
    };
    if use_fuzzy && results.len() < limit {
        let fuzzy = match fuzzy_search_tags(&state, q, 100).await {
            Ok(candidates) => fuzzy_filter(q, candidates, 2),
            Err(error) => return internal_error(error, "failed to fuzzy search tag dictionary"),
        };
        let mut seen = results
            .iter()
            .filter_map(|r| r.get("tag_name").and_then(Value::as_str))
            .map(|name| name.to_lowercase())
            .collect::<HashSet<_>>();
        for mut item in fuzzy {
            let key = item
                .get("tag_name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase();
            if seen.insert(key) {
                item["match_type"] = json!("fuzzy");
                results.push(item);
                if results.len() >= limit {
                    break;
                }
            }
        }
    }
    Json(json!({"results": results})).into_response()
}

async fn search_tags(
    state: &SharedState,
    query: &str,
    limit: usize,
) -> Result<Vec<Value>, sqlx::Error> {
    if query.is_empty() || limit < 1 {
        return Ok(vec![]);
    }
    let escaped = like_escape(query);
    let mut results = Vec::new();
    let mut seen = HashSet::new();
    let prefix_rows = sqlx::query(
        "SELECT tag_name, category, post_count, aliases FROM tag_dictionary
         WHERE tag_name LIKE ? ESCAPE '\\' ORDER BY post_count DESC LIMIT ?",
    )
    .bind(format!("{escaped}%"))
    .bind(limit as i64)
    .fetch_all(&state.db_read)
    .await?;
    for row in prefix_rows {
        let key = row.get::<String, _>("tag_name").to_lowercase();
        if seen.insert(key) {
            results.push(row_to_tag(&row, "prefix"));
        }
    }
    if results.len() >= limit {
        results.truncate(limit);
        return Ok(results);
    }

    let remain = limit - results.len();
    let substring_rows = sqlx::query(
        "SELECT tag_name, category, post_count, aliases FROM tag_dictionary
         WHERE tag_name LIKE ? ESCAPE '\\' ORDER BY post_count DESC LIMIT ?",
    )
    .bind(format!("%{escaped}%"))
    .bind((remain + seen.len()) as i64)
    .fetch_all(&state.db_read)
    .await?;
    for row in substring_rows {
        let key = row.get::<String, _>("tag_name").to_lowercase();
        if seen.insert(key) {
            results.push(row_to_tag(&row, "substring"));
            if results.len() >= limit {
                return Ok(results);
            }
        }
    }

    let remain = limit - results.len();
    let alias_rows = sqlx::query(
        "SELECT tag_name, category, post_count, aliases FROM tag_dictionary
         WHERE aliases LIKE ? ESCAPE '\\' ORDER BY post_count DESC LIMIT ?",
    )
    .bind(format!("%{escaped}%"))
    .bind((remain + seen.len()) as i64)
    .fetch_all(&state.db_read)
    .await?;
    for row in alias_rows {
        let key = row.get::<String, _>("tag_name").to_lowercase();
        if seen.insert(key) {
            results.push(row_to_tag(&row, "alias"));
            if results.len() >= limit {
                break;
            }
        }
    }
    Ok(results)
}

async fn fuzzy_search_tags(
    state: &SharedState,
    query: &str,
    limit: usize,
) -> Result<Vec<Value>, sqlx::Error> {
    let q_len = query.chars().count() as i64;
    let rows = sqlx::query(
        "SELECT tag_name, category, post_count, aliases FROM tag_dictionary
         WHERE LENGTH(tag_name) BETWEEN ? AND ?
         ORDER BY post_count DESC LIMIT ?",
    )
    .bind((q_len - 2).max(1))
    .bind(q_len + 2)
    .bind(limit as i64)
    .fetch_all(&state.db_read)
    .await?;
    Ok(rows.iter().map(|row| row_to_tag(row, "fuzzy")).collect())
}

fn edit_distance(s1: &str, s2: &str, max_dist: usize) -> usize {
    let len1 = s1.chars().count();
    let len2 = s2.chars().count();
    if len1.abs_diff(len2) > max_dist {
        return max_dist + 1;
    }
    let s1 = s1.chars().collect::<Vec<_>>();
    let s2 = s2.chars().collect::<Vec<_>>();
    let mut prev = (0..=len2).collect::<Vec<_>>();
    for i in 1..=len1 {
        let mut curr = vec![0; len2 + 1];
        curr[0] = i;
        let mut row_min = i;
        for j in 1..=len2 {
            let cost = usize::from(s1[i - 1] != s2[j - 1]);
            curr[j] = (curr[j - 1] + 1).min(prev[j] + 1).min(prev[j - 1] + cost);
            row_min = row_min.min(curr[j]);
        }
        if row_min > max_dist {
            return max_dist + 1;
        }
        prev = curr;
    }
    prev[len2]
}

fn fuzzy_filter(query: &str, candidates: Vec<Value>, threshold: usize) -> Vec<Value> {
    let q = query.to_lowercase();
    let mut matches = Vec::new();
    for cand in candidates {
        let tag = cand
            .get("tag_name")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_lowercase();
        let dist = edit_distance(&q, &tag, threshold);
        if dist <= threshold {
            matches.push((dist, cand));
        }
    }
    matches.sort_by(|a, b| {
        a.0.cmp(&b.0).then_with(|| {
            let ap = a.1.get("post_count").and_then(Value::as_i64).unwrap_or(0);
            let bp = b.1.get("post_count").and_then(Value::as_i64).unwrap_or(0);
            bp.cmp(&ap)
        })
    });
    matches.into_iter().map(|(_, value)| value).collect()
}

pub async fn info(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Err(error) = ensure_table(&state).await {
        return internal_error(error, "failed to initialize tag dictionary");
    }
    let tag = params.get("tag").map(String::as_str).unwrap_or("").trim();
    if tag.is_empty() {
        return api_error("tag parameter required", StatusCode::BAD_REQUEST);
    }
    let row = match sqlx::query(
        "SELECT tag_name, category, post_count, aliases
         FROM tag_dictionary WHERE tag_name = ? COLLATE NOCASE",
    )
    .bind(tag)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(row) => row,
        Err(error) => return internal_error(error, "failed to get tag info"),
    };
    match row {
        Some(row) => Json(row_to_tag(&row, "exact")).into_response(),
        None => api_error("Tag not found", StatusCode::NOT_FOUND),
    }
}

pub async fn stats(State(state): State<SharedState>) -> Response {
    if let Err(error) = ensure_table(&state).await {
        return internal_error(error, "failed to initialize tag dictionary");
    }
    let total = match sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM tag_dictionary")
        .fetch_one(&state.db_read)
        .await
    {
        Ok(total) => total,
        Err(error) => return internal_error(error, "failed to count tag dictionary"),
    };
    let rows = match sqlx::query(
        "SELECT category, COUNT(*) AS count FROM tag_dictionary GROUP BY category",
    )
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to count tag dictionary categories"),
    };
    let mut categories = Map::new();
    for row in rows {
        categories.insert(
            row.get::<i64, _>("category").to_string(),
            json!(row.get::<i64, _>("count")),
        );
    }
    Json(json!({"total": total, "categories": categories})).into_response()
}

pub async fn import(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    request: Request,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_table(&state).await {
        return internal_error(error, "failed to initialize tag dictionary");
    }
    let content_type = request
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();
    let Some(boundary) = multipart_boundary(&content_type) else {
        return api_error("file required (multipart form)", StatusCode::BAD_REQUEST);
    };
    let body = match read_limited_body(request.into_body(), MAX_CSV_UPLOAD_BYTES).await {
        Ok(body) => body,
        Err(_) => return api_error("upload too large", StatusCode::PAYLOAD_TOO_LARGE),
    };
    let Some(file_bytes) = multipart_file_part(&body, &boundary) else {
        return api_error("file required (multipart form)", StatusCode::BAD_REQUEST);
    };
    if file_bytes.len() > MAX_CSV_UPLOAD_BYTES {
        return api_error("upload too large", StatusCode::PAYLOAD_TOO_LARGE);
    }
    let result = match import_csv_bytes(&state, &file_bytes).await {
        Ok(result) => result,
        Err(error) => return internal_error(error, "failed to import tag dictionary csv"),
    };
    Json(result).into_response()
}

async fn read_limited_body(body: Body, max_bytes: usize) -> Result<Vec<u8>, ()> {
    let mut out = Vec::new();
    let mut stream = body.into_data_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|_| ())?;
        if out.len().saturating_add(chunk.len()) > max_bytes {
            return Err(());
        }
        out.extend_from_slice(&chunk);
    }
    Ok(out)
}

fn multipart_boundary(content_type: &str) -> Option<String> {
    content_type.split(';').find_map(|part| {
        let part = part.trim();
        part.strip_prefix("boundary=")
            .map(|value| value.trim_matches('"').to_string())
    })
}

fn multipart_file_part(body: &[u8], boundary: &str) -> Option<Vec<u8>> {
    let marker = format!("--{boundary}");
    let text = String::from_utf8_lossy(body);
    for section in text.split(&marker).skip(1) {
        if !section.contains("name=\"file\"") {
            continue;
        }
        let data_start = section
            .find("\r\n\r\n")
            .map(|idx| idx + 4)
            .or_else(|| section.find("\n\n").map(|idx| idx + 2))?;
        let mut data = section.as_bytes()[data_start..].to_vec();
        if data.ends_with(b"\r\n") {
            data.truncate(data.len() - 2);
        } else if data.ends_with(b"\n") {
            data.truncate(data.len() - 1);
        }
        return Some(data);
    }
    None
}

async fn import_csv_bytes(state: &SharedState, bytes: &[u8]) -> Result<Value, sqlx::Error> {
    let started = std::time::Instant::now();
    let text = String::from_utf8_lossy(bytes);
    let mut imported = 0_i64;
    let mut skipped = 0_i64;
    let mut batch = Vec::new();
    for (i, line) in text.lines().enumerate() {
        let row = parse_csv_line(line);
        if i == 0
            && row.first().is_some_and(|cell| {
                matches!(
                    cell.trim().to_lowercase().as_str(),
                    "tag_name" | "name" | "tag"
                )
            })
        {
            continue;
        }
        if row.is_empty() {
            skipped += 1;
            continue;
        }
        let tag_name = row[0].trim().to_string();
        if tag_name.is_empty() {
            skipped += 1;
            continue;
        }
        let category = if row.get(1).is_some_and(|v| !v.trim().is_empty()) {
            match row[1].trim().parse::<i64>() {
                Ok(category) => category,
                Err(_) => {
                    skipped += 1;
                    continue;
                }
            }
        } else {
            0
        };
        let post_count = row
            .get(2)
            .filter(|v| !v.trim().is_empty())
            .and_then(|v| v.trim().parse::<i64>().ok())
            .unwrap_or(0);
        let aliases = row.get(3).map(|v| v.trim().to_string()).unwrap_or_default();
        batch.push((tag_name, category, post_count, aliases));
        if batch.len() >= IMPORT_BATCH_SIZE {
            imported += flush_batch(state, &batch).await?;
            batch.clear();
        }
    }
    if !batch.is_empty() {
        imported += flush_batch(state, &batch).await?;
    }
    Ok(json!({
        "imported": imported,
        "skipped": skipped,
        "total_time": (started.elapsed().as_secs_f64() * 100.0).round() / 100.0,
    }))
}

fn parse_csv_line(line: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut current = String::new();
    let mut chars = line.chars().peekable();
    let mut quoted = false;
    while let Some(ch) = chars.next() {
        match ch {
            '"' if quoted && chars.peek() == Some(&'"') => {
                current.push('"');
                chars.next();
            }
            '"' => quoted = !quoted,
            ',' if !quoted => {
                out.push(current);
                current = String::new();
            }
            _ => current.push(ch),
        }
    }
    out.push(current);
    out
}

async fn flush_batch(
    state: &SharedState,
    batch: &[(String, i64, i64, String)],
) -> Result<i64, sqlx::Error> {
    let mut tx = state.db.begin().await?;
    for (tag_name, category, post_count, aliases) in batch {
        sqlx::query(
            "INSERT INTO tag_dictionary (tag_name, category, post_count, aliases)
             VALUES (?, ?, ?, ?)
             ON CONFLICT(tag_name) DO UPDATE SET
               category=excluded.category,
               post_count=excluded.post_count,
               aliases=excluded.aliases",
        )
        .bind(tag_name)
        .bind(category)
        .bind(post_count)
        .bind(aliases)
        .execute(&mut *tx)
        .await?;
    }
    tx.commit().await?;
    Ok(batch.len() as i64)
}

pub async fn clear(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_table(&state).await {
        return internal_error(error, "failed to initialize tag dictionary");
    }
    let count = match sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM tag_dictionary")
        .fetch_one(&state.db)
        .await
    {
        Ok(count) => count,
        Err(error) => return internal_error(error, "failed to count tag dictionary"),
    };
    if let Err(error) = sqlx::query("DELETE FROM tag_dictionary")
        .execute(&state.db)
        .await
    {
        return internal_error(error, "failed to clear tag dictionary");
    }
    api_result(json!({"deleted": count}))
}

pub async fn split(
    State(state): State<SharedState>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Err(error) = ensure_table(&state).await {
        return internal_error(error, "failed to initialize tag dictionary");
    }
    let body = match body {
        Ok(Json(Value::Object(map))) => Value::Object(map),
        Ok(_) | Err(_) => return api_error("JSON object required", StatusCode::BAD_REQUEST),
    };
    let Some(text) = body.get("text").and_then(Value::as_str).map(str::trim) else {
        return api_error("text required", StatusCode::BAD_REQUEST);
    };
    if text.is_empty() {
        return api_error("text required", StatusCode::BAD_REQUEST);
    }
    match suggest_splits(&state, text, 5).await {
        Ok(suggestions) => Json(json!({"suggestions": suggestions})).into_response(),
        Err(error) => internal_error(error, "failed to split tag text"),
    }
}

async fn suggest_splits(
    state: &SharedState,
    text: &str,
    max_suggestions: usize,
) -> Result<Vec<Value>, sqlx::Error> {
    let normalized = regex::Regex::new(r"[\s_]+")
        .expect("valid regex")
        .replace_all(text, "")
        .to_lowercase();
    if normalized.is_empty() {
        return Ok(vec![]);
    }
    let tag_set = get_all_tag_names(state, 50).await?;
    if tag_set.is_empty() {
        return Ok(vec![]);
    }
    let max_tag_len = tag_set
        .iter()
        .map(|tag| tag.replace('_', "").len())
        .max()
        .unwrap_or(0);
    if max_tag_len == 0 {
        return Ok(vec![]);
    }
    let n = normalized.len();
    let mut dp: Vec<Option<(usize, Vec<String>)>> = vec![None; n + 1];
    dp[0] = Some((0, vec![]));
    for i in 0..n {
        let Some((count_i, tags_i)) = dp[i].clone() else {
            continue;
        };
        for end in (i + 1)..=(i + max_tag_len).min(n) {
            let substr = &normalized[i..end];
            let Some(matched_tag) = find_tag(substr, &tag_set) else {
                continue;
            };
            let new_count = count_i + 1;
            if dp[end].as_ref().is_none_or(|(count, _)| new_count < *count) {
                let mut tags = tags_i.clone();
                tags.push(matched_tag);
                dp[end] = Some((new_count, tags));
            }
        }
    }
    let Some((_, tags)) = dp[n].clone() else {
        let best_idx = (0..=n).rev().find(|idx| dp[*idx].is_some()).unwrap_or(0);
        if best_idx == 0 {
            return Ok(vec![]);
        }
        let (_, tags) = dp[best_idx].clone().expect("checked");
        let coverage = ((best_idx as f64 / n as f64) * 1000.0).round() / 1000.0;
        return Ok(vec![json!({"tags": tags, "coverage": coverage})]
            .into_iter()
            .take(max_suggestions)
            .collect());
    };
    Ok(vec![json!({"tags": tags, "coverage": 1.0})]
        .into_iter()
        .take(max_suggestions)
        .collect())
}

async fn get_all_tag_names(
    state: &SharedState,
    min_post_count: i64,
) -> Result<HashSet<String>, sqlx::Error> {
    let rows = sqlx::query("SELECT tag_name FROM tag_dictionary WHERE post_count >= ?")
        .bind(min_post_count)
        .fetch_all(&state.db_read)
        .await?;
    Ok(rows
        .iter()
        .map(|row| {
            row.get::<String, _>("tag_name")
                .to_lowercase()
                .replace(' ', "_")
        })
        .collect())
}

fn find_tag(substr: &str, tag_set: &HashSet<String>) -> Option<String> {
    if tag_set.contains(substr) {
        return Some(substr.to_string());
    }
    tag_set
        .iter()
        .find(|tag| tag.replace('_', "") == substr)
        .cloned()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::{to_bytes, Body};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    async fn test_state() -> SharedState {
        test_state_with_pin_auth(false).await
    }

    async fn test_state_with_pin_auth(pin_auth_enabled: bool) -> SharedState {
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
                    pin_auth_enabled,
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
    async fn info_missing_tag_parameter_has_exact_error_shape() {
        let state = test_state().await;

        let response = info(State(state), Query(HashMap::new())).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            json_body(response).await,
            json!({"ok": false, "error": "tag parameter required"})
        );
    }

    #[tokio::test]
    async fn fuzzy_filter_threshold_boundary_matches_python() {
        let candidates = vec![
            json!({"tag_name": "kitten", "post_count": 10}),
            json!({"tag_name": "sitting", "post_count": 100}),
        ];

        let filtered = fuzzy_filter("kitton", candidates, 2);

        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0]["tag_name"], "kitten");
    }

    #[tokio::test]
    async fn import_csv_counts_imported_and_skipped() {
        let state = test_state().await;
        let boundary = "BOUNDARY";
        let body = format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"tags.csv\"\r\n\r\ntag_name,category,post_count,aliases\r\nblue_eyes,0,50,blue eyes\r\nbad,not-int,1,\r\ncat,1,,kitty\r\n\r\n--{boundary}--\r\n"
        );
        let request = Request::builder()
            .header(
                header::CONTENT_TYPE,
                format!("multipart/form-data; boundary={boundary}"),
            )
            .body(Body::from(body))
            .unwrap();

        let response = import(State(state), None, request).await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["imported"], 2);
        assert_eq!(body["skipped"], 1);
        assert!(body["total_time"].is_number());
    }

    #[tokio::test]
    async fn import_rejects_oversized_upload_with_api_error_shape() {
        let state = test_state().await;
        let boundary = "BOUNDARY";
        let body = format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"tags.csv\"\r\n\r\n{}\r\n--{boundary}--\r\n",
            "x".repeat(MAX_CSV_UPLOAD_BYTES + 1)
        );
        let request = Request::builder()
            .header(
                header::CONTENT_TYPE,
                format!("multipart/form-data; boundary={boundary}"),
            )
            .body(Body::from(body))
            .unwrap();

        let response = import(State(state), None, request).await;

        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        let body = json_body(response).await;
        assert_eq!(body["ok"], false);
        assert!(body.get("code").is_none());
    }

    #[tokio::test]
    async fn search_is_case_insensitive_with_migration_schema() {
        let state = test_state().await;
        ensure_table(&state).await.unwrap();
        sqlx::query(
            "INSERT INTO tag_dictionary(tag_name, category, post_count, aliases)
             VALUES ('Blue_Eyes', 0, 100, 'blue eyes')",
        )
        .execute(&state.db)
        .await
        .unwrap();

        let response = search(
            State(state),
            Query(HashMap::from([("q".to_string(), "blue_eyes".to_string())])),
        )
        .await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["results"][0]["tag_name"], "Blue_Eyes");
        assert_eq!(body["results"][0]["match_type"], "prefix");
    }

    #[tokio::test]
    async fn import_requires_admin_scope_when_pin_auth_enabled() {
        let state = test_state_with_pin_auth(true).await;
        let request = Request::builder()
            .header(
                header::CONTENT_TYPE,
                "multipart/form-data; boundary=BOUNDARY",
            )
            .body(Body::empty())
            .unwrap();
        let auth = Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: None,
        });

        let response = import(State(state), Some(auth), request).await;

        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        assert_eq!(
            json_body(response).await,
            json!({"ok": false, "error": "Insufficient scope: requires 'admin'"})
        );
    }

    #[tokio::test]
    async fn clear_admin_scope_is_noop_when_pin_auth_disabled() {
        let state = test_state().await;
        ensure_table(&state).await.unwrap();
        sqlx::query(
            "INSERT INTO tag_dictionary(tag_name, category, post_count, aliases)
             VALUES ('cat', 0, 1, '')",
        )
        .execute(&state.db)
        .await
        .unwrap();
        let auth = Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: None,
        });

        let response = clear(State(state), Some(auth)).await;

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            json_body(response).await,
            json!({"ok": true, "error": null, "data": null, "deleted": 1})
        );
    }
}

use std::collections::HashSet;

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

#[derive(Debug, Deserialize)]
pub struct SuggestQuery {
    q: Option<String>,
    query: Option<String>,
    limit: Option<i64>,
    n: Option<i64>,
}

#[derive(Debug, Deserialize)]
pub struct TagsSuggestQuery {
    q: Option<String>,
    limit: Option<i64>,
}

#[derive(Debug, Serialize, sqlx::FromRow)]
struct PromptRow {
    raw_prompt: String,
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

fn query_text(params: &SuggestQuery) -> String {
    params
        .q
        .as_deref()
        .or(params.query.as_deref())
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn suggest_limit(params: &SuggestQuery) -> i64 {
    params.limit.or(params.n).unwrap_or(20).clamp(1, 50)
}

fn like_escape(raw: &str) -> String {
    raw.replace('\\', r"\\")
        .replace('%', r"\%")
        .replace('_', r"\_")
}

fn normalize_tag(tag: &str) -> String {
    let mut value = tag.replace(',', ", ");
    while value.contains("  ") {
        value = value.replace("  ", " ");
    }
    value.trim().to_string()
}

fn dedupe_normalized_tags(tags: impl IntoIterator<Item = String>, limit: usize) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for tag in tags {
        let normalized = normalize_tag(&tag);
        if normalized.is_empty() || !seen.insert(normalized.clone()) {
            continue;
        }
        out.push(normalized);
        if out.len() >= limit {
            break;
        }
    }
    out
}

fn sort_case_insensitive(values: &mut [String]) {
    values.sort_by(|a, b| {
        a.to_lowercase()
            .cmp(&b.to_lowercase())
            .then_with(|| a.cmp(b))
    });
}

fn extract_lora_names(prompts: &[String], q: &str, limit: usize) -> Vec<String> {
    let pattern = Regex::new(r"(?i)<lora:([^:>]+):").expect("valid lora regex");
    let q_lower = q.to_lowercase();
    let mut seen = HashSet::new();
    let mut names = Vec::new();
    for prompt in prompts {
        for capture in pattern.captures_iter(prompt) {
            let Some(name) = capture.get(1).map(|m| m.as_str().trim()) else {
                continue;
            };
            if !q_lower.is_empty() && !name.to_lowercase().starts_with(&q_lower) {
                continue;
            }
            if seen.insert(name.to_lowercase()) {
                names.push(name.to_string());
            }
        }
    }
    sort_case_insensitive(&mut names);
    names.truncate(limit);
    names
}

fn extract_embedding_names(prompts: &[String], q: &str, limit: usize) -> Vec<String> {
    let pattern =
        Regex::new(r"(?i)(?:<embedding:|<hypernet:|\(embedding:|embedding:)([A-Za-z0-9_\-.]+)")
            .expect("valid embedding regex");
    let q_lower = q.to_lowercase();
    let mut seen = HashSet::new();
    let mut names = Vec::new();
    for prompt in prompts {
        for capture in pattern.captures_iter(prompt) {
            let Some(full_match) = capture.get(0) else {
                continue;
            };
            if full_match.as_str().to_lowercase().starts_with("embedding:")
                && prompt[..full_match.start()]
                    .chars()
                    .last()
                    .is_some_and(|c| c == '<' || c == '(')
            {
                continue;
            }
            let Some(name) = capture.get(1).map(|m| m.as_str().trim()) else {
                continue;
            };
            if !q_lower.is_empty() && !name.to_lowercase().starts_with(&q_lower) {
                continue;
            }
            if seen.insert(name.to_lowercase()) {
                names.push(name.to_string());
            }
        }
    }
    sort_case_insensitive(&mut names);
    names.truncate(limit);
    names
}

pub async fn suggest(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<SuggestQuery>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }

    let q = query_text(&params);
    let limit = suggest_limit(&params);
    if q.is_empty() {
        return api_result(json!({"q": q, "suggestions": []}));
    }

    let pattern = format!("{}%", like_escape(&q));
    match sqlx::query_scalar::<_, String>(
        "SELECT DISTINCT tag FROM tags WHERE tag LIKE ? ESCAPE '\\'
         ORDER BY length(tag) ASC, tag ASC LIMIT ?",
    )
    .bind(pattern)
    .bind(limit * 2)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(tags) => api_result(json!({
            "q": q,
            "suggestions": dedupe_normalized_tags(tags, usize::try_from(limit).unwrap_or(20)),
        })),
        Err(error) => internal_error(error, "failed to suggest tags"),
    }
}

pub async fn suggest_lora(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<SuggestQuery>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }

    let q = query_text(&params);
    let limit = usize::try_from(suggest_limit(&params)).unwrap_or(20);
    let pattern = if q.is_empty() {
        "%<lora:%".to_string()
    } else {
        format!("%<lora:{}%", like_escape(&q))
    };

    match sqlx::query_as::<_, PromptRow>(
        "SELECT raw_prompt FROM templates WHERE raw_prompt LIKE ? ESCAPE '\\' LIMIT 5000",
    )
    .bind(pattern)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => {
            let prompts = rows
                .into_iter()
                .map(|row| row.raw_prompt)
                .collect::<Vec<_>>();
            api_result(json!({"q": q, "suggestions": extract_lora_names(&prompts, &q, limit)}))
        }
        Err(error) => internal_error(error, "failed to suggest lora names"),
    }
}

pub async fn suggest_embedding(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<SuggestQuery>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }

    let q = query_text(&params);
    let limit = usize::try_from(suggest_limit(&params)).unwrap_or(20);
    let query = if q.is_empty() {
        sqlx::query_as::<_, PromptRow>(
            "SELECT raw_prompt FROM templates
             WHERE raw_prompt LIKE '%embedding:%' OR raw_prompt LIKE '%hypernet:%'
             LIMIT 5000",
        )
    } else {
        sqlx::query_as::<_, PromptRow>(
            "SELECT raw_prompt FROM templates
             WHERE (raw_prompt LIKE ? ESCAPE '\\' OR raw_prompt LIKE ? ESCAPE '\\')
             LIMIT 5000",
        )
        .bind(format!("%embedding:{}%", like_escape(&q)))
        .bind(format!("%hypernet:{}%", like_escape(&q)))
    };

    match query.fetch_all(&state.db_read).await {
        Ok(rows) => {
            let prompts = rows
                .into_iter()
                .map(|row| row.raw_prompt)
                .collect::<Vec<_>>();
            api_result(json!({"q": q, "suggestions": extract_embedding_names(&prompts, &q, limit)}))
        }
        Err(error) => internal_error(error, "failed to suggest embedding names"),
    }
}

pub async fn tags_suggest(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<TagsSuggestQuery>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(q) = params.q.as_deref().map(str::trim).filter(|q| !q.is_empty()) else {
        return api_result(json!({"data": []}));
    };
    let limit = params.limit.unwrap_or(20).clamp(0, 100);

    match sqlx::query(
        "SELECT t.id, t.tag, t.namespace, COUNT(ft.file_id) AS file_count
         FROM tags t
         LEFT JOIN file_tags ft ON ft.tag_id = t.id
         WHERE t.tag LIKE ?
         GROUP BY t.id
         ORDER BY file_count DESC
         LIMIT ?",
    )
    .bind(format!("%{q}%"))
    .bind(limit)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => api_result(json!({"data": rows
            .into_iter()
            .map(|row| json!({
                "id": row.get::<i64, _>("id"),
                "tag": row.get::<String, _>("tag"),
                "namespace": row.get::<Option<String>, _>("namespace"),
                "file_count": row.get::<i64, _>("file_count"),
            }))
            .collect::<Vec<_>>()
        })),
        Err(error) => internal_error(error, "failed to suggest tags with counts"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{
        body::to_bytes,
        extract::{Query, State},
        http::StatusCode,
    };
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

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
             CREATE TABLE templates (
               id INTEGER PRIMARY KEY,
               raw_prompt TEXT NOT NULL
             );
             INSERT INTO files(id, path, mtime, size) VALUES
               (1, '/a.png', 100, 0),
               (2, '/b.png', 200, 0),
               (3, '/c.png', 300, 0);
             INSERT INTO tags(id, tag, namespace) VALUES
               (1, '1girl', NULL),
               (2, '1girl, solo', NULL),
               (3, '1girl,  solo', NULL),
               (4, 'natural', NULL),
               (5, 'nature', 'meta');
             INSERT INTO file_tags(file_id, tag_id, weight) VALUES
               (1, 4, 1.0),
               (2, 5, 1.0),
               (3, 5, 1.0);
             INSERT INTO templates(id, raw_prompt) VALUES
               (1, 'x <lora:Alpha:0.7> y <lora:alpha:0.8>'),
               (2, 'x <lora:Beta-2:1> y'),
               (3, 'embedding:emb_one, <hypernet:Emb-Two>'),
               (4, '(embedding:emb_three)');",
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

    async fn json_body(response: axum::response::Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn suggest_tags_escapes_like_and_deduplicates_normalized_tags() {
        let response = suggest(
            State(test_state().await),
            None,
            Query(SuggestQuery {
                q: Some("1g".to_string()),
                query: None,
                limit: Some(10),
                n: None,
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["q"], "1g");
        assert_eq!(
            value["suggestions"],
            serde_json::json!(["1girl", "1girl, solo"])
        );
    }

    #[test]
    fn prompt_extractors_sort_and_deduplicate_case_insensitively() {
        let lora = extract_lora_names(
            &[
                "x <lora:Beta-2:1> y".to_string(),
                "x <lora:alpha:0.7> <lora:Alpha:0.8>".to_string(),
            ],
            "a",
            20,
        );
        assert_eq!(lora, vec!["alpha"]);

        let embedding = extract_embedding_names(
            &[
                "embedding:emb_one <hypernet:Emb-Two>".to_string(),
                "(embedding:emb_three)".to_string(),
            ],
            "emb",
            20,
        );
        assert_eq!(embedding, vec!["Emb-Two", "emb_one", "emb_three"]);
    }

    #[tokio::test]
    async fn tags_suggest_returns_api_result_data_sorted_by_count() {
        let response = tags_suggest(
            State(test_state().await),
            None,
            Query(TagsSuggestQuery {
                q: Some("nat".to_string()),
                limit: Some(10),
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["error"], serde_json::Value::Null);
        assert_eq!(value["data"][0]["tag"], "nature");
        assert_eq!(value["data"][0]["file_count"], 2);
        assert_eq!(value["data"][1]["tag"], "natural");
        assert_eq!(value["data"][1]["file_count"], 1);
    }
}

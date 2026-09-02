use std::collections::{HashMap, HashSet};

use axum::{
    extract::{Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use chrono::{DateTime, NaiveDate, Utc};
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite};

use crate::state::SharedState;

fn plain_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"error": message}))).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{message}");
    plain_error("internal_server_error", StatusCode::INTERNAL_SERVER_ERROR)
}

fn int_param(
    params: &HashMap<String, String>,
    name: &str,
    default: i64,
    min: i64,
    max: i64,
) -> i64 {
    params
        .get(name)
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(default)
        .clamp(min, max)
}

fn parse_date_param(params: &HashMap<String, String>, name: &str) -> i64 {
    let Some(raw) = params
        .get(name)
        .map(String::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
    else {
        return 0;
    };
    if let Ok(ts) = raw.parse::<i64>() {
        return ts;
    }
    if let Ok(dt) = DateTime::parse_from_rfc3339(&raw.replace('Z', "+00:00")) {
        return dt.timestamp();
    }
    if let Ok(date) = NaiveDate::parse_from_str(raw, "%Y-%m-%d") {
        return date
            .and_hms_opt(0, 0, 0)
            .map(|dt| dt.and_utc().timestamp())
            .unwrap_or(0);
    }
    if let Ok(dt) = raw.parse::<DateTime<Utc>>() {
        return dt.timestamp();
    }
    0
}

async fn table_exists(state: &SharedState, table: &str) -> Result<bool, sqlx::Error> {
    let count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
    )
    .bind(table)
    .fetch_one(&state.db_read)
    .await?;
    Ok(count > 0)
}

pub(crate) async fn columns(
    state: &SharedState,
    table: &str,
) -> Result<HashSet<String>, sqlx::Error> {
    let rows = sqlx::query(&format!("PRAGMA table_info({table})"))
        .fetch_all(&state.db_read)
        .await?;
    Ok(rows
        .iter()
        .filter_map(|row| row.try_get::<String, _>("name").ok())
        .collect())
}

pub(crate) fn conversation_json(row: &sqlx::sqlite::SqliteRow, cols: &HashSet<String>) -> Value {
    let mut obj = serde_json::Map::new();
    obj.insert("id".to_string(), json!(row.get::<i64, _>("id")));
    obj.insert("source".to_string(), json!(row.get::<String, _>("source")));
    obj.insert(
        "external_id".to_string(),
        json!(row
            .try_get::<Option<String>, _>("external_id")
            .unwrap_or(None)),
    );
    obj.insert("title".to_string(), json!(row.get::<String, _>("title")));
    obj.insert("model".to_string(), json!(row.get::<String, _>("model")));
    obj.insert(
        "created_at".to_string(),
        json!(row.get::<i64, _>("created_at")),
    );
    obj.insert(
        "updated_at".to_string(),
        json!(row.get::<i64, _>("updated_at")),
    );
    obj.insert(
        "message_count".to_string(),
        json!(row.get::<i64, _>("message_count")),
    );
    obj.insert(
        "imported_at".to_string(),
        json!(row.get::<i64, _>("imported_at")),
    );
    if cols.contains("summary") {
        obj.insert(
            "summary".to_string(),
            json!(row.try_get::<Option<String>, _>("summary").unwrap_or(None)),
        );
    }
    if cols.contains("ai_processed_at") {
        obj.insert(
            "ai_processed_at".to_string(),
            json!(row
                .try_get::<Option<i64>, _>("ai_processed_at")
                .unwrap_or(None)),
        );
    }
    if cols.contains("ai_model") {
        obj.insert(
            "ai_model".to_string(),
            json!(row.try_get::<Option<String>, _>("ai_model").unwrap_or(None)),
        );
    }
    if cols.contains("language") {
        obj.insert(
            "language".to_string(),
            json!(row.try_get::<Option<String>, _>("language").unwrap_or(None)),
        );
    }
    if cols.contains("language_confidence") {
        obj.insert(
            "language_confidence".to_string(),
            json!(row
                .try_get::<Option<f64>, _>("language_confidence")
                .unwrap_or(None)),
        );
    }
    Value::Object(obj)
}

pub(crate) fn message_json(row: &sqlx::sqlite::SqliteRow) -> Value {
    json!({
        "id": row.get::<i64, _>("id"),
        "conversation_id": row.get::<i64, _>("conversation_id"),
        "role": row.get::<String, _>("role"),
        "content": row.get::<String, _>("content"),
        "created_at": row.get::<i64, _>("created_at"),
        "seq": row.get::<i64, _>("seq"),
    })
}

fn cjk_query(query: &str) -> bool {
    query.chars().any(|ch| {
        matches!(
            ch as u32,
            0x2E80..=0x9FFF | 0xF900..=0xFAFF | 0xAC00..=0xD7AF | 0xFF65..=0xFF9F
        )
    })
}

pub async fn conversations(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let cols = match columns(&state, "chat_conversations").await {
        Ok(cols) => cols,
        Err(error) => return internal_error(error, "failed to inspect chat conversations"),
    };
    let source = params
        .get("source")
        .map(String::as_str)
        .unwrap_or("")
        .trim();
    let model = params.get("model").map(String::as_str).unwrap_or("").trim();
    let query = params.get("query").map(String::as_str).unwrap_or("").trim();
    let mut date_from = int_param(&params, "date_from", 0, 0, i64::MAX);
    let mut date_to = int_param(&params, "date_to", 0, 0, i64::MAX);
    let after_ts = parse_date_param(&params, "after");
    let before_ts = parse_date_param(&params, "before");
    if after_ts != 0 && date_from == 0 {
        date_from = after_ts;
    }
    if before_ts != 0 && date_to == 0 {
        date_to = before_ts;
    }
    let sort_col = match params
        .get("sort")
        .map(String::as_str)
        .unwrap_or("updated_at")
    {
        "created_at" => "created_at",
        "title" => "title",
        "message_count" => "message_count",
        _ => "updated_at",
    };
    let limit = int_param(&params, "limit", 50, 1, 500);
    let offset = int_param(&params, "offset", 0, 0, i64::MAX);
    let rows = if query.is_empty() {
        let mut builder = QueryBuilder::<Sqlite>::new("SELECT * FROM chat_conversations WHERE 1=1");
        bind_conversation_filters(&mut builder, source, model, date_from, date_to);
        builder
            .push(format!(" ORDER BY {sort_col} DESC LIMIT "))
            .push_bind(limit)
            .push(" OFFSET ")
            .push_bind(offset);
        builder.build().fetch_all(&state.db_read).await
    } else {
        conversation_search_rows(
            &state,
            ConversationSearch {
                query,
                source,
                model,
                date_from,
                date_to,
                limit,
                offset,
            },
        )
        .await
    };
    let rows = match rows {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list chat conversations"),
    };
    let total = match count_conversations(&state, query, source, model).await {
        Ok(total) => total,
        Err(error) => return internal_error(error, "failed to count chat conversations"),
    };
    let convs = rows
        .iter()
        .map(|row| conversation_json(row, &cols))
        .collect::<Vec<_>>();
    Json(json!({"conversations": convs, "total": total})).into_response()
}

fn bind_conversation_filters<'a>(
    builder: &mut QueryBuilder<'a, Sqlite>,
    source: &'a str,
    model: &'a str,
    date_from: i64,
    date_to: i64,
) {
    if !source.is_empty() {
        builder.push(" AND source = ").push_bind(source);
    }
    if !model.is_empty() {
        builder
            .push(" AND model LIKE ")
            .push_bind(format!("%{model}%"));
    }
    if date_from != 0 {
        builder.push(" AND created_at >= ").push_bind(date_from);
    }
    if date_to != 0 {
        builder.push(" AND created_at <= ").push_bind(date_to);
    }
}

struct ConversationSearch<'a> {
    query: &'a str,
    source: &'a str,
    model: &'a str,
    date_from: i64,
    date_to: i64,
    limit: i64,
    offset: i64,
}

async fn conversation_search_rows(
    state: &SharedState,
    search: ConversationSearch<'_>,
) -> Result<Vec<sqlx::sqlite::SqliteRow>, sqlx::Error> {
    let query = search.query;
    let use_like = cjk_query(query);
    let mut builder = if use_like {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT DISTINCT c.* FROM chat_messages m JOIN chat_conversations c ON c.id = m.conversation_id WHERE m.content LIKE ",
        );
        b.push_bind(format!("%{query}%"));
        b
    } else {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT DISTINCT c.* FROM chat_messages_fts f JOIN chat_messages m ON m.id = f.rowid JOIN chat_conversations c ON c.id = m.conversation_id WHERE chat_messages_fts MATCH ",
        );
        b.push_bind(query);
        b
    };
    if !search.source.is_empty() {
        builder.push(" AND c.source = ").push_bind(search.source);
    }
    if !search.model.is_empty() {
        builder
            .push(" AND c.model LIKE ")
            .push_bind(format!("%{}%", search.model));
    }
    if search.date_from != 0 {
        builder
            .push(" AND c.created_at >= ")
            .push_bind(search.date_from);
    }
    if search.date_to != 0 {
        builder
            .push(" AND c.created_at <= ")
            .push_bind(search.date_to);
    }
    builder
        .push(" ORDER BY c.updated_at DESC LIMIT ")
        .push_bind(search.limit)
        .push(" OFFSET ")
        .push_bind(search.offset);
    builder.build().fetch_all(&state.db_read).await
}

async fn count_conversations(
    state: &SharedState,
    query: &str,
    source: &str,
    model: &str,
) -> Result<i64, sqlx::Error> {
    let mut builder = if query.is_empty() {
        QueryBuilder::<Sqlite>::new("SELECT COUNT(*) FROM chat_conversations WHERE 1=1")
    } else if cjk_query(query) {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT COUNT(DISTINCT c.id) FROM chat_messages m JOIN chat_conversations c ON c.id = m.conversation_id WHERE m.content LIKE ",
        );
        b.push_bind(format!("%{query}%"));
        b
    } else {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT COUNT(DISTINCT c.id) FROM chat_messages_fts f JOIN chat_messages m ON m.id = f.rowid JOIN chat_conversations c ON c.id = m.conversation_id WHERE chat_messages_fts MATCH ",
        );
        b.push_bind(query);
        b
    };
    if !source.is_empty() {
        builder
            .push(if query.is_empty() {
                " AND source = "
            } else {
                " AND c.source = "
            })
            .push_bind(source);
    }
    if !model.is_empty() {
        builder
            .push(if query.is_empty() {
                " AND model LIKE "
            } else {
                " AND c.model LIKE "
            })
            .push_bind(format!("%{model}%"));
    }
    builder.build_query_scalar().fetch_one(&state.db_read).await
}

pub async fn conversation_detail(
    State(state): State<SharedState>,
    AxumPath(conv_id): AxumPath<i64>,
) -> Response {
    let cols = match columns(&state, "chat_conversations").await {
        Ok(cols) => cols,
        Err(error) => return internal_error(error, "failed to inspect chat conversations"),
    };
    let row = match sqlx::query("SELECT * FROM chat_conversations WHERE id = ?")
        .bind(conv_id)
        .fetch_optional(&state.db_read)
        .await
    {
        Ok(Some(row)) => row,
        Ok(None) => return plain_error("not found", StatusCode::NOT_FOUND),
        Err(error) => return internal_error(error, "failed to get chat conversation"),
    };
    let mut conv = conversation_json(&row, &cols);
    let messages = match sqlx::query(
        "SELECT id, conversation_id, role, content, created_at, seq FROM chat_messages WHERE conversation_id = ? ORDER BY seq",
    )
    .bind(conv_id)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows.iter().map(message_json).collect::<Vec<_>>(),
        Err(error) => return internal_error(error, "failed to get chat messages"),
    };
    conv["messages"] = json!(messages);
    Json(conv).into_response()
}

pub async fn search(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let query = params.get("query").map(String::as_str).unwrap_or("").trim();
    if query.is_empty() {
        return plain_error("query is required", StatusCode::BAD_REQUEST);
    }
    let source = params
        .get("source")
        .map(String::as_str)
        .unwrap_or("")
        .trim();
    let limit = int_param(&params, "limit", 50, 1, 200);
    let offset = int_param(&params, "offset", 0, 0, i64::MAX);
    if params
        .get("group_by")
        .map(String::as_str)
        .unwrap_or("")
        .trim()
        == "conversation"
    {
        return grouped_search(&state, query, source, limit).await;
    }
    let use_like = cjk_query(query);
    let mut builder = if use_like {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT m.id, m.conversation_id, m.role, m.created_at, m.seq, m.content AS snippet, c.title AS conv_title, c.source AS conv_source FROM chat_messages m JOIN chat_conversations c ON c.id = m.conversation_id WHERE m.content LIKE ",
        );
        b.push_bind(format!("%{query}%"));
        b
    } else {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT m.id, m.conversation_id, m.role, m.created_at, m.seq, snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 40) AS snippet, c.title AS conv_title, c.source AS conv_source FROM chat_messages_fts f JOIN chat_messages m ON m.id = f.rowid JOIN chat_conversations c ON c.id = m.conversation_id WHERE chat_messages_fts MATCH ",
        );
        b.push_bind(query);
        b
    };
    if !source.is_empty() {
        builder.push(" AND c.source = ").push_bind(source);
    }
    builder
        .push(if use_like {
            " ORDER BY m.created_at DESC LIMIT "
        } else {
            " ORDER BY bm25(chat_messages_fts) LIMIT "
        })
        .push_bind(limit)
        .push(" OFFSET ")
        .push_bind(offset);
    let rows = match builder.build().fetch_all(&state.db_read).await {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to search chat messages"),
    };
    let results = rows.iter().map(search_row_json).collect::<Vec<_>>();
    Json(json!({"results": results, "query": query})).into_response()
}

fn search_row_json(row: &sqlx::sqlite::SqliteRow) -> Value {
    json!({
        "id": row.get::<i64, _>("id"),
        "conversation_id": row.get::<i64, _>("conversation_id"),
        "role": row.get::<String, _>("role"),
        "created_at": row.get::<i64, _>("created_at"),
        "seq": row.get::<i64, _>("seq"),
        "snippet": row.get::<String, _>("snippet"),
        "conv_title": row.get::<String, _>("conv_title"),
        "conv_source": row.get::<String, _>("conv_source"),
    })
}

async fn grouped_search(state: &SharedState, query: &str, source: &str, limit: i64) -> Response {
    let use_like = cjk_query(query);
    let mut builder = if use_like {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT c.id AS conversation_id, c.title, c.updated_at, c.source, COUNT(m.id) AS hit_count FROM chat_messages m JOIN chat_conversations c ON c.id = m.conversation_id WHERE m.content LIKE ",
        );
        b.push_bind(format!("%{query}%"));
        b
    } else {
        let mut b = QueryBuilder::<Sqlite>::new(
            "SELECT c.id AS conversation_id, c.title, c.updated_at, c.source, COUNT(m.id) AS hit_count FROM chat_messages_fts f JOIN chat_messages m ON m.id = f.rowid JOIN chat_conversations c ON c.id = m.conversation_id WHERE chat_messages_fts MATCH ",
        );
        b.push_bind(query);
        b
    };
    if !source.is_empty() {
        builder.push(" AND c.source = ").push_bind(source);
    }
    builder
        .push(" GROUP BY c.id ORDER BY hit_count DESC LIMIT ")
        .push_bind(limit);
    let rows = match builder.build().fetch_all(&state.db_read).await {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to group chat search"),
    };
    let mut groups = Vec::new();
    for row in rows {
        let conv_id = row.get::<i64, _>("conversation_id");
        let snippets = match fetch_snippets(state, query, conv_id, use_like).await {
            Ok(snippets) => snippets,
            Err(error) => return internal_error(error, "failed to fetch chat snippets"),
        };
        groups.push(json!({
            "conversation_id": conv_id,
            "title": row.get::<String, _>("title"),
            "updated_at": row.get::<i64, _>("updated_at"),
            "source": row.get::<String, _>("source"),
            "hit_count": row.get::<i64, _>("hit_count"),
            "snippets": snippets,
        }));
    }
    Json(json!({"groups": groups, "query": query})).into_response()
}

async fn fetch_snippets(
    state: &SharedState,
    query: &str,
    conv_id: i64,
    use_like: bool,
) -> Result<Vec<String>, sqlx::Error> {
    let rows = if use_like {
        sqlx::query(
            "SELECT SUBSTR(m.content, 1, 200) AS snip FROM chat_messages m WHERE m.content LIKE ? AND m.conversation_id = ? LIMIT 5",
        )
        .bind(format!("%{query}%"))
        .bind(conv_id)
        .fetch_all(&state.db_read)
        .await?
    } else {
        sqlx::query(
            "SELECT snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 40) AS snip FROM chat_messages_fts f JOIN chat_messages m ON m.id = f.rowid WHERE chat_messages_fts MATCH ? AND m.conversation_id = ? LIMIT 5",
        )
        .bind(query)
        .bind(conv_id)
        .fetch_all(&state.db_read)
        .await?
    };
    Ok(rows
        .iter()
        .filter_map(|row| row.try_get::<String, _>("snip").ok())
        .filter(|s| !s.is_empty())
        .collect())
}

pub async fn delete_conversation(
    State(state): State<SharedState>,
    AxumPath(conv_id): AxumPath<i64>,
) -> Response {
    let result = match sqlx::query("DELETE FROM chat_conversations WHERE id = ?")
        .bind(conv_id)
        .execute(&state.db)
        .await
    {
        Ok(result) => result,
        Err(error) => return internal_error(error, "failed to delete chat conversation"),
    };
    if result.rows_affected() == 0 {
        return plain_error("not found", StatusCode::NOT_FOUND);
    }
    Json(json!({"status": "deleted", "id": conv_id})).into_response()
}

pub async fn stats(State(state): State<SharedState>) -> Response {
    let rows =
        match sqlx::query("SELECT source, COUNT(*) AS cnt FROM chat_conversations GROUP BY source")
            .fetch_all(&state.db_read)
            .await
        {
            Ok(rows) => rows,
            Err(error) => return internal_error(error, "failed to get chat stats"),
        };
    let mut by_source = serde_json::Map::new();
    let mut total_conversations = 0_i64;
    for row in rows {
        let source = row.get::<String, _>("source");
        let count = row.get::<i64, _>("cnt");
        total_conversations += count;
        by_source.insert(source, json!(count));
    }
    let total_messages = match sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM chat_messages")
        .fetch_one(&state.db_read)
        .await
    {
        Ok(total) => total,
        Err(error) => return internal_error(error, "failed to count chat messages"),
    };
    Json(json!({"total_conversations": total_conversations, "total_messages": total_messages, "by_source": by_source})).into_response()
}

pub async fn text_search(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let query = params.get("q").map(String::as_str).unwrap_or("").trim();
    if query.is_empty() {
        return plain_error("q is required", StatusCode::BAD_REQUEST);
    }
    let targets = params
        .get("target")
        .map(String::as_str)
        .unwrap_or("md,chat,prompt");
    let target_set = targets.split(',').map(str::trim).collect::<HashSet<_>>();
    let limit = int_param(&params, "limit", 20, 1, 200);
    let mut results = Vec::new();
    if target_set.contains("chat") {
        match text_search_chat(&state, query, limit).await {
            Ok(items) => results.extend(items),
            Err(error) => return internal_error(error, "failed to text-search chat"),
        }
    }
    results.truncate(usize::try_from(limit).unwrap_or(20));
    Json(json!({"results": results, "query": query, "total": results.len()})).into_response()
}

async fn text_search_chat(
    state: &SharedState,
    query: &str,
    limit: i64,
) -> Result<Vec<Value>, sqlx::Error> {
    if !table_exists(state, "chat_messages_fts").await? {
        return Ok(vec![]);
    }
    let rows = if cjk_query(query) {
        sqlx::query(
            "SELECT m.id, m.conversation_id, m.role, m.content AS snippet, 0.0 AS score, c.title AS conv_title, c.source AS conv_source
             FROM chat_messages m JOIN chat_conversations c ON c.id = m.conversation_id
             WHERE m.content LIKE ? ORDER BY m.created_at DESC LIMIT ?",
        )
        .bind(format!("%{query}%"))
        .bind(limit)
        .fetch_all(&state.db_read)
        .await?
    } else {
        sqlx::query(
            "SELECT m.id, m.conversation_id, m.role, snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 40) AS snippet, bm25(chat_messages_fts) AS score, c.title AS conv_title, c.source AS conv_source
             FROM chat_messages_fts f JOIN chat_messages m ON m.id = f.rowid JOIN chat_conversations c ON c.id = m.conversation_id
             WHERE chat_messages_fts MATCH ? ORDER BY score LIMIT ?",
        )
        .bind(query)
        .bind(limit)
        .fetch_all(&state.db_read)
        .await?
    };
    Ok(rows
        .iter()
        .map(|row| {
            json!({
                "type": "chat",
                "id": row.get::<i64, _>("id"),
                "conversation_id": row.get::<i64, _>("conversation_id"),
                "role": row.get::<String, _>("role"),
                "snippet": row.get::<String, _>("snippet"),
                "score": row.get::<f64, _>("score"),
                "title": row.get::<String, _>("conv_title"),
                "source": row.get::<String, _>("conv_source"),
            })
        })
        .collect())
}

pub async fn entity_search(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let entity_type = params.get("type").map(String::as_str).unwrap_or("").trim();
    let entity_value = params.get("value").map(String::as_str).unwrap_or("").trim();
    if entity_type.is_empty() || entity_value.is_empty() {
        return plain_error("type and value are required", StatusCode::BAD_REQUEST);
    }
    let limit = int_param(&params, "limit", 50, 1, 200);
    let exact = params
        .get("exact")
        .map(String::as_str)
        .unwrap_or("1")
        .trim()
        == "1";
    let rows = if exact {
        sqlx::query(ENTITY_SEARCH_SQL)
            .bind(entity_type)
            .bind(entity_value)
            .bind(limit)
            .fetch_all(&state.db_read)
            .await
    } else {
        sqlx::query(ENTITY_SEARCH_LIKE_SQL)
            .bind(entity_type)
            .bind(format!("%{entity_value}%"))
            .bind(limit)
            .fetch_all(&state.db_read)
            .await
    };
    let rows = match rows {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to search chat entities"),
    };
    let conversations = rows
        .iter()
        .map(entity_conversation_json)
        .collect::<Vec<_>>();
    Json(json!({"conversations": conversations, "total": conversations.len()})).into_response()
}

const ENTITY_SEARCH_SQL: &str = "SELECT DISTINCT c.id, c.source, c.title, c.model, c.created_at, c.updated_at, c.message_count FROM chat_entities e JOIN chat_conversations c ON c.id = e.conversation_id WHERE e.entity_type = ? AND e.entity_value = ? ORDER BY c.updated_at DESC LIMIT ?";
const ENTITY_SEARCH_LIKE_SQL: &str = "SELECT DISTINCT c.id, c.source, c.title, c.model, c.created_at, c.updated_at, c.message_count FROM chat_entities e JOIN chat_conversations c ON c.id = e.conversation_id WHERE e.entity_type = ? AND e.entity_value LIKE ? ORDER BY c.updated_at DESC LIMIT ?";

fn entity_conversation_json(row: &sqlx::sqlite::SqliteRow) -> Value {
    json!({
        "id": row.get::<i64, _>("id"),
        "source": row.get::<String, _>("source"),
        "title": row.get::<String, _>("title"),
        "model": row.get::<String, _>("model"),
        "created_at": row.get::<i64, _>("created_at"),
        "updated_at": row.get::<i64, _>("updated_at"),
        "message_count": row.get::<i64, _>("message_count"),
    })
}

pub async fn conversation_entities(
    State(state): State<SharedState>,
    AxumPath(conv_id): AxumPath<i64>,
) -> Response {
    let exists =
        match sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM chat_conversations WHERE id = ?")
            .bind(conv_id)
            .fetch_one(&state.db_read)
            .await
        {
            Ok(count) => count > 0,
            Err(error) => return internal_error(error, "failed to check chat conversation"),
        };
    if !exists {
        return plain_error("not found", StatusCode::NOT_FOUND);
    }
    let rows = match sqlx::query("SELECT id, conversation_id, message_id, entity_type, entity_value FROM chat_entities WHERE conversation_id = ? ORDER BY entity_type, entity_value")
        .bind(conv_id)
        .fetch_all(&state.db_read)
        .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list chat entities"),
    };
    let entities = rows
        .iter()
        .map(|row| {
            json!({
                "id": row.get::<i64, _>("id"),
                "conversation_id": row.get::<i64, _>("conversation_id"),
                "message_id": row.try_get::<Option<i64>, _>("message_id").unwrap_or(None),
                "entity_type": row.get::<String, _>("entity_type"),
                "entity_value": row.get::<String, _>("entity_value"),
            })
        })
        .collect::<Vec<_>>();
    Json(json!({"entities": entities, "conversation_id": conv_id})).into_response()
}

pub async fn related_conversations(
    State(state): State<SharedState>,
    AxumPath(conv_id): AxumPath<i64>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let limit = int_param(&params, "limit", 10, 1, 50);
    let rows = match sqlx::query(
        "SELECT c.id, c.source, c.title, c.model, c.created_at, c.updated_at, c.message_count,
                COUNT(DISTINCT e2.entity_type || ':' || e2.entity_value) AS shared_count
         FROM chat_entities e1
         JOIN chat_entities e2 ON e2.entity_type = e1.entity_type AND e2.entity_value = e1.entity_value AND e2.conversation_id != e1.conversation_id
         JOIN chat_conversations c ON c.id = e2.conversation_id
         WHERE e1.conversation_id = ?
         GROUP BY c.id ORDER BY shared_count DESC LIMIT ?",
    )
    .bind(conv_id)
    .bind(limit)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list related chat conversations"),
    };
    let related = rows
        .iter()
        .map(|row| {
            let mut value = entity_conversation_json(row);
            value["shared_entity_count"] = json!(row.get::<i64, _>("shared_count"));
            value
        })
        .collect::<Vec<_>>();
    Json(json!({"related": related, "conversation_id": conv_id})).into_response()
}

async fn get_decisions(state: &SharedState, conv_id: i64) -> Result<Vec<Value>, sqlx::Error> {
    let rows = sqlx::query("SELECT id, conversation_id, message_id, decision_text FROM chat_decisions WHERE conversation_id = ? ORDER BY id")
        .bind(conv_id)
        .fetch_all(&state.db_read)
        .await?;
    Ok(rows.iter().map(decision_json).collect())
}

fn decision_json(row: &sqlx::sqlite::SqliteRow) -> Value {
    json!({
        "id": row.get::<i64, _>("id"),
        "conversation_id": row.get::<i64, _>("conversation_id"),
        "message_id": row.try_get::<Option<i64>, _>("message_id").unwrap_or(None),
        "decision_text": row.get::<String, _>("decision_text"),
    })
}

pub async fn topics_search(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let query = params.get("q").map(String::as_str).unwrap_or("").trim();
    if query.is_empty() {
        return plain_error("q is required", StatusCode::BAD_REQUEST);
    }
    let limit = int_param(&params, "limit", 50, 1, 200);
    let rows = match sqlx::query(
        "SELECT DISTINCT c.id, c.source, c.title, c.model, c.created_at, c.updated_at, c.message_count, c.summary, t.topic
         FROM chat_topics t JOIN chat_conversations c ON c.id = t.conversation_id
         WHERE t.topic LIKE ? ORDER BY c.updated_at DESC LIMIT ?",
    )
    .bind(format!("%{query}%"))
    .bind(limit)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to search chat topics"),
    };
    let results = rows
        .iter()
        .map(|row| {
            json!({
                "id": row.get::<i64, _>("id"),
                "source": row.get::<String, _>("source"),
                "title": row.get::<String, _>("title"),
                "model": row.get::<String, _>("model"),
                "created_at": row.get::<i64, _>("created_at"),
                "updated_at": row.get::<i64, _>("updated_at"),
                "message_count": row.get::<i64, _>("message_count"),
                "summary": row.try_get::<Option<String>, _>("summary").unwrap_or(None),
                "matched_topic": row.get::<String, _>("topic"),
            })
        })
        .collect::<Vec<_>>();
    Json(json!({"results": results, "query": query, "total": results.len()})).into_response()
}

pub async fn chat_decisions(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let conv_id_raw = params
        .get("conversation_id")
        .map(String::as_str)
        .unwrap_or("")
        .trim();
    if conv_id_raw.is_empty() {
        return plain_error("conversation_id is required", StatusCode::BAD_REQUEST);
    }
    let Ok(conv_id) = conv_id_raw.parse::<i64>() else {
        return plain_error(
            "conversation_id must be an integer",
            StatusCode::BAD_REQUEST,
        );
    };
    let decisions = match get_decisions(&state, conv_id).await {
        Ok(decisions) => decisions,
        Err(error) => return internal_error(error, "failed to get chat decisions"),
    };
    Json(json!({"decisions": decisions, "conversation_id": conv_id})).into_response()
}

pub async fn decisions_search(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let query = params.get("q").map(String::as_str).unwrap_or("").trim();
    if query.is_empty() {
        return plain_error("q is required", StatusCode::BAD_REQUEST);
    }
    let limit = int_param(&params, "limit", 50, 1, 200);
    let rows = match sqlx::query(
        "SELECT d.id, d.conversation_id, d.message_id, d.decision_text, c.title AS conv_title, c.source AS conv_source
         FROM chat_decisions d JOIN chat_conversations c ON c.id = d.conversation_id
         WHERE d.decision_text LIKE ? ORDER BY d.id DESC LIMIT ?",
    )
    .bind(format!("%{query}%"))
    .bind(limit)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to search chat decisions"),
    };
    let results = rows
        .iter()
        .map(|row| {
            json!({
                "id": row.get::<i64, _>("id"),
                "conversation_id": row.get::<i64, _>("conversation_id"),
                "message_id": row.try_get::<Option<i64>, _>("message_id").unwrap_or(None),
                "decision_text": row.get::<String, _>("decision_text"),
                "conv_title": row.get::<String, _>("conv_title"),
                "conv_source": row.get::<String, _>("conv_source"),
            })
        })
        .collect::<Vec<_>>();
    Json(json!({"results": results, "query": query, "total": results.len()})).into_response()
}

#[cfg(test)]
mod tests {
    use std::{
        collections::{HashMap, HashSet},
        sync::{Arc, Mutex},
    };

    use axum::{
        body::to_bytes,
        extract::{Path as AxumPath, Query, State},
        http::StatusCode,
    };
    use serde_json::{json, Value};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tempfile::TempDir;

    use crate::{
        auth::{PinRateLimiter, QuickLock},
        groups_index::GroupsIndexCache,
        state::{AppState, Config, SharedState},
    };

    async fn test_state() -> (SharedState, TempDir) {
        let temp = TempDir::new().unwrap();
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(SqliteConnectOptions::new().filename(":memory:"))
            .await
            .unwrap();
        sqlx::raw_sql(
            "
            CREATE TABLE chat_conversations (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                source              TEXT    NOT NULL,
                external_id         TEXT,
                title               TEXT    NOT NULL DEFAULT '',
                model               TEXT    NOT NULL DEFAULT '',
                created_at          INTEGER NOT NULL DEFAULT 0,
                updated_at          INTEGER NOT NULL DEFAULT 0,
                message_count       INTEGER NOT NULL DEFAULT 0,
                imported_at         INTEGER NOT NULL DEFAULT 0,
                summary             TEXT,
                ai_processed_at     INTEGER,
                ai_model            TEXT,
                language            TEXT DEFAULT '',
                language_confidence REAL DEFAULT 0.0
            );
            CREATE INDEX idx_chat_conv_source ON chat_conversations(source);
            CREATE INDEX idx_chat_conv_external_id ON chat_conversations(external_id);
            CREATE UNIQUE INDEX uq_chat_conv_source_extid ON chat_conversations(source, external_id);
            CREATE TABLE chat_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
                role            TEXT    NOT NULL,
                content         TEXT    NOT NULL DEFAULT '',
                created_at      INTEGER NOT NULL DEFAULT 0,
                seq             INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX idx_chat_msg_conv_id ON chat_messages(conversation_id);
            CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
                content,
                content=chat_messages, content_rowid=id,
                tokenize='unicode61'
            );
            CREATE TRIGGER chat_msg_fts_ai AFTER INSERT ON chat_messages BEGIN
                INSERT INTO chat_messages_fts(rowid, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER chat_msg_fts_au AFTER UPDATE ON chat_messages BEGIN
                INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
                INSERT INTO chat_messages_fts(rowid, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER chat_msg_fts_ad AFTER DELETE ON chat_messages BEGIN
                INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
            END;
            CREATE TABLE chat_entities (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
                message_id INTEGER,
                entity_type TEXT NOT NULL,
                entity_value TEXT NOT NULL
            );
            CREATE INDEX idx_chat_entities_type_value ON chat_entities(entity_type, entity_value);
            CREATE INDEX idx_chat_entities_conv ON chat_entities(conversation_id);
            CREATE TABLE chat_topics (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
                topic TEXT NOT NULL
            );
            CREATE INDEX idx_chat_topics_topic ON chat_topics(topic);
            CREATE TABLE chat_decisions (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
                message_id INTEGER,
                decision_text TEXT NOT NULL
            );
            CREATE INDEX idx_chat_decisions_conv ON chat_decisions(conversation_id);
            INSERT INTO chat_conversations(id, source, external_id, title, model, created_at, updated_at, message_count, imported_at, summary, ai_processed_at, ai_model, language, language_confidence)
            VALUES (1, 'chatgpt', 'ext-1', 'Rust Migration', 'gpt-4.1', 10, 20, 2, 30, 'summary text', 40, 'model-x', 'en', 0.9),
                   (2, 'claude', 'ext-2', 'Related', 'claude', 11, 22, 1, 31, NULL, NULL, NULL, '', 0),
                   (3, 'chatgpt', NULL, 'Null Optional', 'gpt-4.1', 12, 23, 0, 32, NULL, NULL, NULL, NULL, NULL);
            INSERT INTO chat_messages(id, conversation_id, role, content, created_at, seq)
            VALUES (1, 1, 'user', 'please migrate webhook routes', 10, 0),
                   (2, 1, 'assistant', 'decision: keep proxy routes', 20, 1),
                   (3, 2, 'user', 'webhook shared entity', 11, 0);
            INSERT INTO chat_entities(id, conversation_id, message_id, entity_type, entity_value)
            VALUES (1, 1, 1, 'feature', 'webhook'),
                   (2, 2, 3, 'feature', 'webhook');
            INSERT INTO chat_topics(id, conversation_id, topic) VALUES (1, 1, 'rust migration');
            INSERT INTO chat_decisions(id, conversation_id, message_id, decision_text)
            VALUES (1, 1, 2, 'Keep runtime state routes proxied');
            ",
        )
        .execute(&pool)
        .await
        .unwrap();
        let state = Arc::new(AppState {
            effective_port: 5000,
            gateway_keys: Vec::new(),
            gateway_loopback_bypass: true,
            settings_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            infer_notify_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            scan_roots_generation: std::sync::atomic::AtomicU64::new(0),
            config: Config {
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
                config_path: temp.path().join("config.json"),
                project_root: temp.path().to_path_buf(),
                app_config: json!({}),
                cache_dir: temp.path().join("cache"),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                mcp_native: false,
                standalone: false,
                infer_standalone: true,
                active_profile: None,
                python_executable: String::new(),
            },
            db: pool.clone(),
            db_read: pool.clone(),
            vectors_db: pool.clone(),
            vectors_db_read: pool,
            clip_index: std::sync::Arc::new(
                crate::routes::clip_index::ClipIndex::new_default(std::env::temp_dir())
                    .expect("clip index test default"),
            ),
            clip_indexer: std::sync::Arc::new(crate::routes::clip_indexer::ClipIndexer::new()),
            caption_runner: std::sync::Arc::new(crate::routes::caption_runner::CaptionRunner::new()),
            s2t_runner: std::sync::Arc::new(crate::routes::s2t_runner::S2tRunner::new()),
            clip_runtime_cache: crate::state::TtlCache::new(crate::state::CLIP_RUNTIME_CACHE_TTL),
            inference_client: reqwest::Client::new(),
            python_client: reqwest::Client::new(),
            quick_lock: QuickLock::new(),
            rate_limiter: PinRateLimiter::new(),
            groups_index_cache: GroupsIndexCache::new(temp.path().join("cache")),
            proxy_hits: Mutex::new(HashMap::new()),
            fleet_log_stream_connections: Mutex::new(HashMap::new()),
            sse_hub: Arc::new(crate::sse::SseHub::new()),
            job_manager: Arc::new(crate::jobs::JobManager::new()),
            watcher: Arc::new(crate::watcher::ScanWatcher::new()),
            log_ring: Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            mcp_sessions: Arc::new(crate::mcp::session::McpSessionStore::new(1000, 20, 256)),
            approval_gate: Mutex::new(crate::approval_gate::ApprovalGate::default()),
            env: minijinja::Environment::new(),
            dist_v: "dev".to_string(),
            version: "0.0.0".to_string(),
            start_time: std::time::Instant::now(),
            scheduler_state: std::sync::OnceLock::new(),
            wd_infer: std::sync::Arc::new(std::sync::Mutex::new(std::collections::HashMap::new())),
            infer_client: None,
            infer_child: None,
            scan_manager: std::sync::OnceLock::new(),
            hailo_yolo_stream: None,
            stats_basic_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_models_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_timeline_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_resolutions_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            checkpoints_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            server_info_stats_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
        });
        (state, temp)
    }

    async fn json_body(response: axum::response::Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn conversations_list_matches_plain_jsonify_shape() {
        let (state, _temp) = test_state().await;
        let response = super::conversations(
            State(state),
            Query(HashMap::from([("limit".to_string(), "10".to_string())])),
        )
        .await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert!(body.get("ok").is_none());
        assert_eq!(body["total"], 3);
        assert_eq!(body["conversations"][0]["title"], "Null Optional");
    }

    #[tokio::test]
    async fn conversation_detail_includes_messages_and_optional_columns() {
        let (state, _temp) = test_state().await;
        let response = super::conversation_detail(State(state), AxumPath(1)).await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["summary"], "summary text");
        assert_eq!(
            body["messages"][1]["content"],
            "decision: keep proxy routes"
        );
    }

    #[tokio::test]
    async fn conversation_detail_preserves_nullable_optional_columns() {
        let (state, _temp) = test_state().await;
        let response = super::conversation_detail(State(state), AxumPath(3)).await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["external_id"], Value::Null);
        assert_eq!(body["language"], Value::Null);
        assert_eq!(body["language_confidence"], Value::Null);
    }

    #[tokio::test]
    async fn search_requires_query_with_plain_error_shape() {
        let (state, _temp) = test_state().await;
        let response = super::search(State(state), Query(HashMap::new())).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            json_body(response).await,
            json!({"error": "query is required"})
        );
    }

    #[tokio::test]
    async fn delete_conversation_round_trip_matches_python_shape() {
        let (state, _temp) = test_state().await;
        let response = super::delete_conversation(State(state.clone()), AxumPath(2)).await;

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            json_body(response).await,
            json!({"status": "deleted", "id": 2})
        );
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM chat_conversations WHERE id=2")
            .fetch_one(&state.db)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn entity_topic_and_decision_routes_return_python_keys() {
        let (state, _temp) = test_state().await;

        let entities =
            json_body(super::conversation_entities(State(state.clone()), AxumPath(1)).await).await;
        assert_eq!(entities["conversation_id"], 1);
        assert_eq!(entities["entities"][0]["entity_value"], "webhook");

        let related = json_body(
            super::related_conversations(State(state.clone()), AxumPath(1), Query(HashMap::new()))
                .await,
        )
        .await;
        assert_eq!(related["related"][0]["shared_entity_count"], 1);

        let topics = json_body(
            super::topics_search(
                State(state.clone()),
                Query(HashMap::from([("q".to_string(), "rust".to_string())])),
            )
            .await,
        )
        .await;
        assert_eq!(topics["results"][0]["matched_topic"], "rust migration");

        let decisions = json_body(
            super::decisions_search(
                State(state),
                Query(HashMap::from([("q".to_string(), "prox".to_string())])),
            )
            .await,
        )
        .await;
        assert_eq!(decisions["results"][0]["conv_title"], "Rust Migration");
    }
}

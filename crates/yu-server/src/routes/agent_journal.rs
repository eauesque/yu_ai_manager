#![allow(clippy::result_large_err)]
//! Agent governance: Action Journal reads (Phase B1).
//!
//! Native port of the SQLite-backed, deterministic journal reads:
//!   - `GET /api/agent/journal`       (`action_journal.search_journal`)
//!   - `GET /api/agent/journal/stats` (`action_journal.get_journal_stats`)
//!
//! `agent_action_journal` lives in the shared app DB, so Python and Rust read
//! identical rows — parity holds regardless of content. Sensitive params are
//! redacted at WRITE time (Python `record_action`), so reads need no extra
//! redaction. Recording (the journal write path) stays on the Python side.

use std::collections::HashMap;

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

/// Append the WHERE clause for the journal search — mirrors Python `search_journal`.
fn push_conditions(qb: &mut QueryBuilder<Sqlite>, tool_name: &str, status: &str, session_id: &str) {
    if tool_name.is_empty() && status.is_empty() && session_id.is_empty() {
        return;
    }
    qb.push(" WHERE ");
    let mut first = true;
    if !tool_name.is_empty() {
        qb.push("tool_name = ").push_bind(tool_name.to_string());
        first = false;
    }
    if !status.is_empty() {
        if !first {
            qb.push(" AND ");
        }
        qb.push("status = ").push_bind(status.to_string());
        first = false;
    }
    if !session_id.is_empty() {
        if !first {
            qb.push(" AND ");
        }
        qb.push("session_id = ").push_bind(session_id.to_string());
    }
}

async fn table_exists(db: &SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

async fn search_journal(
    db: &SqlitePool,
    tool_name: &str,
    status: &str,
    session_id: &str,
    limit: i64,
    offset: i64,
) -> Result<Value, sqlx::Error> {
    if !table_exists(db, "agent_action_journal").await? {
        return Ok(json!({"items": [], "total": 0, "limit": limit, "offset": offset}));
    }
    let mut count_qb = QueryBuilder::<Sqlite>::new("SELECT COUNT(*) FROM agent_action_journal");
    push_conditions(&mut count_qb, tool_name, status, session_id);
    let total: i64 = count_qb.build_query_scalar().fetch_one(db).await?;

    let mut qb = QueryBuilder::<Sqlite>::new(
        "SELECT id, session_id, timestamp, tool_name, params_json, result_summary, \
         status, duration_ms, caller_info, affected_count FROM agent_action_journal",
    );
    push_conditions(&mut qb, tool_name, status, session_id);
    qb.push(" ORDER BY id DESC LIMIT ")
        .push_bind(limit)
        .push(" OFFSET ")
        .push_bind(offset);
    let rows = qb.build().fetch_all(db).await?;

    let items: Vec<Value> = rows
        .iter()
        .map(|r| {
            json!({
                "id": r.get::<i64, _>(0),
                "session_id": r.get::<Option<String>, _>(1),
                "timestamp": r.get::<Option<String>, _>(2),
                "tool_name": r.get::<Option<String>, _>(3),
                "params_json": r.get::<Option<String>, _>(4),
                "result_summary": r.get::<Option<String>, _>(5),
                "status": r.get::<Option<String>, _>(6),
                "duration_ms": r.get::<i64, _>(7),
                "caller_info": r.get::<Option<String>, _>(8),
                "affected_count": r.get::<i64, _>(9),
            })
        })
        .collect();

    Ok(json!({"items": items, "total": total, "limit": limit, "offset": offset}))
}

async fn journal_stats(db: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(db, "agent_action_journal").await? {
        return Ok(
            json!({"total_actions": 0, "by_status": {}, "top_tools": [], "total_sessions": 0}),
        );
    }
    // by_status + total derived from one GROUP BY (mirrors Python).
    let status_rows =
        sqlx::query("SELECT status, COUNT(*) FROM agent_action_journal GROUP BY status")
            .fetch_all(db)
            .await?;
    let mut by_status = serde_json::Map::new();
    let mut total: i64 = 0;
    for row in &status_rows {
        let status: Option<String> = row.get(0);
        let count: i64 = row.get(1);
        total += count;
        by_status.insert(status.unwrap_or_default(), json!(count));
    }

    let tool_rows = sqlx::query(
        "SELECT tool_name, COUNT(*) as cnt FROM agent_action_journal \
         GROUP BY tool_name ORDER BY cnt DESC LIMIT 20",
    )
    .fetch_all(db)
    .await?;
    let top_tools: Vec<Value> = tool_rows
        .iter()
        .map(|r| json!({"tool_name": r.get::<Option<String>, _>(0), "count": r.get::<i64, _>(1)}))
        .collect();

    let total_sessions: i64 =
        sqlx::query_scalar("SELECT COUNT(DISTINCT session_id) FROM agent_action_journal")
            .fetch_one(db)
            .await?;

    Ok(json!({
        "total_actions": total,
        "by_status": Value::Object(by_status),
        "top_tools": top_tools,
        "total_sessions": total_sessions,
    }))
}

/// Records one row in `agent_action_journal`. Best-effort: a write failure
/// (e.g. table missing on a not-yet-migrated DB) is swallowed rather than
/// propagated, matching Python `record_action`'s `except Exception` — a
/// broken audit trail must not block the operation being audited.
/// `params_json`/`caller_info`/`reversible`/`undo_params_json` are left to
/// their schema defaults; this covers the MCP dispatch use case (Scope
/// Fence/kill-switch denials and tool executions), not the full journal
/// feature set.
pub async fn record_action(
    db: &SqlitePool,
    session_id: &str,
    tool_name: &str,
    status: &str,
    duration_ms: i64,
    result_summary: &str,
) {
    let timestamp = chrono::Utc::now().to_rfc3339();
    let result = sqlx::query(
        "INSERT INTO agent_action_journal(session_id, timestamp, tool_name, status, duration_ms, result_summary) \
         VALUES (?, ?, ?, ?, ?, ?)",
    )
    .bind(session_id)
    .bind(timestamp)
    .bind(tool_name)
    .bind(status)
    .bind(duration_ms)
    .bind(result_summary)
    .execute(db)
    .await;
    // Non-blocking (the audited operation must not fail on a broken audit
    // trail), but not silent: an unobserved write failure defeats the
    // journal's purpose (COVENANT Liber IV.ii, "Ratio audit disactivari non
    // potest" — audit cannot be silently disabled), matching Python
    // `record_action`'s `logger.warning` on the same failure mode.
    if let Err(e) = result {
        tracing::warn!("agent_action_journal write failed for tool '{tool_name}': {e}");
    }
}

/// GET /api/agent/journal — search the action journal.
pub async fn agent_journal(
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
    let tool_name = params.get("tool_name").cloned().unwrap_or_default();
    let status = params.get("status").cloned().unwrap_or_default();
    let session_id = params.get("session_id").cloned().unwrap_or_default();
    // Python: limit = max(1, min(int(...|50), 200)); offset = max(int(...|0), 0).
    let limit = params
        .get("limit")
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(50)
        .clamp(1, 200);
    let offset = params
        .get("offset")
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(0)
        .max(0);

    match search_journal(
        &state.db_read,
        &tool_name,
        &status,
        &session_id,
        limit,
        offset,
    )
    .await
    {
        Ok(result) => api_result(result),
        Err(error) => internal_error(error, "failed to search action journal"),
    }
}

/// GET /api/agent/journal/stats — action journal statistics.
pub async fn agent_journal_stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    match journal_stats(&state.db_read).await {
        Ok(result) => api_result(result),
        Err(error) => internal_error(error, "failed to get journal stats"),
    }
}

/// GET /api/agent/undoable — list undo-able actions from agent_action_journal.
pub async fn agent_undoable(
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
    let session_id = params.get("session_id").cloned().unwrap_or_default();
    let limit = params
        .get("limit")
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(50)
        .clamp(1, 200);

    match undoable_actions(&state.db_read, &session_id, limit).await {
        Ok(items) => {
            let count = items.len();
            api_result(json!({"items": items, "count": count}))
        }
        Err(error) => internal_error(error, "failed to get undoable actions"),
    }
}

async fn undoable_actions(
    pool: &SqlitePool,
    session_id: &str,
    limit: i64,
) -> Result<Vec<Value>, sqlx::Error> {
    if !table_exists(pool, "agent_action_journal").await? {
        return Ok(vec![]);
    }
    let mut qb = QueryBuilder::new(
        "SELECT id, session_id, timestamp, tool_name, params_json, undo_params_json, affected_count \
         FROM agent_action_journal \
         WHERE reversible = 1 AND undone = 0 AND status = 'success'",
    );
    if !session_id.is_empty() {
        qb.push(" AND session_id = ")
            .push_bind(session_id.to_string());
    }
    qb.push(" ORDER BY id DESC LIMIT ").push_bind(limit);

    let rows = qb.build().fetch_all(pool).await?;
    Ok(rows
        .iter()
        .map(|r| {
            json!({
                "id": r.get::<i64, _>(0),
                "session_id": r.get::<String, _>(1),
                "timestamp": r.get::<String, _>(2),
                "tool_name": r.get::<String, _>(3),
                "params_json": r.get::<Option<String>, _>(4),
                "undo_params_json": r.get::<Option<String>, _>(5),
                "affected_count": r.get::<Option<i64>, _>(6),
            })
        })
        .collect())
}

/// Mirror Python `api_result` success path: merge payload at top level, ensure
/// ok/error/data. (journal endpoints never return ok=false.)
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
    use std::str::FromStr;

    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    async fn seeded_pool() -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE agent_action_journal (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                timestamp TEXT,
                tool_name TEXT,
                params_json TEXT,
                result_summary TEXT,
                status TEXT,
                duration_ms INTEGER DEFAULT 0,
                caller_info TEXT,
                affected_count INTEGER DEFAULT 0,
                reversible INTEGER DEFAULT 0,
                undo_params_json TEXT
             );
             INSERT INTO agent_action_journal(id, session_id, timestamp, tool_name, status, duration_ms, affected_count)
             VALUES
               (1, 's1', 't1', 'set_tags', 'success', 5, 1),
               (2, 's1', 't2', 'delete_thing', 'error', 3, 0),
               (3, 's2', 't3', 'set_tags', 'success', 7, 2);",
        )
        .execute(&pool)
        .await
        .unwrap();
        pool
    }

    #[tokio::test]
    async fn search_returns_all_desc_with_total() {
        let pool = seeded_pool().await;
        let result = search_journal(&pool, "", "", "", 50, 0).await.unwrap();
        assert_eq!(result["total"], 3);
        let items = result["items"].as_array().unwrap();
        assert_eq!(items.len(), 3);
        assert_eq!(items[0]["id"], 3); // ORDER BY id DESC
        assert_eq!(items[0]["tool_name"], "set_tags");
        assert_eq!(result["limit"], 50);
        assert_eq!(result["offset"], 0);
    }

    #[tokio::test]
    async fn search_filters_by_tool_and_status() {
        let pool = seeded_pool().await;
        let result = search_journal(&pool, "set_tags", "success", "", 50, 0)
            .await
            .unwrap();
        assert_eq!(result["total"], 2);
        let ids: Vec<i64> = result["items"]
            .as_array()
            .unwrap()
            .iter()
            .map(|i| i["id"].as_i64().unwrap())
            .collect();
        assert_eq!(ids, vec![3, 1]);
    }

    #[tokio::test]
    async fn search_filters_by_session() {
        let pool = seeded_pool().await;
        let result = search_journal(&pool, "", "", "s2", 50, 0).await.unwrap();
        assert_eq!(result["total"], 1);
        assert_eq!(result["items"][0]["id"], 3);
    }

    #[tokio::test]
    async fn search_respects_limit_offset() {
        let pool = seeded_pool().await;
        let result = search_journal(&pool, "", "", "", 1, 1).await.unwrap();
        assert_eq!(result["total"], 3);
        let items = result["items"].as_array().unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0]["id"], 2); // DESC, offset 1
    }

    #[tokio::test]
    async fn stats_aggregates_status_tools_sessions() {
        let pool = seeded_pool().await;
        let result = journal_stats(&pool).await.unwrap();
        assert_eq!(result["total_actions"], 3);
        assert_eq!(result["by_status"]["success"], 2);
        assert_eq!(result["by_status"]["error"], 1);
        assert_eq!(result["total_sessions"], 2);
        // top_tools sorted by count desc; set_tags(2) before delete_thing(1).
        let top = result["top_tools"].as_array().unwrap();
        assert_eq!(top[0]["tool_name"], "set_tags");
        assert_eq!(top[0]["count"], 2);
    }
}

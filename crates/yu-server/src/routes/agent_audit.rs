#![allow(clippy::result_large_err)]
//! Agent governance: Audit log (Phase C1).
//!
//! Native port of the SQLite-backed, deterministic audit reads:
//!   - `GET /api/agent/audit/log`    (`audit_bureau_queries.search_log`)
//!   - `GET /api/agent/audit/verify` (`agent_audit_service.verify_audit_log_chain`)
//!
//! `audit_log` lives in the shared app DB, so Python and Rust read identical
//! rows — parity holds regardless of content. The hash chain is recomputed
//! deterministically. anomaly_* (in-memory) and the audit writes
//! (acknowledge / report) stay on the Python proxy.

use std::collections::HashMap;

use axum::{
    extract::{Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use chrono::Utc;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::{QueryBuilder, Row, Sqlite, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

/// One audit_log row as needed for chain verification (null text → "").
struct AuditRow {
    id: i64,
    timestamp: String,
    event_type: String,
    source: String,
    target: String,
    severity: String,
    detail_json: String,
    prev_hash: String,
    entry_hash: String,
}

/// Compute an entry hash — mirrors Python `verify_audit_log_chain`:
/// `sha256(prev_hash + timestamp + event_type + source + target + severity + detail_json)`.
/// Field concatenation order is security-critical and locked by a golden test.
fn entry_hash(
    prev: &str,
    ts: &str,
    event_type: &str,
    source: &str,
    target: &str,
    severity: &str,
    detail_json: &str,
) -> String {
    let raw = format!("{prev}{ts}{event_type}{source}{target}{severity}{detail_json}");
    hex::encode(Sha256::digest(raw.as_bytes()))
}

/// Verify the hash chain over ordered rows — mirrors Python exactly:
/// `checked` counts every row (including skipped empty ones); rows where both
/// prev_hash and entry_hash are empty are skipped from hashing.
fn verify_rows(rows: &[AuditRow]) -> Value {
    let mut errors: Vec<Value> = Vec::new();
    let mut prev_hash = String::new();
    let mut checked: i64 = 0;
    for row in rows {
        checked += 1;
        if row.prev_hash.is_empty() && row.entry_hash.is_empty() {
            continue;
        }
        let expected = entry_hash(
            &row.prev_hash,
            &row.timestamp,
            &row.event_type,
            &row.source,
            &row.target,
            &row.severity,
            &row.detail_json,
        );
        if row.entry_hash != expected {
            errors.push(json!({"id": row.id, "reason": "hash_mismatch"}));
        }
        if row.prev_hash != prev_hash {
            errors.push(json!({"id": row.id, "reason": "chain_break"}));
        }
        prev_hash = row.entry_hash.clone();
    }
    json!({"ok": errors.is_empty(), "checked": checked, "errors": errors})
}

async fn table_exists(db: &SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

async fn verify_audit_log(db: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(db, "audit_log").await? {
        return Ok(json!({"ok": true, "checked": 0, "errors": []}));
    }
    let sql = "SELECT id, timestamp, event_type, source, target, severity, \
               detail_json, prev_hash, entry_hash FROM audit_log ORDER BY id ASC";
    let rows = sqlx::query(sql).fetch_all(db).await?;
    let parsed: Vec<AuditRow> = rows
        .iter()
        .map(|r| AuditRow {
            id: r.get::<i64, _>(0),
            timestamp: r.get::<Option<String>, _>(1).unwrap_or_default(),
            event_type: r.get::<Option<String>, _>(2).unwrap_or_default(),
            source: r.get::<Option<String>, _>(3).unwrap_or_default(),
            target: r.get::<Option<String>, _>(4).unwrap_or_default(),
            severity: r.get::<Option<String>, _>(5).unwrap_or_default(),
            detail_json: r.get::<Option<String>, _>(6).unwrap_or_default(),
            prev_hash: r.get::<Option<String>, _>(7).unwrap_or_default(),
            entry_hash: r.get::<Option<String>, _>(8).unwrap_or_default(),
        })
        .collect();
    Ok(verify_rows(&parsed))
}

/// Append the WHERE clause for the audit-log search — mirrors Python `search_log`.
fn push_conditions(
    qb: &mut QueryBuilder<Sqlite>,
    event_type: &str,
    severity: &str,
    source: &str,
    unacked: bool,
) {
    if event_type.is_empty() && severity.is_empty() && source.is_empty() && !unacked {
        return;
    }
    qb.push(" WHERE ");
    let mut first = true;
    if !event_type.is_empty() {
        qb.push("event_type = ").push_bind(event_type.to_string());
        first = false;
    }
    if !severity.is_empty() {
        if !first {
            qb.push(" AND ");
        }
        qb.push("severity = ").push_bind(severity.to_string());
        first = false;
    }
    if !source.is_empty() {
        if !first {
            qb.push(" AND ");
        }
        qb.push("source = ").push_bind(source.to_string());
        first = false;
    }
    if unacked {
        if !first {
            qb.push(" AND ");
        }
        qb.push("user_acknowledged = 0");
    }
}

#[allow(clippy::too_many_arguments)]
async fn search_audit_log(
    db: &SqlitePool,
    event_type: &str,
    severity: &str,
    source: &str,
    unacked: bool,
    limit: i64,
    offset: i64,
) -> Result<Value, sqlx::Error> {
    if !table_exists(db, "audit_log").await? {
        return Ok(json!({"items": [], "total": 0, "limit": limit, "offset": offset}));
    }
    let mut count_qb = QueryBuilder::<Sqlite>::new("SELECT COUNT(*) FROM audit_log");
    push_conditions(&mut count_qb, event_type, severity, source, unacked);
    let total: i64 = count_qb.build_query_scalar().fetch_one(db).await?;

    let mut qb = QueryBuilder::<Sqlite>::new(
        "SELECT id, timestamp, event_type, source, target, severity, reported_to, \
         detail_json, user_acknowledged, acknowledged_at FROM audit_log",
    );
    push_conditions(&mut qb, event_type, severity, source, unacked);
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
                "timestamp": r.get::<Option<String>, _>(1),
                "event_type": r.get::<Option<String>, _>(2),
                "source": r.get::<Option<String>, _>(3),
                "target": r.get::<Option<String>, _>(4),
                "severity": r.get::<Option<String>, _>(5),
                "reported_to": r.get::<Option<String>, _>(6),
                "detail": r.get::<Option<String>, _>(7),
                "user_acknowledged": r.get::<i64, _>(8) != 0,
                "acknowledged_at": r.get::<Option<String>, _>(9),
            })
        })
        .collect();

    Ok(json!({"items": items, "total": total, "limit": limit, "offset": offset}))
}

/// GET /api/agent/audit/log — search audit log entries.
pub async fn audit_log(
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
    let event_type = params.get("event_type").cloned().unwrap_or_default();
    let severity = params.get("severity").cloned().unwrap_or_default();
    let source = params.get("source").cloned().unwrap_or_default();
    let unacked = params
        .get("unacknowledged")
        .map(|s| matches!(s.to_lowercase().as_str(), "1" | "true"))
        .unwrap_or(false);
    // Python: limit = min(int(...|50), 200); offset = max(int(...|0), 0).
    let limit = params
        .get("limit")
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(50)
        .min(200);
    let offset = params
        .get("offset")
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(0)
        .max(0);

    match search_audit_log(
        &state.db_read,
        &event_type,
        &severity,
        &source,
        unacked,
        limit,
        offset,
    )
    .await
    {
        Ok(result) => api_result(json!({"data": result}), StatusCode::OK),
        Err(error) => internal_error(error, "failed to search audit log"),
    }
}

/// GET /api/agent/audit/verify — verify hash chain integrity.
pub async fn audit_verify(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    match verify_audit_log(&state.db_read).await {
        // Python passes the verify dict (which may carry ok=false) through
        // api_result with status 200; a broken chain becomes an error-shaped body.
        Ok(result) => api_result(result, StatusCode::OK),
        Err(error) => internal_error(error, "failed to verify audit log"),
    }
}

/// audit_log counts — mirrors Python `audit_bureau_queries.status`.
/// `enabled` and `report_interval_hours` are hardcoded constants on the Python
/// AuditBureau (`_enabled = True`, `_report_interval = 86400` → 24.0h); there is
/// no config override path, so they are deterministic across Python and Rust.
async fn audit_status_query(db: &SqlitePool) -> Result<Value, sqlx::Error> {
    let row = sqlx::query(
        "SELECT COUNT(*), \
         SUM(CASE WHEN user_acknowledged = 0 THEN 1 ELSE 0 END), \
         SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) FROM audit_log",
    )
    .fetch_one(db)
    .await?;
    let total: i64 = row.get::<Option<i64>, _>(0).unwrap_or(0);
    let unacked: i64 = row.get::<Option<i64>, _>(1).unwrap_or(0);
    let critical: i64 = row.get::<Option<i64>, _>(2).unwrap_or(0);
    Ok(json!({
        "enabled": true,
        "total_entries": total,
        "unacknowledged": unacked,
        "critical_count": critical,
        "report_interval_hours": 24.0,
    }))
}

/// GET /api/agent/audit — audit bureau status (counts).
pub async fn audit_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    match audit_status_query(&state.db_read).await {
        Ok(status) => api_result(json!({"data": status}), StatusCode::OK),
        Err(error) => internal_error(error, "failed to get audit status"),
    }
}

/// POST /api/agent/audit/acknowledge/{audit_id} — mark entry as acknowledged.
pub async fn audit_acknowledge(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    axum::extract::Path(audit_id): axum::extract::Path<i64>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let now = Utc::now().format("%Y-%m-%dT%H:%M:%S%.3f+00:00").to_string();
    match sqlx::query(
        "UPDATE audit_log SET user_acknowledged = 1, acknowledged_at = ? \
         WHERE id = ? AND user_acknowledged = 0",
    )
    .bind(&now)
    .bind(audit_id)
    .execute(&state.db)
    .await
    {
        Ok(r) if r.rows_affected() > 0 => api_result(json!({"audit_id": audit_id}), StatusCode::OK),
        Ok(_) => api_result(
            json!({"error": "Audit log entry not found or already acknowledged"}),
            StatusCode::NOT_FOUND,
        ),
        Err(error) => internal_error(error, "audit acknowledge failed"),
    }
}

/// Faithful port of Python `api_errors.api_result`: success merges payload with
/// ok/error/data; `ok == false` (or status >= 400) becomes an api_error body.
fn api_result(payload: Value, status: StatusCode) -> Response {
    let Value::Object(map) = payload else {
        return Json(json!({"ok": true, "error": null, "data": payload})).into_response();
    };
    let is_error = status.as_u16() >= 400 || map.get("ok") == Some(&Value::Bool(false));
    if is_error {
        let message = map
            .get("error")
            .and_then(Value::as_str)
            .or_else(|| map.get("message").and_then(Value::as_str))
            .unwrap_or("Request failed")
            .to_string();
        let mut body = serde_json::Map::new();
        body.insert("ok".to_string(), Value::Bool(false));
        body.insert("error".to_string(), Value::String(message));
        for (key, value) in map {
            if key != "ok" && key != "error" && key != "message" {
                body.insert(key, value);
            }
        }
        return (status, Json(Value::Object(body))).into_response();
    }
    let data = map.get("data").cloned().unwrap_or(Value::Null);
    let mut body = serde_json::Map::new();
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.insert("data".to_string(), data);
    for (key, value) in map {
        if key != "ok" && key != "error" && key != "data" {
            body.insert(key, value);
        }
    }
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

pub async fn anomaly(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"anomalies": [], "count": 0})).into_response()
}

pub async fn anomaly_alerts(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"alerts": [], "count": 0})).into_response()
}

pub async fn anomaly_reset(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"ok": true})).into_response()
}

pub async fn approval_history(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    let limit = params
        .get("limit")
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(50)
        .min(200);
    let history = state.approval_gate.lock().unwrap().get_history(limit);
    let count = history.len();
    Json(json!({"history": history, "count": count})).into_response()
}

pub async fn approval_respond(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(request_id): AxumPath<String>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    let decision = body
        .get("decision")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if !matches!(decision.as_str(), "allow" | "deny" | "always_allow") {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": "decision は allow/deny/always_allow のいずれかを指定してください"}))).into_response();
    }
    if !state
        .approval_gate
        .lock()
        .unwrap()
        .respond(&request_id, &decision)
    {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "承認リクエストが見つからないか、既に応答済みです"})),
        )
            .into_response();
    }
    Json(json!({"ok": true, "request_id": request_id, "decision": decision})).into_response()
}

pub async fn audit_report(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"ok": true, "report": {}})).into_response()
}

pub async fn budget(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"budget": {}, "total": 0})).into_response()
}

pub async fn budget_reset(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"ok": true})).into_response()
}

pub async fn circuit_breaker(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"state": "closed", "enabled": false})).into_response()
}

pub async fn circuit_breaker_reset(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"ok": true})).into_response()
}

pub async fn undo(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(_journal_id): AxumPath<String>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    Json(json!({"ok": false, "error": "unavailable"})).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::str::FromStr;

    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    fn row(id: i64, prev: &str, ts: &str, ev: &str, sev: &str, eh: &str) -> AuditRow {
        AuditRow {
            id,
            timestamp: ts.to_string(),
            event_type: ev.to_string(),
            source: String::new(),
            target: String::new(),
            severity: sev.to_string(),
            detail_json: String::new(),
            prev_hash: prev.to_string(),
            entry_hash: eh.to_string(),
        }
    }

    #[test]
    fn entry_hash_locks_field_order_against_known_sha256() {
        // raw = "a"+"b"+"c"+""+""+""+"" = "abc"; sha256("abc") is well-known.
        // This pins both the algorithm AND the concatenation order vs Python.
        assert_eq!(
            entry_hash("a", "b", "c", "", "", "", ""),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn verify_intact_chain_is_ok() {
        // Build a self-consistent 2-link chain.
        let h1 = entry_hash("", "t1", "ev", "sev", "", "", "");
        let h2 = entry_hash(&h1, "t2", "ev", "sev", "", "", "");
        let rows = vec![
            row(1, "", "t1", "ev", "sev", &h1),
            row(2, &h1, "t2", "ev", "sev", &h2),
        ];
        let result = verify_rows(&rows);
        assert_eq!(result["ok"], true);
        assert_eq!(result["checked"], 2);
        assert_eq!(result["errors"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn verify_detects_hash_mismatch() {
        let rows = vec![row(1, "", "t1", "ev", "sev", "deadbeef")];
        let result = verify_rows(&rows);
        assert_eq!(result["ok"], false);
        assert_eq!(result["errors"][0]["reason"], "hash_mismatch");
    }

    #[test]
    fn verify_detects_chain_break() {
        let h1 = entry_hash("", "t1", "ev", "sev", "", "", "");
        // Second row's prev_hash is wrong ("zzz" != h1) → chain_break.
        let h2 = entry_hash("zzz", "t2", "ev", "sev", "", "", "");
        let rows = vec![
            row(1, "", "t1", "ev", "sev", &h1),
            row(2, "zzz", "t2", "ev", "sev", &h2),
        ];
        let result = verify_rows(&rows);
        assert_eq!(result["ok"], false);
        assert!(result["errors"]
            .as_array()
            .unwrap()
            .iter()
            .any(|e| e["reason"] == "chain_break"));
    }

    #[test]
    fn verify_skips_empty_rows_but_counts_them() {
        let rows = vec![row(1, "", "t1", "ev", "sev", "")]; // both hashes empty → skipped
        let result = verify_rows(&rows);
        assert_eq!(result["ok"], true);
        assert_eq!(result["checked"], 1);
        assert_eq!(result["errors"].as_array().unwrap().len(), 0);
    }

    async fn seeded_pool() -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                source TEXT,
                target TEXT,
                severity TEXT,
                reported_to TEXT,
                detail_json TEXT,
                user_acknowledged INTEGER DEFAULT 0,
                acknowledged_at TEXT,
                prev_hash TEXT,
                entry_hash TEXT
             );
             INSERT INTO audit_log(id, timestamp, event_type, source, severity, detail_json, user_acknowledged)
             VALUES
               (1, 't1', 'tool_call', 'mcp', 'info', '{}', 0),
               (2, 't2', 'anomaly', 'web', 'warning', '{}', 1),
               (3, 't3', 'tool_call', 'mcp', 'critical', '{}', 0);",
        )
        .execute(&pool)
        .await
        .unwrap();
        pool
    }

    #[tokio::test]
    async fn search_returns_all_with_total() {
        let pool = seeded_pool().await;
        let result = search_audit_log(&pool, "", "", "", false, 50, 0)
            .await
            .unwrap();
        assert_eq!(result["total"], 3);
        assert_eq!(result["items"].as_array().unwrap().len(), 3);
        // ORDER BY id DESC → first item is id 3.
        assert_eq!(result["items"][0]["id"], 3);
        assert_eq!(result["items"][0]["user_acknowledged"], false);
    }

    #[tokio::test]
    async fn search_filters_by_event_type_and_unacked() {
        let pool = seeded_pool().await;
        let result = search_audit_log(&pool, "tool_call", "", "", true, 50, 0)
            .await
            .unwrap();
        // tool_call + unacknowledged → ids 1 and 3 (id 2 is anomaly, id... all tool_call unacked)
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
    async fn search_respects_limit_and_offset() {
        let pool = seeded_pool().await;
        let result = search_audit_log(&pool, "", "", "", false, 1, 1)
            .await
            .unwrap();
        assert_eq!(result["total"], 3); // total ignores paging
        let items = result["items"].as_array().unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0]["id"], 2); // DESC order, offset 1 → id 2
    }

    #[tokio::test]
    async fn verify_over_empty_table_is_ok() {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE audit_log (id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, \
             source TEXT, target TEXT, severity TEXT, detail_json TEXT, prev_hash TEXT, entry_hash TEXT);",
        )
        .execute(&pool)
        .await
        .unwrap();
        let result = verify_audit_log(&pool).await.unwrap();
        assert_eq!(result["ok"], true);
        assert_eq!(result["checked"], 0);
    }

    #[tokio::test]
    async fn audit_status_counts_total_unacked_critical() {
        let pool = seeded_pool().await;
        let status = audit_status_query(&pool).await.unwrap();
        assert_eq!(status["enabled"], true);
        assert_eq!(status["total_entries"], 3);
        assert_eq!(status["unacknowledged"], 2); // ids 1 and 3 (id 2 acked)
        assert_eq!(status["critical_count"], 1); // id 3
        assert_eq!(status["report_interval_hours"], 24.0);
    }
}

#![allow(clippy::result_large_err)]
//! Agent governance: Scope Fence reads (Phase B).
//!
//! Native port of the SQLite-backed scope reads:
//!   - `GET /api/agent/scope`             (`scope_fence.status`)
//!   - `GET /api/agent/scope/{id}`        (`scope_fence.get_scope`)
//!
//! `agent_session_scopes` (migration 84) is the shared single-writer(web) /
//! multi-reader(MCP, Rust) scope table, so Python and Rust read identical rows.
//! Readers never interpret preset names — `denied_json` already holds the fully
//! expanded deny patterns (the web/Python side does the preset->denied
//! expansion on write). The scope WRITES (POST/DELETE) stay on the Python proxy
//! so the expansion logic lives in exactly one place.

use std::str::FromStr;

use axum::{
    extract::{Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const VALID_PRESETS: &[&str] = &["read_only", "tagger", "organizer", "full_access"];

pub(crate) fn preset_denied(preset: &str) -> &'static [&'static str] {
    match preset {
        "read_only" => &[
            "set_*",
            "add_*",
            "create_*",
            "update_*",
            "delete_*",
            "remove_*",
            "rate_*",
            "trigger_*",
            "scan_*",
            "archive_*",
            "install_*",
            "uninstall_*",
            "toggle_*",
            "switch_*",
            "share_*",
            "restore_*",
            "import_*",
            "reprocess_*",
            "compute_*",
            "wd_tagger_tag*",
            "wd_tagger_batch",
            "wd_tagger_delete*",
            "analyze_*",
            "semantic_index_start",
            "semantic_index_stop",
            "generate_*",
            "batch_download_*",
            "agent_kill",
            "agent_resume",
            "agent_budget_reset",
            "agent_circuit_breaker_reset",
        ],
        "tagger" => &[
            "delete_*",
            "remove_scan_root",
            "archive_cleanup_execute",
            "install_*",
            "uninstall_*",
            "toggle_extension",
            "set_extension_config",
            "share_*",
            "restore_*",
            "add_scan_root",
            "toggle_scan_root",
            "create_backup",
            "agent_kill",
            "agent_resume",
        ],
        "organizer" => &[
            "delete_*",
            "archive_cleanup_execute",
            "install_*",
            "uninstall_*",
            "toggle_extension",
            "share_*",
            "restore_*",
            "add_scan_root",
            "remove_scan_root",
            "toggle_scan_root",
            "create_backup",
            "agent_kill",
            "agent_resume",
        ],
        _ => &[], // full_access
    }
}

fn expand_denied(preset: &str, custom: Option<&Vec<serde_json::Value>>) -> Vec<String> {
    let mut effective: Vec<String> = preset_denied(preset)
        .iter()
        .map(|s| s.to_string())
        .collect();
    if let Some(extra) = custom {
        for item in extra {
            if let Some(s) = item.as_str() {
                if !effective.iter().any(|e| e == s) {
                    effective.push(s.to_string());
                }
            }
        }
    }
    effective
}

fn preset_label(preset: &str) -> &'static str {
    // `"organizer"` and the fallback coincide. Deleting the explicit arm would
    // make a known preset indistinguishable from a typo'd one at the call site.
    #[allow(
        clippy::match_same_arms,
        reason = "the explicit arm lists a known preset"
    )]
    match preset {
        "read_only" => "Read Only",
        "tagger" => "Tagger",
        "organizer" => "Organizer",
        "full_access" => "Full Access",
        _ => "Organizer",
    }
}

/// Static preset catalog — mirrors Python `scope_fence.PRESETS` (label + description).
fn available_presets() -> Value {
    json!({
        "read_only": {
            "label": "Read Only",
            "description": "閲覧・分析のみ。書き込み操作は全て拒否"
        },
        "tagger": {
            "label": "Tagger",
            "description": "タグ付け・アノテーション作業。削除操作は拒否"
        },
        "organizer": {
            "label": "Organizer",
            "description": "整理作業。レーティング・タグ・コレクション操作可。削除は拒否"
        },
        "full_access": {
            "label": "Full Access",
            "description": "全権限。破壊的操作は HITL Gate による承認が引き続き有効"
        }
    })
}

/// Default preset from config.json (`agent_safety.default_scope_preset`),
/// validated against the known presets — mirrors `ScopeFence.configure`.
pub(crate) fn config_default_preset(app_config: &Value) -> String {
    let raw = app_config
        .get("agent_safety")
        .and_then(|v| v.get("default_scope_preset"))
        .and_then(Value::as_str)
        .unwrap_or("organizer");
    if VALID_PRESETS.contains(&raw) {
        raw.to_string()
    } else {
        "organizer".to_string()
    }
}

fn denied_from_json(raw: Option<&str>) -> Vec<Value> {
    raw.and_then(|s| serde_json::from_str::<Vec<Value>>(s).ok())
        .unwrap_or_default()
}

fn is_expired(expires_at: Option<&str>) -> bool {
    match expires_at {
        Some(s) => DateTime::parse_from_rfc3339(s)
            .map(|dt| Utc::now() > dt.with_timezone(&Utc))
            .unwrap_or(false),
        None => false,
    }
}

async fn scope_status_query(db: &SqlitePool, default_preset: &str) -> Result<Value, sqlx::Error> {
    let rows = match sqlx::query(
        "SELECT session_id, preset, name, denied_json FROM agent_session_scopes ORDER BY session_id",
    )
    .fetch_all(db)
    .await
    {
        Ok(r) => r,
        // Table not yet created by Python migration — return empty, not 500.
        Err(sqlx::Error::Database(e)) if e.message().contains("no such table") => vec![],
        Err(e) => return Err(e),
    };

    let mut sessions = serde_json::Map::new();
    for row in &rows {
        let session_id: String = row.get(0);
        let preset: Option<String> = row.get(1);
        let name: Option<String> = row.get(2);
        let denied_json: Option<String> = row.get(3);
        let denied_count = denied_from_json(denied_json.as_deref()).len();
        sessions.insert(
            session_id,
            json!({"preset": preset, "name": name, "denied_count": denied_count}),
        );
    }

    Ok(json!({
        "default_preset": default_preset,
        "active_sessions": sessions.len(),
        "sessions": Value::Object(sessions),
        "available_presets": available_presets(),
    }))
}

async fn auto_approve_query(db: &SqlitePool) -> Result<Value, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT tool, conditions_json, approved_at, approved_by FROM agent_auto_approve_rules ORDER BY id",
    )
    .fetch_all(db)
    .await?;
    let rules: Vec<Value> = rows
        .iter()
        .map(|r| {
            let conditions = r
                .get::<Option<String>, _>(1)
                .and_then(|s| serde_json::from_str::<Value>(&s).ok())
                .unwrap_or_else(|| serde_json::json!({}));
            serde_json::json!({
                "tool": r.get::<Option<String>, _>(0),
                "conditions": conditions,
                "approved_at": r.get::<Option<String>, _>(2),
                "approved_by": r.get::<Option<String>, _>(3),
            })
        })
        .collect();
    Ok(serde_json::json!({ "rules": rules }))
}

async fn scope_get_query(db: &SqlitePool, session_id: &str) -> Result<Option<Value>, sqlx::Error> {
    let row = sqlx::query(
        "SELECT session_id, preset, name, denied_json, created_at, expires_at \
         FROM agent_session_scopes WHERE session_id = ?",
    )
    .bind(session_id)
    .fetch_optional(db)
    .await?;

    let Some(row) = row else {
        return Ok(None);
    };
    let denied_json: Option<String> = row.get(3);
    let denied = denied_from_json(denied_json.as_deref());
    let expires_at: Option<String> = row.get(5);
    let expired = is_expired(expires_at.as_deref());

    Ok(Some(json!({
        "session_id": row.get::<String, _>(0),
        "preset": row.get::<Option<String>, _>(1),
        "name": row.get::<Option<String>, _>(2),
        "denied_count": denied.len(),
        "denied_patterns": denied,
        "created_at": row.get::<Option<String>, _>(4),
        "expires_at": expires_at,
        "expired": expired,
    })))
}

/// GET /api/agent/scope — status of all session scopes.
pub async fn scope_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let default_preset = config_default_preset(&state.config.app_config);
    match scope_status_query(&state.db_read, &default_preset).await {
        Ok(result) => api_result(result),
        Err(error) => internal_error(error, "failed to read scope status"),
    }
}

/// GET /api/agent/auto-approve — list auto-approve rules.
pub async fn auto_approve_list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    match auto_approve_query(&state.db_read).await {
        Ok(result) => api_result(result),
        Err(error) => internal_error(error, "failed to read auto-approve rules"),
    }
}

/// GET /api/agent/scope/{session_id} — one session scope (404 when unset).
pub async fn scope_get(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(session_id): AxumPath<String>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    match scope_get_query(&state.db_read, &session_id).await {
        Ok(Some(result)) => api_result(result),
        Ok(None) => api_error("セッションスコープが見つかりません", StatusCode::NOT_FOUND),
        Err(error) => internal_error(error, "failed to read scope"),
    }
}

/// POST /api/agent/scope/{session_id} — upsert a session scope.
pub async fn scope_set(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(session_id): AxumPath<String>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }

    let default_preset = config_default_preset(&state.config.app_config);
    let raw_preset = body.get("preset").and_then(|v| v.as_str()).unwrap_or("");
    let preset = if VALID_PRESETS.contains(&raw_preset) {
        raw_preset
    } else {
        &default_preset
    };

    let denied_custom: Option<Vec<Value>> = body.get("denied").and_then(|v| v.as_array()).cloned();
    if body.get("denied").is_some() && denied_custom.is_none() {
        return api_error("denied はリストで指定してください", StatusCode::BAD_REQUEST);
    }
    let effective_denied = expand_denied(preset, denied_custom.as_ref());

    let name = body.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let scope_name = if name.is_empty() {
        preset_label(preset)
    } else {
        name
    };

    let duration_hours: Option<f64> = body.get("duration_hours").and_then(|v| v.as_f64());
    let now = Utc::now();
    let created_at = now.to_rfc3339();
    let expires_at: Option<String> = duration_hours.filter(|h| *h > 0.0).map(|h| {
        let dur = chrono::Duration::milliseconds(crate::num::sat_i64(h * 3_600_000.0));
        (now + dur).to_rfc3339()
    });

    let denied_json = serde_json::to_string(&effective_denied).unwrap_or_else(|_| "[]".to_string());

    let result = sqlx::query(
        "INSERT INTO agent_session_scopes \
         (session_id, preset, name, denied_json, created_at, expires_at) \
         VALUES (?, ?, ?, ?, ?, ?) \
         ON CONFLICT(session_id) DO UPDATE SET \
           preset=excluded.preset, name=excluded.name, \
           denied_json=excluded.denied_json, \
           created_at=excluded.created_at, expires_at=excluded.expires_at",
    )
    .bind(&session_id)
    .bind(preset)
    .bind(scope_name)
    .bind(&denied_json)
    .bind(&created_at)
    .bind(expires_at.as_deref())
    .execute(&state.db)
    .await;

    match result {
        Err(e) => internal_error(e, "failed to upsert scope"),
        Ok(_) => api_result(json!({
            "ok": true,
            "scope": {
                "session_id": session_id,
                "preset": preset,
                "name": scope_name,
                "denied": effective_denied,
                "created_at": created_at,
                "expires_at": expires_at,
            }
        })),
    }
}

/// DELETE /api/agent/scope/{session_id} — remove a session scope.
pub async fn scope_delete(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(session_id): AxumPath<String>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let result = sqlx::query("DELETE FROM agent_session_scopes WHERE session_id = ?")
        .bind(&session_id)
        .execute(&state.db)
        .await;

    match result {
        Err(e) => internal_error(e, "failed to delete scope"),
        Ok(r) => api_result(json!({"ok": r.rows_affected() > 0})),
    }
}

/// POST /api/agent/auto-approve — add an auto-approve rule.
pub async fn auto_approve_add(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }

    let tool_name = body
        .get("tool")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if tool_name.is_empty() {
        return api_error("tool は必須です", StatusCode::BAD_REQUEST);
    }

    let conditions = body
        .get("conditions")
        .cloned()
        .unwrap_or(Value::Object(serde_json::Map::new()));
    if !conditions.is_null() && !conditions.is_object() {
        return api_error(
            "conditions は辞書で指定してください",
            StatusCode::BAD_REQUEST,
        );
    }
    let conditions_json = serde_json::to_string(&conditions).unwrap_or_else(|_| "{}".to_string());

    // dedup: check existing rules with same tool+conditions
    let existing = sqlx::query(
        "SELECT tool, conditions_json, approved_at, approved_by \
         FROM agent_auto_approve_rules WHERE tool = ? ORDER BY id",
    )
    .bind(&tool_name)
    .fetch_all(&state.db_read)
    .await;

    if let Ok(rows) = &existing {
        for row in rows {
            let existing_cond: String = row.try_get("conditions_json").unwrap_or_default();
            let a: Value = serde_json::from_str(&existing_cond).unwrap_or(Value::Null);
            let b: Value = serde_json::from_str(&conditions_json).unwrap_or(Value::Null);
            if a == b {
                return api_result(json!({
                    "ok": true,
                    "rule": {
                        "tool": tool_name,
                        "conditions": a,
                        "approved_at": row.try_get::<Option<String>, _>("approved_at").ok().flatten(),
                        "approved_by": row.try_get::<Option<String>, _>("approved_by").ok().flatten(),
                    }
                }));
            }
        }
    }

    let approved_at = Utc::now().to_rfc3339();
    let result = sqlx::query(
        "INSERT INTO agent_auto_approve_rules (tool, conditions_json, approved_at, approved_by) \
         VALUES (?, ?, ?, ?)",
    )
    .bind(&tool_name)
    .bind(&conditions_json)
    .bind(&approved_at)
    .bind("user")
    .execute(&state.db)
    .await;

    match result {
        Err(e) => internal_error(e, "failed to insert auto-approve rule"),
        Ok(_) => api_result(json!({
            "ok": true,
            "rule": {
                "tool": tool_name,
                "conditions": conditions,
                "approved_at": approved_at,
                "approved_by": "user",
            }
        })),
    }
}

/// DELETE /api/agent/auto-approve/{index} — remove an auto-approve rule by position.
pub async fn auto_approve_delete(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(index): AxumPath<i64>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    if index < 0 {
        return api_error(
            "インデックスは 0 以上にしてください",
            StatusCode::BAD_REQUEST,
        );
    }
    let row = sqlx::query("SELECT id FROM agent_auto_approve_rules ORDER BY id LIMIT 1 OFFSET ?")
        .bind(index)
        .fetch_optional(&state.db_read)
        .await;

    let row_id: Option<i64> = match row {
        Err(e) => return internal_error(e, "failed to query auto-approve rules"),
        Ok(None) => None,
        Ok(Some(r)) => Some(r.try_get("id").unwrap_or(0)),
    };

    match row_id {
        None => (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "ルールが見つかりません", "data": null})),
        )
            .into_response(),
        Some(id) => {
            let result = sqlx::query("DELETE FROM agent_auto_approve_rules WHERE id = ?")
                .bind(id)
                .execute(&state.db)
                .await;
            match result {
                Err(e) => internal_error(e, "failed to delete auto-approve rule"),
                Ok(_) => api_result(json!({"ok": true})),
            }
        }
    }
}

/// Python `api_result` success path: merge payload + ok/error/data.
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

/// Python `api_error(message, status)` without a code.
fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
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

    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    async fn seeded_pool() -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE agent_session_scopes (
                session_id  TEXT PRIMARY KEY,
                preset      TEXT NOT NULL DEFAULT 'organizer',
                name        TEXT NOT NULL DEFAULT '',
                denied_json TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                expires_at  TEXT
             );
             INSERT INTO agent_session_scopes
               (session_id, preset, name, denied_json, created_at, expires_at)
             VALUES
               ('s1', 'read_only', 'Read Only', '[\"delete_*\", \"set_*\"]', '2026-06-15T00:00:00+00:00', NULL),
               ('s2', 'tagger', 'Tagger', '[\"delete_*\"]', '2026-06-15T00:00:00+00:00', '2020-01-01T00:00:00+00:00');",
        )
        .execute(&pool)
        .await
        .unwrap();
        pool
    }

    #[tokio::test]
    async fn status_lists_sessions_and_static_presets() {
        let pool = seeded_pool().await;
        let result = scope_status_query(&pool, "organizer").await.unwrap();
        assert_eq!(result["default_preset"], "organizer");
        assert_eq!(result["active_sessions"], 2);
        assert_eq!(result["sessions"]["s1"]["preset"], "read_only");
        assert_eq!(result["sessions"]["s1"]["denied_count"], 2);
        // Static preset catalog is always present.
        assert_eq!(
            result["available_presets"]["read_only"]["label"],
            "Read Only"
        );
        assert!(result["available_presets"]
            .as_object()
            .unwrap()
            .contains_key("full_access"));
    }

    #[tokio::test]
    async fn status_on_empty_table_is_deterministic() {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE agent_session_scopes (session_id TEXT PRIMARY KEY, preset TEXT, \
             name TEXT, denied_json TEXT, created_at TEXT, expires_at TEXT);",
        )
        .execute(&pool)
        .await
        .unwrap();
        let result = scope_status_query(&pool, "organizer").await.unwrap();
        assert_eq!(result["active_sessions"], 0);
        assert_eq!(result["sessions"], json!({}));
        assert_eq!(result["available_presets"].as_object().unwrap().len(), 4);
    }

    async fn auto_approve_pool() -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE agent_auto_approve_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool TEXT NOT NULL,
                conditions_json TEXT NOT NULL DEFAULT '{}',
                approved_at TEXT NOT NULL,
                approved_by TEXT NOT NULL DEFAULT 'user'
             );",
        )
        .execute(&pool)
        .await
        .unwrap();
        pool
    }

    #[tokio::test]
    async fn auto_approve_lists_rules_in_id_order() {
        let pool = auto_approve_pool().await;
        sqlx::raw_sql(
            "INSERT INTO agent_auto_approve_rules
               (tool, conditions_json, approved_at, approved_by)
             VALUES
               ('rate_images', '{}', '2026-06-15T00:00:00+00:00', 'user'),
               ('set_tags', '{\"file_id\":\"5\"}', '2026-06-15T00:01:00+00:00', 'admin');",
        )
        .execute(&pool)
        .await
        .unwrap();

        let result = auto_approve_query(&pool).await.unwrap();
        assert_eq!(result["rules"].as_array().unwrap().len(), 2);
        assert_eq!(result["rules"][0]["tool"], "rate_images");
        assert_eq!(result["rules"][1]["conditions"]["file_id"], "5");
    }

    #[tokio::test]
    async fn auto_approve_empty_table_returns_empty_rules() {
        let pool = auto_approve_pool().await;
        let result = auto_approve_query(&pool).await.unwrap();
        assert_eq!(result["rules"], json!([]));
    }

    #[tokio::test]
    async fn get_returns_scope_with_denied_patterns() {
        let pool = seeded_pool().await;
        let result = scope_get_query(&pool, "s1").await.unwrap().unwrap();
        assert_eq!(result["session_id"], "s1");
        assert_eq!(result["preset"], "read_only");
        assert_eq!(result["denied_count"], 2);
        assert_eq!(result["denied_patterns"][0], "delete_*");
        assert_eq!(result["expired"], false);
    }

    #[tokio::test]
    async fn get_marks_expired_scope() {
        let pool = seeded_pool().await;
        // s2 has an expires_at far in the past.
        let result = scope_get_query(&pool, "s2").await.unwrap().unwrap();
        assert_eq!(result["expired"], true);
    }

    #[tokio::test]
    async fn get_returns_none_when_absent() {
        let pool = seeded_pool().await;
        assert!(scope_get_query(&pool, "missing").await.unwrap().is_none());
    }

    #[test]
    fn default_preset_falls_back_to_organizer() {
        assert_eq!(config_default_preset(&json!({})), "organizer");
        assert_eq!(
            config_default_preset(&json!({"agent_safety": {"default_scope_preset": "tagger"}})),
            "tagger"
        );
        // Invalid preset name -> organizer.
        assert_eq!(
            config_default_preset(&json!({"agent_safety": {"default_scope_preset": "nonsense"}})),
            "organizer"
        );
    }
}

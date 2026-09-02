//! Scope Fence enforcement (`agent_session_scopes`, parity with Python
//! migration 84 / `core/agent_safety/scope_fence.py::check`).
//!
//! This is the enforcement-only counterpart to the read-only status
//! endpoints in `routes/agent_scope_store.rs`. That module's readers are
//! intentionally lenient (missing table -> empty result) because they back
//! REST 404 semantics; here a storage failure must deny by default
//! (fail-safe, COVENANT Liber III.iv), so the read path is re-implemented
//! rather than reused.

use serde_json::Value;
use sqlx::{Row, SqlitePool};

use crate::{mcp::fnmatch::fnmatch, routes::agent_scope_store::preset_denied};

const STATELESS_SESSION_ID: &str = "__stateless__";

/// Checks whether `tool_name` is permitted for `scope_key`. Returns `None`
/// when allowed, or `Some(reason)` when denied. Every failure mode —
/// including internal errors this function's author did not anticipate —
/// is folded into a `Some(reason)` return here; the function has no `Err`
/// variant, so a caller cannot accidentally fail open by mishandling one.
pub async fn check_scope(
    db: &SqlitePool,
    scope_key: &str,
    tool_name: &str,
    default_preset: &str,
) -> Option<String> {
    // Branch 0: the stateless transport (`POST /mcp`) has no per-connection
    // identity and must never be customizable via a scope row an operator
    // may have created for the literal key "__stateless__". This is a
    // security invariant, not a DB-access optimization — it is evaluated
    // before any lookup so a stray "__stateless__" row can never widen or
    // narrow stateless enforcement.
    if scope_key == STATELESS_SESSION_ID {
        return deny_if_matches(tool_name, preset_denied(default_preset));
    }

    let row = match sqlx::query(
        "SELECT preset, denied_json, expires_at FROM agent_session_scopes WHERE session_id = ?",
    )
    .bind(scope_key)
    .fetch_optional(db)
    .await
    {
        // Branch 1: storage failure. Fail-safe — deny rather than fall
        // through to any more permissive branch.
        Err(_) => return Some("Scope check unavailable due to a storage error".to_string()),
        Ok(row) => row,
    };

    let Some(row) = row else {
        // Branch 2: no scope set for this key -> the default preset's deny
        // list applies.
        return deny_if_matches(tool_name, preset_denied(default_preset));
    };

    let expires_at: Option<String> = row.get("expires_at");
    if is_expired(expires_at.as_deref()) {
        // Branch 3: an expired scope blocks every tool call until the
        // operator reconnects and sets a fresh scope.
        return Some("Session scope expired".to_string());
    }

    // Branch 4: denied_json holds the fully expanded deny patterns for this
    // session (preset deny list plus any custom patterns); match against
    // fnmatch semantics.
    let denied_json: Option<String> = row.get("denied_json");
    let denied = denied_from_json(denied_json.as_deref());
    deny_if_matches(tool_name, &denied)
}

fn deny_if_matches<S: AsRef<str>>(tool_name: &str, denied: &[S]) -> Option<String> {
    for pattern in denied {
        if fnmatch(tool_name, pattern.as_ref()) {
            return Some(format!("Tool '{tool_name}' is denied by the current scope"));
        }
    }
    None
}

fn denied_from_json(raw: Option<&str>) -> Vec<String> {
    raw.and_then(|s| serde_json::from_str::<Vec<Value>>(s).ok())
        .map(|items| {
            items
                .into_iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

fn is_expired(expires_at: Option<&str>) -> bool {
    match expires_at {
        Some(s) => chrono::DateTime::parse_from_rfc3339(s)
            .map(|dt| chrono::Utc::now() > dt.with_timezone(&chrono::Utc))
            .unwrap_or(false),
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::SqlitePoolOptions;

    /// Drift guard: `preset_denied()` must stay in sync with Python
    /// `core/agent_safety/scope_fence.py::PRESETS`. The golden fixture is
    /// generated from the Python source (not hand-copied), so this test
    /// actually detects Python-side changes rather than merely re-asserting
    /// a second hardcoded copy of the same list.
    #[test]
    fn preset_denied_matches_python_presets_golden() {
        let golden: std::collections::HashMap<String, Vec<String>> = serde_json::from_str(
            include_str!("../../tests/fixtures/scope_fence_presets_golden.json"),
        )
        .unwrap();

        for (preset, expected) in &golden {
            let actual: Vec<String> = preset_denied(preset)
                .iter()
                .map(|s| s.to_string())
                .collect();
            assert_eq!(
                &actual, expected,
                "preset '{preset}' deny list drifted from Python PRESETS (regenerate the \
                 golden fixture from core/agent_safety/scope_fence.py if this preset's \
                 deny list was intentionally changed)"
            );
        }
    }

    async fn memory_pool() -> SqlitePool {
        SqlitePoolOptions::new()
            .connect("sqlite::memory:")
            .await
            .unwrap()
    }

    async fn with_scopes_table(pool: &SqlitePool) {
        sqlx::query(
            "CREATE TABLE agent_session_scopes (
                session_id  TEXT PRIMARY KEY,
                preset      TEXT NOT NULL DEFAULT 'organizer',
                name        TEXT NOT NULL DEFAULT '',
                denied_json TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                expires_at  TEXT
            )",
        )
        .execute(pool)
        .await
        .unwrap();
    }

    #[tokio::test]
    async fn branch1_storage_error_denies() {
        // No table at all -> the query itself fails (not "no rows").
        let pool = memory_pool().await;
        let result = check_scope(&pool, "some-session", "get_server_info", "organizer").await;
        assert!(result.is_some());
    }

    #[tokio::test]
    async fn branch2_no_row_applies_default_preset() {
        let pool = memory_pool().await;
        with_scopes_table(&pool).await;
        // "organizer" denies delete_* but allows get_server_info.
        assert!(
            check_scope(&pool, "unknown-session", "delete_thing", "organizer")
                .await
                .is_some()
        );
        assert!(
            check_scope(&pool, "unknown-session", "get_server_info", "organizer")
                .await
                .is_none()
        );
    }

    #[tokio::test]
    async fn branch3_expired_denies_everything() {
        let pool = memory_pool().await;
        with_scopes_table(&pool).await;
        sqlx::query(
            "INSERT INTO agent_session_scopes(session_id, preset, denied_json, created_at, expires_at) \
             VALUES ('s1', 'full_access', '[]', '2020-01-01T00:00:00Z', '2020-01-02T00:00:00Z')",
        )
        .execute(&pool)
        .await
        .unwrap();
        let result = check_scope(&pool, "s1", "get_server_info", "organizer").await;
        assert_eq!(result, Some("Session scope expired".to_string()));
    }

    #[tokio::test]
    async fn branch4_denied_json_fnmatch_match_denies() {
        let pool = memory_pool().await;
        with_scopes_table(&pool).await;
        sqlx::query(
            "INSERT INTO agent_session_scopes(session_id, preset, denied_json, created_at, expires_at) \
             VALUES ('s1', 'full_access', '[\"delete_*\"]', '2020-01-01T00:00:00Z', NULL)",
        )
        .execute(&pool)
        .await
        .unwrap();
        assert!(check_scope(&pool, "s1", "delete_thing", "organizer")
            .await
            .is_some());
        assert!(check_scope(&pool, "s1", "get_server_info", "organizer")
            .await
            .is_none());
    }

    #[tokio::test]
    async fn branch0_stateless_ignores_any_row_for_that_literal_key() {
        let pool = memory_pool().await;
        with_scopes_table(&pool).await;
        // An operator (mistakenly or not) sets a wide-open scope for the
        // literal key "__stateless__" — it must still be ignored.
        sqlx::query(
            "INSERT INTO agent_session_scopes(session_id, preset, denied_json, created_at, expires_at) \
             VALUES ('__stateless__', 'full_access', '[]', '2020-01-01T00:00:00Z', NULL)",
        )
        .execute(&pool)
        .await
        .unwrap();
        // full_access denies nothing, but the stateless short-circuit must
        // still apply the default preset's deny list, not this row.
        assert!(
            check_scope(&pool, "__stateless__", "delete_thing", "organizer")
                .await
                .is_some()
        );
    }
}

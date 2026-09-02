use serde_json::{json, Value};

use crate::{
    mcp::scope_check,
    routes::{agent::kill_flag_path, agent_scope_store::config_default_preset},
    state::AppState,
};

const STATELESS_SESSION_ID: &str = "__stateless__";
const AGENT_ID_MAX_LEN: usize = 128;

pub struct McpTool {
    pub name: &'static str,
    pub description: &'static str,
    pub input_schema: Value,
}

pub fn list_tools() -> Vec<McpTool> {
    vec![
        McpTool {
            name: "get_server_info",
            description: "Get server version and status",
            input_schema: json!({"type": "object", "properties": {}}),
        },
        McpTool {
            name: "diagnostics_doctor",
            description: "Run local environment diagnosis",
            input_schema: json!({"type": "object", "properties": {}}),
        },
        McpTool {
            name: "auto_scan_info",
            description: "Get auto-scan watcher status",
            input_schema: json!({"type": "object", "properties": {}}),
        },
        McpTool {
            name: "auto_scan_start",
            description: "Start filesystem watcher auto-scanning new images",
            input_schema: json!({"type": "object", "properties": {}}),
        },
        McpTool {
            name: "auto_scan_stop",
            description: "Stop filesystem watcher",
            input_schema: json!({"type": "object", "properties": {}}),
        },
        McpTool {
            name: "agent_scope_bind",
            description: "Bind this connection to a caller-chosen, durable agent_id \
                so a Scope Fence preset set for that agent_id (via the web UI's \
                POST /api/agent/scope/{agent_id}) applies to this and future \
                connections that bind the same agent_id.",
            input_schema: json!({
                "type": "object",
                "properties": {"agent_id": {"type": "string"}},
                "required": ["agent_id"]
            }),
        },
    ]
}

fn text_result(msg_id: Option<Value>, text: impl Into<String>) -> Option<Value> {
    Some(json!({
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"content": [{"type": "text", "text": text.into()}]}
    }))
}

pub async fn dispatch(
    state: &AppState,
    is_local: bool,
    session_id: &str,
    msg: Value,
) -> Option<Value> {
    let method = msg.get("method").and_then(|v| v.as_str()).unwrap_or("");
    let msg_id = msg.get("id").cloned();
    let params = msg.get("params").cloned().unwrap_or_else(|| json!({}));

    match method {
        "initialize" => Some(json!({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "yu-ai-manager", "version": env!("CARGO_PKG_VERSION")},
                "capabilities": {
                    "tools": {"listChanged": false},
                    "resources": {"listChanged": false}
                }
            }
        })),
        "notifications/initialized" => None,
        "tools/list" => {
            let tools: Vec<Value> = list_tools()
                .iter()
                .map(|t| {
                    json!({
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema,
                    })
                })
                .collect();
            Some(json!({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}))
        }
        "tools/call" => {
            let name = params.get("name").and_then(|v| v.as_str()).unwrap_or("");
            let arguments = params
                .get("arguments")
                .cloned()
                .unwrap_or_else(|| json!({}));

            // 0. Kill Switch. dispatch() previously had no safety gate at all
            // (a pre-existing gap relative to the Python reference, which
            // double-checks this at the same layer); this closes that gap
            // without narrowing any existing behavior.
            if kill_flag_path(&state.config.project_root).exists() {
                return text_result(msg_id, "Agent kill switch is active");
            }

            // 1. agent_scope_bind is handled here directly (not delegated to
            // call_tool) because it needs mutable access to this
            // connection's McpSessionEntry, which only dispatch() can reach
            // via session_id + state.mcp_sessions.
            if name == "agent_scope_bind" {
                if session_id == STATELESS_SESSION_ID {
                    return text_result(
                        msg_id,
                        "agent_scope_bind is not available on the stateless (POST /mcp) transport",
                    );
                }
                let agent_id = arguments
                    .get("agent_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                if agent_id.is_empty() || agent_id.len() > AGENT_ID_MAX_LEN {
                    return text_result(
                        msg_id,
                        format!(
                            "agent_id must be non-empty and at most {AGENT_ID_MAX_LEN} characters"
                        ),
                    );
                }
                state
                    .mcp_sessions
                    .set_bound_scope_id(session_id, agent_id.to_string());
                return text_result(
                    msg_id,
                    json!({"agent_id": agent_id, "bound": true}).to_string(),
                );
            }

            // 2. Scope Fence. bound_scope_id (set via agent_scope_bind) is
            // preferred; a connection that never bound falls back to the
            // raw (volatile) session_id, which resolves to the default
            // preset since no row exists for it under normal operation.
            let scope_key = state
                .mcp_sessions
                .bound_scope_id(session_id)
                .unwrap_or_else(|| session_id.to_string());
            let default_preset = config_default_preset(&state.config.app_config);
            if let Some(reason) =
                scope_check::check_scope(&state.db_read, &scope_key, name, &default_preset).await
            {
                crate::routes::agent_journal::record_action(
                    &state.db,
                    &scope_key,
                    name,
                    "scope_blocked",
                    0,
                    &reason,
                )
                .await;
                return text_result(msg_id, reason);
            }

            let started = std::time::Instant::now();
            let call_result = call_tool(state, is_local, name, arguments).await;
            let duration_ms = i64::try_from(started.elapsed().as_millis()).unwrap_or(i64::MAX);
            match call_result {
                Ok(content) => {
                    crate::routes::agent_journal::record_action(
                        &state.db,
                        &scope_key,
                        name,
                        "success",
                        duration_ms,
                        "",
                    )
                    .await;
                    Some(json!({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"content": [{"type": "text", "text": content}]}
                    }))
                }
                Err(e) => {
                    crate::routes::agent_journal::record_action(
                        &state.db,
                        &scope_key,
                        name,
                        "error",
                        duration_ms,
                        &e,
                    )
                    .await;
                    Some(json!({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32603, "message": e}
                    }))
                }
            }
        }
        "resources/list" => {
            Some(json!({"jsonrpc": "2.0", "id": msg_id, "result": {"resources": []}}))
        }
        "resources/read" => Some(json!({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": "Resource not found"}
        })),
        _ => Some(json!({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": format!("Method not found: {method}")}
        })),
    }
}

async fn call_tool(
    state: &AppState,
    is_local: bool,
    name: &str,
    _args: Value,
) -> Result<String, String> {
    match name {
        "get_server_info" => Ok(
            crate::routes::server_info::server_info_body(state, is_local)
                .await
                .to_string(),
        ),
        "diagnostics_doctor" => Ok(crate::mcp::diagnostics::run_and_report(state)
            .await
            .to_string()),
        "auto_scan_info" => Ok(crate::routes::watcher::watcher_info_body(state).to_string()),
        "auto_scan_start" => {
            let (_status, body) = crate::routes::watcher::watcher_start_result(state);
            Ok(body.to_string())
        }
        "auto_scan_stop" => {
            let body = if state.watcher.stop() {
                json!({"ok": true})
            } else {
                json!({"ok": false, "error": "Not running"})
            };
            Ok(body.to_string())
        }
        _ => Err(format!("Tool not yet native: {name}")),
    }
}

#[cfg(test)]
mod tests {
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use super::*;
    use crate::state::{AppState, Config, SharedState};

    async fn test_state() -> SharedState {
        test_state_with(serde_json::json!({}), false).await
    }

    async fn test_state_with(app_config: Value, safe_mode: bool) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();

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
        .execute(&pool)
        .await
        .unwrap();

        sqlx::query(
            "CREATE TABLE agent_action_journal (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       TEXT NOT NULL,
                timestamp        TEXT NOT NULL,
                tool_name        TEXT NOT NULL,
                params_json      TEXT NOT NULL DEFAULT '{}',
                result_summary   TEXT,
                status           TEXT NOT NULL DEFAULT 'success',
                duration_ms      INTEGER DEFAULT 0,
                caller_info      TEXT DEFAULT '',
                affected_count   INTEGER DEFAULT 0,
                reversible       INTEGER DEFAULT 0,
                undo_params_json TEXT,
                undone           INTEGER DEFAULT 0,
                undone_at        TEXT
            )",
        )
        .execute(&pool)
        .await
        .unwrap();

        let project_root = tempfile::tempdir().unwrap().keep();

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
                    project_root,
                    app_config,
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode,
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

    fn tools_call(name: &str, arguments: Value) -> Value {
        json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        })
    }

    fn content_text(resp: &Value) -> &str {
        resp["result"]["content"][0]["text"].as_str().unwrap()
    }

    #[tokio::test]
    async fn denial_is_returned_as_result_content_not_a_protocol_error() {
        let state = test_state().await;
        // "organizer" (the default preset) denies delete_*.
        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("delete_something", json!({})),
        )
        .await
        .unwrap();
        assert!(
            resp.get("error").is_none(),
            "denial must not be a JSON-RPC error: {resp}"
        );
        assert!(content_text(&resp).contains("denied"));
    }

    #[tokio::test]
    async fn allowed_tool_reaches_call_tool() {
        let state = test_state().await;
        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("get_server_info", json!({})),
        )
        .await
        .unwrap();
        assert!(resp.get("error").is_none());
        assert!(content_text(&resp).contains("\"ok\":true"));
    }

    #[tokio::test]
    async fn auto_scan_info_matches_rest_shape() {
        let state = test_state().await;
        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("auto_scan_info", json!({})),
        )
        .await
        .unwrap();
        assert!(resp.get("error").is_none());
        let text = content_text(&resp);
        assert!(text.contains("\"running\""));
        assert!(text.contains("\"watched_roots\""));
        assert!(text.contains("\"stats\""));
    }

    #[tokio::test]
    async fn auto_scan_start_returns_400_body_when_no_scan_roots_configured() {
        let state = test_state().await;
        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("auto_scan_start", json!({})),
        )
        .await
        .unwrap();
        // Config has no scan_roots -> the underlying route would 400, but
        // the MCP tool must surface the body regardless of HTTP status.
        assert!(resp.get("error").is_none());
        assert!(content_text(&resp).contains("No scan_roots configured"));
    }

    #[tokio::test]
    async fn auto_scan_stop_reports_not_running_when_watcher_never_started() {
        let state = test_state().await;
        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("auto_scan_stop", json!({})),
        )
        .await
        .unwrap();
        assert!(resp.get("error").is_none());
        assert!(content_text(&resp).contains("Not running"));
    }

    #[tokio::test]
    async fn diagnostics_doctor_reports_ok_checks_on_a_healthy_state() {
        let state = test_state().await;
        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("diagnostics_doctor", json!({})),
        )
        .await
        .unwrap();
        assert!(resp.get("error").is_none());
        let text = content_text(&resp);
        assert!(text.contains("\"overall_status\":\"OK\""));
        assert!(text.contains("\"db_integrity\""));
        assert!(text.contains("\"writable_data_dir\""));
    }

    async fn journal_rows(state: &SharedState) -> Vec<(String, String)> {
        sqlx::query_as::<_, (String, String)>(
            "SELECT status, tool_name FROM agent_action_journal ORDER BY id",
        )
        .fetch_all(&state.db_read)
        .await
        .unwrap()
    }

    #[tokio::test]
    async fn scope_denial_is_recorded_in_the_action_journal() {
        let state = test_state().await;
        dispatch(
            &state,
            true,
            "conn-1",
            tools_call("delete_something", json!({})),
        )
        .await
        .unwrap();
        let rows = journal_rows(&state).await;
        assert_eq!(
            rows,
            vec![("scope_blocked".to_string(), "delete_something".to_string())]
        );
    }

    #[tokio::test]
    async fn successful_tool_execution_is_recorded_in_the_action_journal() {
        let state = test_state().await;
        dispatch(
            &state,
            true,
            "conn-1",
            tools_call("get_server_info", json!({})),
        )
        .await
        .unwrap();
        let rows = journal_rows(&state).await;
        assert_eq!(
            rows,
            vec![("success".to_string(), "get_server_info".to_string())]
        );
    }

    #[tokio::test]
    async fn agent_scope_bind_then_reconnect_with_same_agent_id_keeps_scope() {
        let state = test_state().await;

        // First connection binds.
        let _rx1 = state
            .mcp_sessions
            .try_register("conn-a", "1.2.3.4")
            .unwrap();
        let bind_resp = dispatch(
            &state,
            true,
            "conn-a",
            tools_call("agent_scope_bind", json!({"agent_id": "agent-42"})),
        )
        .await
        .unwrap();
        assert!(bind_resp.get("error").is_none());
        assert!(content_text(&bind_resp).contains("\"bound\":true"));

        // Operator grants full_access to "agent-42".
        sqlx::query(
            "INSERT INTO agent_session_scopes(session_id, preset, denied_json, created_at) \
             VALUES ('agent-42', 'full_access', '[]', '2020-01-01T00:00:00Z')",
        )
        .execute(&state.db_read)
        .await
        .unwrap();

        // "delete_something" isn't a registered tool, so once it clears the
        // scope check it still errors out of call_tool with "Tool not yet
        // native" — that JSON-RPC error (not a scope-denial text response)
        // is exactly the signal that scope enforcement let it through.
        let resp = dispatch(
            &state,
            true,
            "conn-a",
            tools_call("delete_something", json!({})),
        )
        .await
        .unwrap();
        assert!(
            passed_scope_check(&resp),
            "expected to pass scope check: {resp}"
        );

        // Disconnect and reconnect with a fresh volatile session_id, then
        // rebind the same durable agent_id: the scope must still apply.
        state.mcp_sessions.remove("conn-a", "1.2.3.4");
        let _rx2 = state
            .mcp_sessions
            .try_register("conn-b", "1.2.3.4")
            .unwrap();
        dispatch(
            &state,
            true,
            "conn-b",
            tools_call("agent_scope_bind", json!({"agent_id": "agent-42"})),
        )
        .await
        .unwrap();
        let resp2 = dispatch(
            &state,
            true,
            "conn-b",
            tools_call("delete_something", json!({})),
        )
        .await
        .unwrap();
        assert!(
            passed_scope_check(&resp2),
            "expected to pass scope check after reconnect: {resp2}"
        );
    }

    /// A response "passed" scope enforcement if it is either a successful
    /// tool result that isn't a scope-denial text, or a JSON-RPC error that
    /// originated from `call_tool` itself (proving dispatch let it through
    /// scope enforcement before failing on the tool's own account).
    fn passed_scope_check(resp: &Value) -> bool {
        if let Some(err) = resp.get("error") {
            return err["message"]
                .as_str()
                .unwrap_or("")
                .contains("Tool not yet native");
        }
        !content_text(resp).contains("denied")
    }

    #[tokio::test]
    async fn agent_scope_bind_rejected_on_stateless_transport() {
        let state = test_state().await;
        let resp = dispatch(
            &state,
            true,
            STATELESS_SESSION_ID,
            tools_call("agent_scope_bind", json!({"agent_id": "agent-42"})),
        )
        .await
        .unwrap();
        assert!(content_text(&resp).contains("stateless"));
    }

    #[tokio::test]
    async fn stateless_ignores_a_row_planted_under_the_literal_stateless_key() {
        let state = test_state().await;
        // An operator plants a wide-open row for the literal key
        // "__stateless__" (e.g. via a scripting mistake). It must be
        // ignored: stateless always uses the default preset.
        sqlx::query(
            "INSERT INTO agent_session_scopes(session_id, preset, denied_json, created_at) \
             VALUES ('__stateless__', 'full_access', '[]', '2020-01-01T00:00:00Z')",
        )
        .execute(&state.db_read)
        .await
        .unwrap();

        let resp = dispatch(
            &state,
            true,
            STATELESS_SESSION_ID,
            tools_call("delete_something", json!({})),
        )
        .await
        .unwrap();
        assert!(content_text(&resp).contains("denied"));
    }

    #[tokio::test]
    async fn agent_scope_bind_rejects_empty_or_oversized_agent_id() {
        let state = test_state().await;
        let _rx = state
            .mcp_sessions
            .try_register("conn-a", "1.2.3.4")
            .unwrap();

        let empty = dispatch(
            &state,
            true,
            "conn-a",
            tools_call("agent_scope_bind", json!({"agent_id": ""})),
        )
        .await
        .unwrap();
        assert!(content_text(&empty).contains("non-empty"));

        let too_long = "a".repeat(AGENT_ID_MAX_LEN + 1);
        let oversized = dispatch(
            &state,
            true,
            "conn-a",
            tools_call("agent_scope_bind", json!({"agent_id": too_long})),
        )
        .await
        .unwrap();
        assert!(content_text(&oversized).contains("128"));
    }

    #[tokio::test]
    async fn auto_scan_start_returns_503_body_when_safe_mode_active() {
        let root = tempfile::tempdir().unwrap();
        let scan_roots = json!([{"path": root.path().display().to_string(), "recursive": false}]);
        let state = test_state_with(json!({"scan_roots": scan_roots}), true).await;
        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("auto_scan_start", json!({})),
        )
        .await
        .unwrap();
        assert!(resp.get("error").is_none());
        assert!(content_text(&resp).contains("safe mode active"));
    }

    #[tokio::test]
    async fn auto_scan_start_returns_409_body_when_already_running() {
        let root = tempfile::tempdir().unwrap();
        let scan_roots = json!([{"path": root.path().display().to_string(), "recursive": false}]);
        let state = test_state_with(json!({"scan_roots": scan_roots}), false).await;
        let first = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("auto_scan_start", json!({})),
        )
        .await
        .unwrap();
        assert!(
            content_text(&first).contains("\"watched_roots\""),
            "first start should succeed: {first}"
        );

        let second = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("auto_scan_start", json!({})),
        )
        .await
        .unwrap();
        assert!(content_text(&second).contains("Already running"));
    }

    #[tokio::test]
    async fn kill_switch_blocks_every_tool_call() {
        let state = test_state().await;
        std::fs::create_dir_all(state.config.project_root.join("data")).unwrap();
        std::fs::write(
            state
                .config
                .project_root
                .join("data")
                .join("agent_kill.flag"),
            "test",
        )
        .unwrap();

        let resp = dispatch(
            &state,
            true,
            "conn-1",
            tools_call("get_server_info", json!({})),
        )
        .await
        .unwrap();
        assert!(content_text(&resp).to_lowercase().contains("kill"));
    }
}

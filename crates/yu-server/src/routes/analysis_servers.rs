#![allow(clippy::result_large_err)]
//! Analysis (AI) server management — config.json CRUD (batch 1).
//!
//! Native port of `core/analysis_api/server_crud.py` for the dependency-light
//! operations that only manipulate the existing `ai_servers` list /
//! `ai_servers_active` in config.json (same pattern as `scan_roots.rs`):
//!   - POST   /api/analysis/servers/{id}/activate  (set_active_server)
//!   - PUT    /api/analysis/servers/reorder        (reorder_servers)
//!
//! add/update (need id generation + validation from server_model_data.py),
//! remove (needs discovery-metadata cleanup), test/migrate/discovered stay on
//! the Python proxy for now. These write endpoints have no admin scope gate in
//! Python (only the GET list does), so the Rust ports match that behavior.

use std::collections::HashMap;
use std::path::Path;

use axum::{
    extract::{Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{auth::AuthContext, state::SharedState};

#[derive(Deserialize)]
pub struct ReorderServersBody {
    #[serde(default)]
    pub server_ids: Vec<String>,
}

fn read_config(config_path: &Path) -> Result<Value, std::io::Error> {
    let text = std::fs::read_to_string(config_path)?;
    crate::config_io::parse_strict(config_path, &text)
}

/// `ai_servers` accessor that distinguishes "absent" (treated as empty) from
/// "present but not a list" (Python returns an error in that case).
fn servers_array(config: &Value) -> Result<Option<&Vec<Value>>, String> {
    match config.get("ai_servers") {
        None => Ok(None),
        Some(Value::Array(arr)) => Ok(Some(arr)),
        Some(_) => Err("No servers configured".to_string()),
    }
}

/// set_active_server: verify the id exists, then set `ai_servers_active`.
fn do_activate(config: &mut Value, server_id: &str) -> Result<Value, String> {
    let exists = servers_array(config)?
        .map(|servers| {
            servers
                .iter()
                .any(|s| s.get("id").and_then(Value::as_str) == Some(server_id))
        })
        .unwrap_or(false);
    if !exists {
        return Err(format!("Server '{server_id}' not found"));
    }
    config["ai_servers_active"] = json!(server_id);
    Ok(json!({"success": true, "active": server_id}))
}

/// reorder_servers: set priority = (idx+1)*10 for each listed id, preserving the
/// original list order (Python rebuilds from an insertion-ordered id map).
fn do_reorder(config: &mut Value, server_ids: &[String]) -> Result<Value, String> {
    // Validate shape (present-but-not-array → error); absent is a no-op success.
    servers_array(config)?;
    if let Some(servers) = config.get_mut("ai_servers").and_then(Value::as_array_mut) {
        for (idx, server_id) in server_ids.iter().enumerate() {
            let priority = ((idx + 1) * 10) as i64;
            for server in servers.iter_mut() {
                if server.get("id").and_then(Value::as_str) == Some(server_id.as_str()) {
                    server["priority"] = json!(priority);
                }
            }
        }
    }
    Ok(json!({"success": true}))
}

const MAX_SERVERS: usize = 10;
const VALID_SERVER_TYPES: &[&str] = &[
    "claude_api",
    "openai",
    "openai_compat",
    "ollama",
    "hailo_vlm",
];

#[derive(Debug)]
pub struct AddServerBody {
    pub id: Option<String>,
    pub name: String,
    pub server_type: String,
    pub priority: Option<i64>,
    pub enabled: bool,
    pub config: Value,
}

#[derive(Debug, Default, Deserialize)]
pub struct UpdateServerBody {
    pub name: Option<String>,
    #[serde(rename = "type")]
    pub server_type: Option<String>,
    pub priority: Option<i64>,
    pub enabled: Option<bool>,
    pub config: Option<Value>,
}

/// Strictly validates a raw JSON request body into an `AddServerBody`,
/// mirroring pydantic's `AnalysisServerCreateRequest` (`StrictStr`/
/// `StrictInt`/`StrictBool`, `name` and `type` required with no default,
/// `config` constrained to a JSON object). Unlike a plain
/// `#[serde(default)]`-based `Deserialize` struct, this rejects:
/// - a missing or non-string `name`/`type`/`id`
/// - a non-integer (e.g. float) `priority`
/// - a non-bool `enabled`
/// - a non-object `config` (Python's `dict[str, Any]` type-checks this)
fn parse_add_server_body(raw: &Value) -> Result<AddServerBody, String> {
    let obj = raw
        .as_object()
        .ok_or_else(|| "JSON object body required".to_string())?;

    let id = match obj.get("id") {
        None | Some(Value::Null) => None,
        Some(Value::String(s)) => Some(s.clone()),
        Some(_) => return Err("'id' must be a string".to_string()),
    };

    let name = match obj.get("name") {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) | None => return Err("Server name is required".to_string()),
        Some(_) => return Err("'name' must be a string".to_string()),
    };

    let server_type = match obj.get("type") {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) | None => {
            return Err(format!(
                "Invalid type: . Must be one of {VALID_SERVER_TYPES:?}"
            ))
        }
        Some(_) => return Err("'type' must be a string".to_string()),
    };

    let priority = match obj.get("priority") {
        None | Some(Value::Null) => None,
        Some(Value::Number(n)) => match n.as_i64() {
            Some(i) => Some(i),
            None => return Err("'priority' must be an integer".to_string()),
        },
        Some(_) => return Err("'priority' must be an integer".to_string()),
    };

    // Python's `enabled: StrictBool = True` and `config: dict[str, Any] =
    // Field(default_factory=dict)` are NOT `Optional` — the default only
    // applies when the key is absent. An explicit `null` still fails
    // pydantic's type check, so it must be rejected here too, not folded
    // into the same "absent" branch as `id`/`priority` (which really are
    // `X | None` in Python).
    let enabled = match obj.get("enabled") {
        None => true,
        Some(Value::Bool(b)) => *b,
        Some(_) => return Err("'enabled' must be a boolean".to_string()),
    };

    let config = match obj.get("config") {
        None => json!({}),
        Some(v @ Value::Object(_)) => v.clone(),
        Some(_) => return Err("'config' must be a JSON object".to_string()),
    };

    Ok(AddServerBody {
        id,
        name,
        server_type,
        priority,
        enabled,
        config,
    })
}

/// Mirrors Python's `server_model_data.py::_slugify`.
fn slugify_server_name(name: &str) -> String {
    let mut result = String::new();
    let mut last_was_dash = false;
    for c in name.to_lowercase().trim().chars() {
        if c.is_ascii_alphanumeric() {
            result.push(c);
            last_was_dash = false;
        } else if !last_was_dash {
            result.push('-');
            last_was_dash = true;
        }
    }
    let trimmed: String = result.trim_matches('-').chars().take(32).collect();
    if trimmed.is_empty() {
        "server".to_string()
    } else {
        trimmed
    }
}

/// add_server: validate name/type, dedupe/slugify id, apply default priority,
/// append to `ai_servers`, and set `ai_servers_active` if unset — mirrors
/// Python's `server_crud.py::add_server` + `server_model_data.py::_validate_and_build`.
fn do_add(config: &mut Value, body: &AddServerBody) -> Result<Value, String> {
    let name = body.name.trim();
    if name.is_empty() {
        return Err("Server name is required".to_string());
    }
    if !VALID_SERVER_TYPES.contains(&body.server_type.as_str()) {
        return Err(format!(
            "Invalid type: {}. Must be one of {:?}",
            body.server_type, VALID_SERVER_TYPES
        ));
    }

    let servers: Vec<Value> = servers_array(config)?.cloned().unwrap_or_default();
    if servers.len() >= MAX_SERVERS {
        return Err(format!("Maximum {MAX_SERVERS} servers allowed"));
    }

    let id_taken = |candidate: &str, servers: &[Value]| {
        servers
            .iter()
            .any(|s| s.get("id").and_then(Value::as_str) == Some(candidate))
    };

    let mut sid = body
        .id
        .clone()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| slugify_server_name(name));
    if id_taken(&sid, &servers) {
        let base = sid.clone();
        for i in 2..100 {
            let candidate = format!("{base}-{i}");
            if !id_taken(&candidate, &servers) {
                sid = candidate;
                break;
            }
        }
    }

    let priority = body
        .priority
        .unwrap_or_else(|| ((servers.len() + 1) * 10) as i64);
    let entry = json!({
        "id": sid,
        "name": name,
        "type": body.server_type,
        "priority": priority,
        "enabled": body.enabled,
        "config": body.config,
    });

    let ai_servers = config
        .as_object_mut()
        .expect("config root is always a JSON object")
        .entry("ai_servers")
        .or_insert_with(|| json!([]));
    if let Some(arr) = ai_servers.as_array_mut() {
        arr.push(entry.clone());
    }

    let needs_active = config
        .get("ai_servers_active")
        .and_then(Value::as_str)
        .map(str::is_empty)
        .unwrap_or(true);
    if needs_active {
        config["ai_servers_active"] = json!(sid);
    }

    Ok(json!({"success": true, "server": entry}))
}

/// POST /api/analysis/servers
///
/// No admin scope gate — matches Python (`api_servers_add` has none; see
/// module doc-comment for the established parity rationale for this file's
/// write endpoints).
pub async fn add_server(State(state): State<SharedState>, Json(raw): Json<Value>) -> Response {
    let body = match parse_add_server_body(&raw) {
        Ok(body) => body,
        Err(message) => return api_error(&message, StatusCode::BAD_REQUEST),
    };
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    match do_add(&mut config, &body) {
        Ok(result) => match crate::config_io::write(&state.config.config_path, &config) {
            Ok(()) => api_created(result),
            Err(error) => internal_error(error, "failed to write config"),
        },
        Err(message) => api_error(&message, StatusCode::BAD_REQUEST),
    }
}

/// POST /api/analysis/servers/{id}/activate
pub async fn activate_server(
    State(state): State<SharedState>,
    AxumPath(server_id): AxumPath<String>,
) -> Response {
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    match do_activate(&mut config, &server_id) {
        Ok(result) => match crate::config_io::write(&state.config.config_path, &config) {
            Ok(()) => api_result(result),
            Err(error) => internal_error(error, "failed to write config"),
        },
        Err(message) => api_error(&message, StatusCode::BAD_REQUEST),
    }
}

/// PUT /api/analysis/servers/reorder
pub async fn reorder_servers(
    State(state): State<SharedState>,
    Json(body): Json<ReorderServersBody>,
) -> Response {
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    match do_reorder(&mut config, &body.server_ids) {
        Ok(result) => match crate::config_io::write(&state.config.config_path, &config) {
            Ok(()) => api_result(result),
            Err(error) => internal_error(error, "failed to write config"),
        },
        Err(message) => api_error(&message, StatusCode::BAD_REQUEST),
    }
}

/// Compatible server types per discovery provider — mirrors Python
/// `_compatible_server_types`.
fn compatible_server_types(provider: &str) -> &'static [&'static str] {
    match provider {
        "ollama" => &["ollama"],
        "openai_compat" => &["openai_compat"],
        "hailo_genai" => &["hailo_vlm"],
        _ => &[],
    }
}

/// Prune discovery-match entries that reference a removed/incompatible server —
/// mirrors Python `_cleanup_discovery_metadata`.
fn cleanup_discovery_metadata(config: &mut Value) {
    let server_types: HashMap<String, String> = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .map(|servers| {
            servers
                .iter()
                .filter_map(|s| {
                    let id = s
                        .get("id")
                        .and_then(Value::as_str)
                        .filter(|i| !i.is_empty())?;
                    let ty = s.get("type").and_then(Value::as_str).unwrap_or("");
                    Some((id.to_string(), ty.to_string()))
                })
                .collect()
        })
        .unwrap_or_default();

    let Some(matches) = config
        .get("ai_servers_discovery_matches")
        .and_then(Value::as_object)
        .cloned()
    else {
        return;
    };

    let cleaned: serde_json::Map<String, Value> = matches
        .into_iter()
        .filter(|(_, data)| {
            let Some(obj) = data.as_object() else {
                return false;
            };
            let Some(sid) = obj.get("server_id").and_then(Value::as_str) else {
                return false;
            };
            let Some(stype) = server_types.get(sid) else {
                return false;
            };
            let provider = obj.get("provider").and_then(Value::as_str).unwrap_or("");
            compatible_server_types(provider).contains(&stype.as_str())
        })
        .collect();

    if cleaned.is_empty() {
        if let Some(obj) = config.as_object_mut() {
            obj.remove("ai_servers_discovery_matches");
        }
    } else {
        config["ai_servers_discovery_matches"] = Value::Object(cleaned);
    }
}

/// remove_server: drop the server by id, reassign active to the lowest-priority
/// survivor, and prune discovery metadata.
fn do_remove(config: &mut Value, server_id: &str) -> Result<Value, String> {
    // present-but-not-list → error; absent → empty list (Python `.get` default []).
    let servers: Vec<Value> = match config.get("ai_servers") {
        None => Vec::new(),
        Some(Value::Array(arr)) => arr.clone(),
        Some(_) => return Err("No servers configured".to_string()),
    };
    let new_servers: Vec<Value> = servers
        .iter()
        .filter(|s| s.get("id").and_then(Value::as_str) != Some(server_id))
        .cloned()
        .collect();
    if new_servers.len() == servers.len() {
        return Err(format!("Server '{server_id}' not found"));
    }
    let active_removed = config.get("ai_servers_active").and_then(Value::as_str) == Some(server_id);

    config["ai_servers"] = json!(new_servers);

    if active_removed {
        if new_servers.is_empty() {
            if let Some(obj) = config.as_object_mut() {
                obj.remove("ai_servers_active");
            }
        } else {
            let mut sorted = new_servers.clone();
            sorted.sort_by_key(|s| s.get("priority").and_then(Value::as_i64).unwrap_or(50));
            config["ai_servers_active"] = sorted[0].get("id").cloned().unwrap_or(Value::Null);
        }
    }

    cleanup_discovery_metadata(config);
    Ok(json!({"success": true}))
}

fn apply_update(server: &mut Value, body: &UpdateServerBody) -> Result<(), String> {
    let entry = server
        .as_object_mut()
        .ok_or_else(|| "Invalid server entry".to_string())?;
    if let Some(name) = &body.name {
        let name = name.trim();
        if name.is_empty() {
            return Err("Server name is required".to_string());
        }
        entry.insert("name".to_string(), Value::String(name.to_string()));
    }
    if let Some(server_type) = &body.server_type {
        if !VALID_SERVER_TYPES.contains(&server_type.as_str()) {
            return Err(format!("Invalid type: {server_type}"));
        }
        entry.insert("type".to_string(), Value::String(server_type.clone()));
    }
    if let Some(priority) = body.priority {
        entry.insert("priority".to_string(), json!(priority));
    }
    if let Some(enabled) = body.enabled {
        entry.insert("enabled".to_string(), json!(enabled));
    }
    if let Some(config) = &body.config {
        entry.insert("config".to_string(), config.clone());
    }
    Ok(())
}

pub(crate) fn do_update(
    config: &mut Value,
    server_id: &str,
    body: &UpdateServerBody,
) -> Result<Value, String> {
    if matches!(config.get("ai_servers"), Some(value) if !value.is_array()) {
        return Err("No servers configured".to_string());
    }

    if let Some(server) = config
        .get_mut("ai_servers")
        .and_then(Value::as_array_mut)
        .and_then(|servers| {
            servers
                .iter_mut()
                .find(|server| server.get("id").and_then(Value::as_str) == Some(server_id))
        })
    {
        apply_update(server, body)?;
        let server = server.clone();
        cleanup_discovery_metadata(config);
        return Ok(json!({"success": true, "server": server}));
    }

    if server_id == "legacy-default" {
        // Persist the raw stored key; all_servers decrypts only the API response.
        if let Some(mut server) = super::analysis::legacy_server_entry(config) {
            apply_update(&mut server, body)?;
            if config.get("ai_servers").is_none() {
                config["ai_servers"] = json!([]);
            }
            config["ai_servers"]
                .as_array_mut()
                .expect("ai_servers checked as an array")
                .push(server.clone());
            if config
                .get("ai_servers_active")
                .and_then(Value::as_str)
                .is_none_or(str::is_empty)
            {
                config["ai_servers_active"] = json!("legacy-default");
            }
            cleanup_discovery_metadata(config);
            return Ok(json!({"success": true, "server": server}));
        }
    }

    Err(format!("Server '{server_id}' not found"))
}

/// DELETE /api/analysis/servers/{id}
pub async fn remove_server(
    State(state): State<SharedState>,
    AxumPath(server_id): AxumPath<String>,
) -> Response {
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    match do_remove(&mut config, &server_id) {
        Ok(result) => match crate::config_io::write(&state.config.config_path, &config) {
            Ok(()) => api_result(result),
            Err(error) => internal_error(error, "failed to write config"),
        },
        Err(message) => api_error(&message, StatusCode::BAD_REQUEST),
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

/// Same envelope as `api_result` but with a 201 Created status, for
/// resource-creation endpoints (mirrors Python's `api_result(result, 201)`).
fn api_created(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return (
                StatusCode::CREATED,
                Json(json!({"ok": true, "error": null, "data": other})),
            )
                .into_response()
        }
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    (StatusCode::CREATED, Json(Value::Object(body))).into_response()
}

/// Python `api_error(message, status)` without a code (matches the call site).
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

/// POST /api/analysis/servers/{server_id}/test — Rust native connectivity check
pub async fn test_server(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(server_id): AxumPath<String>,
) -> Response {
    use crate::auth::scope::require_admin_scope;
    if let Some(r) = require_admin_scope(state.config.pin_auth_enabled, auth.as_deref()) {
        return r;
    }
    let config = match read_config(&state.config.config_path) {
        Ok(c) => c,
        Err(e) => return internal_error(e, "Failed to read config"),
    };
    let servers = match config.get("ai_servers").and_then(Value::as_array) {
        Some(s) => s.clone(),
        None => return api_error("No servers configured", StatusCode::NOT_FOUND),
    };
    let server = match servers
        .iter()
        .find(|s| s.get("id").and_then(Value::as_str) == Some(&server_id))
    {
        Some(s) => s.clone(),
        None => {
            return api_error(
                &format!("Server '{server_id}' not found"),
                StatusCode::NOT_FOUND,
            )
        }
    };
    let stype = server.get("type").and_then(Value::as_str).unwrap_or("");
    let cfg = server.get("config").cloned().unwrap_or(json!({}));
    let start = std::time::Instant::now();
    let available = match stype {
        "claude_api" | "openai" => cfg
            .get("api_key")
            .and_then(Value::as_str)
            .map(|k| !k.is_empty())
            .unwrap_or(false),
        "ollama" => {
            let url = cfg
                .get("base_url")
                .and_then(Value::as_str)
                .unwrap_or("http://localhost:11434");
            let tags_url = format!("{}/api/tags", url.trim_end_matches('/'));
            let client = reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(3))
                .build()
                .unwrap_or_default();
            client
                .get(&tags_url)
                .header("Accept", "application/json")
                .send()
                .await
                .map(|r| r.status().is_success())
                .unwrap_or(false)
        }
        "openai_compat" => {
            let url = cfg.get("base_url").and_then(Value::as_str).unwrap_or("");
            if url.is_empty() {
                false
            } else {
                let api_key = cfg.get("api_key").and_then(Value::as_str).unwrap_or("");
                let models_url = format!("{}/v1/models", url.trim_end_matches('/'));
                let client = reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(3))
                    .build()
                    .unwrap_or_default();
                let mut req = client.get(&models_url).header("Accept", "application/json");
                if !api_key.is_empty() {
                    req = req.header("Authorization", format!("Bearer {api_key}"));
                }
                req.send()
                    .await
                    .map(|r| r.status().is_success() || r.status().as_u16() == 401)
                    .unwrap_or(false)
            }
        }
        _ => false,
    };
    let elapsed_ms = u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX);
    Json(json!({"ok": true, "available": available, "elapsed_ms": elapsed_ms})).into_response()
}

/// PUT /api/analysis/servers/{server_id} — admin scope required.
///
/// Native port of `core/analysis_api/server_crud.py::update_server`.
pub async fn update_server(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(server_id): AxumPath<String>,
    Json(raw): Json<Value>,
) -> Response {
    use crate::auth::scope::require_admin_scope;
    if let Some(r) = require_admin_scope(state.config.pin_auth_enabled, auth.as_ref().map(|c| &c.0))
    {
        return r;
    }
    let body = match serde_json::from_value::<UpdateServerBody>(raw) {
        Ok(body) => body,
        Err(error) => return api_error(&error.to_string(), StatusCode::BAD_REQUEST),
    };
    let _write_guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    match do_update(&mut config, &server_id, &body) {
        Ok(result) => match crate::config_io::write(&state.config.config_path, &config) {
            Ok(()) => api_result(result),
            Err(error) => internal_error(error, "failed to write config"),
        },
        Err(error) => api_error(&error, StatusCode::BAD_REQUEST),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config_with_servers() -> Value {
        json!({
            "ai_servers": [
                {"id": "a", "name": "A", "priority": 10},
                {"id": "b", "name": "B", "priority": 20},
                {"id": "c", "name": "C", "priority": 30}
            ],
            "ai_servers_active": "a"
        })
    }

    #[test]
    fn activate_sets_active_when_id_exists() {
        let mut config = config_with_servers();
        let result = do_activate(&mut config, "b").unwrap();
        assert_eq!(result["success"], true);
        assert_eq!(result["active"], "b");
        assert_eq!(config["ai_servers_active"], "b");
    }

    #[test]
    fn activate_errors_when_id_missing() {
        let mut config = config_with_servers();
        let err = do_activate(&mut config, "zzz").unwrap_err();
        assert_eq!(err, "Server 'zzz' not found");
        // active unchanged
        assert_eq!(config["ai_servers_active"], "a");
    }

    #[test]
    fn activate_errors_when_servers_not_a_list() {
        let mut config = json!({"ai_servers": {"oops": true}});
        assert_eq!(
            do_activate(&mut config, "a").unwrap_err(),
            "No servers configured"
        );
    }

    #[test]
    fn reorder_sets_priorities_preserving_list_order() {
        let mut config = config_with_servers();
        // New order c, a, b → priorities 10, 20, 30 by listed position.
        let result = do_reorder(&mut config, &["c".into(), "a".into(), "b".into()]).unwrap();
        assert_eq!(result["success"], true);
        let servers = config["ai_servers"].as_array().unwrap();
        // List order is preserved (a, b, c); only priorities change.
        assert_eq!(servers[0]["id"], "a");
        assert_eq!(servers[0]["priority"], 20); // a was listed 2nd → (1+1)*10
        assert_eq!(servers[1]["id"], "b");
        assert_eq!(servers[1]["priority"], 30); // b listed 3rd → (2+1)*10
        assert_eq!(servers[2]["id"], "c");
        assert_eq!(servers[2]["priority"], 10); // c listed 1st → (0+1)*10
    }

    #[test]
    fn reorder_ignores_unknown_ids_and_is_noop_when_absent() {
        let mut config = json!({});
        assert_eq!(
            do_reorder(&mut config, &["x".into()]).unwrap()["success"],
            true
        );

        let mut config = config_with_servers();
        do_reorder(&mut config, &["zzz".into()]).unwrap();
        // unknown id changes nothing
        assert_eq!(config["ai_servers"][0]["priority"], 10);
    }

    #[test]
    fn remove_drops_server_and_reassigns_active() {
        let mut config = config_with_servers(); // a(10),b(20),c(30), active=a
        let result = do_remove(&mut config, "a").unwrap();
        assert_eq!(result["success"], true);
        let servers = config["ai_servers"].as_array().unwrap();
        assert_eq!(servers.len(), 2);
        assert!(servers.iter().all(|s| s["id"] != "a"));
        // active was the removed server → reassigned to lowest-priority survivor (b).
        assert_eq!(config["ai_servers_active"], "b");
    }

    #[test]
    fn remove_errors_when_id_missing() {
        let mut config = config_with_servers();
        assert_eq!(
            do_remove(&mut config, "zzz").unwrap_err(),
            "Server 'zzz' not found"
        );
    }

    #[test]
    fn remove_non_active_keeps_active() {
        let mut config = config_with_servers(); // active=a
        do_remove(&mut config, "b").unwrap();
        assert_eq!(config["ai_servers_active"], "a");
    }

    #[test]
    fn remove_prunes_stale_discovery_matches() {
        let mut config = json!({
            "ai_servers": [{"id": "a", "type": "ollama", "priority": 10}],
            "ai_servers_active": "a",
            "ai_servers_discovery_matches": {
                "http://x": {"server_id": "a", "provider": "ollama"},
                "http://y": {"server_id": "gone", "provider": "ollama"}
            }
        });
        do_remove(&mut config, "a").unwrap();
        // No servers remain → every match references an absent server → key removed.
        assert!(config.get("ai_servers_discovery_matches").is_none());
    }

    #[test]
    fn remove_keeps_match_to_surviving_compatible_server() {
        let mut config = json!({
            "ai_servers": [
                {"id": "a", "type": "ollama", "priority": 10},
                {"id": "b", "type": "ollama", "priority": 20}
            ],
            "ai_servers_active": "x",
            "ai_servers_discovery_matches": {"http://x": {"server_id": "b", "provider": "ollama"}}
        });
        do_remove(&mut config, "a").unwrap();
        assert_eq!(
            config["ai_servers_discovery_matches"]["http://x"]["server_id"],
            "b"
        );
    }

    fn add_body(name: &str, server_type: &str) -> AddServerBody {
        AddServerBody {
            id: None,
            name: name.to_string(),
            server_type: server_type.to_string(),
            priority: None,
            enabled: true,
            config: json!({}),
        }
    }

    #[test]
    fn add_rejects_empty_name() {
        let mut config = json!({});
        let err = do_add(&mut config, &add_body("  ", "ollama")).unwrap_err();
        assert_eq!(err, "Server name is required");
    }

    #[test]
    fn add_rejects_invalid_type() {
        let mut config = json!({});
        let err = do_add(&mut config, &add_body("My Server", "bogus")).unwrap_err();
        assert!(err.starts_with("Invalid type: bogus"));
    }

    #[test]
    fn add_rejects_when_at_max_servers() {
        let servers: Vec<Value> = (0..10)
            .map(|i| json!({"id": format!("s{i}"), "name": format!("S{i}"), "priority": 10}))
            .collect();
        let mut config = json!({"ai_servers": servers});
        let err = do_add(&mut config, &add_body("New", "ollama")).unwrap_err();
        assert_eq!(err, "Maximum 10 servers allowed");
    }

    #[test]
    fn add_slugifies_name_when_id_absent() {
        let mut config = json!({});
        let result = do_add(&mut config, &add_body("My Cool Server!", "ollama")).unwrap();
        assert_eq!(result["server"]["id"], "my-cool-server");
        assert_eq!(result["server"]["name"], "My Cool Server!");
        assert_eq!(result["server"]["priority"], 10); // (0+1)*10, empty list
    }

    #[test]
    fn add_appends_suffix_on_id_collision() {
        let mut config = json!({"ai_servers": [{"id": "myserver", "name": "Existing"}]});
        let mut body = add_body("Another", "ollama");
        body.id = Some("myserver".to_string());
        let result = do_add(&mut config, &body).unwrap();
        assert_eq!(result["server"]["id"], "myserver-2");
    }

    #[test]
    fn add_sets_active_when_previously_unset() {
        let mut config = json!({});
        let result = do_add(&mut config, &add_body("First", "ollama")).unwrap();
        let sid = result["server"]["id"].as_str().unwrap().to_string();
        assert_eq!(config["ai_servers_active"], sid);
    }

    #[test]
    fn add_does_not_override_existing_active() {
        let mut config = json!({"ai_servers_active": "existing"});
        do_add(&mut config, &add_body("Second", "ollama")).unwrap();
        assert_eq!(config["ai_servers_active"], "existing");
    }

    #[test]
    fn add_uses_explicit_priority_and_id_when_given() {
        let mut config = json!({});
        let mut body = add_body("Named", "openai");
        body.id = Some("custom-id".to_string());
        body.priority = Some(5);
        let result = do_add(&mut config, &body).unwrap();
        assert_eq!(result["server"]["id"], "custom-id");
        assert_eq!(result["server"]["priority"], 5);
    }

    #[test]
    fn slugify_collapses_runs_and_truncates() {
        assert_eq!(slugify_server_name("My Cool Server!!"), "my-cool-server");
        assert_eq!(slugify_server_name("   "), "server");
        assert_eq!(slugify_server_name(&"a".repeat(50)), "a".repeat(32));
    }

    // parse_add_server_body: strict validation matching pydantic StrictStr/
    // StrictInt/StrictBool/dict[str, Any] semantics (Codex stop-time review
    // flagged the original #[serde(default)]-based struct as too permissive).

    #[test]
    fn parse_rejects_non_object_body() {
        let err = parse_add_server_body(&json!(["not", "an", "object"])).unwrap_err();
        assert_eq!(err, "JSON object body required");
    }

    #[test]
    fn parse_rejects_missing_name() {
        let err = parse_add_server_body(&json!({"type": "ollama"})).unwrap_err();
        assert_eq!(err, "Server name is required");
    }

    #[test]
    fn parse_rejects_explicit_null_name() {
        let err = parse_add_server_body(&json!({"name": null, "type": "ollama"})).unwrap_err();
        assert_eq!(err, "Server name is required");
    }

    #[test]
    fn parse_rejects_explicit_null_type() {
        let err = parse_add_server_body(&json!({"name": "My Server", "type": null})).unwrap_err();
        assert!(err.starts_with("Invalid type: ."));
    }

    #[test]
    fn parse_rejects_non_string_name() {
        let err = parse_add_server_body(&json!({"name": 123, "type": "ollama"})).unwrap_err();
        assert_eq!(err, "'name' must be a string");
    }

    #[test]
    fn parse_rejects_missing_type() {
        let err = parse_add_server_body(&json!({"name": "My Server"})).unwrap_err();
        assert!(err.starts_with("Invalid type: ."));
    }

    #[test]
    fn parse_rejects_non_string_type() {
        let err = parse_add_server_body(&json!({"name": "My Server", "type": 5})).unwrap_err();
        assert_eq!(err, "'type' must be a string");
    }

    #[test]
    fn parse_rejects_float_priority() {
        let err = parse_add_server_body(
            &json!({"name": "My Server", "type": "ollama", "priority": 10.5}),
        )
        .unwrap_err();
        assert_eq!(err, "'priority' must be an integer");
    }

    #[test]
    fn parse_rejects_non_bool_enabled() {
        let err = parse_add_server_body(
            &json!({"name": "My Server", "type": "ollama", "enabled": "yes"}),
        )
        .unwrap_err();
        assert_eq!(err, "'enabled' must be a boolean");
    }

    #[test]
    fn parse_rejects_explicit_null_enabled() {
        // Python's `enabled: StrictBool = True` is not Optional: the default
        // applies only when the key is absent, not when it's explicitly null.
        let err =
            parse_add_server_body(&json!({"name": "My Server", "type": "ollama", "enabled": null}))
                .unwrap_err();
        assert_eq!(err, "'enabled' must be a boolean");
    }

    #[test]
    fn parse_rejects_explicit_null_config() {
        // Python's `config: dict[str, Any] = Field(default_factory=dict)` is
        // not Optional either.
        let err =
            parse_add_server_body(&json!({"name": "My Server", "type": "ollama", "config": null}))
                .unwrap_err();
        assert_eq!(err, "'config' must be a JSON object");
    }

    #[test]
    fn parse_rejects_non_object_config() {
        let err = parse_add_server_body(
            &json!({"name": "My Server", "type": "ollama", "config": "not-an-object"}),
        )
        .unwrap_err();
        assert_eq!(err, "'config' must be a JSON object");

        let err = parse_add_server_body(
            &json!({"name": "My Server", "type": "ollama", "config": ["a", "b"]}),
        )
        .unwrap_err();
        assert_eq!(err, "'config' must be a JSON object");
    }

    #[test]
    fn parse_rejects_non_string_id() {
        let err = parse_add_server_body(&json!({"id": 42, "name": "My Server", "type": "ollama"}))
            .unwrap_err();
        assert_eq!(err, "'id' must be a string");
    }

    #[test]
    fn parse_accepts_minimal_valid_body_with_defaults() {
        let body = parse_add_server_body(&json!({"name": "My Server", "type": "ollama"})).unwrap();
        assert_eq!(body.name, "My Server");
        assert_eq!(body.server_type, "ollama");
        assert_eq!(body.id, None);
        assert_eq!(body.priority, None);
        assert!(body.enabled);
        assert_eq!(body.config, json!({}));
    }

    #[test]
    fn parse_accepts_full_valid_body() {
        let body = parse_add_server_body(&json!({
            "id": "custom",
            "name": "My Server",
            "type": "openai_compat",
            "priority": 15,
            "enabled": false,
            "config": {"base_url": "http://x"}
        }))
        .unwrap();
        assert_eq!(body.id, Some("custom".to_string()));
        assert_eq!(body.priority, Some(15));
        assert!(!body.enabled);
        assert_eq!(body.config, json!({"base_url": "http://x"}));
    }

    fn update_body() -> UpdateServerBody {
        UpdateServerBody::default()
    }

    #[test]
    fn update_name_only_preserves_other_fields() {
        let mut config = json!({"ai_servers": [{"id": "a", "name": "Old", "type": "ollama", "priority": 3, "enabled": false, "config": {"model": "x"}}]});
        let body = UpdateServerBody {
            name: Some(" New ".to_string()),
            ..update_body()
        };
        do_update(&mut config, "a", &body).unwrap();
        assert_eq!(
            config["ai_servers"][0],
            json!({"id": "a", "name": "New", "type": "ollama", "priority": 3, "enabled": false, "config": {"model": "x"}})
        );
    }

    #[test]
    fn update_rejects_invalid_type() {
        let mut config = json!({"ai_servers": [{"id": "a"}]});
        let body = UpdateServerBody {
            server_type: Some("bogus".to_string()),
            ..update_body()
        };
        assert_eq!(
            do_update(&mut config, "a", &body),
            Err("Invalid type: bogus".to_string())
        );
    }

    #[test]
    fn update_rejects_blank_name() {
        let mut config = json!({"ai_servers": [{"id": "a"}]});
        let body = UpdateServerBody {
            name: Some("   ".to_string()),
            ..update_body()
        };
        assert_eq!(
            do_update(&mut config, "a", &body),
            Err("Server name is required".to_string())
        );
    }

    #[test]
    fn update_rejects_unknown_server_without_legacy_config() {
        let mut config = json!({"ai_servers": []});
        assert_eq!(
            do_update(&mut config, "nope", &update_body()),
            Err("Server 'nope' not found".to_string())
        );
    }

    #[test]
    fn update_legacy_default_appends_raw_legacy_entry() {
        let mut config = json!({"ai_analysis": {"engine": "ollama", "ollama_model": "vision"}});
        do_update(&mut config, "legacy-default", &update_body()).unwrap();
        assert_eq!(config["ai_servers"][0]["priority"], 10);
        assert_eq!(config["ai_servers"][0]["enabled"], true);
        assert_eq!(config["ai_servers"][0]["config"]["model"], "vision");
    }

    #[test]
    fn update_legacy_default_keeps_stored_api_key() {
        let mut config =
            json!({"ai_analysis": {"engine": "openai", "openai_api_key": "encrypted-key"}});
        do_update(&mut config, "legacy-default", &update_body()).unwrap();
        assert_eq!(
            config["ai_servers"][0]["config"]["api_key"],
            "encrypted-key"
        );
    }

    #[test]
    fn update_rejects_non_list_servers() {
        let mut config = json!({"ai_servers": {"oops": true}});
        assert_eq!(
            do_update(&mut config, "a", &update_body()),
            Err("No servers configured".to_string())
        );
    }

    #[test]
    fn update_writes_priority_enabled_and_config() {
        let mut config = json!({"ai_servers": [{"id": "a", "priority": 1, "enabled": true, "config": {"model": "old"}}]});
        let body = UpdateServerBody {
            priority: Some(42),
            enabled: Some(false),
            config: Some(json!({"model": "new"})),
            ..update_body()
        };
        do_update(&mut config, "a", &body).unwrap();
        assert_eq!(config["ai_servers"][0]["priority"], 42);
        assert_eq!(config["ai_servers"][0]["enabled"], false);
        assert_eq!(config["ai_servers"][0]["config"], json!({"model": "new"}));
    }

    #[test]
    fn update_legacy_default_sets_active_when_unset() {
        let mut config = json!({"ai_analysis": {"engine": "ollama"}});
        do_update(&mut config, "legacy-default", &update_body()).unwrap();
        assert_eq!(config["ai_servers_active"], "legacy-default");
    }

    #[test]
    fn update_legacy_default_keeps_an_existing_active_id() {
        let mut config = json!({"ai_analysis": {"engine": "ollama"}, "ai_servers_active": "other"});
        do_update(&mut config, "legacy-default", &update_body()).unwrap();
        assert_eq!(config["ai_servers_active"], "other");
    }

    #[test]
    fn update_legacy_default_rejects_empty_ai_analysis() {
        // Python `_legacy_to_entry` bails on a falsy ai_config; an empty object
        // must not synthesise a claude_api entry.
        let mut config = json!({"ai_analysis": {}});
        assert_eq!(
            do_update(&mut config, "legacy-default", &update_body()),
            Err("Server 'legacy-default' not found".to_string())
        );
        assert!(config.get("ai_servers").is_none());
    }

    #[test]
    fn update_returns_the_stored_entry_not_the_request() {
        let mut config = json!({"ai_servers": [{"id": "a", "name": "Kept", "type": "ollama"}]});
        let body = UpdateServerBody {
            priority: Some(7),
            ..update_body()
        };
        let result = do_update(&mut config, "a", &body).unwrap();
        assert_eq!(result["server"]["name"], "Kept");
        assert_eq!(result["server"]["priority"], 7);
    }

    #[test]
    fn update_leaves_config_unwritten_shape_on_validation_error() {
        // A later invalid field must not let an earlier valid one reach the
        // caller as a success; the handler discards the config on Err.
        let mut config = json!({"ai_servers": [{"id": "a", "name": "Old"}]});
        let body = UpdateServerBody {
            name: Some("New".to_string()),
            server_type: Some("bogus".to_string()),
            ..update_body()
        };
        assert!(do_update(&mut config, "a", &body).is_err());
    }

    #[test]
    fn update_prunes_incompatible_discovery_match() {
        let mut config = json!({
            "ai_servers": [{"id": "a", "type": "ollama"}],
            "ai_servers_discovery_matches": {"http://x": {"server_id": "a", "provider": "ollama"}}
        });
        let body = UpdateServerBody {
            server_type: Some("openai".to_string()),
            ..update_body()
        };
        do_update(&mut config, "a", &body).unwrap();
        assert!(config.get("ai_servers_discovery_matches").is_none());
    }
}

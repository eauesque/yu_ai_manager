use axum::{
    extract::{Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    secret_store,
    state::SharedState,
};

pub async fn list_llm_endpoints(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let mut result = serde_json::Map::new();
    if let Some(endpoints) = state
        .config
        .app_config
        .get("llm_endpoints")
        .and_then(Value::as_object)
    {
        for (category, endpoint) in endpoints {
            if let Some(endpoint_map) = endpoint.as_object() {
                let mut entry = endpoint_map.clone();
                let api_key = entry.get("api_key").and_then(Value::as_str).unwrap_or("");
                let api_key = secret_store::decrypt(api_key, &state.config.project_root);
                entry.insert(
                    "api_key".to_string(),
                    Value::String(secret_store::mask_secret(&api_key)),
                );
                result.insert(category.clone(), Value::Object(entry));
            }
        }
    }
    api_result(Value::Object(result))
}

const READ_TOOLS: &[&str] = &[
    "search_files",
    "get_file_info",
    "get_file_tags",
    "list_scan_roots",
    "get_stats",
    "get_server_info",
    "list_collections",
    "list_llm_endpoints",
    "get_server_mode",
];

const WRITE_TOOLS: &[&str] = &[
    "set_tags",
    "add_to_collection",
    "remove_from_collection",
    "create_collection",
    "rate_image",
    "toggle_favorite",
];

/// GET /api/llm/agent/capabilities
pub async fn agent_capabilities(State(state): State<SharedState>) -> Response {
    let llm_hef = {
        std::env::var_os("HAILO_LLM_HEF")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| {
                let home = std::env::var_os("HOME")
                    .map(std::path::PathBuf::from)
                    .unwrap_or_else(|| std::path::PathBuf::from("/home/pi"));
                home.join("hailo_models").join("Llama3.2-1B-Instruct.hef")
            })
    };
    let hailo_available = llm_hef.exists();
    let available_models: Vec<&str> = if hailo_available {
        vec!["qwen2.5-coder-1.5b"]
    } else {
        vec![]
    };
    let _ = state; // state unused here; kept for consistency with other handlers
    api_result(json!({
        "hailo_available": hailo_available,
        "recommended_model": "qwen2.5-coder-1.5b",
        "available_models": available_models,
        "usage": {
            "category": "hailo",
            "tools_default": "read-only (search, stats, collections, server info)",
            "tools_all": "read + write (tags, collections, ratings, favorites)",
            "example": {
                "endpoint": "POST /api/llm/agent",
                "body": {
                    "category": "hailo",
                    "message": "your task here",
                    "tools": "all",
                    "max_rounds": 5
                }
            },
            "mcp_tool": "llm_agent_run(category='hailo', message='...', tools='all')"
        },
        "tools": {
            "read": READ_TOOLS,
            "write": WRITE_TOOLS
        },
        "strengths": [
            "Zero API cost — runs entirely on local Hailo-10H NPU",
            "Works offline — no internet required",
            "Fast for structured tool calling — search, tag, rate, organize",
            "Single-step tool calls are highly reliable",
            "Good at: file search, stats lookup, tag operations, collection management, rating"
        ],
        "limitations": [
            "1.5B parameter model — limited reasoning capability",
            "Max ~2-3 tool call rounds are reliable; beyond that quality degrades",
            "Cannot analyze image content (use VLM separately for that)",
            "Poor at: ambiguous instructions, multi-step planning, creative writing",
            "Context window is small — large search results are truncated to 1500 chars",
            "Shares NPU bandwidth with other Hailo models — concurrent CLIP/YOLO/VLM workloads are time-sliced by HailoRT scheduler and may slow each other down"
        ],
        "delegation_guidelines": {
            "delegate_to_hailo": [
                "Simple file searches by tag (search_files)",
                "Database statistics queries (get_stats)",
                "Batch tag operations (set_tags with known file_ids)",
                "Adding/removing files to/from collections",
                "Rating files (rate_image)",
                "Toggling favorites",
                "Listing collections or scan roots"
            ],
            "keep_in_orchestrator": [
                "Complex multi-step plans requiring reasoning",
                "Tasks needing image content understanding",
                "Ambiguous or open-ended instructions",
                "Tasks requiring more than 3 tool calls",
                "Any task requiring external API calls"
            ]
        }
    }))
}

/// DELETE /api/settings/llm-endpoints/{category}
pub async fn delete_endpoint(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(category): AxumPath<String>,
) -> Response {
    if let Some(err) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return err;
    }
    let config_path = std::path::PathBuf::from(&state.config.db_path)
        .parent()
        .unwrap_or_else(|| std::path::Path::new("."))
        .join("config.json");
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let endpoints = config
        .get_mut("llm_endpoints")
        .and_then(|v| v.as_object_mut());
    let not_found = || {
        (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "not found", "data": null})),
        )
            .into_response()
    };
    match config
        .get_mut("llm_endpoints")
        .and_then(|v| v.as_object_mut())
    {
        None => return not_found(),
        Some(map) if !map.contains_key(&category) => return not_found(),
        Some(map) => {
            map.remove(&category);
        }
    }
    if let Err(e) = crate::config_io::write(&config_path, &config) {
        tracing::error!("delete_endpoint write error: {e}");
        return Json(json!({"ok": false, "error": "write failed", "data": null})).into_response();
    }
    api_result(json!({"deleted": category}))
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

/// PUT /api/settings/llm-endpoints
pub async fn update_llm_endpoints(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(r) = crate::auth::scope::require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    let category = body
        .get("category")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let base_url = body
        .get("base_url")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let model = body
        .get("model")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if category.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "category is required", "data": null})),
        )
            .into_response();
    }
    if base_url.is_empty() || model.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "base_url and model are required", "data": null})),
        )
            .into_response();
    }
    let raw_key = body
        .get("api_key")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let timeout = body.get("timeout").and_then(Value::as_i64).unwrap_or(60);
    let config_path = std::path::PathBuf::from(&state.config.db_path)
        .parent()
        .unwrap_or_else(|| std::path::Path::new("."))
        .join("config.json");
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let stored_key = if raw_key.is_empty() || raw_key.contains("****") {
        config
            .get("llm_endpoints")
            .and_then(|e| e.get(&category))
            .and_then(|e| e.get("api_key"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string()
    } else {
        secret_store::encrypt(&raw_key, &state.config.project_root)
    };
    if let Some(root) = config.as_object_mut() {
        root.entry("llm_endpoints").or_insert_with(|| json!({}));
    }
    if let Some(ep_map) = config
        .get_mut("llm_endpoints")
        .and_then(|v| v.as_object_mut())
    {
        ep_map.insert(
            category.clone(),
            json!({"base_url": base_url, "model": model, "api_key": stored_key, "timeout": timeout}),
        );
    }
    if let Err(e) = crate::config_io::write(&config_path, &config) {
        tracing::error!("update_llm_endpoints write error: {e}");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "write failed", "data": null})),
        )
            .into_response();
    }
    api_result(json!({"category": category}))
}

/// POST /api/settings/llm-endpoints/test
pub async fn test_endpoint_connection(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(r) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return r;
    }
    let base_url = body
        .get("base_url")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if base_url.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "base_url is required"})),
        )
            .into_response();
    }
    let raw_key = body
        .get("api_key")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let api_key = if raw_key.starts_with("enc:") {
        secret_store::decrypt(&raw_key, &state.config.project_root)
    } else {
        raw_key
    };
    let mut req = state
        .inference_client
        .get(format!("{}/models", base_url.trim_end_matches('/')))
        .timeout(std::time::Duration::from_secs(10));
    if !api_key.is_empty() && !api_key.contains("****") {
        req = req.header("Authorization", format!("Bearer {}", api_key));
    }
    match req.send().await {
        Ok(resp) if resp.status().as_u16() < 400 => {
            let data = resp.json::<Value>().await.unwrap_or(Value::Null);
            api_result(json!({"models": data}))
        }
        Ok(resp) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({"ok": false, "error": format!("HTTP {}", resp.status())})),
        )
            .into_response(),
        Err(_) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({"ok": false, "error": "Endpoint connection failed"})),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use base64::Engine;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    async fn test_state(app_config: serde_json::Value) -> SharedState {
        test_state_with_root(app_config, PathBuf::from(".")).await
    }

    async fn test_state_with_root(
        app_config: serde_json::Value,
        project_root: PathBuf,
    ) -> SharedState {
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
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("config.json"),
                    project_root,
                    app_config,
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

    fn temp_secret_root(name: &str, plaintext: &str) -> (PathBuf, String) {
        let root = std::env::temp_dir().join(format!(
            "yu-llm-endpoints-secret-{name}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("data")).unwrap();
        let key = base64::engine::general_purpose::URL_SAFE.encode([13_u8; 32]);
        std::fs::write(root.join("data").join("secret.key"), &key).unwrap();
        let token = crate::secret_store::encrypt_for_test(plaintext, key.as_bytes());
        (root, format!("enc:{token}"))
    }

    async fn json_body(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn list_llm_endpoints_returns_empty_top_level_envelope_without_config() {
        let response = list_llm_endpoints(State(test_state(json!({})).await), None).await;
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value, json!({"ok": true, "error": null, "data": null}));
    }

    #[tokio::test]
    async fn list_llm_endpoints_masks_api_keys_and_preserves_endpoint_fields() {
        let response = list_llm_endpoints(
            State(
                test_state(json!({
                    "llm_endpoints": {
                        "openai": {
                            "base_url": "https://api.example.test/v1",
                            "model": "model-a",
                            "api_key": "abcdefghijklmnop",
                            "timeout": 45
                        }
                    }
                }))
                .await,
            ),
            None,
        )
        .await;
        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["data"], serde_json::Value::Null);
        assert_eq!(value["openai"]["base_url"], "https://api.example.test/v1");
        assert_eq!(value["openai"]["model"], "model-a");
        assert_eq!(value["openai"]["api_key"], "a****p");
        assert_eq!(value["openai"]["timeout"], 45);
    }

    #[tokio::test]
    async fn list_llm_endpoints_masks_decrypted_api_key_not_encrypted_blob() {
        let (root, stored) = temp_secret_root("mask", "plain-secret-value");
        let response = list_llm_endpoints(
            State(
                test_state_with_root(
                    json!({
                        "llm_endpoints": {
                            "openai": {
                                "base_url": "https://api.example.test/v1",
                                "model": "model-a",
                                "api_key": stored
                            }
                        }
                    }),
                    root,
                )
                .await,
            ),
            None,
        )
        .await;
        let value = json_body(response).await;
        assert_eq!(value["openai"]["api_key"], "p****e");
    }
}

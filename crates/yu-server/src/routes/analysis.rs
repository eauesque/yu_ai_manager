use std::collections::{HashMap, HashSet};
use std::net::{SocketAddr, UdpSocket};
use std::path::{Path, PathBuf};
use std::time::Duration;

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    analysis_engines::{
        zstd_write::compress_for_storage, AnalysisEngine, AnalysisResult, AnalyzeContext,
        AnalyzeMode,
    },
    auth::{scope::require_admin_scope, AuthContext},
    secret_store,
    state::SharedState,
};

use super::analysis_net;

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.entry("ok".to_string()).or_insert(Value::Bool(true));
    body.entry("error".to_string()).or_insert(Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn ai_config(state: &SharedState) -> Value {
    state
        .config
        .app_config
        .get("ai_analysis")
        .cloned()
        .unwrap_or_else(|| json!({}))
}

fn non_empty(value: Option<&Value>) -> bool {
    value.and_then(Value::as_str).is_some_and(|s| !s.is_empty())
}

fn mask_api_key(api_key: &str) -> String {
    let chars = api_key.chars().collect::<Vec<_>>();
    if chars.len() <= 6 {
        return api_key.to_string();
    }
    let first = chars.iter().take(4).collect::<String>();
    let last = chars
        .iter()
        .skip(chars.len().saturating_sub(2))
        .collect::<String>();
    format!("{first}...{last}")
}

fn should_probe_local_engine(url: &str, local_only: bool) -> bool {
    !local_only || analysis_net::is_private_url(url)
}

fn decrypted_config_secret(config: &Value, key: &str, project_root: &Path) -> String {
    config
        .get(key)
        .and_then(Value::as_str)
        .map(|stored| secret_store::decrypt(stored, project_root))
        .unwrap_or_default()
}

fn normalize_base_url(url: &str) -> String {
    let raw = url.trim();
    if raw.is_empty() {
        return String::new();
    }
    let Ok(parsed) = reqwest::Url::parse(raw) else {
        return String::new();
    };
    let scheme = parsed.scheme().to_ascii_lowercase();
    let Some(host) = parsed.host_str().map(str::to_ascii_lowercase) else {
        return String::new();
    };
    let default_port = match scheme.as_str() {
        "http" => Some(80),
        "https" => Some(443),
        _ => None,
    };
    let netloc = match parsed.port() {
        Some(port) if Some(port) != default_port => format!("{host}:{port}"),
        _ => host,
    };
    let path = parsed.path().trim_end_matches('/');
    if path.is_empty() || path == "/" {
        format!("{scheme}://{netloc}")
    } else {
        format!("{scheme}://{netloc}{path}")
    }
}

#[derive(Clone)]
struct ServerEntry {
    id: String,
    name: String,
    server_type: String,
    config: Value,
}

pub(crate) fn legacy_server_entry(config: &Value) -> Option<Value> {
    let ai = config.get("ai_analysis")?;
    // Python `_legacy_to_entry` bails on a falsy ai_config, so an empty object
    // yields no legacy entry rather than a synthesised claude_api default.
    if ai.as_object().is_none_or(|fields| fields.is_empty()) {
        return None;
    }
    let engine = ai
        .get("engine")
        .and_then(Value::as_str)
        .unwrap_or("claude_api");
    let language = ai.get("language").and_then(Value::as_str).unwrap_or("ja");
    let (name, cfg) = match engine {
        "ollama" => {
            let model = ai
                .get("ollama_model")
                .and_then(Value::as_str)
                .unwrap_or("llava:latest");
            (
                format!("Ollama ({model})"),
                json!({"base_url": ai.get("ollama_url").and_then(Value::as_str).unwrap_or("http://localhost:11434"), "model": model, "language": language}),
            )
        }
        "openai_compat" => {
            let model = ai
                .get("openai_compat_model")
                .and_then(Value::as_str)
                .unwrap_or("");
            (
                format!(
                    "OpenAI Compatible ({})",
                    if model.is_empty() { "default" } else { model }
                ),
                json!({"base_url": ai.get("openai_compat_url").and_then(Value::as_str).unwrap_or(""), "api_key": ai.get("openai_compat_api_key").and_then(Value::as_str).unwrap_or(""), "model": model, "language": language}),
            )
        }
        "hailo_vlm" => {
            let model = ai
                .get("hailo_vlm_model")
                .and_then(Value::as_str)
                .unwrap_or("qwen2-vl-2b-instruct");
            (
                format!("Hailo VLM ({model})"),
                json!({"model_name": model, "language": language}),
            )
        }
        "openai" => {
            let model = ai
                .get("openai_model")
                .and_then(Value::as_str)
                .unwrap_or("gpt-4o-mini");
            (
                format!("OpenAI ({model})"),
                json!({"api_key": ai.get("openai_api_key").and_then(Value::as_str).unwrap_or(""), "model": model, "language": language}),
            )
        }
        _ => {
            let model = ai
                .get("model")
                .and_then(Value::as_str)
                .unwrap_or("claude-sonnet-4-6");
            (
                format!("Claude ({model})"),
                json!({"api_key": ai.get("api_key").and_then(Value::as_str).unwrap_or(""), "model": model, "language": language}),
            )
        }
    };
    Some(json!({
        "id": "legacy-default",
        "name": name,
        "type": engine,
        "priority": 10,
        "enabled": true,
        "config": cfg,
    }))
}

fn all_servers(config: &Value, project_root: &Path) -> Vec<ServerEntry> {
    let mut servers = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .filter(|servers| !servers.is_empty())
        .map(|servers| {
            servers
                .iter()
                .map(|server| {
                    let mut config = server.get("config").cloned().unwrap_or_else(|| json!({}));
                    if let Some(map) = config.as_object_mut() {
                        if let Some(stored) = map.get("api_key").and_then(Value::as_str) {
                            map.insert(
                                "api_key".to_string(),
                                Value::String(secret_store::decrypt(stored, project_root)),
                            );
                        }
                    }
                    ServerEntry {
                        id: server
                            .get("id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        name: server
                            .get("name")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        server_type: server
                            .get("type")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        config,
                    }
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    servers.sort_by_key(|server| {
        config
            .get("ai_servers")
            .and_then(Value::as_array)
            .and_then(|raw| {
                raw.iter()
                    .find(|item| item.get("id").and_then(Value::as_str) == Some(server.id.as_str()))
            })
            .and_then(|raw| raw.get("priority"))
            .and_then(Value::as_i64)
            .unwrap_or(50)
    });
    if !servers.is_empty() {
        return servers;
    }
    let Some(server) = legacy_server_entry(config) else {
        return Vec::new();
    };
    let mut server_config = server.get("config").cloned().unwrap_or_else(|| json!({}));
    if let Some(map) = server_config.as_object_mut() {
        if let Some(stored) = map.get("api_key").and_then(Value::as_str) {
            map.insert(
                "api_key".to_string(),
                Value::String(secret_store::decrypt(stored, project_root)),
            );
        }
    }
    vec![ServerEntry {
        id: server["id"].as_str().unwrap_or_default().to_string(),
        name: server["name"].as_str().unwrap_or_default().to_string(),
        server_type: server["type"].as_str().unwrap_or_default().to_string(),
        config: server_config,
    }]
}

fn compatible_server_types(provider: &str) -> &'static [&'static str] {
    match provider {
        "ollama" => &["ollama"],
        "openai_compat" => &["openai_compat"],
        "hailo_genai" => &["hailo_vlm"],
        _ => &[],
    }
}

fn build_match_state(
    provider: &str,
    canonical_url: &str,
    servers: &[ServerEntry],
    config: &Value,
) -> (Vec<Value>, Value, Value) {
    let compatible = compatible_server_types(provider);
    let matchable_servers = servers
        .iter()
        .filter(|server| compatible.contains(&server.server_type.as_str()))
        .map(|server| json!({"id": server.id, "name": server.name}))
        .collect::<Vec<_>>();
    let raw_match = config
        .get("ai_servers_discovery_matches")
        .and_then(Value::as_object)
        .and_then(|matches| matches.get(canonical_url))
        .and_then(Value::as_object);
    let Some(raw_match) = raw_match else {
        return (matchable_servers, Value::Null, Value::Null);
    };
    let server_id = raw_match.get("server_id").and_then(Value::as_str);
    let matched = servers.iter().find(|server| {
        Some(server.id.as_str()) == server_id && compatible.contains(&server.server_type.as_str())
    });
    match matched {
        Some(server) => (
            matchable_servers,
            Value::String(server.id.clone()),
            Value::String(server.name.clone()),
        ),
        None => (matchable_servers, Value::Null, Value::Null),
    }
}

fn discovery_ignored(config: &Value) -> HashSet<String> {
    config
        .get("ai_servers_discovery_ignored")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(normalize_base_url)
                .filter(|url| !url.is_empty())
                .collect()
        })
        .unwrap_or_default()
}

fn detect_local_network_facts() -> (Option<String>, Vec<String>, String) {
    let mut addresses = Vec::new();
    if let Ok(socket) = UdpSocket::bind("0.0.0.0:0") {
        if socket.connect("8.8.8.8:80").is_ok() {
            if let Ok(SocketAddr::V4(addr)) = socket.local_addr() {
                addresses.push(addr.ip().to_string());
            }
        }
    }
    if addresses.is_empty() {
        addresses.push("127.0.0.1".to_string());
    }
    let primary = addresses.iter().find(|ip| !ip.starts_with("127.")).cloned();
    (primary, addresses, hostname())
}

fn hostname() -> String {
    std::env::var("HOSTNAME")
        .ok()
        .filter(|value| !value.is_empty())
        .or_else(|| {
            std::fs::read_to_string("/etc/hostname")
                .ok()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
        })
        .unwrap_or_else(|| "localhost".to_string())
}

async fn probe_ollama_tags(base_url: &str, timeout: Duration, user_agent: &str) -> bool {
    let base = normalize_base_url(base_url);
    if base.is_empty() {
        return false;
    }
    let Ok(client) = reqwest::Client::builder().timeout(timeout).build() else {
        return false;
    };
    client
        .get(format!("{base}/api/tags"))
        .header(reqwest::header::USER_AGENT, user_agent)
        .send()
        .await
        .map(|response| response.status() == reqwest::StatusCode::OK)
        .unwrap_or(false)
}

async fn probe_openai_compat_models(base_url: &str, api_key: &str) -> (bool, Option<&'static str>) {
    let base = normalize_base_url(base_url);
    if base.is_empty() {
        return (false, Some("connection_failed"));
    }
    let Ok(client) = reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
    else {
        return (false, Some("connection_failed"));
    };
    let mut request = client
        .get(format!("{base}/v1/models"))
        .header(reqwest::header::USER_AGENT, "yu_ai_manager/discovery")
        .header(reqwest::header::ACCEPT, "application/json");
    if !api_key.is_empty() {
        request = request.bearer_auth(api_key);
    }
    let Ok(response) = request.send().await else {
        return (false, Some("connection_failed"));
    };
    match response.status().as_u16() {
        200 => match response.json::<Value>().await {
            Ok(payload) if payload.get("data").and_then(Value::as_array).is_some() => (true, None),
            _ => (false, Some("invalid_response")),
        },
        401 | 403 => (false, Some("auth_required")),
        404 => (false, Some("probe_not_found")),
        _ => (false, Some("connection_failed")),
    }
}

async fn discover_local_ollama_candidates() -> Vec<Value> {
    let (primary_lan_ip, _, _) = detect_local_network_facts();
    if let Some(ip) = primary_lan_ip {
        let lan_url = normalize_base_url(&format!("http://{ip}:11434"));
        if probe_ollama_tags(&lan_url, Duration::from_secs(1), "yu_ai_manager/mdns").await {
            return vec![json!({
                "provider": "ollama",
                "base_url": lan_url,
                "display_preferred_url": lan_url,
                "scope": "private_lan",
                "source": "local_auto",
                "reachable": true,
                "advertisable": true,
                "duplicate_of_canonical_url": null,
                "suppressed_reason": null,
            })];
        }
    }
    let loopback_url = normalize_base_url("http://localhost:11434");
    if probe_ollama_tags(&loopback_url, Duration::from_secs(1), "yu_ai_manager/mdns").await {
        return vec![json!({
            "provider": "ollama",
            "base_url": loopback_url,
            "display_preferred_url": loopback_url,
            "scope": "loopback",
            "source": "local_auto",
            "reachable": true,
            "advertisable": false,
            "duplicate_of_canonical_url": null,
            "suppressed_reason": "policy_hidden",
        })];
    }
    Vec::new()
}

fn hailo_device_paths() -> [&'static str; 2] {
    ["/dev/hailo0", "/dev/h1x-0"]
}

fn is_hailo_device_available() -> bool {
    hailo_device_paths()
        .iter()
        .any(|path| Path::new(path).exists())
}

fn hailo_model_filename(model_name: &str) -> Option<&'static str> {
    match model_name {
        "qwen2-vl-2b-instruct" => Some("Qwen2-VL-2B-Instruct.hef"),
        "qwen3-vl-2b-instruct" => Some("Qwen3-VL-2B-Instruct.hef"),
        "qwen3-1.7b-instruct" => Some("Qwen3-1.7B-Instruct.hef"),
        "qwen2.5-1.5b-chat" => Some("Qwen2.5-1.5B-Instruct.hef"),
        "llama3.2-1b" => Some("Llama3.2-1B-Instruct.hef"),
        "deepseek-r1-1.5b" => Some("DeepSeek-R1-Distill-Qwen-1.5B.hef"),
        "qwen2.5-coder-1.5b" => Some("Qwen2.5-Coder-1.5B-Instruct.hef"),
        "whisper-base" => Some("Whisper-Base.hef"),
        "whisper-small" => Some("Whisper-Small.hef"),
        _ => None,
    }
}

fn hailo_hef_dir() -> PathBuf {
    std::env::var_os("HAILO_HEF_DIR")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join("hailo_models")))
        .unwrap_or_else(|| PathBuf::from("hailo_models"))
}

pub(crate) fn is_hailo_hef_available(model_name: &str) -> bool {
    let Some(filename) = hailo_model_filename(model_name) else {
        return false;
    };
    hailo_hef_dir().join(filename).exists()
}

fn is_hailo_vlm_available(model_name: &str) -> bool {
    is_hailo_device_available() && is_hailo_hef_available(model_name)
}

fn hailo_extension_available() -> bool {
    is_hailo_device_available()
}

fn self_web_port(config: &Value) -> i64 {
    config
        .get("server")
        .and_then(|server| server.get("port"))
        .and_then(Value::as_i64)
        .unwrap_or(5000)
}

fn local_hailo_candidates(config: &Value) -> Vec<Value> {
    if !config
        .get("hailo")
        .and_then(|hailo| hailo.get("enabled"))
        .and_then(Value::as_bool)
        .unwrap_or(true)
        || !hailo_extension_available()
    {
        return Vec::new();
    }
    let port = self_web_port(config);
    let url = normalize_base_url(&format!("http://localhost:{port}/ext/hailo-genai/v1"));
    vec![json!({
        "provider": "hailo_genai",
        "base_url": url,
        "display_preferred_url": format!("http://localhost:{port}/ext/hailo-genai/v1"),
        "scope": "loopback",
        "source": "local_auto",
        "reachable": true,
        "advertisable": false,
        "duplicate_of_canonical_url": null,
        "suppressed_reason": null,
        "model_name": "qwen2-vl-2b-instruct",
    })]
}

pub async fn available_engines(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let ai = ai_config(&state);
    let local_only = ai
        .get("fallback_local_only")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let mut engines = Vec::new();
    if !local_only && non_empty(ai.get("api_key")) {
        engines.push(json!({
            "type": "claude_api",
            "label": "Claude API",
            "model": ai.get("model").and_then(Value::as_str).unwrap_or("claude-sonnet-4-6"),
            "models": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"],
        }));
    }
    if !local_only && non_empty(ai.get("openai_api_key")) {
        engines.push(json!({
            "type": "openai",
            "label": "OpenAI",
            "model": ai.get("openai_model").and_then(Value::as_str).unwrap_or("gpt-4o-mini"),
            "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
        }));
    }
    let compat_url = ai
        .get("openai_compat_url")
        .and_then(Value::as_str)
        .unwrap_or("");
    if !compat_url.is_empty() && should_probe_local_engine(compat_url, local_only) {
        let compat_key =
            decrypted_config_secret(&ai, "openai_compat_api_key", &state.config.project_root);
        let result =
            analysis_net::check_openai_compat_connection_allowing_local(compat_url, &compat_key)
                .await;
        if result
            .get("connected")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            let models = result
                .get("models")
                .and_then(Value::as_array)
                .map(|models| {
                    models
                        .iter()
                        .filter_map(|model| model.get("id").and_then(Value::as_str))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            engines.push(json!({
                "type": "openai_compat",
                "label": "OpenAI Compatible",
                "model": ai.get("openai_compat_model").and_then(Value::as_str).unwrap_or(""),
                "models": models,
            }));
        }
    }
    let ollama_url = ai
        .get("ollama_url")
        .and_then(Value::as_str)
        .unwrap_or("http://localhost:11434");
    if should_probe_local_engine(ollama_url, local_only) {
        let ollama = analysis_net::check_ollama_connection(ollama_url).await;
        if ollama
            .get("connected")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            let models = ollama
                .get("models")
                .and_then(Value::as_array)
                .map(|models| {
                    models
                        .iter()
                        .filter_map(|model| model.get("name").and_then(Value::as_str))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            engines.push(json!({
                "type": "ollama",
                "label": "Ollama",
                "model": ai.get("ollama_model").and_then(Value::as_str).unwrap_or("llava:latest"),
                "models": models,
            }));
        }
    }
    let hailo_model = ai
        .get("hailo_vlm_model")
        .and_then(Value::as_str)
        .unwrap_or("qwen2-vl-2b-instruct");
    if is_hailo_vlm_available(hailo_model) {
        engines.push(json!({
            "type": "hailo_vlm",
            "label": "Hailo VLM",
            "model": hailo_model,
            "models": [hailo_model],
        }));
    }
    api_result(json!({"engines": engines}))
}

pub async fn ollama_models(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let ai = ai_config(&state);
    let base_url = ai
        .get("ollama_url")
        .and_then(Value::as_str)
        .unwrap_or("http://localhost:11434");
    if let Some(error) = analysis_net::validate_ollama_url(base_url) {
        return api_error(&error, StatusCode::BAD_REQUEST);
    }
    api_result(analysis_net::check_ollama_connection(base_url).await)
}

pub async fn openai_compat_models(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let ai = ai_config(&state);
    let base_url = ai
        .get("openai_compat_url")
        .and_then(Value::as_str)
        .unwrap_or("");
    if base_url.is_empty() {
        return api_error(
            "OpenAI Compatible URL is not configured",
            StatusCode::BAD_REQUEST,
        );
    }
    if let Some(error) = analysis_net::validate_openai_compat_url(base_url, false) {
        return api_error(&error, StatusCode::BAD_REQUEST);
    }
    let api_key = decrypted_config_secret(&ai, "openai_compat_api_key", &state.config.project_root);
    api_result(analysis_net::check_openai_compat_connection(base_url, &api_key).await)
}

pub async fn discovered_servers(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let candidates =
        compute_discovered_candidates(&state.config.app_config, &state.config.project_root).await;
    api_result(json!({"candidates": candidates}))
}

async fn compute_discovered_candidates(config: &Value, project_root: &Path) -> Vec<Value> {
    let servers = all_servers(config, project_root);
    let ignored_urls = discovery_ignored(config);
    let registered_urls = servers
        .iter()
        .filter_map(|server| server.config.get("base_url").and_then(Value::as_str))
        .map(normalize_base_url)
        .filter(|url| !url.is_empty())
        .collect::<HashSet<_>>();
    let openai_compat_registered_urls = servers
        .iter()
        .filter(|server| server.server_type == "openai_compat")
        .filter_map(|server| server.config.get("base_url").and_then(Value::as_str))
        .map(normalize_base_url)
        .filter(|url| !url.is_empty())
        .collect::<HashSet<_>>();
    let hailo_registered = servers
        .iter()
        .any(|server| server.server_type == "hailo_vlm");
    let mut candidates = Vec::new();

    for endpoint in discover_local_ollama_candidates().await {
        let canonical = normalize_base_url(
            endpoint
                .get("base_url")
                .and_then(Value::as_str)
                .unwrap_or(""),
        );
        let ignored = ignored_urls.contains(&canonical);
        let (matchable_servers, matched_id, matched_name) =
            build_match_state("ollama", &canonical, &servers, config);
        let suppressed_reason = endpoint
            .get("suppressed_reason")
            .cloned()
            .filter(|value| !value.is_null())
            .unwrap_or_else(|| {
                if !matched_id.is_null() {
                    json!("matched_existing")
                } else if ignored {
                    json!("policy_hidden")
                } else {
                    Value::Null
                }
            });
        candidates.push(json!({
            "provider": "ollama",
            "base_url": canonical,
            "display_preferred_url": endpoint.get("display_preferred_url").and_then(Value::as_str).unwrap_or(&canonical),
            "scope": endpoint.get("scope").and_then(Value::as_str).unwrap_or("loopback"),
            "source": endpoint.get("source").and_then(Value::as_str).unwrap_or("local_auto"),
            "reachable": endpoint.get("reachable").and_then(Value::as_bool).unwrap_or(false),
            "advertisable": endpoint.get("advertisable").and_then(Value::as_bool).unwrap_or(false),
            "duplicate_of_canonical_url": endpoint.get("duplicate_of_canonical_url").cloned().unwrap_or(Value::Null),
            "already_registered": registered_urls.contains(&canonical),
            "ignored": ignored,
            "suppressed_reason": suppressed_reason,
            "matched_existing_server_id": matched_id,
            "matched_existing_server_name": matched_name,
            "matchable_servers": matchable_servers,
        }));
    }

    if let Some(mut candidate) = discover_known_openai_compat_candidate(config, project_root).await
    {
        let canonical = normalize_base_url(
            candidate
                .get("base_url")
                .and_then(Value::as_str)
                .unwrap_or(""),
        );
        let ignored = ignored_urls.contains(&canonical);
        let (matchable_servers, matched_id, matched_name) =
            build_match_state("openai_compat", &canonical, &servers, config);
        let base_reason = candidate
            .get("suppressed_reason")
            .cloned()
            .filter(|value| !value.is_null());
        let suppressed_reason = base_reason.unwrap_or_else(|| {
            if !matched_id.is_null() {
                json!("matched_existing")
            } else if ignored {
                json!("policy_hidden")
            } else {
                Value::Null
            }
        });
        let map = candidate.as_object_mut().expect("candidate object");
        map.insert("base_url".to_string(), json!(canonical));
        map.insert(
            "display_preferred_url".to_string(),
            json!(map
                .get("display_preferred_url")
                .and_then(Value::as_str)
                .unwrap_or(&canonical)),
        );
        map.insert(
            "already_registered".to_string(),
            json!(openai_compat_registered_urls.contains(&canonical)),
        );
        map.insert("ignored".to_string(), json!(ignored));
        map.insert("suppressed_reason".to_string(), suppressed_reason);
        map.insert("matched_existing_server_id".to_string(), matched_id);
        map.insert("matched_existing_server_name".to_string(), matched_name);
        map.insert("matchable_servers".to_string(), json!(matchable_servers));
        candidates.push(candidate);
    }

    for endpoint in local_hailo_candidates(config) {
        let canonical = normalize_base_url(
            endpoint
                .get("base_url")
                .and_then(Value::as_str)
                .unwrap_or(""),
        );
        let ignored = ignored_urls.contains(&canonical);
        let (matchable_servers, matched_id, matched_name) =
            build_match_state("hailo_genai", &canonical, &servers, config);
        let suppressed_reason = endpoint
            .get("suppressed_reason")
            .cloned()
            .filter(|value| !value.is_null())
            .unwrap_or_else(|| {
                if !matched_id.is_null() {
                    json!("matched_existing")
                } else if ignored {
                    json!("policy_hidden")
                } else {
                    Value::Null
                }
            });
        candidates.push(json!({
            "provider": "hailo_genai",
            "base_url": canonical,
            "display_preferred_url": endpoint.get("display_preferred_url").and_then(Value::as_str).unwrap_or(&canonical),
            "scope": endpoint.get("scope").and_then(Value::as_str).unwrap_or("loopback"),
            "source": endpoint.get("source").and_then(Value::as_str).unwrap_or("local_auto"),
            "reachable": endpoint.get("reachable").and_then(Value::as_bool).unwrap_or(false),
            "advertisable": endpoint.get("advertisable").and_then(Value::as_bool).unwrap_or(false),
            "duplicate_of_canonical_url": endpoint.get("duplicate_of_canonical_url").cloned().unwrap_or(Value::Null),
            "already_registered": hailo_registered,
            "ignored": ignored,
            "suppressed_reason": suppressed_reason,
            "model_name": endpoint.get("model_name").and_then(Value::as_str).unwrap_or("qwen2-vl-2b-instruct"),
            "matched_existing_server_id": matched_id,
            "matched_existing_server_name": matched_name,
            "matchable_servers": matchable_servers,
        }));
    }
    candidates
}

async fn discover_known_openai_compat_candidate(
    config: &Value,
    project_root: &Path,
) -> Option<Value> {
    let ai = config.get("ai_analysis").unwrap_or(&Value::Null);
    let base_url = normalize_base_url(
        ai.get("openai_compat_url")
            .and_then(Value::as_str)
            .unwrap_or(""),
    );
    if base_url.is_empty() || !analysis_net::is_private_url(&base_url) {
        return None;
    }
    let api_key = decrypted_config_secret(ai, "openai_compat_api_key", project_root);
    let (reachable, reason) = probe_openai_compat_models(&base_url, &api_key).await;
    Some(json!({
        "provider": "openai_compat",
        "base_url": base_url,
        "display_preferred_url": base_url,
        "scope": if base_url.contains("localhost") || base_url.contains("127.0.0.1") { "loopback" } else { "private_lan" },
        "source": "local_auto",
        "reachable": reachable,
        "advertisable": false,
        "duplicate_of_canonical_url": null,
        "already_registered": false,
        "suppressed_reason": reason,
        "model": ai.get("openai_compat_model").and_then(Value::as_str).unwrap_or(""),
        "matched_existing_server_id": null,
        "matched_existing_server_name": null,
        "matchable_servers": [],
        "ignored": false,
    }))
}

pub async fn servers(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let active_id = state
        .config
        .app_config
        .get("ai_servers_active")
        .and_then(Value::as_str);
    let mut servers = state
        .config
        .app_config
        .get("ai_servers")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    servers.sort_by_key(|server| server.get("priority").and_then(Value::as_i64).unwrap_or(50));
    for server in &mut servers {
        let Some(map) = server.as_object_mut() else {
            continue;
        };
        let id = map.get("id").and_then(Value::as_str).map(str::to_string);
        map.insert(
            "is_active".to_string(),
            Value::Bool(id.as_deref() == active_id),
        );
        map.insert("status".to_string(), Value::String("unknown".to_string()));
        if let Some(config) = map.get_mut("config").and_then(Value::as_object_mut) {
            if let Some(api_key) = config.get("api_key").and_then(Value::as_str) {
                let plaintext = secret_store::decrypt(api_key, &state.config.project_root);
                if plaintext.len() > 6 {
                    config.insert(
                        "api_key".to_string(),
                        Value::String(mask_api_key(&plaintext)),
                    );
                } else {
                    config.insert("api_key".to_string(), Value::String(plaintext));
                }
            }
        }
    }
    api_result(json!({"servers": servers}))
}

pub async fn trend_history(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let limit = params
        .get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(20)
        .min(50);
    let offset = params
        .get("offset")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(0)
        .max(0);
    match sqlx::query(
        "SELECT id, engine, analyzed_at, prompt_count, result_json
         FROM prompt_trend_history
         ORDER BY analyzed_at DESC
         LIMIT ? OFFSET ?",
    )
    .bind(limit)
    .bind(offset)
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => {
            let mut items = Vec::new();
            for row in rows {
                let result_json = row.try_get::<String, _>("result_json").unwrap_or_default();
                let result = serde_json::from_str::<Value>(&result_json).unwrap_or(Value::Null);
                items.push(json!({
                    "id": row.try_get::<i64, _>("id").unwrap_or_default(),
                    "engine": row.try_get::<String, _>("engine").unwrap_or_default(),
                    "analyzed_at": row.try_get::<i64, _>("analyzed_at").unwrap_or_default(),
                    "prompt_count": row.try_get::<i64, _>("prompt_count").unwrap_or_default(),
                    "result": result,
                }));
            }
            api_result(json!({"items": items}))
        }
        Err(error) => {
            tracing::error!(?error, "trend_history error");
            api_error(
                "Failed to get trend history",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

/// POST /api/analysis/batch/cancel
pub async fn batch_cancel() -> axum::response::Response {
    axum::Json(json!({"ok": true, "cancelled": 0})).into_response()
}

/// POST /api/analysis/analyze/{file_id}
pub async fn analyze_file(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    axum::extract::Path(file_id): axum::extract::Path<i64>,
) -> Response {
    if let Some(response) = require_admin_scope(state.config.pin_auth_enabled, auth.as_deref()) {
        return response;
    }
    let ai = ai_config(&state);
    if !ai.is_object() || ai.as_object().is_some_and(serde_json::Map::is_empty) {
        return Json(json!({"ok": false, "error": "no_legacy_ai_analysis_config"})).into_response();
    }
    let engine_type = ai.get("engine").and_then(Value::as_str).unwrap_or("ollama");
    let Some(file_path) = resolve_analysis_file_path(&state, file_id).await else {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "file_not_found"})),
        )
            .into_response();
    };
    let language = ai
        .get("language")
        .and_then(Value::as_str)
        .unwrap_or("ja")
        .to_string();
    let engine: Box<dyn AnalysisEngine> = match engine_type {
        "ollama" => Box::new(crate::analysis_engines::ollama::OllamaEngine {
            base_url: ai
                .get("ollama_url")
                .and_then(Value::as_str)
                .unwrap_or("http://localhost:11434")
                .to_string(),
            model: ai
                .get("ollama_model")
                .and_then(Value::as_str)
                .unwrap_or("llava:latest")
                .to_string(),
            language: language.clone(),
        }),
        "openai" => Box::new(crate::analysis_engines::openai_compat::OpenAiCompatEngine {
            base_url: None,
            model: ai
                .get("openai_model")
                .and_then(Value::as_str)
                .unwrap_or("gpt-4o-mini")
                .to_string(),
            api_key: decrypted_config_secret(&ai, "openai_api_key", &state.config.project_root),
            language: language.clone(),
        }),
        "openai_compat" => Box::new(crate::analysis_engines::openai_compat::OpenAiCompatEngine {
            base_url: Some(
                ai.get("openai_compat_url")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
            ),
            model: ai
                .get("openai_compat_model")
                .and_then(Value::as_str)
                .unwrap_or("gpt-4o-mini")
                .to_string(),
            api_key: decrypted_config_secret(
                &ai,
                "openai_compat_api_key",
                &state.config.project_root,
            ),
            language: language.clone(),
        }),
        "claude_api" => Box::new(crate::analysis_engines::claude::ClaudeEngine {
            api_key: decrypted_config_secret(&ai, "api_key", &state.config.project_root),
            model: ai
                .get("model")
                .and_then(Value::as_str)
                .unwrap_or("claude-sonnet-4-6")
                .to_string(),
            language: language.clone(),
        }),
        _ => return Json(
            json!({"ok": false, "error": format!("engine_type '{engine_type}' not yet supported")}),
        )
        .into_response(),
    };
    let context = build_analyze_context(&state, file_id, &language, AnalyzeMode::Full).await;
    match engine.analyze_image(&file_path, &context).await {
        Ok(result) => {
            match save_analysis_result(&state, file_id, &engine.name(), AnalyzeMode::Full, &result)
                .await
            {
                Ok(()) => {
                    Json(json!({"ok": true, "data": result.to_public_json()})).into_response()
                }
                Err(error) => {
                    tracing::error!(?error, "analyze_file: db write failed");
                    (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        Json(json!({"ok": false, "error": format!("db_write_failed: {error}")})),
                    )
                        .into_response()
                }
            }
        }
        Err(error) => Json(json!({"ok": false, "error": error.to_string()})).into_response(),
    }
}

async fn resolve_analysis_file_path(state: &SharedState, file_id: i64) -> Option<PathBuf> {
    sqlx::query_scalar::<_, String>("SELECT path FROM files WHERE id = ? AND is_deleted = 0")
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
        .ok()
        .flatten()
        .map(PathBuf::from)
}

async fn build_analyze_context(
    state: &SharedState,
    file_id: i64,
    language: &str,
    mode: AnalyzeMode,
) -> AnalyzeContext {
    let existing_tags = sqlx::query_scalar(
        "SELECT t.tag FROM tags t JOIN file_tags ft ON t.id = ft.tag_id WHERE ft.file_id = ?",
    )
    .bind(file_id)
    .fetch_all(&state.db_read)
    .await
    .unwrap_or_default();
    let existing_prompt = sqlx::query_scalar("SELECT raw_prompt FROM templates WHERE file_id = ?")
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
        .ok()
        .flatten();
    AnalyzeContext {
        existing_tags,
        existing_prompt,
        mode,
        language: language.to_string(),
        json_schema: None,
    }
}

async fn save_analysis_result(
    state: &SharedState,
    file_id: i64,
    engine_name: &str,
    mode: AnalyzeMode,
    result: &AnalysisResult,
) -> Result<(), sqlx::Error> {
    let engine = format!("{engine_name}{}", mode.db_suffix().unwrap_or_default());
    let analyzed_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    sqlx::query(
        "INSERT INTO analysis (file_id, engine, analyzed_at, tags_json, quality_score, quality_notes, description, style, composition, mood, color_palette_json, prompt_suggestion, raw_response)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(file_id, engine) DO UPDATE SET
           analyzed_at=excluded.analyzed_at, tags_json=excluded.tags_json, quality_score=excluded.quality_score,
           quality_notes=excluded.quality_notes, description=excluded.description, style=excluded.style,
           composition=excluded.composition, mood=excluded.mood, color_palette_json=excluded.color_palette_json,
           prompt_suggestion=excluded.prompt_suggestion, raw_response=excluded.raw_response",
    )
    .bind(file_id)
    .bind(engine)
    .bind(analyzed_at)
    .bind(serde_json::to_string(&result.tags).unwrap_or_default())
    .bind(result.quality_score)
    .bind(compress_for_storage(&result.quality_notes))
    .bind(&result.description)
    .bind(&result.style)
    .bind(&result.composition)
    .bind(&result.mood)
    .bind(serde_json::to_string(&result.color_palette).unwrap_or_default())
    .bind(compress_for_storage(&result.prompt_suggestion))
    .bind(compress_for_storage(&result.raw_response))
    .execute(&state.db)
    .await?;
    Ok(())
}

/// POST /api/analysis/batch
pub async fn analysis_batch() -> axum::response::Response {
    axum::Json(json!({"ok": false, "error": "analysis_unavailable"})).into_response()
}

/// POST /api/analysis/trends
pub async fn analysis_trends() -> axum::response::Response {
    axum::Json(json!({"trends": [], "ok": false, "error": "analysis_unavailable"})).into_response()
}

/// DELETE /api/analysis/trends/history/{history_id} — Rust native
pub async fn analysis_trends_history_delete(
    State(state): State<SharedState>,
    axum::extract::Path(history_id): axum::extract::Path<i64>,
) -> axum::response::Response {
    let result = sqlx::query("DELETE FROM prompt_trend_history WHERE id = ?")
        .bind(history_id)
        .execute(&state.db)
        .await;
    match result {
        Ok(r) if r.rows_affected() > 0 => Json(json!({"success": true})).into_response(),
        Ok(_) => (
            StatusCode::NOT_FOUND,
            Json(json!({"success": false, "error": "Not found"})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"success": false, "error": e.to_string()})),
        )
            .into_response(),
    }
}

/// Reject URLs pointing at loopback, private, link-local, or unspecified addresses.
/// Only the literal IP in the URL is checked; use redirect=none on the client to prevent
/// redirect-based bypass.
fn reject_ssrf_url(url_str: &str) -> Option<axum::response::Response> {
    let Ok(parsed) = reqwest::Url::parse(url_str) else {
        return Some(
            (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "Invalid URL"})),
            )
                .into_response(),
        );
    };
    let host = parsed.host_str().unwrap_or("");
    // Block "localhost" by name
    if host.eq_ignore_ascii_case("localhost") {
        return Some(
            (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "URL not allowed"})),
            )
                .into_response(),
        );
    }
    // Block numeric IP addresses in private/loopback ranges
    let bare = host.trim_start_matches('[').trim_end_matches(']');
    if let Ok(ip) = bare.parse::<std::net::IpAddr>() {
        let blocked = match ip {
            std::net::IpAddr::V4(v4) => {
                v4.is_loopback()
                    || v4.is_private()
                    || v4.is_link_local()
                    || v4.is_unspecified()
                    || v4.is_multicast()
            }
            std::net::IpAddr::V6(v6) => {
                v6.is_loopback() || v6.is_unspecified() || v6.is_multicast()
            }
        };
        if blocked {
            return Some(
                (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"error": "URL not allowed"})),
                )
                    .into_response(),
            );
        }
    }
    None
}

/// POST /api/analysis/ollama/test — Rust native
pub async fn analysis_ollama_test(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    if let Some(r) = require_admin_scope(state.config.pin_auth_enabled, auth.as_deref()) {
        return r;
    }
    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid_json"})),
            )
                .into_response()
        }
    };
    let base_url = match data
        .get("ollama_url")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
    {
        Some(u) => u.to_string(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "URL is required"})),
            )
                .into_response()
        }
    };
    if !base_url.starts_with("http://") && !base_url.starts_with("https://") {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Only http/https URLs are allowed"})),
        )
            .into_response();
    }
    if let Some(r) = reject_ssrf_url(&base_url) {
        return r;
    }
    let tags_url = format!("{}/api/tags", base_url.trim_end_matches('/'));
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .unwrap_or_default();
    match client
        .get(&tags_url)
        .header("Accept", "application/json")
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => {
            let json_body: Value = resp.json().await.unwrap_or(json!({}));
            let models: Vec<Value> = json_body.get("models").and_then(Value::as_array).cloned().unwrap_or_default()
                .into_iter().map(|m| json!({"name": m.get("name").and_then(Value::as_str).unwrap_or(""), "size": m.get("size").and_then(Value::as_u64).unwrap_or(0)})).collect();
            Json(json!({"connected": true, "models": models, "error": null})).into_response()
        }
        Err(e) if e.is_timeout() => {
            Json(json!({"connected": false, "models": [], "error": "Connection timeout"}))
                .into_response()
        }
        // Any other status, and any non-timeout transport error, is the same
        // answer to the caller.
        Ok(_) | Err(_) => {
            Json(json!({"connected": false, "models": [], "error": "Connection failed"}))
                .into_response()
        }
    }
}

/// POST /api/analysis/openai-compat/test — Rust native
pub async fn analysis_openai_compat_test(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    if let Some(r) = require_admin_scope(state.config.pin_auth_enabled, auth.as_deref()) {
        return r;
    }
    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid_json"})),
            )
                .into_response()
        }
    };
    let base_url = match data
        .get("url")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
    {
        Some(u) => u.to_string(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "URL is required"})),
            )
                .into_response()
        }
    };
    if !base_url.starts_with("http://") && !base_url.starts_with("https://") {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Only http/https URLs are allowed"})),
        )
            .into_response();
    }
    if let Some(r) = reject_ssrf_url(&base_url) {
        return r;
    }
    let api_key = data
        .get("api_key")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let models_url = format!("{}/v1/models", base_url.trim_end_matches('/'));
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .unwrap_or_default();
    let mut req = client.get(&models_url).header("Accept", "application/json");
    if !api_key.is_empty() {
        req = req.header("Authorization", format!("Bearer {api_key}"));
    }
    match req.send().await {
        Ok(resp) if resp.status().is_success() => {
            let json_body: Value = resp.json().await.unwrap_or(json!({}));
            let models: Vec<Value> = json_body.get("data").and_then(Value::as_array).cloned().unwrap_or_default()
                .into_iter().map(|m| json!({"id": m.get("id").and_then(Value::as_str).unwrap_or(""), "owned_by": m.get("owned_by").and_then(Value::as_str).unwrap_or("")})).collect();
            Json(json!({"connected": true, "models": models, "error": null})).into_response()
        }
        Ok(resp) if resp.status().as_u16() == 401 => {
            Json(json!({"connected": false, "models": [], "error": "Authentication failed"}))
                .into_response()
        }
        Err(e) if e.is_timeout() => {
            Json(json!({"connected": false, "models": [], "error": "Connection timeout"}))
                .into_response()
        }
        // Any other status, and any non-timeout transport error, is the same
        // answer to the caller.
        Ok(_) | Err(_) => {
            Json(json!({"connected": false, "models": [], "error": "Connection failed"}))
                .into_response()
        }
    }
}

/// POST /api/analysis/servers/discovered/register — Rust native
pub async fn analysis_servers_discovered_register(
    State(state): State<SharedState>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"success": false, "error": "invalid_json"})),
            )
                .into_response()
        }
    };
    let provider = data
        .get("provider")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let config_path = state.config.config_path.clone();
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let servers = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let entry_json: Value = match provider.as_str() {
        "ollama" => {
            let base_url = normalize_base_url_simple(
                data.get("base_url").and_then(Value::as_str).unwrap_or(""),
            );
            if base_url.is_empty() {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"success": false, "error": "base_url is required"})),
                )
                    .into_response();
            }
            let existing_urls: Vec<String> = servers
                .iter()
                .filter_map(|s| {
                    s.get("config")
                        .and_then(|c| c.get("base_url"))
                        .and_then(Value::as_str)
                })
                .map(normalize_base_url_simple)
                .collect();
            if existing_urls.contains(&base_url) {
                return Json(json!({"success": false, "error": "Server already registered"}))
                    .into_response();
            }
            let host_label = base_url
                .split_once("://")
                .map(|x| x.1)
                .unwrap_or(&base_url)
                .to_string();
            let name = data
                .get("name")
                .and_then(Value::as_str)
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| format!("Ollama ({})", host_label));
            let model = data
                .get("model")
                .and_then(Value::as_str)
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| "llava:latest".to_string());
            let id = make_unique_id(&name, &servers);
            let priority = next_low_priority(&servers);
            json!({"id": id, "name": name, "type": "ollama", "priority": priority, "enabled": true,
                   "config": {"base_url": base_url, "model": model}})
        }
        "openai_compat" => {
            let base_url = normalize_base_url_simple(
                data.get("base_url").and_then(Value::as_str).unwrap_or(""),
            );
            if base_url.is_empty() {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"success": false, "error": "base_url is required"})),
                )
                    .into_response();
            }
            let existing_urls: Vec<String> = servers
                .iter()
                .filter_map(|s| {
                    s.get("config")
                        .and_then(|c| c.get("base_url"))
                        .and_then(Value::as_str)
                })
                .map(normalize_base_url_simple)
                .collect();
            if existing_urls.contains(&base_url) {
                return Json(json!({"success": false, "error": "Server already registered"}))
                    .into_response();
            }
            let host_label = base_url
                .split_once("://")
                .map(|x| x.1)
                .unwrap_or(&base_url)
                .to_string();
            let name = data
                .get("name")
                .and_then(Value::as_str)
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| format!("OpenAI Compatible ({})", host_label));
            let model = data
                .get("model")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            let api_key = data
                .get("api_key")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            let id = make_unique_id(&name, &servers);
            let priority = next_low_priority(&servers);
            let mut cfg = json!({"base_url": base_url, "model": model});
            if !api_key.is_empty() {
                cfg["api_key"] = json!(api_key);
            }
            json!({"id": id, "name": name, "type": "openai_compat", "priority": priority, "enabled": true, "config": cfg})
        }
        "hailo_genai" => {
            let already = servers
                .iter()
                .any(|s| s.get("type").and_then(Value::as_str) == Some("hailo_vlm"));
            if already {
                return Json(json!({"success": false, "error": "Server already registered"}))
                    .into_response();
            }
            let model_name = data
                .get("model_name")
                .and_then(Value::as_str)
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| "qwen2-vl-2b-instruct".to_string());
            let name = data
                .get("name")
                .and_then(Value::as_str)
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| format!("Hailo VLM ({})", model_name));
            let id = make_unique_id(&name, &servers);
            let priority = next_low_priority(&servers);
            json!({"id": id, "name": name, "type": "hailo_vlm", "priority": priority, "enabled": true,
                   "config": {"model_name": model_name}})
        }
        p => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"success": false, "error": format!("Unsupported provider: {}", p)})),
            )
                .into_response()
        }
    };

    let base_url = entry_json
        .get("config")
        .and_then(|c| c.get("base_url"))
        .and_then(Value::as_str)
        .map(normalize_base_url_simple)
        .unwrap_or_default();

    let mut servers_arr = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    servers_arr.push(entry_json.clone());
    config["ai_servers"] = Value::Array(servers_arr);

    if !base_url.is_empty() {
        // Remove from discovery matches
        if let Some(Value::Object(ref mut matches)) = config.get_mut("ai_servers_discovery_matches")
        {
            matches.remove(&base_url);
            if matches.is_empty() {
                config
                    .as_object_mut()
                    .map(|m| m.remove("ai_servers_discovery_matches"));
            }
        }
        // Remove from discovery ignored
        if let Some(ignored) = config
            .get("ai_servers_discovery_ignored")
            .and_then(Value::as_array)
            .cloned()
        {
            let new_ignored: Vec<Value> = ignored
                .into_iter()
                .filter(|v| v.as_str().map(normalize_base_url_simple) != Some(base_url.clone()))
                .collect();
            if new_ignored.is_empty() {
                config
                    .as_object_mut()
                    .map(|m| m.remove("ai_servers_discovery_ignored"));
            } else {
                config["ai_servers_discovery_ignored"] = Value::Array(new_ignored);
            }
        }
    }

    crate::config_io::write(&config_path, &config);
    Json(json!({"success": true, "server": entry_json})).into_response()
}

/// POST /api/analysis/servers/discovered/test — Rust native
pub async fn analysis_servers_discovered_test(
    _state: State<SharedState>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid_json"})),
            )
                .into_response()
        }
    };
    let provider = data
        .get("provider")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let base_url = data
        .get("base_url")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .trim_end_matches('/')
        .to_string();
    let start = std::time::Instant::now();
    let (available, auth_required) = match provider.as_str() {
        "ollama" => {
            if base_url.is_empty() {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"error": "base_url is required"})),
                )
                    .into_response();
            }
            let tags_url = format!("{base_url}/api/tags");
            let client = reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(3))
                .build()
                .unwrap_or_default();
            let ok = client
                .get(&tags_url)
                .header("Accept", "application/json")
                .send()
                .await
                .map(|r| r.status().is_success())
                .unwrap_or(false);
            (ok, false)
        }
        "openai_compat" => {
            if base_url.is_empty() {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"error": "base_url is required"})),
                )
                    .into_response();
            }
            let api_key = data
                .get("api_key")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            let models_url = format!("{base_url}/v1/models");
            let client = reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(3))
                .build()
                .unwrap_or_default();
            let mut req = client.get(&models_url).header("Accept", "application/json");
            if !api_key.is_empty() {
                req = req.header("Authorization", format!("Bearer {api_key}"));
            }
            match req.send().await {
                Ok(r) if r.status().as_u16() == 401 => (false, true),
                Ok(r) => (r.status().is_success(), false),
                Err(_) => (false, false),
            }
        }
        p => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": format!("Unsupported provider: {p}")})),
            )
                .into_response()
        }
    };
    let elapsed_ms = u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX);
    if auth_required {
        Json(json!({"success": true, "available": false, "auth_required": true, "elapsed_ms": elapsed_ms})).into_response()
    } else {
        Json(json!({"success": true, "available": available, "elapsed_ms": elapsed_ms}))
            .into_response()
    }
}

/// POST /api/analysis/servers/migrate — Rust native
pub async fn analysis_servers_migrate(
    State(state): State<SharedState>,
    _body: axum::body::Bytes,
) -> axum::response::Response {
    let config_path = state.config.config_path.clone();
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let has_servers = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .is_some_and(|a| !a.is_empty());
    if has_servers {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"success": false, "error": "ai_servers already exists"})),
        )
            .into_response();
    }
    let ai = config.get("ai_analysis").cloned().unwrap_or(json!({}));
    let engine_type = ai
        .get("engine")
        .and_then(Value::as_str)
        .unwrap_or("claude_api");
    let language = ai.get("language").and_then(Value::as_str).unwrap_or("ja");
    let mut servers: Vec<Value> = Vec::new();
    let mut priority = 10i64;

    // Primary engine entry
    let main_entry: Option<Value> = match engine_type {
        "ollama" => Some(json!({
            "id": "ollama",
            "name": format!("Ollama ({})", ai.get("ollama_model").and_then(Value::as_str).unwrap_or("llava:latest")),
            "type": "ollama", "priority": priority, "enabled": true,
            "config": {"base_url": ai.get("ollama_url").and_then(Value::as_str).unwrap_or("http://localhost:11434"),
                       "model": ai.get("ollama_model").and_then(Value::as_str).unwrap_or("llava:latest"),
                       "language": language}
        })),
        "openai_compat" => Some(json!({
            "id": "openai-compat",
            "name": format!("OpenAI Compatible ({})", ai.get("openai_compat_model").and_then(Value::as_str).unwrap_or("default")),
            "type": "openai_compat", "priority": priority, "enabled": true,
            "config": {"base_url": ai.get("openai_compat_url").and_then(Value::as_str).unwrap_or(""),
                       "api_key": ai.get("openai_compat_api_key").and_then(Value::as_str).unwrap_or(""),
                       "model": ai.get("openai_compat_model").and_then(Value::as_str).unwrap_or(""),
                       "language": language}
        })),
        "openai" => Some(json!({
            "id": "openai",
            "name": format!("OpenAI ({})", ai.get("openai_model").and_then(Value::as_str).unwrap_or("gpt-4o-mini")),
            "type": "openai", "priority": priority, "enabled": true,
            "config": {"api_key": ai.get("openai_api_key").and_then(Value::as_str).unwrap_or(""),
                       "model": ai.get("openai_model").and_then(Value::as_str).unwrap_or("gpt-4o-mini"),
                       "language": language}
        })),
        "hailo_vlm" => Some(json!({
            "id": "hailo-vlm",
            "name": format!("Hailo VLM ({})", ai.get("hailo_vlm_model").and_then(Value::as_str).unwrap_or("qwen2-vl-2b-instruct")),
            "type": "hailo_vlm", "priority": priority, "enabled": true,
            "config": {"model_name": ai.get("hailo_vlm_model").and_then(Value::as_str).unwrap_or("qwen2-vl-2b-instruct"),
                       "language": language}
        })),
        _ => Some(json!({
            "id": slugify_id(&format!("Claude ({})", ai.get("model").and_then(Value::as_str).unwrap_or("claude-sonnet-4-6"))),
            "name": format!("Claude ({})", ai.get("model").and_then(Value::as_str).unwrap_or("claude-sonnet-4-6")),
            "type": "claude_api", "priority": priority, "enabled": true,
            "config": {"api_key": ai.get("api_key").and_then(Value::as_str).unwrap_or(""),
                       "model": ai.get("model").and_then(Value::as_str).unwrap_or("claude-sonnet-4-6"),
                       "language": language}
        })),
    };
    if let Some(entry) = main_entry {
        servers.push(entry);
        priority += 10;
    }
    // Additional engines not already the primary
    if engine_type != "openai_compat"
        && ai
            .get("openai_compat_url")
            .and_then(Value::as_str)
            .is_some_and(|s| !s.is_empty())
    {
        let model = ai
            .get("openai_compat_model")
            .and_then(Value::as_str)
            .unwrap_or("default");
        servers.push(json!({
            "id": "openai-compat", "name": format!("OpenAI Compatible ({})", model),
            "type": "openai_compat", "priority": priority, "enabled": true,
            "config": {"base_url": ai.get("openai_compat_url").and_then(Value::as_str).unwrap_or(""),
                       "api_key": ai.get("openai_compat_api_key").and_then(Value::as_str).unwrap_or(""),
                       "model": model}
        }));
        priority += 10;
    }
    if engine_type != "ollama"
        && ai
            .get("ollama_url")
            .and_then(Value::as_str)
            .is_some_and(|s| !s.is_empty())
    {
        let model = ai
            .get("ollama_model")
            .and_then(Value::as_str)
            .unwrap_or("llava:latest");
        servers.push(json!({
            "id": "ollama", "name": format!("Ollama ({})", model),
            "type": "ollama", "priority": priority, "enabled": true,
            "config": {"base_url": ai.get("ollama_url").and_then(Value::as_str).unwrap_or("http://localhost:11434"),
                       "model": model}
        }));
        priority += 10;
    }
    if engine_type != "hailo_vlm" {
        let model = ai
            .get("hailo_vlm_model")
            .and_then(Value::as_str)
            .unwrap_or("qwen2-vl-2b-instruct");
        servers.push(json!({
            "id": "hailo-vlm", "name": format!("Hailo VLM ({})", model),
            "type": "hailo_vlm", "priority": priority, "enabled": true,
            "config": {"model_name": model}
        }));
    }
    let migrated = servers.len();
    let first_id = servers
        .first()
        .and_then(|s| s.get("id"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    config["ai_servers"] = Value::Array(servers.clone());
    if !first_id.is_empty() {
        config["ai_servers_active"] = json!(first_id);
    }
    if !language.is_empty() {
        config["ai_servers_language"] = json!(language);
    }
    if let Some(flo) = ai.get("fallback_local_only") {
        config["ai_servers_fallback_local_only"] = flo.clone();
    }
    crate::config_io::write(&config_path, &config);
    Json(json!({"success": true, "servers": servers, "migrated": migrated})).into_response()
}

/// POST /api/analysis/servers/discovered/match — Rust native
pub async fn analysis_servers_discovered_match_post(
    State(state): State<SharedState>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"success": false, "error": "invalid_json"})),
            )
                .into_response()
        }
    };
    let base_url =
        normalize_base_url_simple(data.get("base_url").and_then(Value::as_str).unwrap_or(""));
    let server_id = data
        .get("server_id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let provider = data
        .get("provider")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if base_url.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"success": false, "error": "base_url is required"})),
        )
            .into_response();
    }
    if server_id.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"success": false, "error": "server_id is required"})),
        )
            .into_response();
    }
    let config_path = state.config.config_path.clone();
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let servers = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let matched = servers
        .iter()
        .find(|s| s.get("id").and_then(Value::as_str) == Some(server_id.as_str()));
    let (matched_id, matched_name) = match matched {
        Some(s) => (
            s.get("id")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            s.get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
        ),
        None => {
            return Json(
                json!({"success": false, "error": format!("Server '{}' not found", server_id)}),
            )
            .into_response()
        }
    };
    let now = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
    let mut matches_map = config
        .get("ai_servers_discovery_matches")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    matches_map.insert(
        base_url,
        json!({"server_id": matched_id, "provider": provider, "matched_at": now}),
    );
    config["ai_servers_discovery_matches"] = Value::Object(matches_map);
    crate::config_io::write(&config_path, &config);
    Json(json!({"success": true, "server_id": matched_id, "server_name": matched_name}))
        .into_response()
}

/// DELETE /api/analysis/servers/discovered/match — Rust native
pub async fn analysis_servers_discovered_match_delete(
    State(state): State<SharedState>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let data: Value = serde_json::from_slice(&body).unwrap_or(json!({}));
    let base_url =
        normalize_base_url_simple(data.get("base_url").and_then(Value::as_str).unwrap_or(""));
    if base_url.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"success": false, "error": "base_url is required"})),
        )
            .into_response();
    }
    let config_path = state.config.config_path.clone();
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let mut matches_map = config
        .get("ai_servers_discovery_matches")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    if !matches_map.contains_key(&base_url) {
        return Json(json!({"success": false, "error": "Match not found"})).into_response();
    }
    matches_map.remove(&base_url);
    if matches_map.is_empty() {
        config
            .as_object_mut()
            .map(|m| m.remove("ai_servers_discovery_matches"));
    } else {
        config["ai_servers_discovery_matches"] = Value::Object(matches_map);
    }
    crate::config_io::write(&config_path, &config);
    Json(json!({"success": true})).into_response()
}

/// POST /api/analysis/servers/discovered/ignore — Rust native
pub async fn analysis_servers_discovered_ignore_post(
    State(state): State<SharedState>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"success": false, "error": "invalid_json"})),
            )
                .into_response()
        }
    };
    let base_url =
        normalize_base_url_simple(data.get("base_url").and_then(Value::as_str).unwrap_or(""));
    if base_url.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"success": false, "error": "base_url is required"})),
        )
            .into_response();
    }
    let config_path = state.config.config_path.clone();
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let mut ignored: std::collections::BTreeSet<String> = config
        .get("ai_servers_discovery_ignored")
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();
    ignored.insert(base_url);
    config["ai_servers_discovery_ignored"] =
        Value::Array(ignored.into_iter().map(Value::String).collect());
    crate::config_io::write(&config_path, &config);
    Json(json!({"success": true})).into_response()
}

/// DELETE /api/analysis/servers/discovered/ignore — Rust native
pub async fn analysis_servers_discovered_ignore_delete(
    State(state): State<SharedState>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let data: Value = serde_json::from_slice(&body).unwrap_or(json!({}));
    let base_url =
        normalize_base_url_simple(data.get("base_url").and_then(Value::as_str).unwrap_or(""));
    if base_url.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"success": false, "error": "base_url is required"})),
        )
            .into_response();
    }
    let config_path = state.config.config_path.clone();
    let _guard = state.settings_lock.lock().await;
    let mut config = crate::config_io::load(&config_path);
    let mut ignored: std::collections::BTreeSet<String> = config
        .get("ai_servers_discovery_ignored")
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();
    if !ignored.contains(&base_url) {
        return Json(json!({"success": false, "error": "Ignore entry not found"})).into_response();
    }
    ignored.remove(&base_url);
    if ignored.is_empty() {
        config
            .as_object_mut()
            .map(|m| m.remove("ai_servers_discovery_ignored"));
    } else {
        config["ai_servers_discovery_ignored"] =
            Value::Array(ignored.into_iter().map(Value::String).collect());
    }
    crate::config_io::write(&config_path, &config);
    Json(json!({"success": true})).into_response()
}

fn slugify_id(name: &str) -> String {
    let s = name.to_lowercase();
    let mut result = String::new();
    let mut prev_dash = false;
    for c in s.chars() {
        if c.is_alphanumeric() {
            result.push(c);
            prev_dash = false;
        } else if !prev_dash {
            result.push('-');
            prev_dash = true;
        }
    }
    let trimmed = result.trim_matches('-').to_string();
    let s = if trimmed.is_empty() {
        "server".to_string()
    } else {
        trimmed
    };
    s.chars().take(32).collect()
}

fn make_unique_id(name: &str, existing: &[Value]) -> String {
    let base = slugify_id(name);
    if !existing
        .iter()
        .any(|s| s.get("id").and_then(Value::as_str) == Some(&base))
    {
        return base;
    }
    for i in 2u32..100 {
        let candidate = format!("{}-{}", base, i);
        if !existing
            .iter()
            .any(|s| s.get("id").and_then(Value::as_str) == Some(candidate.as_str()))
        {
            return candidate;
        }
    }
    base
}

fn normalize_base_url_simple(url: &str) -> String {
    url.trim().trim_end_matches('/').to_string()
}

fn next_low_priority(servers: &[Value]) -> i64 {
    servers
        .iter()
        .filter_map(|s| s.get("priority").and_then(Value::as_i64))
        .max()
        .map(|m| m + 10)
        .unwrap_or(10)
}

fn is_local_url(url: &str) -> bool {
    if url.is_empty() {
        return false;
    }
    let host = url
        .find("://")
        .map(|i| &url[i + 3..])
        .unwrap_or(url)
        .split('/')
        .next()
        .unwrap_or("")
        .split(':')
        .next()
        .unwrap_or("");
    matches!(host, "localhost" | "127.0.0.1" | "::1" | "")
        || host.starts_with("192.168.")
        || host.starts_with("10.")
        || host.starts_with("172.")
}

fn is_local_engine(ai: &Value) -> bool {
    match ai
        .get("engine")
        .and_then(Value::as_str)
        .unwrap_or("claude_api")
    {
        "hailo_vlm" => true,
        "ollama" => is_local_url(
            ai.get("ollama_url")
                .and_then(Value::as_str)
                .unwrap_or("http://localhost:11434"),
        ),
        "openai_compat" => is_local_url(
            ai.get("openai_compat_url")
                .and_then(Value::as_str)
                .unwrap_or(""),
        ),
        _ => false,
    }
}

/// GET /api/analysis/config — Rust native (reads config.json directly)
pub async fn analysis_config_get(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> axum::response::Response {
    if let Some(r) = require_admin_scope(state.config.pin_auth_enabled, auth.as_ref().map(|c| &c.0))
    {
        return r;
    }
    let config = crate::config_io::load(&state.config.config_path);
    let mut ai = config.get("ai_analysis").cloned().unwrap_or(json!({}));

    for key in ["api_key", "openai_api_key", "openai_compat_api_key"] {
        if let Some(Value::String(raw)) = ai.get(key) {
            if !raw.is_empty() {
                let plain = secret_store::decrypt(raw, &state.config.project_root);
                ai[key] = json!(secret_store::mask_secret(&plain));
            }
        }
    }
    ai["is_local"] = json!(is_local_engine(&ai));
    ai["ok"] = json!(true);

    let has_servers = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .map(|a| !a.is_empty())
        .unwrap_or(false);
    ai["has_servers"] = json!(has_servers);
    if has_servers {
        ai["servers"] = config.get("ai_servers").cloned().unwrap_or(json!([]));
        ai["active_server"] = config
            .get("ai_servers_active")
            .cloned()
            .unwrap_or(json!(null));
    }

    Json(ai).into_response()
}

/// POST /api/analysis/config — Rust native (writes config.json directly)
pub async fn analysis_config_post(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    if let Some(r) = require_admin_scope(state.config.pin_auth_enabled, auth.as_ref().map(|c| &c.0))
    {
        return r;
    }
    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid_json"})),
            )
                .into_response()
        }
    };
    let config_path = state.config.config_path.clone();
    let project_root = state.config.project_root.clone();
    let _guard = state.settings_lock.lock().await;
    let result = tokio::task::spawn_blocking(move || {
        let mut config = crate::config_io::load(&config_path);
        if !config["ai_analysis"].is_object() {
            config["ai_analysis"] = json!({});
        }
        const ALLOWED: &[&str] = &[
            "engine",
            "api_key",
            "model",
            "ollama_url",
            "ollama_model",
            "openai_api_key",
            "openai_model",
            "openai_compat_url",
            "openai_compat_api_key",
            "openai_compat_model",
            "hailo_vlm_model",
            "fallback_local_only",
            "language",
        ];
        const SECRETS: &[&str] = &["api_key", "openai_api_key", "openai_compat_api_key"];
        for key in ALLOWED {
            let Some(val) = data.get(key) else { continue };
            if val.as_str().map(|s| s.contains("...")).unwrap_or(false) {
                continue; // skip masked placeholder
            }
            let stored = if SECRETS.contains(key) {
                match val.as_str() {
                    Some("") | None => val.clone(),
                    Some(s) => json!(secret_store::encrypt(s, &project_root)),
                }
            } else {
                val.clone()
            };
            config["ai_analysis"][key] = stored;
        }
        crate::config_io::write(&config_path, &config)
    })
    .await;

    match result {
        Ok(Ok(())) => Json(json!({"ok": true, "success": true})).into_response(),
        _ => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": "save_failed"})),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{body::to_bytes, extract::State, routing::post, Router};
    use base64::Engine;
    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

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
        sqlx::raw_sql(
            "CREATE TABLE prompt_trend_history (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               engine TEXT NOT NULL,
               analyzed_at INTEGER NOT NULL,
               prompt_count INTEGER NOT NULL DEFAULT 0,
               result_json TEXT NOT NULL
             );
             INSERT INTO prompt_trend_history(id, engine, analyzed_at, prompt_count, result_json)
             VALUES (1, 'ollama', 200, 3, '{\"topics\":[\"rust\"]}'),
                    (2, 'openai', 300, 5, '{\"topics\":[\"api\"]}');",
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
        let root =
            std::env::temp_dir().join(format!("yu-analysis-secret-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("data")).unwrap();
        let key = base64::engine::general_purpose::URL_SAFE.encode([11_u8; 32]);
        std::fs::write(root.join("data").join("secret.key"), &key).unwrap();
        let token = crate::secret_store::encrypt_for_test(plaintext, key.as_bytes());
        (root, format!("enc:{token}"))
    }

    async fn json_body(response: axum::response::Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn available_engines_returns_configured_cloud_engines() {
        let state = test_state(json!({
            "ai_analysis": {
                "api_key": "secret",
                "model": "claude-sonnet-4-6",
                "openai_api_key": "secret",
                "openai_model": "gpt-4o-mini"
            }
        }))
        .await;

        let value = json_body(available_engines(State(state), None).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["engines"][0]["type"], "claude_api");
        assert_eq!(value["engines"][1]["type"], "openai");
    }

    #[tokio::test]
    async fn analyze_file_stores_ollama_result_with_uncompressed_round_trip() {
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            // Restricted CI sandboxes may prohibit loopback listeners.
            return;
        };
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().route(
                    "/api/chat",
                    post(|| async {
                        "{\"message\":{\"content\":\"{\\\"tags\\\":[\\\"cat\\\"],\\\"quality_score\\\":1,\\\"quality_notes\\\":\\\"ok\\\"}\"},\"done\":true}\n"
                    }),
                ),
            )
            .await
            .unwrap()
        });
        let directory = tempfile::tempdir().unwrap();
        let image_path = directory.path().join("image.png");
        image::RgbImage::new(1, 1).save(&image_path).unwrap();
        let state = test_state(json!({"ai_analysis": {"engine": "ollama", "ollama_url": format!("http://{address}"), "ollama_model": "llava:latest"}})).await;
        sqlx::raw_sql(
            "CREATE TABLE files(id INTEGER PRIMARY KEY, path TEXT NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0);
             CREATE TABLE tags(id INTEGER PRIMARY KEY, tag TEXT NOT NULL);
             CREATE TABLE file_tags(file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL);
             CREATE TABLE templates(file_id INTEGER NOT NULL, raw_prompt TEXT);
             CREATE TABLE analysis(id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL, engine TEXT NOT NULL, analyzed_at INTEGER NOT NULL, tags_json TEXT, quality_score REAL, quality_notes BLOB, description TEXT, style TEXT, composition TEXT, mood TEXT, color_palette_json TEXT, prompt_suggestion BLOB, raw_response BLOB, UNIQUE(file_id, engine));",
        ).execute(&state.db).await.unwrap();
        sqlx::query("INSERT INTO files(id, path) VALUES(1, ?)")
            .bind(image_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        let response = analyze_file(State(state.clone()), None, axum::extract::Path(1)).await;
        assert_eq!(json_body(response).await["ok"], true);
        let row = sqlx::query("SELECT engine, quality_notes FROM analysis WHERE file_id = 1")
            .fetch_one(&state.db_read)
            .await
            .unwrap();
        assert_eq!(
            row.get::<String, _>("engine"),
            "Ollama Vision (llava:latest)"
        );
        assert_eq!(
            crate::routes::analysis_results::decompress_blob(
                row.try_get_raw("quality_notes").unwrap()
            )
            .unwrap(),
            "ok"
        );
        server.abort();
    }

    #[test]
    fn fallback_local_only_true_disallows_non_private_engine_url() {
        assert!(!should_probe_local_engine("https://example.com", true));
    }

    #[test]
    fn fallback_local_only_false_allows_non_private_engine_url() {
        assert!(should_probe_local_engine("https://example.com", false));
    }

    #[tokio::test]
    async fn ollama_models_returns_connection_error_shape() {
        let state = test_state(json!({"ai_analysis": {"ollama_url": "http://127.0.0.1:1"}})).await;

        let value = json_body(ollama_models(State(state), None).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["connected"], false);
        assert_eq!(value["models"], json!([]));
        assert_eq!(
            value["error"],
            "Cannot connect: [Errno 111] Connection refused"
        );
    }

    #[tokio::test]
    async fn openai_compat_models_requires_configured_url() {
        let value =
            json_body(openai_compat_models(State(test_state(json!({})).await), None).await).await;

        assert_eq!(value["ok"], false);
        assert_eq!(value["error"], "OpenAI Compatible URL is not configured");
    }

    #[test]
    fn openai_compat_config_secret_decrypts_before_outbound_use() {
        let (root, stored) = temp_secret_root("compat-key", "plain-compat-key");
        let ai = json!({"openai_compat_api_key": stored});

        assert_eq!(
            decrypted_config_secret(&ai, "openai_compat_api_key", &root),
            "plain-compat-key"
        );
    }

    #[test]
    fn normalize_base_url_matches_python_examples() {
        assert_eq!(
            normalize_base_url(" HTTP://LOCALHOST:80/foo/ "),
            "http://localhost/foo"
        );
        assert_eq!(
            normalize_base_url("https://Example.COM:443/v1/"),
            "https://example.com/v1"
        );
        assert_eq!(normalize_base_url("localhost:11434"), "");
        assert_eq!(normalize_base_url(""), "");
    }

    #[test]
    fn match_state_returns_compatible_servers_and_valid_match() {
        let config = json!({
            "ai_servers": [
                {"id": "ollama-a", "name": "Ollama A", "type": "ollama", "priority": 10, "enabled": true, "config": {"base_url": "http://localhost:11434"}},
                {"id": "openai-a", "name": "OpenAI A", "type": "openai", "priority": 20, "enabled": true, "config": {}}
            ],
            "ai_servers_discovery_matches": {
                "http://localhost:11434": {"server_id": "ollama-a", "provider": "ollama"}
            }
        });
        let servers = all_servers(&config, Path::new("."));
        let (matchable, matched_id, matched_name) =
            build_match_state("ollama", "http://localhost:11434", &servers, &config);

        assert_eq!(
            matchable,
            vec![json!({"id": "ollama-a", "name": "Ollama A"})]
        );
        assert_eq!(matched_id, "ollama-a");
        assert_eq!(matched_name, "Ollama A");
    }

    #[test]
    fn match_state_ignores_incompatible_saved_match() {
        let config = json!({
            "ai_servers": [
                {"id": "openai-a", "name": "OpenAI A", "type": "openai", "priority": 20, "enabled": true, "config": {}}
            ],
            "ai_servers_discovery_matches": {
                "http://localhost:11434": {"server_id": "openai-a", "provider": "ollama"}
            }
        });
        let servers = all_servers(&config, Path::new("."));
        let (matchable, matched_id, matched_name) =
            build_match_state("ollama", "http://localhost:11434", &servers, &config);

        assert!(matchable.is_empty());
        assert!(matched_id.is_null());
        assert!(matched_name.is_null());
    }

    #[test]
    fn hailo_vlm_unavailable_when_model_is_absent() {
        assert!(!is_hailo_vlm_available("__missing_model__"));
    }

    #[tokio::test]
    async fn discovered_pipeline_applies_registered_ignored_and_match_flags() {
        let config = json!({
            "ai_analysis": {
                "openai_compat_url": "http://127.0.0.1:1/v1",
                "openai_compat_model": "local-model"
            },
            "ai_servers": [
                {"id": "compat-a", "name": "Compat A", "type": "openai_compat", "priority": 10, "enabled": true, "config": {"base_url": "http://127.0.0.1:1/v1"}}
            ],
            "ai_servers_discovery_ignored": ["http://127.0.0.1:1/v1/"],
            "ai_servers_discovery_matches": {
                "http://127.0.0.1:1/v1": {"server_id": "compat-a", "provider": "openai_compat"}
            }
        });

        let candidates = compute_discovered_candidates(&config, Path::new(".")).await;
        let compat = candidates
            .iter()
            .find(|candidate| candidate["provider"] == "openai_compat")
            .expect("openai compat candidate");

        assert_eq!(compat["base_url"], "http://127.0.0.1:1/v1");
        assert_eq!(compat["already_registered"], true);
        assert_eq!(compat["ignored"], true);
        assert_eq!(compat["matched_existing_server_id"], "compat-a");
        assert_eq!(compat["matched_existing_server_name"], "Compat A");
        assert_eq!(
            compat["matchable_servers"],
            json!([{"id": "compat-a", "name": "Compat A"}])
        );
    }

    #[tokio::test]
    async fn servers_returns_priority_sorted_masked_entries() {
        let state = test_state(json!({
            "ai_servers": [
                {"id": "b", "name": "B", "type": "openai", "priority": 20, "enabled": true, "config": {"api_key": "abcdefghijkl", "model": "gpt-4o"}},
                {"id": "a", "name": "A", "type": "ollama", "priority": 10, "enabled": false, "config": {"base_url": "http://localhost:11434"}}
            ],
            "ai_servers_active": "a"
        }))
        .await;

        let value = json_body(servers(State(state), None).await).await;

        assert_eq!(value["servers"][0]["id"], "a");
        assert_eq!(value["servers"][0]["is_active"], true);
        assert_eq!(value["servers"][1]["config"]["api_key"], "abcd...kl");
        assert_eq!(value["servers"][1]["status"], "unknown");
    }

    #[tokio::test]
    async fn servers_masks_decrypted_api_key_not_encrypted_blob() {
        let (root, stored) = temp_secret_root("server-mask", "plain-secret-value");
        let state = test_state_with_root(
            json!({
                "ai_servers": [
                    {"id": "a", "name": "A", "type": "openai", "priority": 10, "enabled": true, "config": {"api_key": stored, "model": "gpt-4o"}}
                ]
            }),
            root,
        )
        .await;

        let value = json_body(servers(State(state), None).await).await;

        assert_eq!(value["servers"][0]["config"]["api_key"], "plai...ue");
    }

    #[tokio::test]
    async fn trend_history_returns_newest_first_with_limit_and_offset() {
        let value = json_body(
            trend_history(
                State(test_state(json!({})).await),
                None,
                axum::extract::Query(std::collections::HashMap::from([
                    ("limit".to_string(), "1".to_string()),
                    ("offset".to_string(), "0".to_string()),
                ])),
            )
            .await,
        )
        .await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["items"][0]["id"], 2);
        assert_eq!(value["items"][0]["result"]["topics"][0], "api");
    }
}

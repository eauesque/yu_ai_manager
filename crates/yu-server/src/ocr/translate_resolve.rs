use std::{path::Path, time::Duration};

use async_trait::async_trait;
use reqwest::{header, StatusCode};
use serde_json::{Map, Value};

use crate::{
    analysis_engines::http_client::build_pinned_client,
    routes::{analysis, analysis_net},
    secret_store,
};

const NO_SERVERS: &str = "AI サーバーが登録されていません。";
const NO_LOCAL_SERVER: &str =
    "ローカル限定モードが有効です。利用可能なローカル AI サーバーがありません。";
const NO_AVAILABLE_SERVER: &str =
    "利用可能な AI サーバーがありません。サーバー設定を確認してください。";

/// Four-field boundary for translation resolution; Stage 4 supplies `engine_name`.
#[derive(Debug, Clone, PartialEq)]
pub struct TranslationServerResolution {
    pub engine_type: Option<String>,
    pub kwargs: Option<Value>,
    pub engine_name: Option<String>,
    pub error: Option<String>,
}

impl TranslationServerResolution {
    fn available(engine_type: String, kwargs: Value) -> Self {
        Self {
            engine_type: Some(engine_type),
            kwargs: Some(kwargs),
            engine_name: None,
            error: None,
        }
    }

    fn unavailable(error: &str) -> Self {
        Self {
            engine_type: None,
            kwargs: None,
            engine_name: None,
            error: Some(error.to_owned()),
        }
    }

    pub fn with_engine_name(mut self, engine_name: String) -> Self {
        self.engine_name = Some(engine_name);
        self
    }
}

#[derive(Debug, Clone)]
struct ServerEntry {
    id: String,
    name: String,
    engine_type: String,
    priority: i64,
    enabled: bool,
    config: Map<String, Value>,
}

impl ServerEntry {
    fn from_value(value: &Value, project_root: &Path) -> Self {
        let mut config = value
            .get("config")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        if let Some(Value::String(stored)) = config.get("api_key") {
            config.insert(
                "api_key".to_owned(),
                Value::String(secret_store::decrypt(stored, project_root)),
            );
        }
        Self {
            id: value
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            engine_type: value
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            name: value
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            priority: value.get("priority").and_then(Value::as_i64).unwrap_or(50),
            enabled: value
                .get("enabled")
                .and_then(Value::as_bool)
                .unwrap_or(true),
            config,
        }
    }
}

#[async_trait]
trait ServerAvailability: Sync {
    async fn check(&self, server: &ServerEntry) -> bool;
}

struct NetworkAvailability;

#[async_trait]
impl ServerAvailability for NetworkAvailability {
    async fn check(&self, server: &ServerEntry) -> bool {
        match server.engine_type.as_str() {
            "claude_api" | "openai" => {
                config_string(&server.config, "api_key").is_some_and(|key| !key.is_empty())
            }
            "ollama" => {
                let url =
                    config_string(&server.config, "base_url").unwrap_or("http://localhost:11434");
                probe(url, "/api/tags", None).await
            }
            "openai_compat" => {
                let Some(url) = config_string(&server.config, "base_url") else {
                    return false;
                };
                probe(url, "/v1/models", config_string(&server.config, "api_key")).await
            }
            "hailo_vlm" => is_hailo_vlm_available(
                config_string(&server.config, "model_name").unwrap_or("qwen2-vl-2b-instruct"),
            ),
            _ => false,
        }
    }
}

/// Resolves the configured translation server, then falls back in priority order.
pub async fn resolve_active_server(
    config: &Value,
    project_root: &Path,
    server_id: Option<&str>,
) -> TranslationServerResolution {
    resolve_active_server_with(config, project_root, server_id, &NetworkAvailability).await
}

async fn resolve_active_server_with<A: ServerAvailability>(
    config: &Value,
    project_root: &Path,
    server_id: Option<&str>,
    availability: &A,
) -> TranslationServerResolution {
    let mut servers = servers_from_config(config, project_root);
    servers.sort_by_key(|server| server.priority);
    if servers.is_empty() {
        return TranslationServerResolution::unavailable(NO_SERVERS);
    }
    let language = config_string_value(config, "ai_servers_language")
        .or_else(|| {
            config
                .get("ai_analysis")
                .and_then(|value| value.get("language"))
                .and_then(Value::as_str)
        })
        .unwrap_or("ja");
    let local_only = config
        .get("ai_servers_fallback_local_only")
        .and_then(Value::as_bool)
        .or_else(|| {
            config
                .get("ai_analysis")
                .and_then(|value| value.get("fallback_local_only"))
                .and_then(Value::as_bool)
        })
        .unwrap_or(false);
    let target_id = server_id
        .filter(|id| !id.is_empty())
        .or_else(|| config_string_value(config, "ai_servers_active"));

    if let Some(target_id) = target_id {
        for server in &servers {
            if server.id == target_id && server.enabled {
                if local_only && !is_server_local(server) {
                    break;
                }
                if availability.check(server).await {
                    return TranslationServerResolution::available(
                        server.engine_type.clone(),
                        build_kwargs(server, language),
                    );
                }
                break;
            }
        }
    }

    // Match Python: retry the target during this complete priority scan, including its HTTP probe.
    for server in &servers {
        if !server.enabled || local_only && !is_server_local(server) {
            continue;
        }
        if availability.check(server).await {
            return TranslationServerResolution::available(
                server.engine_type.clone(),
                build_kwargs(server, language),
            );
        }
    }
    TranslationServerResolution::unavailable(if local_only {
        NO_LOCAL_SERVER
    } else {
        NO_AVAILABLE_SERVER
    })
}

fn build_kwargs(server: &ServerEntry, language: &str) -> Value {
    let mut kwargs = server.config.clone();
    kwargs
        .entry("language".to_owned())
        .or_insert_with(|| Value::String(language.to_owned()));
    Value::Object(kwargs)
}

fn config_string<'a>(config: &'a Map<String, Value>, key: &str) -> Option<&'a str> {
    config.get(key).and_then(Value::as_str)
}

fn config_string_value<'a>(config: &'a Value, key: &str) -> Option<&'a str> {
    config.get(key).and_then(Value::as_str)
}

fn is_server_local(server: &ServerEntry) -> bool {
    match server.engine_type.as_str() {
        "claude_api" | "openai" => false,
        "hailo_vlm" => true,
        // Unlike Python, malformed URLs are non-local here. Under local-only they then skip
        // instead of failing their ollama/openai_compat probe, so no resolution result can differ.
        _ => config_string(&server.config, "base_url").is_some_and(analysis_net::is_private_url),
    }
}

fn servers_from_config(config: &Value, project_root: &Path) -> Vec<ServerEntry> {
    let servers = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .filter(|servers| !servers.is_empty())
        .map(|servers| {
            servers
                .iter()
                .map(|server| ServerEntry::from_value(server, project_root))
                .collect()
        });
    servers.unwrap_or_else(|| {
        legacy_server(
            config.get("ai_analysis").and_then(Value::as_object),
            project_root,
        )
        .into_iter()
        .collect()
    })
}

fn legacy_server(
    ai_config: Option<&Map<String, Value>>,
    project_root: &Path,
) -> Option<ServerEntry> {
    let ai_config = ai_config.filter(|config| !config.is_empty())?;
    let engine_type = config_string(ai_config, "engine").unwrap_or("claude_api");
    let language = config_string(ai_config, "language").unwrap_or("ja");
    let mut config = Map::new();
    let name = match engine_type {
        "ollama" => {
            let model = ai_config
                .get("ollama_model")
                .cloned()
                .unwrap_or_else(|| Value::String("llava:latest".to_owned()));
            config.insert(
                "base_url".to_owned(),
                ai_config
                    .get("ollama_url")
                    .cloned()
                    .unwrap_or_else(|| Value::String("http://localhost:11434".to_owned())),
            );
            config.insert("model".to_owned(), model.clone());
            format!("Ollama ({})", model.as_str().unwrap_or_default())
        }
        "openai_compat" => {
            let model = ai_config
                .get("openai_compat_model")
                .cloned()
                .unwrap_or_else(|| Value::String(String::new()));
            config.insert(
                "base_url".to_owned(),
                ai_config
                    .get("openai_compat_url")
                    .cloned()
                    .unwrap_or_else(|| Value::String(String::new())),
            );
            config.insert(
                "api_key".to_owned(),
                Value::String(secret_store::decrypt(
                    config_string(ai_config, "openai_compat_api_key").unwrap_or_default(),
                    project_root,
                )),
            );
            config.insert("model".to_owned(), model.clone());
            format!(
                "OpenAI Compatible ({})",
                model
                    .as_str()
                    .filter(|model| !model.is_empty())
                    .unwrap_or("default")
            )
        }
        "openai" => {
            let model = ai_config
                .get("openai_model")
                .cloned()
                .unwrap_or_else(|| Value::String("gpt-4o-mini".to_owned()));
            config.insert(
                "api_key".to_owned(),
                Value::String(secret_store::decrypt(
                    config_string(ai_config, "openai_api_key").unwrap_or_default(),
                    project_root,
                )),
            );
            config.insert("model".to_owned(), model.clone());
            format!("OpenAI ({})", model.as_str().unwrap_or_default())
        }
        "hailo_vlm" => {
            let model = ai_config
                .get("hailo_vlm_model")
                .cloned()
                .unwrap_or_else(|| Value::String("qwen2-vl-2b-instruct".to_owned()));
            config.insert("model_name".to_owned(), model.clone());
            format!("Hailo VLM ({})", model.as_str().unwrap_or_default())
        }
        _ => {
            let model = ai_config
                .get("model")
                .cloned()
                .unwrap_or_else(|| Value::String("claude-sonnet-4-6".to_owned()));
            config.insert(
                "api_key".to_owned(),
                Value::String(secret_store::decrypt(
                    config_string(ai_config, "api_key").unwrap_or_default(),
                    project_root,
                )),
            );
            config.insert("model".to_owned(), model.clone());
            format!("Claude ({})", model.as_str().unwrap_or_default())
        }
    };
    config.insert("language".to_owned(), Value::String(language.to_owned()));
    Some(ServerEntry {
        id: "legacy-default".to_owned(),
        name,
        engine_type: engine_type.to_owned(),
        priority: 10,
        enabled: true,
        config,
    })
}

fn is_hailo_vlm_available(model_name: &str) -> bool {
    analysis::is_hailo_device_available() && analysis::is_hailo_hef_available(model_name)
}

async fn probe(base_url: &str, suffix: &str, api_key: Option<&str>) -> bool {
    let Ok(client) = build_pinned_client(base_url, true, Duration::from_secs(3)).await else {
        return false;
    };
    let url = format!("{}{}", base_url.trim_end_matches('/'), suffix);
    let mut request = client.get(url).header(header::ACCEPT, "application/json");
    if let Some(api_key) = api_key.filter(|key| !key.is_empty()) {
        request = request.bearer_auth(api_key);
    }
    matches!(request.send().await, Ok(response) if response.status() == StatusCode::OK)
}

#[cfg(test)]
mod tests {
    use std::{collections::HashMap, path::Path};

    use super::*;
    use serde_json::json;

    struct FakeAvailability(HashMap<String, bool>);

    #[async_trait]
    impl ServerAvailability for FakeAvailability {
        async fn check(&self, server: &ServerEntry) -> bool {
            self.0.get(&server.id).copied().unwrap_or(false)
        }
    }

    fn server(
        id: &str,
        engine_type: &str,
        priority: i64,
        enabled: bool,
        base_url: Option<&str>,
    ) -> Value {
        let mut config = Map::new();
        if let Some(base_url) = base_url {
            config.insert("base_url".to_owned(), json!(base_url));
        }
        json!({"id": id, "type": engine_type, "priority": priority, "enabled": enabled, "config": config})
    }

    async fn resolve(config: Value, available: &[(&str, bool)]) -> TranslationServerResolution {
        resolve_at(config, Path::new("."), available).await
    }

    async fn resolve_at(
        config: Value,
        project_root: &Path,
        available: &[(&str, bool)],
    ) -> TranslationServerResolution {
        resolve_active_server_with(
            &config,
            project_root,
            None,
            &FakeAvailability(
                available
                    .iter()
                    .map(|(id, value)| ((*id).to_owned(), *value))
                    .collect(),
            ),
        )
        .await
    }

    #[tokio::test]
    async fn resolve_reports_no_servers() {
        assert_eq!(
            resolve(json!({}), &[]).await.error.as_deref(),
            Some(NO_SERVERS)
        );
    }

    #[tokio::test]
    async fn resolve_prefers_reachable_target() {
        let config = json!({"ai_servers_active":"target", "ai_servers":[server("fallback", "openai", 20, true, None), server("target", "openai", 10, true, None)]});
        assert_eq!(
            resolve(config, &[("target", true)])
                .await
                .engine_type
                .as_deref(),
            Some("openai")
        );
    }

    #[tokio::test]
    async fn unreachable_target_falls_through_to_next_server() {
        let config = json!({"ai_servers_active":"target", "ai_servers":[server("target", "ollama", 10, true, Some("http://localhost:11434")), server("fallback", "openai", 20, true, None)]});
        let result = resolve(config, &[("target", false), ("fallback", true)]).await;
        assert_eq!(result.engine_type.as_deref(), Some("openai"));
    }

    #[tokio::test]
    async fn non_local_target_falls_through_in_local_only_mode() {
        let config = json!({"ai_servers_active":"remote", "ai_servers_fallback_local_only":true, "ai_servers":[server("remote", "openai", 10, true, None), server("local", "ollama", 20, true, Some("http://localhost:11434"))]});
        assert_eq!(
            resolve(config, &[("remote", true), ("local", true)])
                .await
                .engine_type
                .as_deref(),
            Some("ollama")
        );
    }

    #[tokio::test]
    async fn resolve_reports_no_local_server() {
        let config = json!({"ai_servers_fallback_local_only":true, "ai_servers":[server("remote", "openai", 10, true, None)]});
        assert_eq!(
            resolve(config, &[]).await.error.as_deref(),
            Some(NO_LOCAL_SERVER)
        );
    }

    #[tokio::test]
    async fn resolve_reports_no_available_server() {
        let config = json!({"ai_servers":[server("down", "ollama", 10, true, Some("http://localhost:11434"))]});
        assert_eq!(
            resolve(config, &[("down", false)]).await.error.as_deref(),
            Some(NO_AVAILABLE_SERVER)
        );
    }

    #[test]
    fn hailo_is_local() {
        assert!(is_server_local(&ServerEntry::from_value(
            &server("hailo", "hailo_vlm", 10, true, None,),
            Path::new(".")
        )));
    }

    #[test]
    fn shared_private_url_matches_observable_python_cases() {
        for (url, expected) in [
            ("http://localhost:11434", true),
            ("http://127.0.0.1", true),
            ("http://192.168.1.1", true),
            ("http://8.8.8.8", false),
            ("notaurl", false),
        ] {
            assert_eq!(analysis_net::is_private_url(url), expected, "{url}");
        }
    }

    #[tokio::test]
    async fn legacy_engines_resolve_and_keep_python_names() {
        let cases = [
            (
                "ollama",
                json!({"engine":"ollama", "ollama_model":"vision", "language":"en"}),
                "Ollama (vision)",
            ),
            (
                "openai_compat",
                json!({"engine":"openai_compat", "openai_compat_model":"compatible"}),
                "OpenAI Compatible (compatible)",
            ),
            (
                "openai",
                json!({"engine":"openai", "openai_model":"gpt"}),
                "OpenAI (gpt)",
            ),
            (
                "hailo_vlm",
                json!({"engine":"hailo_vlm", "hailo_vlm_model":"hailo"}),
                "Hailo VLM (hailo)",
            ),
            (
                "claude_api",
                json!({"engine":"claude_api", "model":"claude"}),
                "Claude (claude)",
            ),
        ];
        for (engine, ai_analysis, name) in cases {
            let config = json!({"ai_analysis": ai_analysis});
            let result = resolve(config.clone(), &[("legacy-default", true)]).await;
            assert_eq!(result.engine_type.as_deref(), Some(engine));
            assert_eq!(servers_from_config(&config, Path::new("."))[0].name, name);
        }
    }

    #[tokio::test]
    async fn empty_legacy_config_reports_no_servers() {
        assert_eq!(
            resolve(json!({"ai_analysis": {}}), &[])
                .await
                .error
                .as_deref(),
            Some(NO_SERVERS)
        );
    }

    #[tokio::test]
    async fn empty_registry_falls_back_to_legacy() {
        let result = resolve(
            json!({"ai_servers": [], "ai_analysis": {"engine":"openai"}}),
            &[("legacy-default", true)],
        )
        .await;
        assert_eq!(result.engine_type.as_deref(), Some("openai"));
    }

    #[tokio::test]
    async fn populated_registry_ignores_legacy() {
        let config = json!({"ai_servers": [server("registered", "openai", 10, true, None)], "ai_analysis": {"engine":"ollama"}});
        assert_eq!(
            resolve(config, &[("registered", true), ("legacy-default", true)])
                .await
                .engine_type
                .as_deref(),
            Some("openai")
        );
    }

    #[tokio::test]
    async fn registered_api_key_is_decrypted_without_synthesizing_missing_keys() {
        let root = tempfile::tempdir().unwrap();
        let encrypted = secret_store::encrypt("secret", root.path());
        let encrypted_config =
            json!({"ai_servers": [{"id":"key", "type":"openai", "config":{"api_key":encrypted}}]});
        let result = resolve_at(encrypted_config, root.path(), &[("key", true)]).await;
        assert_eq!(
            result
                .kwargs
                .and_then(|kwargs| kwargs.get("api_key").cloned()),
            Some(json!("secret"))
        );

        let config = json!({"ai_servers": [{"id":"none", "type":"openai", "config":{}}]});
        let result = resolve(config, &[("none", true)]).await;
        assert!(result
            .kwargs
            .is_some_and(|kwargs| kwargs.get("api_key").is_none()));
    }
}

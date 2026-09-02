//! OpenAI-compatible LLM client and local agent tool definitions.

use axum::http::{HeaderMap, Method};
use serde_json::{json, Map, Value};

use crate::state::SharedState;

pub struct Endpoint {
    pub base_url: String,
    pub model: String,
    pub api_key: String,
    pub timeout_secs: u64,
}

pub struct ChatResponse {
    pub content: String,
    pub model: String,
    pub usage: Value,
    pub tool_calls: Vec<ToolCall>,
}

#[derive(Debug, PartialEq)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: String,
}

pub fn resolve_endpoint(state: &SharedState, category: &str) -> Option<Endpoint> {
    let endpoint = state
        .config
        .app_config
        .get("llm_endpoints")?
        .get(category)?;
    let base_url = endpoint.get("base_url")?.as_str()?.trim();
    if base_url.is_empty() {
        return None;
    }
    let raw_key = endpoint
        .get("api_key")
        .and_then(Value::as_str)
        .unwrap_or("");
    Some(Endpoint {
        base_url: base_url.trim_end_matches('/').to_string(),
        model: endpoint
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        api_key: crate::secret_store::decrypt(raw_key, &state.config.project_root),
        timeout_secs: endpoint
            .get("timeout")
            .and_then(Value::as_u64)
            .unwrap_or(60),
    })
}

/// True for the textual loopback hosts a base_url may use. `Url::host_str()` returns
/// IPv6 hosts in bracketed form, hence `[::1]` rather than `::1`.
fn is_loopback_host(host: Option<&str>) -> bool {
    matches!(host, Some("127.0.0.1" | "localhost" | "[::1]"))
}

/// True only for this exact server's own hailo-genai self-loopback base_url
/// (as built in `misc_admin::llm_agent`'s synthetic hailo endpoint). Host/port alone
/// are not enough: any other route on our own port must never receive the caller's
/// forwarded Cookie/Authorization, since a differently-configured `llm_endpoints`
/// entry could otherwise point at this port with a different, unintended path.
///
/// `pub(crate)`: also used by `llm_agent_prompt::run_agent_prompt_based` to decide
/// whether `tools` may be unwrapped to HailoRT's native bare-object shape — a
/// substring check like `base_url.contains("hailo-genai")` would wrongly match an
/// external OpenAI-compatible endpoint whose URL merely contains that text (Codex
/// stop-time review, 2026-08-16), so both call sites share this exact check.
pub(crate) fn is_own_loopback(effective_port: u16, base_url: &str) -> bool {
    let Ok(url) = url::Url::parse(base_url) else {
        return false;
    };
    is_loopback_host(url.host_str())
        && url.scheme() == "http"
        && url.port() == Some(effective_port)
        && url.path() == "/ext/hailo-genai/v1"
}

pub async fn chat(
    state: &SharedState,
    endpoint: &Endpoint,
    messages: &[Value],
    max_tokens: u32,
    temperature: f64,
    tools: Option<&Value>,
    caller_headers: Option<&HeaderMap>,
) -> Result<ChatResponse, String> {
    let mut payload = json!({
        "model": endpoint.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": false,
    });
    if let Some(tools) = tools.filter(|value| value.is_array()) {
        payload["tools"] = tools.clone();
    }
    let mut request = state
        .inference_client
        .post(format!("{}/chat/completions", endpoint.base_url))
        .timeout(std::time::Duration::from_secs(endpoint.timeout_secs))
        .json(&payload);
    // Forward the caller's own auth (e.g. PIN session cookie) only when the target is this
    // same server's own loopback port and it has no configured api_key — never leak the
    // caller's credentials to an externally configured (real third-party) endpoint.
    if endpoint.api_key.is_empty() && is_own_loopback(state.effective_port, &endpoint.base_url) {
        if let Some(headers) = caller_headers {
            for header in ["Authorization", "X-Api-Key", "Cookie"] {
                if let Some(value) = headers.get(header) {
                    request = request.header(header, value);
                }
            }
        }
    } else if caller_headers.is_some()
        && endpoint.api_key.is_empty()
        && url::Url::parse(&endpoint.base_url)
            .ok()
            .is_some_and(|url| is_loopback_host(url.host_str()))
    {
        tracing::warn!(base_url = %endpoint.base_url, "caller auth was not forwarded because the URL is not this server's own hailo self-loopback route");
    }
    if !endpoint.api_key.is_empty() {
        request = request.header("Authorization", format!("Bearer {}", endpoint.api_key));
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("HTTP {}", response.status()));
    }
    let value = response
        .json::<Value>()
        .await
        .map_err(|error| error.to_string())?;
    let message = value
        .pointer("/choices/0/message")
        .and_then(Value::as_object)
        .ok_or_else(|| "missing choices[0].message".to_string())?;
    let tool_calls = message
        .get("tool_calls")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(|call| ToolCall {
            id: call
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            name: call
                .pointer("/function/name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            arguments: call
                .pointer("/function/arguments")
                .and_then(Value::as_str)
                .unwrap_or("{}")
                .to_string(),
        })
        .collect();
    Ok(ChatResponse {
        content: message
            .get("content")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        model: value
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or(&endpoint.model)
            .to_string(),
        usage: value.get("usage").cloned().unwrap_or(Value::Null),
        tool_calls,
    })
}

pub const TOOL_API_MAP: &[(&str, &str, &str)] = &[
    ("search_files", "GET", "/api/search"),
    ("get_file_tags", "GET", "/api/files/{file_id}/tags"),
    ("list_scan_roots", "GET", "/api/scan-roots"),
    ("get_stats", "GET", "/api/stats"),
    ("get_server_info", "GET", "/api/server-info"),
    ("list_collections", "GET", "/api/collections"),
    ("list_llm_endpoints", "GET", "/api/settings/llm-endpoints"),
    ("get_server_mode", "GET", "/api/server/mode"),
    ("set_tags", "POST", "/api/tags/batch-set"),
    (
        "add_to_collection",
        "POST",
        "/api/collections/{collection_id}/batch-add",
    ),
    (
        "remove_from_collection",
        "POST",
        "/api/collections/{collection_id}/batch-remove",
    ),
    ("create_collection", "POST", "/api/collections"),
    ("rate_image", "POST", "/api/ratings/set"),
    ("toggle_favorite", "POST", "/api/favorites/toggle"),
];

/// Unwraps OpenAI Chat Completions tool objects (`{"type":"function",
/// "function":{"name":...,"description":...,"parameters":...}}`) down to the
/// inner `function` object HailoRT's native `write(messages, tools)` expects
/// (`{"name":...,"description":...,"parameters":...}`). An entry with no
/// `function` key (already in the inner shape) passes through unchanged, so
/// this is safe to apply defensively at more than one point in a call chain.
pub fn unwrap_openai_tools(tools: &[Value]) -> Vec<Value> {
    tools
        .iter()
        .map(|tool| {
            tool.get("function")
                .cloned()
                .unwrap_or_else(|| tool.clone())
        })
        .collect()
}

pub fn tool_definitions() -> Vec<Value> {
    let definitions = [
        (
            "search_files",
            "Search files by tag query",
            json!({"q":{"type":"string"},"limit":{"type":"integer"}}),
            json!(["q"]),
        ),
        (
            "get_file_tags",
            "Get all tags for a file",
            json!({"file_id":{"type":"integer"}}),
            json!(["file_id"]),
        ),
        (
            "list_scan_roots",
            "List registered scan root directories",
            json!({}),
            json!([]),
        ),
        ("get_stats", "Get database statistics", json!({}), json!([])),
        ("get_server_info", "Get server status", json!({}), json!([])),
        (
            "list_collections",
            "List all collections",
            json!({}),
            json!([]),
        ),
        (
            "list_llm_endpoints",
            "List configured LLM endpoints",
            json!({}),
            json!([]),
        ),
        (
            "get_server_mode",
            "Get current server mode",
            json!({}),
            json!([]),
        ),
        (
            "set_tags",
            "Add or remove tags on files",
            json!({"items":{"type":"array","items":{"type":"object"}}}),
            json!(["items"]),
        ),
        (
            "add_to_collection",
            "Add files to a collection",
            json!({"collection_id":{"type":"integer"},"file_ids":{"type":"array","items":{"type":"integer"}}}),
            json!(["collection_id", "file_ids"]),
        ),
        (
            "remove_from_collection",
            "Remove files from a collection",
            json!({"collection_id":{"type":"integer"},"file_ids":{"type":"array","items":{"type":"integer"}}}),
            json!(["collection_id", "file_ids"]),
        ),
        (
            "create_collection",
            "Create a new collection",
            json!({"name":{"type":"string"}}),
            json!(["name"]),
        ),
        (
            "rate_image",
            "Set a file rating",
            json!({"file_id":{"type":"integer"},"rating":{"type":"integer"}}),
            json!(["file_id", "rating"]),
        ),
        (
            "toggle_favorite",
            "Toggle a file favorite",
            json!({"file_id":{"type":"integer"}}),
            json!(["file_id"]),
        ),
    ];
    definitions.into_iter().map(|(name, description, properties, required)| json!({
        "type": "function",
        "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required}}
    })).collect()
}

pub async fn execute_tool(
    state: &SharedState,
    caller_headers: &HeaderMap,
    name: &str,
    arguments: &Map<String, Value>,
) -> Value {
    let Some((_, method, template)) = TOOL_API_MAP.iter().find(|(tool, _, _)| *tool == name) else {
        return json!({"error": format!("Unknown tool: {name}")});
    };
    let (path, body) = match interpolate_path(template, arguments) {
        Ok(value) => value,
        Err(error) => return json!({"error": error}),
    };
    let url = executor_url(state.effective_port, &path);
    let mut request = state
        .inference_client
        .request(
            Method::from_bytes(method.as_bytes()).expect("static method"),
            url,
        )
        .timeout(std::time::Duration::from_secs(30))
        .header("Content-Type", "application/json")
        .header("X-Requested-With", "XMLHttpRequest");
    for header in ["Authorization", "X-Api-Key", "Cookie"] {
        if let Some(value) = caller_headers.get(header) {
            request = request.header(header, value);
        }
    }
    let response = if *method == "GET" {
        request.query(&body).send().await
    } else {
        request.json(&body).send().await
    };
    match response {
        Ok(response) => response
            .json::<Value>()
            .await
            .unwrap_or_else(|error| json!({"error": error.to_string()})),
        Err(error) => json!({"error": error.to_string()}),
    }
}

fn executor_url(port: u16, path: &str) -> String {
    format!("http://127.0.0.1:{port}{path}")
}

fn interpolate_path(
    template: &str,
    arguments: &Map<String, Value>,
) -> Result<(String, Map<String, Value>), String> {
    let mut path = template.to_string();
    let mut body = arguments.clone();
    while let Some(start) = path.find('{') {
        let end = path[start..]
            .find('}')
            .map(|offset| start + offset)
            .ok_or_else(|| "invalid tool path".to_string())?;
        let key = &path[start + 1..end];
        let value = body
            .remove(key)
            .ok_or_else(|| format!("missing path argument: {key}"))?;
        let value = value
            .as_str()
            .map(str::to_string)
            .unwrap_or_else(|| value.to_string());
        path.replace_range(start..=end, &urlencoding::encode(&value));
    }
    Ok((path, body))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tool_map_has_exactly_the_supported_fourteen_routes() {
        assert_eq!(TOOL_API_MAP.len(), 14);
        let expected = [
            ("search_files", "GET", "/api/search", None),
            (
                "get_file_tags",
                "GET",
                "/api/files/7/tags",
                Some(("file_id", 7)),
            ),
            ("list_scan_roots", "GET", "/api/scan-roots", None),
            ("get_stats", "GET", "/api/stats", None),
            ("get_server_info", "GET", "/api/server-info", None),
            ("list_collections", "GET", "/api/collections", None),
            (
                "list_llm_endpoints",
                "GET",
                "/api/settings/llm-endpoints",
                None,
            ),
            ("get_server_mode", "GET", "/api/server/mode", None),
            ("set_tags", "POST", "/api/tags/batch-set", None),
            (
                "add_to_collection",
                "POST",
                "/api/collections/7/batch-add",
                Some(("collection_id", 7)),
            ),
            (
                "remove_from_collection",
                "POST",
                "/api/collections/7/batch-remove",
                Some(("collection_id", 7)),
            ),
            ("create_collection", "POST", "/api/collections", None),
            ("rate_image", "POST", "/api/ratings/set", None),
            ("toggle_favorite", "POST", "/api/favorites/toggle", None),
        ];
        for (name, method, path, parameter) in expected {
            let (_, actual_method, template) = TOOL_API_MAP
                .iter()
                .find(|(tool, _, _)| *tool == name)
                .unwrap();
            let mut arguments = Map::new();
            if let Some((key, value)) = parameter {
                arguments.insert(key.to_string(), json!(value));
            }
            let (actual_path, body) = interpolate_path(template, &arguments).unwrap();
            assert_eq!((*actual_method, actual_path.as_str()), (method, path));
            assert!(body.is_empty());
        }
    }

    #[test]
    fn tools_cannot_target_ip_authorized_routes() {
        // Keep this list aligned with auth/chain.rs, auth/gateway.rs, mcp_client.rs,
        // tools_ops.rs, and misc_admin.rs. Every tool path is checked, so additions
        // must prove they do not enter an IP-dependent authorization route.
        const IP_AUTHORIZED_PREFIXES: &[&str] = &["/api/gateway/", "/api/mcp/", "/api/tools/"];
        for (_, _, path) in TOOL_API_MAP {
            assert!(
                IP_AUTHORIZED_PREFIXES
                    .iter()
                    .all(|prefix| !path.starts_with(prefix)),
                "IP-authorized tool path: {path}"
            );
        }
    }

    #[test]
    fn effective_port_is_the_executor_destination() {
        let port = 32123;
        assert_eq!(
            executor_url(port, "/api/search"),
            "http://127.0.0.1:32123/api/search"
        );
    }

    #[test]
    fn caller_auth_forwards_only_to_this_servers_own_hailo_loopback_route() {
        assert!(is_own_loopback(
            5000,
            "http://127.0.0.1:5000/ext/hailo-genai/v1"
        ));
        assert!(is_own_loopback(
            5000,
            "http://localhost:5000/ext/hailo-genai/v1"
        ));
        assert_eq!(
            url::Url::parse("http://[::1]:5000/ext/hailo-genai/v1")
                .unwrap()
                .host_str(),
            Some("[::1]")
        );
        assert!(is_own_loopback(
            5000,
            "http://[::1]:5000/ext/hailo-genai/v1"
        ));
        // wrong port, wrong host, wrong scheme, wrong path, or an external URL must never
        // receive the caller's Cookie/Authorization — same host:port is not enough, since a
        // differently-configured llm_endpoints entry could target any other route on our port.
        assert!(!is_own_loopback(
            5000,
            "http://127.0.0.1:5001/ext/hailo-genai/v1"
        ));
        assert!(!is_own_loopback(5000, "https://api.openai.com/v1"));
        assert!(!is_own_loopback(
            5000,
            "https://127.0.0.1:5000/ext/hailo-genai/v1"
        ));
        assert!(!is_own_loopback(5000, "http://127.0.0.1:5000/v1"));
        assert!(!is_own_loopback(5000, "http://127.0.0.1:5000/api/settings"));
        // a lookalike path must not pass a prefix-style check — require the exact
        // synthetic base path built in misc_admin::llm_agent's hailo fallback.
        assert!(!is_own_loopback(
            5000,
            "http://127.0.0.1:5000/ext/hailo-genai-attacker/v1"
        ));
        assert!(!is_own_loopback(
            5000,
            "http://127.0.0.1:5000/ext/hailo-genai/v1/extra"
        ));
        assert!(!is_own_loopback(5000, "not a url"));
    }

    #[test]
    fn parses_openai_tool_calls() {
        let data = json!({"id":"call-1", "function":{"name":"get_stats", "arguments":"{}"}});
        let call = ToolCall {
            id: data["id"].as_str().unwrap().to_string(),
            name: data["function"]["name"].as_str().unwrap().to_string(),
            arguments: data["function"]["arguments"].as_str().unwrap().to_string(),
        };
        assert_eq!(
            call,
            ToolCall {
                id: "call-1".into(),
                name: "get_stats".into(),
                arguments: "{}".into()
            }
        );
    }
}

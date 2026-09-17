use std::time::Duration;

use async_trait::async_trait;
use reqwest::StatusCode;
use serde_json::{json, Value};

use crate::{
    analysis_engines::http_client::{build_pinned_client, read_response_capped},
    infer_client::InferClient,
};

const TIMEOUT: Duration = Duration::from_secs(300);
const TIMEOUT_MS: u32 = 300_000;
const MAX_RESPONSE_BYTES: usize = 20 * 1024 * 1024;
const USER_AGENT: &str = "YU-AI-Manager";

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum TranslationLlmError {
    #[error("translation_failed")]
    Failed,
    #[error("translate_hailo_unavailable")]
    HailoUnavailable,
    #[error("Unsupported engine type for translation: {0}")]
    Unsupported(String),
}

#[async_trait]
trait TranslationTransport: Sync {
    async fn post_json(
        &self,
        url: String,
        body: Value,
        headers: Vec<(&'static str, String)>,
        allow_local: bool,
    ) -> Result<(StatusCode, String), String>;

    async fn hailo_generate(&self, model: &str, prompt: String) -> Result<String, String>;
}

struct LiveTransport<'a> {
    infer_client: Option<&'a InferClient>,
}

#[async_trait]
impl TranslationTransport for LiveTransport<'_> {
    async fn post_json(
        &self,
        url: String,
        body: Value,
        headers: Vec<(&'static str, String)>,
        allow_local: bool,
    ) -> Result<(StatusCode, String), String> {
        let client = build_pinned_client(&url, allow_local, TIMEOUT)
            .await
            .map_err(|error| error.to_string())?;
        let mut request = client.post(url).json(&body);
        for (name, value) in headers {
            request = request.header(name, value);
        }
        let response = request.send().await.map_err(|error| error.to_string())?;
        let status = response.status();
        let body = read_response_capped(response, MAX_RESPONSE_BYTES)
            .await
            .map_err(|error| error.to_string())?;
        Ok((status, body))
    }

    async fn hailo_generate(&self, model: &str, prompt: String) -> Result<String, String> {
        let client = self
            .infer_client
            .ok_or_else(|| "infer client unavailable".to_owned())?;
        let value = client
            .llm_generate(Some(model.to_owned()), prompt, Some(TIMEOUT_MS))
            .await
            .map_err(|error| error.to_string())?;
        value
            .pointer("/data/text")
            .or_else(|| value.get("text"))
            .and_then(Value::as_str)
            .or_else(|| value.as_str())
            .map(str::to_owned)
            .ok_or_else(|| "missing generated text".to_owned())
    }
}

/// Calls the text-only translation backends directly, deliberately bypassing `AnalysisEngine`.
pub async fn call_llm(
    engine_type: &str,
    kwargs: &Value,
    prompt: &str,
    infer_client: Option<&InferClient>,
) -> Result<String, TranslationLlmError> {
    if engine_type == "hailo_vlm" && infer_client.is_none() {
        return Err(TranslationLlmError::HailoUnavailable);
    }
    call_llm_with(engine_type, kwargs, prompt, &LiveTransport { infer_client }).await
}

async fn call_llm_with<T: TranslationTransport>(
    engine_type: &str,
    kwargs: &Value,
    prompt: &str,
    transport: &T,
) -> Result<String, TranslationLlmError> {
    match engine_type {
        "ollama" => {
            let base_url = setting(kwargs, "base_url", "http://localhost:11434");
            let body = json!({
                "model": setting(kwargs, "model", ""),
                "messages": [{"role": "user", "content": prompt}],
                "stream": false,
            });
            response_text(
                transport
                    .post_json(
                        format!("{}/api/chat", base_url.trim_end_matches('/')),
                        body,
                        standard_headers(),
                        true,
                    )
                    .await
                    .map_err(upstream_error)?,
                |value| value.pointer("/message/content").and_then(Value::as_str),
            )
        }
        "openai" | "openai_compat" => {
            let base_url = setting(kwargs, "base_url", "https://api.openai.com");
            let mut headers = standard_headers();
            if let Some(key) = kwargs
                .get("api_key")
                .and_then(Value::as_str)
                .filter(|key| !key.is_empty())
            {
                headers.push(("authorization", format!("Bearer {key}")));
            }
            response_text(
                transport
                    .post_json(
                        format!("{}/v1/chat/completions", base_url.trim_end_matches('/')),
                        json!({
                            "model": setting(kwargs, "model", "gpt-4o-mini"),
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.3,
                        }),
                        headers,
                        engine_type == "openai_compat",
                    )
                    .await
                    .map_err(upstream_error)?,
                |value| {
                    value
                        .pointer("/choices/0/message/content")
                        .and_then(Value::as_str)
                },
            )
        }
        "claude_api" => response_text(
            transport
                .post_json(
                    "https://api.anthropic.com/v1/messages".to_owned(),
                    json!({
                        "model": setting(kwargs, "model", "claude-sonnet-4-6-20250514"),
                        "max_tokens": 4096,
                        "messages": [{"role": "user", "content": prompt}],
                    }),
                    vec![
                        ("content-type", "application/json".to_owned()),
                        ("x-api-key", setting(kwargs, "api_key", "")),
                        ("anthropic-version", "2023-06-01".to_owned()),
                        ("user-agent", USER_AGENT.to_owned()),
                    ],
                    false,
                )
                .await
                .map_err(upstream_error)?,
            |value| {
                value
                    .pointer("/content/0")
                    .filter(|block| block.get("type").and_then(Value::as_str) == Some("text"))
                    .and_then(|block| block.get("text"))
                    .and_then(Value::as_str)
            },
        ),
        "hailo_vlm" => {
            let model = setting(kwargs, "llm_model", "qwen2.5-1.5b-chat");
            // Python clears session context first; this request-scoped sidecar call has no context to clear.
            // Python's generate_all(temperature=0.3, max_generated_tokens=1024) has no equivalent here:
            // infer_client::llm_generate only takes (hef_path, prompt, timeout_ms), so the sidecar API
            // cannot convey either setting and the model runs at its own defaults.
            // Python sends system/user as separate chat messages and lets the model's chat template
            // assemble them; the sidecar takes a single prompt, so this flattens both into one string.
            // The text the model actually sees therefore differs from what Python sends it.
            let hailo_prompt = format!(
                "System: You are a translator. Translate accurately and naturally.\nUser: {prompt}"
            );
            transport
                .hailo_generate(&model, hailo_prompt)
                .await
                .map(|text| text.trim().to_owned())
                .map_err(|error| {
                    tracing::error!(%error, "Hailo translation failed");
                    TranslationLlmError::Failed
                })
        }
        other => Err(TranslationLlmError::Unsupported(other.to_owned())),
    }
}

fn standard_headers() -> Vec<(&'static str, String)> {
    vec![
        ("content-type", "application/json".to_owned()),
        ("user-agent", USER_AGENT.to_owned()),
    ]
}

fn setting(kwargs: &Value, key: &str, default: &str) -> String {
    kwargs
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or(default)
        .to_owned()
}

fn response_text(
    response: (StatusCode, String),
    extract: impl FnOnce(&Value) -> Option<&str>,
) -> Result<String, TranslationLlmError> {
    let (status, body) = response;
    if !status.is_success() {
        tracing::error!(status = %status, response_body = %body, "Translation upstream failed");
        return Err(TranslationLlmError::Failed);
    }
    serde_json::from_str::<Value>(&body)
        .map_err(|error| {
            tracing::error!(%error, "Invalid translation upstream response");
            TranslationLlmError::Failed
        })
        .map(|value| extract(&value).unwrap_or_default().trim().to_owned())
}

fn upstream_error(error: String) -> TranslationLlmError {
    tracing::error!(%error, "Translation upstream request failed");
    TranslationLlmError::Failed
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use super::*;

    #[derive(Clone)]
    struct Request {
        url: String,
        body: Value,
        headers: Vec<(&'static str, String)>,
        allow_local: bool,
    }

    struct FakeTransport {
        requests: Arc<Mutex<Vec<Request>>>,
        response: (StatusCode, String),
        hailo: Result<String, String>,
    }

    #[async_trait]
    impl TranslationTransport for FakeTransport {
        async fn post_json(
            &self,
            url: String,
            body: Value,
            headers: Vec<(&'static str, String)>,
            allow_local: bool,
        ) -> Result<(StatusCode, String), String> {
            self.requests.lock().unwrap().push(Request {
                url,
                body,
                headers,
                allow_local,
            });
            Ok(self.response.clone())
        }

        async fn hailo_generate(&self, _model: &str, _prompt: String) -> Result<String, String> {
            self.hailo.clone()
        }
    }

    fn fake(response: (StatusCode, &str)) -> FakeTransport {
        FakeTransport {
            requests: Arc::new(Mutex::new(Vec::new())),
            response: (response.0, response.1.to_owned()),
            hailo: Ok(" hailo text ".to_owned()),
        }
    }

    #[tokio::test]
    async fn backend_shapes_and_dispatches_match_python() {
        let cases = [
            ("ollama", json!({}), r#"{"message":{"content":" ollama "}}"#),
            (
                "openai",
                json!({"api_key":"key"}),
                r#"{"choices":[{"message":{"content":" openai "}}]}"#,
            ),
            ("openai_compat", json!({}), r#"{"choices":[]}"#),
            (
                "claude_api",
                json!({"api_key":"key"}),
                r#"{"content":[{"type":"text","text":" claude "}]}"#,
            ),
        ];
        for (engine, kwargs, response) in cases {
            let transport = fake((StatusCode::OK, response));
            let result = call_llm_with(engine, &kwargs, "translate this", &transport)
                .await
                .unwrap();
            let request = transport.requests.lock().unwrap().pop().unwrap();
            assert_eq!(request.body["messages"][0]["content"], "translate this");
            assert!(request
                .headers
                .iter()
                .any(|(name, _)| *name == "user-agent"));
            match engine {
                "ollama" => {
                    assert_eq!(result, "ollama");
                    assert_eq!(request.url, "http://localhost:11434/api/chat");
                    assert_eq!(request.body["stream"], false);
                    assert!(request.allow_local);
                }
                "openai" | "openai_compat" => {
                    assert_eq!(request.body["temperature"], 0.3);
                    assert!(request.body.get("response_format").is_none());
                    assert_eq!(result, if engine == "openai" { "openai" } else { "" });
                }
                "claude_api" => {
                    assert_eq!(result, "claude");
                    assert_eq!(request.url, "https://api.anthropic.com/v1/messages");
                    assert_eq!(request.body["max_tokens"], 4096);
                    assert!(request.body.get("system").is_none());
                }
                _ => unreachable!(),
            }
        }
        let transport = fake((StatusCode::OK, "{}"));
        assert_eq!(
            call_llm_with("hailo_vlm", &json!({}), "translate this", &transport)
                .await
                .unwrap(),
            "hailo text"
        );
    }

    #[tokio::test]
    async fn bearer_is_optional_and_claude_non_text_is_empty() {
        let transport = fake((
            StatusCode::OK,
            r#"{"choices":[{"message":{"content":"x"}}]}"#,
        ));
        call_llm_with("openai", &json!({"api_key":"secret"}), "x", &transport)
            .await
            .unwrap();
        assert!(transport.requests.lock().unwrap()[0]
            .headers
            .iter()
            .any(|(name, value)| *name == "authorization" && value == "Bearer secret"));
        let no_key = fake((
            StatusCode::OK,
            r#"{"choices":[{"message":{"content":"x"}}]}"#,
        ));
        call_llm_with("openai", &json!({"api_key":""}), "x", &no_key)
            .await
            .unwrap();
        assert!(!no_key.requests.lock().unwrap()[0]
            .headers
            .iter()
            .any(|(name, _)| *name == "authorization"));
        let claude = fake((
            StatusCode::OK,
            r#"{"content":[{"type":"tool_use","text":"nope"}]}"#,
        ));
        assert_eq!(
            call_llm_with("claude_api", &json!({}), "x", &claude)
                .await
                .unwrap(),
            ""
        );
    }

    #[tokio::test]
    async fn unsupported_and_upstream_body_are_not_exposed() {
        assert_eq!(
            call_llm_with("unknown", &json!({}), "x", &fake((StatusCode::OK, "{}")))
                .await
                .unwrap_err(),
            TranslationLlmError::Unsupported("unknown".to_owned())
        );
        let injected = "Authorization: Bearer secret";
        let error = call_llm_with(
            "ollama",
            &json!({}),
            "x",
            &fake((StatusCode::INTERNAL_SERVER_ERROR, injected)),
        )
        .await
        .unwrap_err();
        assert_eq!(error, TranslationLlmError::Failed);
        assert!(!error.to_string().contains(injected));
    }
}

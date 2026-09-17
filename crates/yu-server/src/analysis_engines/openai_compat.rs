use std::{path::Path, time::Duration};

use async_trait::async_trait;
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::json;

use super::{
    http_client::{build_pinned_client, check_image_size_limits, read_response_capped},
    prompts,
    result_parse::{parse_analysis_result, parse_trends_result},
    AnalysisEngine, AnalysisResult, AnalyzeContext, AnalyzeMode, EngineError,
};

const TIMEOUT: Duration = Duration::from_secs(90);
const DEFAULT_BASE: &str = "https://api.openai.com";
const MAX_RESPONSE_BYTES: usize = 20 * 1024 * 1024;
const NATIVE_FORMATS: [&str; 3] = ["png", "jpg", "jpeg"];

pub struct OpenAiCompatEngine {
    pub base_url: Option<String>,
    pub model: String,
    pub api_key: String,
    pub language: String,
}

impl OpenAiCompatEngine {
    fn effective_base(&self) -> String {
        self.base_url
            .clone()
            .unwrap_or_else(|| DEFAULT_BASE.to_string())
    }

    fn is_custom_compat(&self) -> bool {
        matches!(&self.base_url, Some(base) if base.trim_end_matches('/') != DEFAULT_BASE)
    }

    /// Strip a trailing `/v1` (with or without a trailing slash) from a
    /// configured base URL before we append `/v1/chat/completions`.
    ///
    /// Many OpenAI-compatible servers are documented/configured with the
    /// `/v1` suffix already included in the base URL (e.g. LM Studio,
    /// text-generation-webui, or copy-pasting `https://api.openai.com/v1`
    /// verbatim). Appending `/v1/chat/completions` unconditionally in that
    /// case produces a broken `.../v1/v1/chat/completions` path. Normalize
    /// so both `http://host:1234` and `http://host:1234/v1` work.
    fn strip_trailing_v1(base: &str) -> &str {
        let trimmed = base.trim_end_matches('/');
        trimmed.strip_suffix("/v1").unwrap_or(trimmed)
    }

    async fn call_api(
        &self,
        messages: &serde_json::Value,
        max_tokens: u32,
        use_schema: bool,
        ctx: &AnalyzeContext,
    ) -> Result<String, EngineError> {
        let base = self.effective_base();
        let client = build_pinned_client(&base, self.is_custom_compat(), TIMEOUT).await?;
        let token_key = if ["gpt-5", "o1", "o3", "o4"]
            .iter()
            .any(|prefix| self.model.starts_with(prefix))
        {
            "max_completion_tokens"
        } else {
            "max_tokens"
        };
        let mut with_schema = use_schema;
        loop {
            let mut payload = json!({
                "model": self.model,
                "messages": messages,
                token_key: max_tokens,
            });
            if with_schema {
                let schema = ctx.json_schema.clone().unwrap_or_else(
                    || serde_json::json!({"type": "object", "additionalProperties": true}),
                );
                payload["response_format"] = serde_json::json!({
                    "type": "json_schema",
                    "json_schema": {"name": "image_analysis", "schema": schema},
                });
            }
            let mut request = client
                .post(format!(
                    "{}/v1/chat/completions",
                    Self::strip_trailing_v1(&base)
                ))
                .json(&payload);
            if !self.api_key.is_empty() {
                request = request.bearer_auth(&self.api_key);
            }
            let response = request
                .send()
                .await
                .map_err(|error| EngineError::msg(format!("Cannot connect to {base}: {error}")))?;
            let status = response.status().as_u16();
            let body = read_response_capped(response, MAX_RESPONSE_BYTES).await?;
            if status == 200 {
                let value = serde_json::from_str::<serde_json::Value>(&body).map_err(|error| {
                    EngineError::msg(format!("Failed to parse OpenAI response: {error}"))
                })?;
                return Ok(value
                    .pointer("/choices/0/message/content")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default()
                    .to_string());
            }
            if status == 401 {
                return Err(EngineError::msg("OpenAI API key is invalid or expired"));
            }
            if status == 429 {
                return Err(EngineError::msg(
                    "OpenAI rate limit exceeded. Please wait and retry.",
                ));
            }
            if status == 404 {
                return Err(EngineError::msg(format!("Model not found: {}", self.model)));
            }
            if with_schema && body.to_lowercase().contains("grammar") {
                with_schema = false;
                continue;
            }
            let detail = serde_json::from_str::<serde_json::Value>(&body)
                .ok()
                .and_then(|value| {
                    value
                        .pointer("/error/message")
                        .and_then(serde_json::Value::as_str)
                        .map(str::to_string)
                })
                .unwrap_or_else(|| body.chars().take(500).collect());
            let suffix = if !detail.is_empty() {
                format!(": {detail}")
            } else {
                Default::default()
            };
            return Err(EngineError::msg(format!(
                "OpenAI API error (HTTP {status}){suffix}"
            )));
        }
    }
}

#[async_trait]
impl AnalysisEngine for OpenAiCompatEngine {
    async fn analyze_image(
        &self,
        image_path: &Path,
        ctx: &AnalyzeContext,
    ) -> Result<AnalysisResult, EngineError> {
        let (media_type, image_data) = encode_image_for_openai(image_path)?;
        let system = if ctx.mode == AnalyzeMode::Ocr {
            "You are an OCR assistant. Read text from images accurately and return JSON."
                .to_string()
        } else {
            prompts::get_system_prompt(&ctx.language, ctx.mode)
        };
        let prompt = prompts::build_image_prompt(
            &ctx.existing_tags,
            ctx.existing_prompt.as_deref(),
            &ctx.language,
            ctx.mode,
        );
        let raw = self.call_api(&json!([
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": format!("data:{media_type};base64,{image_data}"), "detail": "low"}},
                {"type": "text", "text": prompt},
            ]},
        ]), 2000, true, ctx).await?;
        Ok(if ctx.mode == AnalyzeMode::Ocr {
            AnalysisResult {
                raw_response: raw,
                ..Default::default()
            }
        } else {
            parse_analysis_result(&raw)
        })
    }

    async fn analyze_trends(
        &self,
        prompts_in: &[String],
    ) -> Result<serde_json::Value, EngineError> {
        let prompts = prompts_in
            .iter()
            .take(50)
            .map(|value| value.chars().take(200).collect())
            .filter(|value: &String| !value.is_empty())
            .collect::<Vec<_>>();
        if prompts.is_empty() {
            return Ok(json!({"error": "No prompts to analyze"}));
        }
        let ctx = AnalyzeContext {
            existing_tags: vec![],
            existing_prompt: None,
            mode: AnalyzeMode::Full,
            language: self.language.clone(),
            json_schema: None,
        };
        let raw = self.call_api(&json!([{"role": "user", "content": prompts::build_trends_prompt(&prompts, &self.language)}]), 3000, true, &ctx).await?;
        Ok(parse_trends_result(&raw))
    }

    fn name(&self) -> String {
        let kind = if self.is_custom_compat() {
            "OpenAI Compatible"
        } else {
            "OpenAI Vision"
        };
        format!("{kind} ({})", self.model)
    }
}

fn encode_image_for_openai(image_path: &Path) -> Result<(String, String), EngineError> {
    let extension = image_path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    let reader = check_image_size_limits(image_path)?;
    if NATIVE_FORMATS.contains(&extension.as_str()) {
        let media_type = if extension == "png" {
            "image/png"
        } else {
            "image/jpeg"
        };
        return std::fs::read(image_path)
            .map(|bytes| (media_type.to_string(), STANDARD.encode(bytes)))
            .map_err(|error| EngineError::msg(format!("Failed to read image file: {error}")));
    }
    let image = reader
        .decode()
        .map_err(|error| EngineError::msg(format!("Failed to decode image: {error}")))?;
    let mut bytes = std::io::Cursor::new(Vec::new());
    image
        .write_to(&mut bytes, image::ImageFormat::Png)
        .map_err(|error| EngineError::msg(format!("Failed to encode image: {error}")))?;
    Ok(("image/png".to_string(), STANDARD.encode(bytes.into_inner())))
}

#[cfg(test)]
mod tests {
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };

    use super::*;
    use axum::{extract::Json, http::StatusCode, response::IntoResponse, routing::post, Router};

    fn test_context() -> AnalyzeContext {
        AnalyzeContext {
            existing_tags: vec![],
            existing_prompt: None,
            mode: AnalyzeMode::Full,
            language: "ja".into(),
            json_schema: None,
        }
    }

    #[tokio::test]
    async fn grammar_error_retries_without_schema_once() {
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            return;
        };
        let address = listener.local_addr().unwrap();
        let attempts = Arc::new(AtomicUsize::new(0));
        let app = Router::new().route(
            "/v1/chat/completions",
            post({
                let attempts = Arc::clone(&attempts);
                move |Json(payload): Json<serde_json::Value>| {
                    let attempts = Arc::clone(&attempts);
                    async move {
                        let first = attempts.fetch_add(1, Ordering::SeqCst) == 0;
                        if first {
                            assert!(payload.get("response_format").is_some());
                            (StatusCode::INTERNAL_SERVER_ERROR, "grammar stack failure")
                                .into_response()
                        } else {
                            assert!(payload.get("response_format").is_none());
                            (
                                StatusCode::OK,
                                r#"{"choices":[{"message":{"content":"{\"tags\":[\"cat\"]}"}}]}"#,
                            )
                                .into_response()
                        }
                    }
                }
            }),
        );
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let engine = OpenAiCompatEngine {
            base_url: Some(format!("http://{address}")),
            model: "gemma".into(),
            api_key: String::new(),
            language: "ja".into(),
        };
        assert!(engine
            .call_api(
                &json!([{"role": "user", "content": "x"}]),
                2000,
                true,
                &test_context()
            )
            .await
            .unwrap()
            .contains("cat"));
        assert_eq!(attempts.load(Ordering::SeqCst), 2);
        server.abort();
    }

    #[tokio::test]
    async fn auth_error_does_not_trigger_grammar_fallback() {
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            return;
        };
        let address = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/v1/chat/completions",
            post(|| async { (StatusCode::UNAUTHORIZED, "grammar unauthorized") }),
        );
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let engine = OpenAiCompatEngine {
            base_url: Some(format!("http://{address}")),
            model: "gpt-4o-mini".into(),
            api_key: "bad".into(),
            language: "ja".into(),
        };
        assert!(engine
            .call_api(&json!([]), 2000, true, &test_context())
            .await
            .unwrap_err()
            .to_string()
            .contains("invalid or expired"));
        server.abort();
    }

    #[test]
    fn strip_trailing_v1_normalizes_common_configurations() {
        assert_eq!(
            OpenAiCompatEngine::strip_trailing_v1("http://localhost:1234/v1"),
            "http://localhost:1234"
        );
        assert_eq!(
            OpenAiCompatEngine::strip_trailing_v1("http://localhost:1234/v1/"),
            "http://localhost:1234"
        );
        assert_eq!(
            OpenAiCompatEngine::strip_trailing_v1("http://localhost:1234"),
            "http://localhost:1234"
        );
        assert_eq!(
            OpenAiCompatEngine::strip_trailing_v1("https://api.openai.com/v1"),
            "https://api.openai.com"
        );
    }

    #[tokio::test]
    async fn call_api_works_when_base_url_already_includes_v1() {
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            return;
        };
        let address = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/v1/chat/completions",
            post(|| async {
                (
                    StatusCode::OK,
                    r#"{"choices":[{"message":{"content":"{\"tags\":[\"dog\"]}"}}]}"#,
                )
            }),
        );
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let engine = OpenAiCompatEngine {
            base_url: Some(format!("http://{address}/v1")),
            model: "local-model".into(),
            api_key: String::new(),
            language: "ja".into(),
        };
        assert!(engine
            .call_api(
                &json!([{"role": "user", "content": "x"}]),
                2000,
                true,
                &test_context()
            )
            .await
            .unwrap()
            .contains("dog"));
        server.abort();
    }

    #[test]
    fn name_distinguishes_cloud_and_compat() {
        let cloud = OpenAiCompatEngine {
            base_url: None,
            model: "gpt-4o-mini".into(),
            api_key: String::new(),
            language: "ja".into(),
        };
        let compat = OpenAiCompatEngine {
            base_url: Some("http://localhost:11434".into()),
            model: "gemma".into(),
            api_key: String::new(),
            language: "ja".into(),
        };
        assert_eq!(cloud.name(), "OpenAI Vision (gpt-4o-mini)");
        assert_eq!(compat.name(), "OpenAI Compatible (gemma)");
    }
}

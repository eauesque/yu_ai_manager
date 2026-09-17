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

const TIMEOUT: Duration = Duration::from_secs(60);
const API_BASE: &str = "https://api.anthropic.com";
const MAX_RESPONSE_BYTES: usize = 20 * 1024 * 1024;
/// Extensions Claude accepts as-is, each with the media type to send.
///
/// One table, not two. The extension list and the extension -> media-type match
/// used to be separate, kept in sync by hand, with an `unreachable!()` where
/// they could drift: adding one entry to the list without the other panicked in
/// the request path rather than failing to compile.
const NATIVE_FORMATS: [(&str, &str); 5] = [
    ("png", "image/png"),
    ("jpg", "image/jpeg"),
    ("jpeg", "image/jpeg"),
    ("webp", "image/webp"),
    ("gif", "image/gif"),
];

pub struct ClaudeEngine {
    pub api_key: String,
    pub model: String,
    pub language: String,
}

impl ClaudeEngine {
    async fn call_api(
        &self,
        messages: &serde_json::Value,
        max_tokens: u32,
        system: Option<&str>,
    ) -> Result<String, EngineError> {
        let client = build_pinned_client(API_BASE, false, TIMEOUT).await?;
        let mut payload =
            json!({"model": self.model, "max_tokens": max_tokens, "messages": messages});
        if let Some(system) = system {
            payload["system"] = json!(system);
        }
        let response = client
            .post(format!("{API_BASE}/v1/messages"))
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", "2023-06-01")
            .json(&payload)
            .send()
            .await
            .map_err(|error| EngineError::msg(format!("Cannot connect to Claude API: {error}")))?;
        let status = response.status().as_u16();
        let body = read_response_capped(response, MAX_RESPONSE_BYTES).await?;
        if status != 200 {
            if status == 401 {
                return Err(EngineError::msg("Anthropic API key is invalid or expired"));
            }
            if status == 404 {
                return Err(EngineError::msg(format!(
                    "Model not found: {}. Valid IDs: claude-sonnet-4-6, claude-opus-4-6, claude-haiku-4-5",
                    self.model
                )));
            }
            if status == 429 {
                return Err(EngineError::msg(
                    "Anthropic rate limit exceeded. Please wait and retry.",
                ));
            }
            return Err(EngineError::msg(format!(
                "Anthropic API error (HTTP {status})"
            )));
        }
        let response = serde_json::from_str::<serde_json::Value>(&body).map_err(|error| {
            EngineError::msg(format!("Failed to parse Claude response: {error}"))
        })?;
        Ok(response
            .get("content")
            .and_then(serde_json::Value::as_array)
            .map(|blocks| {
                blocks
                    .iter()
                    .filter(|block| {
                        block.get("type").and_then(serde_json::Value::as_str) == Some("text")
                    })
                    .filter_map(|block| block.get("text").and_then(serde_json::Value::as_str))
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default())
    }
}

#[async_trait]
impl AnalysisEngine for ClaudeEngine {
    async fn analyze_image(
        &self,
        image_path: &Path,
        ctx: &AnalyzeContext,
    ) -> Result<AnalysisResult, EngineError> {
        let (media_type, image_data) = encode_image_for_claude(image_path)?;
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
        let raw = self.call_api(&json!([{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
            {"type": "text", "text": prompt},
        ]}]), 2000, Some(&system)).await?;
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
        let raw = self.call_api(&json!([{"role": "user", "content": prompts::build_trends_prompt(&prompts, &self.language)}]), 3000, None).await?;
        Ok(parse_trends_result(&raw))
    }

    fn name(&self) -> String {
        format!("Claude Vision ({})", self.model)
    }
}

fn encode_image_for_claude(image_path: &Path) -> Result<(String, String), EngineError> {
    let extension = image_path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    let reader = check_image_size_limits(image_path)?;
    if let Some((_, media_type)) = NATIVE_FORMATS
        .iter()
        .find(|(candidate, _)| *candidate == extension)
    {
        return std::fs::read(image_path)
            .map(|bytes| ((*media_type).to_string(), STANDARD.encode(bytes)))
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
    use super::*;

    #[test]
    fn name_format() {
        let engine = ClaudeEngine {
            api_key: String::new(),
            model: "claude-sonnet-4-6".into(),
            language: "ja".into(),
        };
        assert_eq!(engine.name(), "Claude Vision (claude-sonnet-4-6)");
    }

    #[test]
    fn native_formats_include_webp_and_gif() {
        assert!(NATIVE_FORMATS.iter().any(|(ext, _)| *ext == "webp"));
        assert!(NATIVE_FORMATS.iter().any(|(ext, _)| *ext == "gif"));
    }

    /// The table is the only source of media types now; a wrong one ships a
    /// body Claude rejects, and nothing else in this file would catch it.
    #[test]
    fn every_native_format_carries_its_media_type() {
        for (ext, media_type) in NATIVE_FORMATS {
            assert!(
                media_type.starts_with("image/"),
                "{ext} maps to {media_type}"
            );
        }
        assert_eq!(
            NATIVE_FORMATS
                .iter()
                .find(|(ext, _)| *ext == "jpeg")
                .map(|(_, mt)| *mt),
            Some("image/jpeg")
        );
    }
}

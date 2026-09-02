pub mod claude;
pub mod http_client;
pub mod ollama;
pub mod openai_compat;
pub mod parse;
pub mod prompts;
pub mod result_parse;
pub mod zstd_write;

use std::path::Path;

use async_trait::async_trait;
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnalyzeMode {
    Full,
    Simple,
    Ocr,
}

impl AnalyzeMode {
    pub fn db_suffix(self) -> Option<&'static str> {
        match self {
            Self::Full => None,
            Self::Simple => Some(" [simple]"),
            Self::Ocr => Some(" [ocr]"),
        }
    }
}

pub struct AnalyzeContext {
    pub existing_tags: Vec<String>,
    pub existing_prompt: Option<String>,
    pub mode: AnalyzeMode,
    pub language: String,
    /// OCR passes a JSON schema here; ollama enforces it at generation time.
    /// `None` keeps the pre-existing behaviour byte-for-byte.
    pub json_schema: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct AnalysisResult {
    pub tags: Vec<String>,
    pub quality_score: f64,
    pub quality_notes: String,
    pub description: String,
    pub style: String,
    pub composition: String,
    pub mood: String,
    pub color_palette: Vec<String>,
    pub prompt_suggestion: String,
    #[serde(skip)]
    pub raw_response: String,
}

impl AnalysisResult {
    pub fn to_public_json(&self) -> serde_json::Value {
        serde_json::json!({
            "tags": self.tags,
            "quality_score": self.quality_score,
            "quality_notes": self.quality_notes,
            "description": self.description,
            "style": self.style,
            "composition": self.composition,
            "mood": self.mood,
            "color_palette": self.color_palette,
            "prompt_suggestion": self.prompt_suggestion,
        })
    }
}

#[derive(Debug, thiserror::Error)]
pub enum EngineError {
    #[error("{0}")]
    Message(String),
}

impl EngineError {
    pub fn msg(s: impl Into<String>) -> Self {
        Self::Message(s.into())
    }
}

#[async_trait]
pub trait AnalysisEngine: Send + Sync {
    async fn analyze_image(
        &self,
        image_path: &Path,
        ctx: &AnalyzeContext,
    ) -> Result<AnalysisResult, EngineError>;

    async fn analyze_trends(&self, prompts: &[String]) -> Result<serde_json::Value, EngineError>;

    fn name(&self) -> String;
}

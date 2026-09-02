use crate::models::{MetaResult, PngTextChunks};
use serde_json::Value;
use std::collections::HashMap;

pub fn parse_tensor_art(chunks: &PngTextChunks) -> Option<MetaResult> {
    let raw = chunks.entries.get("generation_data")?;
    if raw.is_empty() {
        return None;
    }
    let raw = raw.trim_end_matches('\0').trim();
    let data: Value = serde_json::from_str(raw).ok()?;
    let object = data.as_object()?;
    if !object.contains_key("prompt") {
        return None;
    }

    Some(MetaResult {
        positive: Some(
            object
                .get("prompt")
                .and_then(Value::as_str)
                .unwrap_or("")
                .into(),
        ),
        negative: Some(
            object
                .get("negativePrompt")
                .and_then(Value::as_str)
                .unwrap_or("")
                .into(),
        ),
        format: "tensor_art".into(),
        raw_meta: Some(raw.into()),
        params: HashMap::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunks(generation_data: &str) -> PngTextChunks {
        let mut chunks = PngTextChunks::default();
        chunks
            .entries
            .insert("generation_data".into(), generation_data.into());
        chunks
    }

    #[test]
    fn generation_data_prompt_detected() {
        let raw = "  {\"prompt\":\"a cat\",\"negativePrompt\":\"lowres\"}  \0\0";
        let result = parse_tensor_art(&chunks(raw)).unwrap();
        assert_eq!(result.positive.as_deref(), Some("a cat"));
        assert_eq!(result.negative.as_deref(), Some("lowres"));
        assert_eq!(result.format, "tensor_art");
        assert_eq!(
            result.raw_meta.as_deref(),
            Some(r#"{"prompt":"a cat","negativePrompt":"lowres"}"#)
        );
    }

    #[test]
    fn invalid_or_promptless_json_ignored() {
        assert!(parse_tensor_art(&chunks("not json")).is_none());
        assert!(parse_tensor_art(&chunks(r#"{"negativePrompt":"lowres"}"#)).is_none());
    }
}

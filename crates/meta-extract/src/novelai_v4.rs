use crate::models::{MetaResult, PngTextChunks};
use serde_json::Value;
use std::collections::HashMap;

pub fn parse_novelai_v4(chunks: &PngTextChunks) -> Option<MetaResult> {
    let raw = chunks.entries.get("Comment")?;
    let data: Value = serde_json::from_str(raw).ok()?;

    // Direct v4 format: Comment JSON has v4_prompt / v4_negative_prompt
    if let Some((pos, neg, params)) = try_direct_v4(&data) {
        return Some(MetaResult {
            positive: pos,
            negative: neg,
            format: "nai_v4".into(),
            raw_meta: Some(raw.clone()),
            params,
        });
    }

    // Double-wrapped format (WebP/EXIF): outer JSON has "Comment" key with inner JSON
    if let Some(inner_str) = data.get("Comment").and_then(|v| v.as_str()) {
        if let Ok(inner) = serde_json::from_str::<Value>(inner_str) {
            if let Some((pos, neg, params)) = try_direct_v4(&inner) {
                return Some(MetaResult {
                    positive: pos,
                    negative: neg,
                    format: "nai_v4".into(),
                    raw_meta: Some(raw.clone()),
                    params,
                });
            }
        }
    }

    None
}

/// Positive caption, negative caption, and the per-character caption map that
/// the NovelAI v4 payload carries. Named so the tuple does not trip
/// `clippy::type_complexity` at every function that returns it.
type V4Captions = (Option<String>, Option<String>, HashMap<String, String>);

fn try_direct_v4(data: &Value) -> Option<V4Captions> {
    if data.get("v4_prompt").is_none() && data.get("v4_negative_prompt").is_none() {
        return None;
    }
    let pos = extract_v4_caption(data.get("v4_prompt"));
    let neg = extract_v4_caption(data.get("v4_negative_prompt"));
    Some((pos, neg, extract_params(data)))
}

fn extract_v4_caption(v4_obj: Option<&Value>) -> Option<String> {
    v4_obj?
        .get("caption")?
        .get("base_caption")?
        .as_str()
        .map(|s| s.to_string())
}

fn extract_params(data: &Value) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for key in &["steps", "scale", "seed", "sampler", "noise_schedule"] {
        if let Some(val) = data.get(*key) {
            let s = match val {
                Value::String(s) => s.clone(),
                other => other.to_string(),
            };
            map.insert(key.to_string(), s);
        }
    }
    map
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunks(comment: &str) -> PngTextChunks {
        let mut c = PngTextChunks::default();
        c.entries.insert("Comment".into(), comment.into());
        c
    }

    #[test]
    fn direct_v4() {
        let j = r#"{"v4_prompt":{"caption":{"base_caption":"a cat"}},"v4_negative_prompt":{"caption":{"base_caption":"lowres"}},"steps":28}"#;
        let r = parse_novelai_v4(&chunks(j)).unwrap();
        assert_eq!(r.positive.as_deref(), Some("a cat"));
        assert_eq!(r.negative.as_deref(), Some("lowres"));
        assert_eq!(r.format, "nai_v4");
        assert_eq!(r.params.get("steps").map(|s| s.as_str()), Some("28"));
    }

    #[test]
    fn double_wrapped_v4() {
        let inner = r#"{"v4_prompt":{"caption":{"base_caption":"a dog"}},"v4_negative_prompt":{"caption":{"base_caption":"blurry"}}}"#;
        let outer = format!(r#"{{"Comment":{}}}"#, serde_json::to_string(inner).unwrap());
        let r = parse_novelai_v4(&chunks(&outer)).unwrap();
        assert_eq!(r.positive.as_deref(), Some("a dog"));
        assert_eq!(r.negative.as_deref(), Some("blurry"));
    }

    #[test]
    fn v3_format_rejected() {
        let j = r#"{"prompt":"a fox","uc":"bad"}"#;
        assert!(parse_novelai_v4(&chunks(j)).is_none());
    }
}

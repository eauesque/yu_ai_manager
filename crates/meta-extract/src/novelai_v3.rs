use crate::models::{MetaResult, PngTextChunks};
use serde_json::Value;
use std::collections::HashMap;

pub fn parse_novelai_v3(chunks: &PngTextChunks) -> Option<MetaResult> {
    let raw = chunks.entries.get("Comment")?;
    let data: Value = serde_json::from_str(raw).ok()?;

    // Must not be v4 format
    if data.get("v4_prompt").is_some() || data.get("v4_negative_prompt").is_some() {
        return None;
    }

    let positive = data.get("prompt").and_then(|v| v.as_str())?;
    let negative = data.get("uc").and_then(|v| v.as_str());

    Some(MetaResult {
        positive: Some(positive.to_string()),
        negative: negative.map(|s| s.to_string()),
        format: "nai_v3".into(),
        raw_meta: Some(raw.clone()),
        params: extract_params(&data),
    })
}

fn extract_params(data: &Value) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for key in &[
        "steps",
        "scale",
        "seed",
        "sampler",
        "noise_schedule",
        "strength",
        "cfg_rescale",
    ] {
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
    fn basic_v3() {
        let j = r#"{"prompt":"a fox","uc":"bad anatomy","steps":28,"scale":7.0,"seed":123}"#;
        let r = parse_novelai_v3(&chunks(j)).unwrap();
        assert_eq!(r.positive.as_deref(), Some("a fox"));
        assert_eq!(r.negative.as_deref(), Some("bad anatomy"));
        assert_eq!(r.format, "nai_v3");
        assert_eq!(r.params.get("steps").map(|s| s.as_str()), Some("28"));
    }

    #[test]
    fn v4_fields_reject() {
        let j = r#"{"v4_prompt":{},"prompt":"a fox","uc":"bad"}"#;
        assert!(parse_novelai_v3(&chunks(j)).is_none());
    }

    #[test]
    fn missing_prompt_reject() {
        let j = r#"{"uc":"bad anatomy"}"#;
        assert!(parse_novelai_v3(&chunks(j)).is_none());
    }
}

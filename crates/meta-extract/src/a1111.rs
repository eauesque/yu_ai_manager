use crate::models::{MetaResult, PngTextChunks};
use std::collections::HashMap;

pub fn parse_a1111(chunks: &PngTextChunks) -> Option<MetaResult> {
    let raw = chunks
        .entries
        .get("parameters")
        .or_else(|| chunks.entries.get("Parameters"))
        .or_else(|| chunks.entries.get("PARAMETERS"))?
        .clone();
    Some(parse_a1111_text(&raw))
}

pub fn parse_a1111_text(raw: &str) -> MetaResult {
    let text = raw.trim_start_matches('\u{feff}').replace("\r\n", "\n");
    let text = text
        .strip_prefix("Parameters:")
        .unwrap_or(&text)
        .trim_start()
        .to_string();

    // Normalize mid-line section markers to newline-prefixed form.
    let text = text.replace(". Negative prompt:", "\nNegative prompt:");
    let text = text.replace(". Steps:", "\nSteps:");

    let neg_marker = "\nNegative prompt:";
    let steps_marker = "\nSteps:";

    // Split off positive
    let (positive, rest) = if let Some(pos) = text.find(neg_marker) {
        (text[..pos].to_string(), text[pos + 1..].to_string())
    } else if let Some(pos) = text.find(steps_marker) {
        (text[..pos].to_string(), text[pos + 1..].to_string())
    } else {
        return MetaResult {
            positive: Some(text.trim().to_string()),
            format: "a1111".into(),
            raw_meta: Some(raw.to_string()),
            ..Default::default()
        };
    };

    // Split rest into negative / params
    let (negative_opt, params_str) = if let Some(after) = rest.strip_prefix("Negative prompt:") {
        if let Some(pos) = after.find("\nSteps:") {
            (
                Some(after[..pos].trim().to_string()),
                Some(after[pos + 1..].to_string()),
            )
        } else {
            (Some(after.trim().to_string()), None)
        }
    } else if rest.starts_with("Steps:") {
        (None, Some(rest.clone()))
    } else {
        (None, None)
    };

    let params = params_str
        .as_deref()
        .map(parse_params_section)
        .unwrap_or_default();

    MetaResult {
        positive: Some(positive.trim().to_string()),
        negative: negative_opt,
        format: "a1111".into(),
        raw_meta: Some(raw.to_string()),
        params,
    }
}

fn parse_params_section(s: &str) -> HashMap<String, String> {
    let mut map = HashMap::new();
    let line = s.lines().next().unwrap_or(s);
    for part in line.split(',') {
        let part = part.trim();
        if let Some(colon) = part.find(':') {
            let key = part[..colon].trim().to_string();
            let val = part[colon + 1..].trim().to_string();
            if !key.is_empty() {
                map.insert(key, val);
            }
        }
    }
    map
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunks(params: &str) -> PngTextChunks {
        let mut c = PngTextChunks::default();
        c.entries.insert("parameters".into(), params.into());
        c
    }

    #[test]
    fn basic_pos_neg_params() {
        let raw = "masterpiece, best quality\nNegative prompt: lowres, bad anatomy\nSteps: 20, Sampler: Euler a, CFG scale: 7";
        let r = parse_a1111(&chunks(raw)).unwrap();
        assert_eq!(r.positive.as_deref(), Some("masterpiece, best quality"));
        assert_eq!(r.negative.as_deref(), Some("lowres, bad anatomy"));
        assert_eq!(r.params.get("Steps").map(|s| s.as_str()), Some("20"));
        assert_eq!(r.format, "a1111");
    }

    #[test]
    fn no_negative() {
        let raw = "a cat\nSteps: 10, Sampler: DPM";
        let r = parse_a1111(&chunks(raw)).unwrap();
        assert_eq!(r.positive.as_deref(), Some("a cat"));
        assert!(r.negative.is_none());
    }

    #[test]
    fn no_steps() {
        let raw = "a dog";
        let r = parse_a1111(&chunks(raw)).unwrap();
        assert_eq!(r.positive.as_deref(), Some("a dog"));
        assert!(r.params.is_empty());
    }

    #[test]
    fn parameters_prefix_stripped() {
        let raw = "Parameters: a fox\nSteps: 5";
        let r = parse_a1111(&chunks(raw)).unwrap();
        assert_eq!(r.positive.as_deref(), Some("a fox"));
    }
}

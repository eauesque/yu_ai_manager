/// Strip a leading and trailing markdown code fence.
pub fn clean_markdown_json(raw: &str) -> String {
    let cleaned = raw.trim();
    if !cleaned.starts_with("```") {
        return cleaned.to_string();
    }

    let mut body = match cleaned.find('\n') {
        Some(index) => &cleaned[index + 1..],
        None => &cleaned[3.min(cleaned.len())..],
    };
    if let Some(stripped) = body.strip_suffix("```") {
        body = stripped;
    }
    body.to_string()
}

/// Return a JSON-parseable outermost object or array where possible.
pub fn best_effort_json(raw: &str) -> String {
    let cleaned = clean_markdown_json(raw);
    if serde_json::from_str::<serde_json::Value>(&cleaned).is_ok() {
        return cleaned;
    }

    for (open, close) in [('{', '}'), ('[', ']')] {
        if let (Some(start), Some(end)) = (cleaned.find(open), cleaned.rfind(close)) {
            if end > start {
                let candidate = &cleaned[start..=end];
                if serde_json::from_str::<serde_json::Value>(candidate).is_ok() {
                    return candidate.to_string();
                }
            }
        }
    }
    cleaned
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clean_plain_json_unchanged() {
        let raw = r#"{"tags": ["cat"]}"#;
        assert_eq!(clean_markdown_json(raw), raw);
    }

    #[test]
    fn clean_markdown_fences_with_lang() {
        let raw = "```json\n{\"tags\": [\"cat\"]}\n```";
        assert_eq!(clean_markdown_json(raw), "{\"tags\": [\"cat\"]}\n");
    }

    #[test]
    fn clean_markdown_fences_no_lang() {
        let raw = "```\n{\"key\": 1}\n```";
        assert_eq!(clean_markdown_json(raw), "{\"key\": 1}\n");
    }

    #[test]
    fn best_effort_plain_json_parses_directly() {
        let out = best_effort_json(r#"{"tags": ["cat"]}"#);
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&out).unwrap()["tags"][0],
            "cat"
        );
    }

    #[test]
    fn best_effort_extracts_object_from_surrounding_prose() {
        let out =
            best_effort_json("Sure:\n\n{\"tags\": [\"cat\"], \"description\": \"A cat\"}\n\nDone.");
        let value: serde_json::Value = serde_json::from_str(&out).unwrap();
        assert_eq!(value["tags"][0], "cat");
        assert_eq!(value["description"], "A cat");
    }

    #[test]
    fn best_effort_extracts_array_when_object_extraction_fails() {
        let out = best_effort_json("notes: [\"a\", \"b\"] end");
        let value: serde_json::Value = serde_json::from_str(&out).unwrap();
        assert!(value.is_array());
        assert_eq!(value[0], "a");
    }

    #[test]
    fn best_effort_returns_cleaned_input_when_unparseable() {
        let out = best_effort_json("not json at all");
        assert!(serde_json::from_str::<serde_json::Value>(&out).is_err());
        assert_eq!(out, "not json at all");
    }

    #[test]
    fn best_effort_takes_outermost_span_not_balanced() {
        let raw = "{\"a\": 1} garbage {\"b\": 2}";
        assert_eq!(best_effort_json(raw), raw);
    }
}

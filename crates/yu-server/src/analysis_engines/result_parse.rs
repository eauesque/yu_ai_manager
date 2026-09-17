use serde_json::{json, Value};

use super::{parse::best_effort_json, AnalysisResult};

pub fn parse_analysis_result(raw: &str) -> AnalysisResult {
    let mut result = AnalysisResult {
        raw_response: raw.to_string(),
        ..Default::default()
    };
    let Ok(data) = serde_json::from_str::<Value>(&best_effort_json(raw)) else {
        return failed_result(raw);
    };
    let Some(data) = data.as_object() else {
        return failed_result(raw);
    };
    let Some(quality_score) = data.get("quality_score").map_or(Some(0.0), Value::as_f64) else {
        return failed_result(raw);
    };
    result.tags = json_str_array(data, "tags");
    result.quality_score = quality_score;
    result.quality_notes = json_str(data, "quality_notes");
    result.description = json_str(data, "description");
    result.style = json_str(data, "style");
    result.composition = json_str(data, "composition");
    result.mood = json_str(data, "mood");
    result.color_palette = json_str_array(data, "color_palette");
    result.prompt_suggestion = json_str(data, "prompt_suggestion");
    result
}

pub fn parse_trends_result(raw: &str) -> Value {
    serde_json::from_str(&best_effort_json(raw)).unwrap_or_else(|_| json!({"raw": raw}))
}

fn failed_result(raw: &str) -> AnalysisResult {
    AnalysisResult {
        quality_notes: format!("解析失敗: {}", truncate_chars(raw, 200)),
        raw_response: raw.to_string(),
        ..Default::default()
    }
}

fn json_str(data: &serde_json::Map<String, Value>, key: &str) -> String {
    data.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn json_str_array(data: &serde_json::Map<String, Value>, key: &str) -> Vec<String> {
    data.get(key)
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn truncate_chars(value: &str, limit: usize) -> String {
    value.chars().take(limit).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discards_all_fields_when_quality_score_is_missing_or_invalid() {
        for raw in [r#"{"quality_score":"bad"}"#, "[]"] {
            let result = parse_analysis_result(raw);
            assert!(result.tags.is_empty());
            assert_eq!(result.quality_score, 0.0);
            assert!(result.quality_notes.starts_with("解析失敗: "));
            assert_eq!(result.raw_response, raw);
        }
        assert_eq!(parse_analysis_result(r#"{"tags":["cat"]}"#).tags, ["cat"]);
    }
}

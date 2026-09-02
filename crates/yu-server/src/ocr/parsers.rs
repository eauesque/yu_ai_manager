use regex::Regex;
use serde_json::Value;

use super::prompts::normalize_label;

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct OcrRegion {
    pub region_id: usize,
    pub bbox: Vec<i64>,
    pub text: String,
    pub confidence: f64,
    pub direction: String,
    pub label: String,
}

pub fn extract_json_value(raw: &str) -> Option<Value> {
    let fence = Regex::new(r"(?s)```(?:json)?\s*\n?(.*?)\n?```").expect("valid fence regex");
    if let Some(captures) = fence.captures(raw) {
        let content = captures.get(1).expect("capture exists").as_str();
        if let Ok(value) = serde_json::from_str(content) {
            return Some(value);
        }
        if let Some(value) = parse_jsonl(content) {
            return Some(value);
        }
    }

    let stripped = raw.trim();
    if let Ok(value) = serde_json::from_str(stripped) {
        return Some(value);
    }
    if let Some(value) = parse_jsonl(stripped) {
        return Some(value);
    }

    let array = Regex::new(r"(?s)\[.*\]").expect("valid array regex");
    if let Some(found) = array.find(stripped) {
        if let Ok(value) = serde_json::from_str(found.as_str()) {
            return Some(value);
        }
    }

    // `[^{}]*` matches newlines: re.DOTALL governs `.` only, and Python's
    // pattern (vlm_ocr_json.py:83) has no `.`. Writing `[^\n{}]` here would be
    // narrower than the source. Contract §5.8.
    let object = Regex::new(r"\{[^{}]*\}").expect("valid object regex");
    if let Some(found) = object.find(stripped) {
        if let Ok(value) = serde_json::from_str(found.as_str()) {
            return Some(value);
        }
    }
    None
}

fn parse_jsonl(text: &str) -> Option<Value> {
    let lines: Vec<_> = text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect();
    if lines.len() < 2 || !lines.iter().all(|line| line.starts_with('{')) {
        return None;
    }
    lines
        .into_iter()
        .map(serde_json::from_str)
        .collect::<Result<Vec<Value>, _>>()
        .ok()
        .map(Value::Array)
}

pub fn regions_from_value(value: &Value) -> Vec<Value> {
    match value {
        Value::Array(items) => items.clone(),
        Value::Object(object) => ["regions", "texts", "items", "results", "content"]
            .iter()
            .find_map(|key| {
                object
                    .get(*key)
                    .and_then(Value::as_array)
                    .filter(|items| !items.is_empty())
                    .cloned()
            })
            .unwrap_or_default(),
        _ => Vec::new(),
    }
}

fn regions_from_array(items: &[Value]) -> Vec<OcrRegion> {
    items
        .iter()
        .enumerate()
        .filter_map(|(index, item)| {
            let object = item.as_object()?;
            let text = object
                .get("text")
                .and_then(Value::as_str)
                .filter(|text| !text.is_empty())
                .or_else(|| {
                    object
                        .get("name")
                        .and_then(Value::as_str)
                        .filter(|text| !text.is_empty())
                })?
                .trim();
            if text.is_empty() {
                return None;
            }
            let raw_type = ["type", "label", "category"]
                .iter()
                .find_map(|key| object.get(*key).and_then(Value::as_str))
                .unwrap_or("");
            let confidence = object
                .get("confidence")
                .and_then(Value::as_f64)
                .or_else(|| {
                    object
                        .get("confidence")
                        .and_then(Value::as_str)
                        .and_then(|value| value.parse().ok())
                })
                .unwrap_or(0.0)
                .clamp(0.0, 1.0);
            let bbox = object
                .get("bbox")
                .and_then(Value::as_array)
                .map(|bbox| bbox.iter().filter_map(Value::as_i64).collect())
                .unwrap_or_default();
            Some(OcrRegion {
                region_id: index + 1,
                bbox,
                text: text.to_owned(),
                confidence,
                direction: object
                    .get("direction")
                    .and_then(Value::as_str)
                    .unwrap_or("vertical")
                    .to_owned(),
                label: normalize_label(raw_type).to_owned(),
            })
        })
        .collect()
}

pub fn parse_manga_any_format(raw: &str) -> Vec<OcrRegion> {
    if let Some(Value::Array(items)) = extract_json_value(raw) {
        let regions = regions_from_array(&items);
        if !regions.is_empty() {
            return regions;
        }
    }
    if let Some(Value::Object(object)) = extract_json_value(raw) {
        let regions = regions_from_array(&regions_from_value(&Value::Object(object)));
        if !regions.is_empty() {
            return regions;
        }
    }
    let regions = parse_manga_from_text(raw);
    if !regions.is_empty() {
        return regions;
    }
    let text = fallback_text(raw);
    if text.is_empty() {
        Vec::new()
    } else {
        vec![OcrRegion {
            region_id: 1,
            bbox: Vec::new(),
            text,
            confidence: 0.0,
            direction: "vertical".to_owned(),
            label: "other".to_owned(),
        }]
    }
}

fn parse_manga_from_text(raw: &str) -> Vec<OcrRegion> {
    let pattern = Regex::new(r#"\*\*([^*]+)\*\*\s*:?\s*[「"']*([^「」"'\n*]+)[」"']*"#)
        .expect("valid manga markdown regex");
    pattern
        .captures_iter(raw)
        .enumerate()
        .filter_map(|(index, captures)| {
            let text = captures.get(2)?.as_str().trim();
            let label = captures.get(1)?.as_str().trim();
            (!text.is_empty()).then(|| OcrRegion {
                region_id: index + 1,
                bbox: Vec::new(),
                text: text.to_owned(),
                confidence: 0.0,
                direction: "vertical".to_owned(),
                label: normalize_label(label).to_owned(),
            })
        })
        .collect()
}

pub fn fallback_text(raw: &str) -> String {
    let fence = Regex::new(r"(?s)```(?:json)?\s*\n?.*?\n?```").expect("valid fence regex");
    let text = fence.replace_all(raw, "").trim().to_owned();
    if text.is_empty() {
        raw.trim().to_owned()
    } else {
        text
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct OcrResult {
    pub full_text: String,
    pub language: String,
    pub regions: Vec<OcrRegion>,
    pub structured: Option<Value>,
}

pub fn parse_response(raw: &str, task: &str, language: &str) -> OcrResult {
    if task == "ocr_document" {
        return parse_document(
            extract_json_value(raw).unwrap_or(Value::Null),
            raw,
            language,
        );
    }
    if task == "ocr_manga" {
        return parse_manga(raw, language);
    }
    parse_general(
        extract_json_value(raw).unwrap_or(Value::Null),
        raw,
        language,
    )
}

fn parse_general(data: Value, raw: &str, language: &str) -> OcrResult {
    let object = data.as_object();
    let regions: Vec<OcrRegion> = object
        .and_then(|object| object.get("regions"))
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .enumerate()
                .filter_map(|(index, item)| {
                    let item = item.as_object()?;
                    Some(OcrRegion {
                        region_id: index + 1,
                        bbox: item
                            .get("bbox")
                            .and_then(Value::as_array)
                            .map(|bbox| bbox.iter().filter_map(Value::as_i64).collect())
                            .unwrap_or_default(),
                        text: item
                            .get("text")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_owned(),
                        confidence: item
                            .get("confidence")
                            .and_then(Value::as_f64)
                            .unwrap_or(0.0),
                        direction: item
                            .get("direction")
                            .and_then(Value::as_str)
                            .unwrap_or("horizontal")
                            .to_owned(),
                        label: normalize_label(
                            item.get("label").and_then(Value::as_str).unwrap_or(""),
                        )
                        .to_owned(),
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    let full_text = object
        .and_then(|object| object.get("full_text"))
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
        .map(str::to_owned)
        .or_else(|| {
            (!regions.is_empty()).then(|| {
                regions
                    .iter()
                    .filter(|r| !r.text.is_empty())
                    .map(|r| r.text.as_str())
                    .collect::<Vec<_>>()
                    .join("\n")
            })
        })
        .unwrap_or_else(|| fallback_text(raw));
    let resolved = object
        .and_then(|object| object.get("language_detected"))
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .or_else(|| {
            object
                .and_then(|object| object.get("language"))
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
        })
        .unwrap_or(language);
    OcrResult {
        full_text,
        language: if resolved == "auto" {
            String::new()
        } else {
            resolved.to_owned()
        },
        regions,
        structured: None,
    }
}

fn parse_document(data: Value, raw: &str, language: &str) -> OcrResult {
    let object = data.as_object();
    let headings = object
        .and_then(|object| object.get("headings"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let body_text = object
        .and_then(|object| object.get("body_text"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let mut regions = Vec::new();
    for heading in &headings {
        if let Some(text) = heading.as_str() {
            regions.push(OcrRegion {
                region_id: regions.len() + 1,
                bbox: vec![],
                text: text.to_owned(),
                confidence: 0.0,
                direction: "horizontal".to_owned(),
                label: "heading".to_owned(),
            });
        }
    }
    if !body_text.is_empty() {
        regions.push(OcrRegion {
            region_id: regions.len() + 1,
            bbox: vec![],
            text: body_text.to_owned(),
            confidence: 0.0,
            direction: "horizontal".to_owned(),
            label: "body".to_owned(),
        });
    }
    let full_text = object
        .and_then(|object| object.get("full_text"))
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
        .unwrap_or(body_text);
    let resolved = object
        .and_then(|object| object.get("language_detected"))
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .unwrap_or(language);
    OcrResult {
        full_text: if full_text.is_empty() {
            fallback_text(raw)
        } else {
            full_text.to_owned()
        },
        language: if resolved == "auto" {
            String::new()
        } else {
            resolved.to_owned()
        },
        regions,
        structured: Some(serde_json::json!({
            "headings": headings,
            "tables": object.and_then(|object| object.get("tables")).cloned().unwrap_or_else(|| Value::Array(vec![])),
            "page_layout": object.and_then(|object| object.get("page_layout")).cloned().unwrap_or_else(|| Value::String(String::new())),
        })),
    }
}

fn parse_manga(raw: &str, language: &str) -> OcrResult {
    let before_dedup = parse_manga_any_format(raw);
    let full_text = before_dedup
        .iter()
        .filter(|region| !region.text.is_empty())
        .map(|region| region.text.as_str())
        .collect::<Vec<_>>()
        .join("\n");
    let mut seen = std::collections::HashSet::new();
    let regions = before_dedup
        .into_iter()
        .filter(|region| {
            !region.text.trim().is_empty() && seen.insert(region.text.trim().to_owned())
        })
        .enumerate()
        .map(|(index, mut region)| {
            region.region_id = index + 1;
            region
        })
        .collect();
    OcrResult {
        full_text: if full_text.is_empty() {
            fallback_text(raw)
        } else {
            full_text
        },
        language: if language == "auto" {
            "ja".to_owned()
        } else {
            language.to_owned()
        },
        regions,
        structured: None,
    }
}

pub fn manga_parse_quality(result: &OcrResult) -> i64 {
    if result.regions.is_empty() {
        return 0;
    }
    result
        .regions
        .iter()
        .map(|region| {
            10 + i64::from(!region.label.is_empty() && region.label != "other") * 3
                + i64::from(region.bbox.len() >= 4) * 5
                + i64::from(!region.text.trim().starts_with('{')) * 2
        })
        .sum()
}

pub fn should_retry_manga(result: &OcrResult) -> bool {
    result.regions.is_empty()
        || (result.regions.len() == 1 && result.regions[0].label == "other")
        || result
            .regions
            .iter()
            .all(|region| region.text.trim().starts_with('{'))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn general_defaults() {
        let r = parse_response(r#"{"regions":[{"text":"a"}]}"#, "ocr", "auto");
        assert_eq!(r.language, "");
        assert_eq!(r.regions[0].direction, "horizontal");
        assert_eq!(r.regions[0].label, "speech_bubble");
    }

    #[test]
    fn document_defaults_differ_from_general() {
        let r = parse_response(
            r#"{"headings":[],"tables":[],"page_layout":"","full_text":"d"}"#,
            "ocr_document",
            "auto",
        );
        assert_eq!(r.language, "");
        assert_eq!(r.full_text, "d");
        assert!(r.structured.is_some());
    }

    #[test]
    fn manga_defaults_differ_again() {
        let r = parse_response(r#"{"items":[{"text":"m"}]}"#, "ocr_manga", "auto");
        assert_eq!(r.language, "ja");
        assert_eq!(r.regions[0].direction, "vertical");
    }

    #[test]
    fn manga_full_text_is_built_before_dedup() {
        let r = parse_response(
            r#"{"items":[{"text":"x"},{"text":"x"}]}"#,
            "ocr_manga",
            "auto",
        );
        assert_eq!(r.regions.len(), 1);
        assert_eq!(r.full_text.matches('x').count(), 2);
    }

    #[test]
    fn language_resolution_differs_per_parser() {
        let payload = r#"{"full_text":"x","language":"en"}"#;
        assert_eq!(parse_response(payload, "ocr", "auto").language, "en");
        assert_eq!(parse_response(payload, "ocr_document", "auto").language, "");
        assert_eq!(parse_response(payload, "ocr_document", "ja").language, "ja");
    }

    #[test]
    fn language_detected_wins_for_both_parsers_that_read_it() {
        let payload = r#"{"full_text":"x","language":"en","language_detected":"zh"}"#;
        assert_eq!(parse_response(payload, "ocr", "auto").language, "zh");
        assert_eq!(
            parse_response(payload, "ocr_document", "auto").language,
            "zh"
        );
    }

    #[test]
    fn document_under_the_enforced_schema_yields_zero_regions() {
        let r = parse_response(
            r#"{"full_text":"page text","language":"ja"}"#,
            "ocr_document",
            "auto",
        );
        assert!(r.regions.is_empty());
        assert_eq!(r.full_text, "page text");
    }

    #[test]
    fn document_yields_regions_when_the_schema_is_not_enforced() {
        let r = parse_response(
            r#"{"headings":["H1"],"body_text":"b","full_text":"f"}"#,
            "ocr_document",
            "auto",
        );
        assert_eq!(r.regions.len(), 2);
        assert_eq!(r.regions[0].label, "heading");
        assert_eq!(r.regions[1].label, "body");
    }

    #[test]
    fn document_labels_skip_normalisation() {
        let r = parse_response(
            r#"{"headings":["H"],"body_text":"b"}"#,
            "ocr_document",
            "auto",
        );
        assert!(r
            .regions
            .iter()
            .all(|x| x.label == "heading" || x.label == "body"));
    }

    #[test]
    fn document_structured_is_non_null_even_when_empty() {
        let st = parse_response(r#"{"full_text":"x"}"#, "ocr_document", "auto")
            .structured
            .expect("must be Some");
        assert!(st.get("headings").is_some());
        assert!(st.get("tables").is_some());
        assert!(st.get("page_layout").is_some());
    }

    fn region(text: &str, label: &str, bbox_len: usize) -> OcrRegion {
        OcrRegion {
            region_id: 0,
            bbox: vec![0; bbox_len],
            text: text.into(),
            confidence: 0.0,
            direction: "vertical".into(),
            label: label.into(),
        }
    }

    fn result(regions: Vec<OcrRegion>) -> OcrResult {
        OcrResult {
            full_text: String::new(),
            language: "ja".into(),
            regions,
            structured: None,
        }
    }

    #[test]
    fn retry_condition_1_no_regions() {
        assert!(should_retry_manga(&result(vec![])));
    }

    #[test]
    fn retry_condition_2_is_exactly_one_region_labelled_other() {
        assert!(should_retry_manga(&result(vec![region("a", "other", 4)])));
        assert!(!should_retry_manga(&result(vec![region(
            "a",
            "speech_bubble",
            4,
        )])));
        assert!(!should_retry_manga(&result(vec![
            region("a", "other", 4),
            region("b", "other", 4)
        ])));
    }

    #[test]
    fn retry_condition_3_needs_all_regions_to_be_raw_json() {
        assert!(should_retry_manga(&result(vec![
            region("{a}", "speech_bubble", 4),
            region("{b}", "speech_bubble", 4)
        ])));
        assert!(!should_retry_manga(&result(vec![
            region("{a}", "speech_bubble", 4),
            region("clean", "speech_bubble", 4)
        ])));
    }

    #[test]
    fn the_last_resort_parse_trips_retry_condition_2() {
        let regions = parse_manga_any_format("unstructured prose");
        assert!(should_retry_manga(&result(regions)));
    }

    #[test]
    fn quality_is_zero_for_no_regions_not_a_sum_of_nothing() {
        assert_eq!(manga_parse_quality(&result(vec![])), 0);
    }

    #[test]
    fn quality_components_are_each_worth_their_python_weight() {
        assert_eq!(
            manga_parse_quality(&result(vec![region("clean", "speech_bubble", 4)])),
            20
        );
        assert_eq!(
            manga_parse_quality(&result(vec![region("clean", "other", 4)])),
            17
        );
        assert_eq!(
            manga_parse_quality(&result(vec![region("clean", "speech_bubble", 3)])),
            15
        );
        assert_eq!(
            manga_parse_quality(&result(vec![region("{x}", "speech_bubble", 4)])),
            18
        );
    }

    #[test]
    fn stage1_plain_json() {
        let v = extract_json_value(r#"{"full_text":"a"}"#).expect("plain json");
        assert_eq!(v["full_text"], "a");
    }

    #[test]
    fn stage2_markdown_fence() {
        // Not parseable as plain JSON — only the fence-stripping stage recovers it.
        let raw = "here you go:\n```json\n{\"full_text\":\"b\"}\n```\n";
        assert!(
            serde_json::from_str::<serde_json::Value>(raw).is_err(),
            "must not parse plainly"
        );
        let v = extract_json_value(raw).expect("fenced json");
        assert_eq!(v["full_text"], "b");
    }

    #[test]
    fn stage3_object_scan_does_cross_newlines() {
        // Measured, not assumed (contract §5.8): Python's object regex is
        // `\{[^{}]*\}` with no flags. re.DOTALL governs `.` only, and a
        // negated character class matches newlines either way. Narrowing this
        // to `[^\n{}]` would drop a bare pretty-printed object surrounded by
        // prose — and for manga that falls through to the last-resort parse,
        // which triggers a second billed VLM call.
        let raw = "noise {\"a\":\n1} more";
        let value = extract_json_value(raw).expect("the object scan must span newlines");
        assert_eq!(value["a"], 1);
    }

    #[test]
    fn stage3_object_scan_still_refuses_nested_braces() {
        // `[^{}]` excludes braces, so a nested object is not matched here.
        // That half of the asymmetry is real and must be kept.
        let raw = "noise {\"a\": {\"b\": 1}} more";
        let value = extract_json_value(raw);
        assert!(
            value.is_none() || value.unwrap().get("a").is_none_or(|a| !a.is_object()),
            "the single-object scan must not swallow a nested object"
        );
    }

    #[test]
    fn stage4_jsonl_turns_object_lines_into_an_array() {
        // Assert the shape, not just is_some(). The earlier version checked
        // only that one line and two lines each produced *something*, which
        // holds whether or not the `>= 2` guard exists — it pinned nothing.
        let two = "{\"text\":\"x\"}\n{\"text\":\"y\"}";
        let value = extract_json_value(two).expect("two object lines are JSONL");
        let items = value.as_array().expect("JSONL yields an array");
        assert_eq!(items.len(), 2);
        assert_eq!(items[0]["text"], "x");
        assert_eq!(items[1]["text"], "y");
    }

    #[test]
    fn a_single_object_line_stays_an_object() {
        // Not an array of one. Plain parsing runs before JSONL, so this holds
        // regardless of the `>= 2` guard — which is therefore not observable
        // from the outside and cannot be pinned by any test here. The guard is
        // kept because the source has it, not because a test demands it.
        let value = extract_json_value("{\"text\":\"x\"}").expect("parses");
        assert!(
            value.is_object(),
            "a lone object must not be wrapped in an array"
        );
    }

    #[test]
    fn manga_stage3_recovers_markdown_when_no_json_parses() {
        // parse_manga_from_text. Dropping it makes a Markdown answer yield zero
        // regions, which trips retry condition 1 — the retry then costs a second
        // call and returns Markdown again. Two calls, nothing gained.
        let raw = "**Speech bubble**: \"hello\"\n**SFX**: bang";
        assert!(extract_json_value(raw).is_none(), "must not parse as JSON");
        let regions = parse_manga_any_format(raw);
        assert_eq!(regions.len(), 2, "markdown must yield regions");
        assert_eq!(regions[0].text, "hello");
    }

    #[test]
    fn manga_stage4_wraps_the_whole_response_as_one_other_region() {
        // This stage is what *triggers* the retry: exactly one region labelled
        // "other" is retry condition 2. Drop it and the retry never fires.
        let raw = "just some prose with no structure at all";
        let regions = parse_manga_any_format(raw);
        assert_eq!(regions.len(), 1);
        assert_eq!(regions[0].label, "other");
        assert_eq!(regions[0].direction, "vertical");
        assert!(regions[0].text.contains("prose"));
    }

    #[test]
    fn stage5_alias_items_is_the_manga_main_path() {
        // manga's schema asks for `items`, so this alias is load-bearing.
        let v = serde_json::json!({"items": [{"text": "hi"}]});
        let regions = regions_from_value(&v);
        assert_eq!(regions.len(), 1);
        assert_eq!(regions[0]["text"], "hi");
    }

    #[test]
    fn stage5_alias_order_regions_wins_over_items() {
        let v = serde_json::json!({"regions": [{"text": "r"}], "items": [{"text": "i"}]});
        let regions = regions_from_value(&v);
        assert_eq!(regions[0]["text"], "r", "regions has priority over items");
    }
}

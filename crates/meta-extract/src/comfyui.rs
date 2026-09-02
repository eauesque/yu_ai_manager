use crate::models::{MetaResult, PngTextChunks};
use serde_json::Value;
use std::collections::HashMap;

pub fn parse_comfyui(chunks: &PngTextChunks) -> Option<MetaResult> {
    let (_, raw_json, parsed) = extract_comfyui_json(chunks).ok()??;
    let (positives, negatives) = find_clip_texts(&parsed);

    Some(MetaResult {
        positive: if positives.is_empty() {
            None
        } else {
            Some(positives.join(", "))
        },
        negative: if negatives.is_empty() {
            None
        } else {
            Some(negatives.join(", "))
        },
        format: "comfy".into(),
        raw_meta: Some(raw_json),
        params: HashMap::new(),
    })
}

pub fn extract_comfyui_workflow(
    chunks: &PngTextChunks,
) -> Result<Option<(&'static str, Value)>, &'static str> {
    Ok(extract_comfyui_json(chunks)?.map(|(format, _, workflow)| (format, workflow)))
}

fn extract_comfyui_json(
    chunks: &PngTextChunks,
) -> Result<Option<(&'static str, String, Value)>, &'static str> {
    for (key, format) in [
        ("prompt", "api"),
        ("workflow", "editor"),
        ("exif:UserComment", "api"),
    ] {
        if let Some(raw) = chunks.entries.get(key) {
            if let Ok(obj) = serde_json::from_str::<Value>(raw) {
                if is_comfyui_dict(&obj) {
                    return Ok(Some((format, raw.clone(), obj)));
                }
            }
        }
        if chunks
            .compressed_itxt_keywords
            .iter()
            .any(|compressed| compressed == key)
        {
            return Err("Compressed iTXt workflow metadata is not supported");
        }
    }
    Ok(None)
}

fn is_comfyui_dict(v: &Value) -> bool {
    if let Value::Object(map) = v {
        if map.is_empty() {
            return false;
        }
        // All top-level keys are numeric strings → id-keyed workflow dict
        if map.keys().all(|k| k.parse::<u64>().is_ok()) {
            return true;
        }
        // Any value has "class_type" → workflow node dict
        if map.values().any(|v| v.get("class_type").is_some()) {
            return true;
        }
        // Has "nodes" array
        if map.contains_key("nodes") {
            return true;
        }
    }
    false
}

fn find_clip_texts(obj: &Value) -> (Vec<String>, Vec<String>) {
    let nodes_by_id: HashMap<String, &Value> = if let Value::Object(map) = obj {
        if map.keys().all(|k| k.parse::<u64>().is_ok()) {
            map.iter().map(|(k, v)| (k.clone(), v)).collect()
        } else if let Some(Value::Array(nodes)) = map.get("nodes") {
            nodes
                .iter()
                .filter_map(|n| {
                    n.get("id")
                        .and_then(|id| id.as_u64())
                        .map(|id| (id.to_string(), n))
                })
                .collect()
        } else {
            return (vec![], vec![]);
        }
    } else {
        return (vec![], vec![]);
    };

    let mut positives = Vec::new();
    let mut negatives = Vec::new();

    // Find KSampler* nodes, trace positive/negative inputs
    for node in nodes_by_id.values() {
        let class = node
            .get("class_type")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if !class.starts_with("KSampler") {
            continue;
        }
        let inputs = match node.get("inputs") {
            Some(Value::Object(m)) => m,
            _ => continue,
        };
        for (slot_name, target) in [("positive", &mut positives), ("negative", &mut negatives)] {
            if let Some(link) = inputs.get(slot_name).and_then(|v| v.as_array()) {
                let source_id = match link.first() {
                    Some(Value::String(s)) => Some(s.clone()),
                    Some(Value::Number(n)) => n.as_u64().map(|n| n.to_string()),
                    _ => None,
                };
                if let Some(sid) = source_id {
                    if let Some(src) = nodes_by_id.get(&sid) {
                        if let Some(text) = extract_clip_text(src) {
                            target.push(text);
                        }
                    }
                }
            }
        }
    }

    // Fallback: classify all CLIPTextEncode nodes by title
    if positives.is_empty() && negatives.is_empty() {
        for node in nodes_by_id.values() {
            if let Some(text) = extract_clip_text(node) {
                let title = node
                    .get("_meta")
                    .and_then(|m| m.get("title"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                if title.to_lowercase().contains("neg") {
                    negatives.push(text);
                } else {
                    positives.push(text);
                }
            }
        }
    }

    (positives, negatives)
}

fn extract_clip_text(node: &Value) -> Option<String> {
    let class = node
        .get("class_type")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if !class.contains("CLIPTextEncode") {
        return None;
    }
    let inputs = node.get("inputs")?;
    // Standard format
    if let Some(s) = inputs.get("text").and_then(|v| v.as_str()) {
        return Some(s.to_string());
    }
    // Flux format (clip_l / t5xxl)
    if let Some(s) = inputs.get("clip_l").and_then(|v| v.as_str()) {
        return Some(s.to_string());
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunks_with(key: &str, val: &str) -> PngTextChunks {
        let mut c = PngTextChunks::default();
        c.entries.insert(key.into(), val.into());
        c
    }

    #[test]
    fn numeric_key_workflow_detected() {
        let json = r#"{"1":{"class_type":"KSampler","inputs":{"positive":["2",0],"negative":["3",0]}},"2":{"class_type":"CLIPTextEncode","inputs":{"text":"a cat"}},"3":{"class_type":"CLIPTextEncode","inputs":{"text":"lowres"}}}"#;
        let c = chunks_with("prompt", json);
        let r = parse_comfyui(&c).unwrap();
        assert_eq!(r.positive.as_deref(), Some("a cat"));
        assert_eq!(r.negative.as_deref(), Some("lowres"));
        assert_eq!(r.format, "comfy");
    }

    #[test]
    fn non_comfyui_json_ignored() {
        let json = r#"{"prompt":"hello","uc":"bad"}"#;
        let c = chunks_with("prompt", json);
        assert!(parse_comfyui(&c).is_none());
    }
}

//! The `sections` the four builtin format extensions contribute to a file's
//! detail view: LoRA / Embedding tables, ComfyUI's multi-prompt list and
//! workflow JSON, and NovelAI v4's character and vibe-transfer blocks.
//!
//! Ports `extensions/builtin_{a1111,comfyui,novelai_v3,novelai_v4}/*_sections.py`.
//! Those are Python `on_build_sections` hooks, which the Rust server cannot
//! run; but their bodies are thin dispatchers over core parsers that already
//! exist here, so the sections are produced directly rather than through a
//! hook mechanism nothing else would use.
//!
//! Section titles and `display_type` values are what the UI renders, so they
//! are copied verbatim.

use serde_json::{json, Value};

/// meta_source values each format claims, from the extensions' `__init__.py`.
const A1111_SOURCES: &[&str] = &[
    "a1111_png",
    "a1111_webp",
    "a1111_jpg",
    "a1111_webm",
    "a1111_jxl",
    "a1111_avif",
    "a1111_heif",
];
const COMFY_SOURCES: &[&str] = &["comfy_png", "comfy_webp", "comfy_webm", "comfy_flac"];
const NAI_V3_SOURCES: &[&str] = &["novelai_png", "novelai_webp", "nai_webp"];
const NAI_V4_SOURCES: &[&str] = &["novelai_v4_png", "novelai_v4_webp", "novelai_v4"];

fn section(title: &str, display_type: &str, content: Value, copyable: bool) -> Value {
    json!({
        "title": title,
        "display_type": display_type,
        "content": content,
        "copyable": copyable,
    })
}

/// LoRA and Embedding tables, shared by A1111, ComfyUI and NovelAI v3.
fn prompt_token_sections(positive: &str) -> Vec<Value> {
    let mut out = Vec::new();
    let loras = meta_extract::extract_loras(positive);
    if !loras.is_empty() {
        out.push(section("LoRA", "table", Value::Array(loras), false));
    }
    let embeddings = meta_extract::extract_embeddings(positive);
    if !embeddings.is_empty() {
        out.push(section(
            "Embedding",
            "table",
            Value::Array(embeddings),
            false,
        ));
    }
    out
}

/// Sections for one file, or an empty vec when the format contributes none.
///
/// `positive` and `novelai_v4` come from `resolve_detail_fields`, the same
/// `parsed_fields` Python hands the hooks.
pub fn build_format_sections(
    meta_source: &str,
    positive: Option<&str>,
    raw_meta_json: Option<&str>,
    novelai_v4: Option<&Value>,
) -> Vec<Value> {
    let positive = positive.filter(|p| !p.is_empty());

    if A1111_SOURCES.contains(&meta_source) || NAI_V3_SOURCES.contains(&meta_source) {
        // NAI v3 rarely carries <lora:>, but Python checks anyway and so do we.
        return positive.map(prompt_token_sections).unwrap_or_default();
    }

    if COMFY_SOURCES.contains(&meta_source) {
        let mut out = positive.map(prompt_token_sections).unwrap_or_default();
        let Some(raw) = raw_meta_json else {
            return out;
        };
        let Ok(obj) = serde_json::from_str::<Value>(raw) else {
            return out;
        };
        if !obj.is_object() {
            return out;
        }
        // The parsed fields keep only the first positive; a workflow with
        // several CLIPTextEncode nodes lists all of them here.
        let (positives, _) = meta_extract::comfyui::find_clip_texts(&obj);
        if positives.len() > 1 {
            let items: Vec<Value> = positives
                .iter()
                .enumerate()
                .map(|(i, t)| json!({"index": i, "text": t}))
                .collect();
            out.push(section(
                "All Positive Prompts",
                "list",
                Value::Array(items),
                true,
            ));
        }
        out.push(section("Workflow JSON", "json", obj, true));
        return out;
    }

    if NAI_V4_SOURCES.contains(&meta_source) {
        let Some(nai) = novelai_v4 else {
            return vec![];
        };
        let mut out = Vec::new();
        // `use_coords` / `negative_use_coords` / `use_order` are deliberately not
        // rendered as sections. They are not facts a reader wants as text; they
        // decide how the character-position overlay draws (grid vs free
        // coordinates vs order-only), and that renderer reads them straight off
        // the payload. Mirrors extensions/builtin_novelai_v4/novelai_v4_sections.py.
        if let Some(Value::Array(chars)) = nai.get("character_prompts") {
            if !chars.is_empty() {
                out.push(section(
                    "V4 Characters (Positive)",
                    "list",
                    Value::Array(chars.clone()),
                    true,
                ));
            }
        }
        if let Some(Value::Array(negs)) = nai.get("negative_characters") {
            if !negs.is_empty() {
                let items: Vec<Value> = negs.iter().map(|n| json!({"prompt": n})).collect();
                out.push(section(
                    "V4 Characters (Negative)",
                    "list",
                    Value::Array(items),
                    true,
                ));
            }
        }
        if let Some(Value::Array(vibe)) = nai.get("vibe_transfer") {
            if !vibe.is_empty() {
                let items: Vec<Value> = vibe
                    .iter()
                    .enumerate()
                    .map(|(i, v)| {
                        // Python falls back to the string "?" when a reference
                        // image carries no extraction strength.
                        let strength = v
                            .get("information_extracted")
                            .cloned()
                            .unwrap_or_else(|| json!("?"));
                        json!({"index": i, "strength": strength})
                    })
                    .collect();
                // Python omits `copyable` here, which defaults to false.
                out.push(section(
                    "Reference Images",
                    "table",
                    Value::Array(items),
                    false,
                ));
            }
        }
        return out;
    }

    vec![]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn titles(sections: &[Value]) -> Vec<&str> {
        sections
            .iter()
            .map(|s| s["title"].as_str().unwrap())
            .collect()
    }

    #[test]
    fn a1111_yields_lora_and_embedding_tables() {
        let sections = build_format_sections(
            "a1111_png",
            Some("1girl <lora:style:0.7> <embedding:emb>"),
            None,
            None,
        );
        assert_eq!(titles(&sections), vec!["LoRA", "Embedding"]);
        assert_eq!(sections[0]["content"][0]["name"], json!("style"));
        assert_eq!(sections[0]["display_type"], json!("table"));
        assert_eq!(sections[0]["copyable"], json!(false));
    }

    #[test]
    fn a_prompt_without_special_tokens_yields_nothing() {
        assert!(build_format_sections("a1111_png", Some("1girl, solo"), None, None).is_empty());
        assert!(build_format_sections("a1111_png", None, None, None).is_empty());
        // An empty string is "no positive", as Python's falsy check treats it.
        assert!(build_format_sections("a1111_png", Some(""), None, None).is_empty());
    }

    #[test]
    fn an_unknown_meta_source_contributes_no_sections() {
        assert!(build_format_sections("txt", Some("<lora:a:1>"), None, None).is_empty());
    }

    #[test]
    fn nai_v3_reuses_the_prompt_token_sections() {
        let sections = build_format_sections("nai_webp", Some("<embedding:e>"), None, None);
        assert_eq!(titles(&sections), vec!["Embedding"]);
    }

    #[test]
    fn comfy_lists_every_positive_and_the_workflow() {
        let workflow = r#"{
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "first"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "second"}},
            "3": {"class_type": "KSampler", "inputs": {"positive": ["1", 0], "negative": ["2", 0]}}
        }"#;
        let sections = build_format_sections("comfy_png", Some("first"), Some(workflow), None);
        let t = titles(&sections);
        assert!(t.contains(&"Workflow JSON"), "got {t:?}");
        assert_eq!(sections.last().unwrap()["display_type"], json!("json"));
    }

    /// A single-prompt workflow gets the JSON section but no list -- Python
    /// only adds the list when there is more than one positive.
    #[test]
    fn comfy_with_one_positive_omits_the_list() {
        let workflow = r#"{"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "only"}}}"#;
        let sections = build_format_sections("comfy_png", Some("only"), Some(workflow), None);
        assert_eq!(titles(&sections), vec!["Workflow JSON"]);
    }

    #[test]
    fn comfy_without_workflow_json_still_yields_prompt_tokens() {
        let sections = build_format_sections("comfy_png", Some("<lora:a:1>"), None, None);
        assert_eq!(titles(&sections), vec!["LoRA"]);
    }

    #[test]
    fn comfy_with_unparsable_json_does_not_fail() {
        let sections = build_format_sections("comfy_png", Some("x"), Some("not json"), None);
        assert!(sections.is_empty());
    }

    #[test]
    fn nai_v4_renders_characters_and_reference_images() {
        let nai = json!({
            "character_prompts": [{"prompt": "girl"}],
            "negative_characters": ["bad hands"],
            "vibe_transfer": [{"information_extracted": 0.7}, {}],
        });
        let sections = build_format_sections("novelai_v4_png", None, None, Some(&nai));
        assert_eq!(
            titles(&sections),
            vec![
                "V4 Characters (Positive)",
                "V4 Characters (Negative)",
                "Reference Images"
            ]
        );
        assert_eq!(sections[1]["content"][0]["prompt"], json!("bad hands"));
        assert_eq!(sections[2]["content"][0]["strength"], json!(0.7));
        // A reference image with no strength renders "?" rather than null.
        assert_eq!(sections[2]["content"][1]["strength"], json!("?"));
    }

    #[test]
    fn nai_v4_without_parsed_data_yields_nothing() {
        assert!(build_format_sections("novelai_v4_png", Some("x"), None, None).is_empty());
        let empty = json!({"character_prompts": [], "negative_characters": []});
        assert!(build_format_sections("novelai_v4_png", None, None, Some(&empty)).is_empty());
    }
}

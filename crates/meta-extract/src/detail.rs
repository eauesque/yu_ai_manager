use crate::{is_comfy_source, is_nai_source};
use serde_json::{json, Value};

// ---------------------------------------------------------------------------
// Detail field resolution
// ---------------------------------------------------------------------------

pub struct DetailFields {
    pub positive: String,
    pub negative: String,
    pub resolution: Option<String>,
    pub model: Option<String>,
    pub parameters: Value,
    pub novelai_v4: Option<Value>,
}

pub fn resolve_detail_fields(
    meta_source: &str,
    raw_prompt: &str,
    raw_negative: &str,
    raw_meta_json: Option<&str>,
    model_name: Option<&str>,
) -> DetailFields {
    let mut model = model_name.filter(|s| !s.is_empty()).map(str::to_owned);
    let mut positive = raw_prompt.to_owned();
    let mut negative = raw_negative.to_owned();
    let mut resolution: Option<String> = None;
    let mut parameters = json!({});
    let mut novelai_v4: Option<Value> = None;

    match meta_source {
        source if is_nai_source(source) => {
            if let Some(json_str) = raw_meta_json {
                if let Some(nai) = parse_novelai_v4_metadata(json_str) {
                    resolution = nai["parameters"]
                        .get("Size")
                        .and_then(|v| v.as_str())
                        .map(str::to_owned);
                    if model.is_none() {
                        model = Some("NovelAI Diffusion V4.5".to_owned());
                    }
                    if negative.is_empty() {
                        negative = join_novelai_negative(&nai);
                    }
                    parameters = nai["parameters"].clone();
                    novelai_v4 = Some(json!({
                        "base_caption": nai["base_caption"],
                        "character_prompts": nai["character_prompts"],
                        "negative_base": nai["negative_base"],
                        "negative_characters": nai["negative_characters"],
                        "vibe_transfer": nai["vibe_transfer"],
                    }));
                }
            }
        }
        source if is_comfy_source(source) => {
            if let Some(json_str) = raw_meta_json {
                let (comfy_params, comfy_model) = parse_comfy_parameters(json_str);
                if let Value::Object(ref map) = comfy_params {
                    if !map.is_empty() {
                        if model.is_none() {
                            model = comfy_model;
                        }
                        if let (Some(w), Some(h)) = (map.get("width"), map.get("height")) {
                            let ws = w.as_str().unwrap_or("");
                            let hs = h.as_str().unwrap_or("");
                            if !ws.is_empty() && !hs.is_empty() {
                                resolution = Some(format!("{ws}x{hs}"));
                            }
                        }
                        parameters = comfy_params;
                    }
                }
            }
        }
        _ => {
            if raw_prompt.contains("Steps:") || raw_prompt.contains("Negative prompt:") {
                let (pos, neg, params) = parse_a1111_prompt(raw_prompt);
                positive = pos;
                if negative.is_empty() && !neg.is_empty() {
                    negative = neg;
                }
                resolution = params
                    .get("Size")
                    .and_then(|v| v.as_str())
                    .map(str::to_owned);
                if model.is_none() {
                    model = params
                        .get("Model")
                        .and_then(|v| v.as_str())
                        .map(str::to_owned);
                }
                parameters = params;
            } else if !raw_prompt.is_empty() {
                resolution = str_after(raw_prompt, "Size: ", &[',', '\n']);
                if model.is_none() {
                    model = str_after(raw_prompt, "Model: ", &[',', '\n']);
                }
            }
        }
    }

    DetailFields {
        positive,
        negative,
        resolution,
        model,
        parameters,
        novelai_v4,
    }
}

// ---------------------------------------------------------------------------
// A1111 prompt parser
// ---------------------------------------------------------------------------

fn parse_a1111_prompt(text: &str) -> (String, String, Value) {
    let lines: Vec<&str> = text.split('\n').collect();
    let mut pos_lines: Vec<&str> = vec![];
    let mut neg_lines: Vec<String> = vec![];
    let mut i = 0;

    while i < lines.len() {
        let t = lines[i].trim();
        if t.starts_with("Negative prompt:") || t.starts_with("Steps:") {
            break;
        }
        pos_lines.push(lines[i]);
        i += 1;
    }
    let positive = pos_lines.join("\n").trim().to_owned();

    if i < lines.len() && lines[i].trim().starts_with("Negative prompt:") {
        let rest = lines[i]
            .trim()
            .trim_start_matches("Negative prompt:")
            .trim();
        if !rest.is_empty() {
            neg_lines.push(rest.to_owned());
        }
        i += 1;
        while i < lines.len() && !lines[i].trim().starts_with("Steps:") {
            neg_lines.push(lines[i].trim().to_owned());
            i += 1;
        }
    }
    let negative = neg_lines.join("\n").trim().to_owned();

    let mut params = serde_json::Map::new();
    if i < lines.len() {
        for part in lines[i].split(',') {
            let p = part.trim();
            if let Some(colon) = p.find(':') {
                let k = p[..colon].trim();
                let v = p[colon + 1..].trim();
                params.insert(k.to_owned(), json!(v));
            }
        }
    }
    (positive, negative, Value::Object(params))
}

// ---------------------------------------------------------------------------
// NovelAI V4 metadata parser
// ---------------------------------------------------------------------------

fn parse_novelai_v4_metadata(raw: &str) -> Option<Value> {
    let outer: Value = serde_json::from_str(raw).ok()?;
    let comment: Value = serde_json::from_str(outer.get("Comment")?.as_str()?).ok()?;

    let mut base_caption = String::new();
    let mut char_prompts: Vec<Value> = vec![];
    let mut neg_base = String::new();
    let mut neg_chars: Vec<Value> = vec![];

    if let Some(v4) = comment.get("v4_prompt") {
        if let Some(cap) = v4.get("caption") {
            base_caption = cap
                .get("base_caption")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_owned();
            if let Some(chars) = cap.get("char_captions").and_then(|v| v.as_array()) {
                char_prompts = chars
                    .iter()
                    .map(|c| {
                        json!({
                            "prompt": c.get("char_caption").and_then(|v| v.as_str()).unwrap_or(""),
                            "positions": c.get("centers").cloned().unwrap_or(json!([])),
                        })
                    })
                    .collect();
            }
        }
    }
    if let Some(v4) = comment.get("v4_negative_prompt") {
        if let Some(cap) = v4.get("caption") {
            neg_base = cap
                .get("base_caption")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_owned();
            if let Some(chars) = cap.get("char_captions").and_then(|v| v.as_array()) {
                neg_chars = chars
                    .iter()
                    .map(|c| {
                        json!({
                            "prompt": c.get("char_caption").and_then(|v| v.as_str()).unwrap_or(""),
                            "positions": c.get("centers").cloned().unwrap_or(json!([])),
                        })
                    })
                    .collect();
            }
        }
    }

    let mut params = serde_json::Map::new();
    if let Some(v) = comment.get("steps").and_then(|v| v.as_u64()) {
        params.insert("Steps".to_owned(), json!(v.to_string()));
    }
    if let Some(v) = comment.get("sampler").and_then(|v| v.as_str()) {
        params.insert("Sampler".to_owned(), json!(v));
    }
    if let Some(v) = comment.get("scale") {
        params.insert("CFG scale".to_owned(), json!(v.to_string()));
    }
    if let Some(v) = comment.get("seed") {
        params.insert("Seed".to_owned(), json!(v.to_string()));
    }
    if let (Some(w), Some(h)) = (comment.get("width"), comment.get("height")) {
        params.insert("Size".to_owned(), json!(format!("{w}x{h}")));
    }
    if let Some(v) = comment.get("noise_schedule").and_then(|v| v.as_str()) {
        params.insert("Noise Schedule".to_owned(), json!(v));
    }
    if let Some(v) = comment.get("sm").and_then(|v| v.as_bool()) {
        params.insert(
            "SMEA".to_owned(),
            json!(if v { "Enabled" } else { "Disabled" }),
        );
    }
    if let Some(v) = comment.get("sm_dyn").and_then(|v| v.as_bool()) {
        params.insert(
            "SMEA DYN".to_owned(),
            json!(if v { "Enabled" } else { "Disabled" }),
        );
    }
    if let Some(v) = comment.get("cfg_rescale") {
        params.insert("CFG Rescale".to_owned(), json!(v.to_string()));
    }

    let vibe = comment
        .get("director_reference_strengths")
        .and_then(|v| v.as_array())
        .filter(|a| !a.is_empty())
        .map(|strengths| {
            let s = strengths[0].as_f64().unwrap_or(0.0);
            let desc = comment
                .get("director_reference_descriptions")
                .and_then(|v| v.as_array())
                .and_then(|a| a.first())
                .and_then(|d| d.get("caption"))
                .and_then(|c| c.get("base_caption"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let info = comment
                .get("director_reference_information_extracted")
                .and_then(|v| v.as_array())
                .and_then(|a| a.first())
                .cloned()
                .unwrap_or(Value::Null);
            json!({"strength": s, "description": desc, "info_extracted": info})
        });

    Some(json!({
        "base_caption": base_caption,
        "character_prompts": char_prompts,
        "negative_base": neg_base,
        "negative_characters": neg_chars,
        "parameters": Value::Object(params),
        "vibe_transfer": vibe.unwrap_or(Value::Null),
    }))
}

fn join_novelai_negative(nai: &Value) -> String {
    let mut parts: Vec<&str> = vec![];
    if let Some(s) = nai.get("negative_base").and_then(|v| v.as_str()) {
        if !s.is_empty() {
            parts.push(s);
        }
    }
    if let Some(chars) = nai.get("negative_characters").and_then(|v| v.as_array()) {
        for c in chars {
            if let Some(p) = c.get("prompt").and_then(|v| v.as_str()) {
                if !p.is_empty() {
                    parts.push(p);
                }
            }
        }
    }
    parts.join(", ")
}

// ---------------------------------------------------------------------------
// ComfyUI parameter extractor
// ---------------------------------------------------------------------------

const COMFY_LABELS: &[(&str, &str)] = &[
    ("seed", "Seed"),
    ("steps", "Steps"),
    ("cfg", "CFG scale"),
    ("sampler_name", "Sampler"),
    ("scheduler", "Scheduler"),
    ("denoise", "Denoise"),
    ("guidance", "Guidance"),
    ("vae", "VAE"),
    ("clip_name1", "CLIP 1"),
    ("clip_name2", "CLIP 2"),
    ("ckpt_name", "Checkpoint"),
    ("diffusion_model", "Diffusion Model"),
    ("clip_type", "CLIP Type"),
];

fn parse_comfy_parameters(raw: &str) -> (Value, Option<String>) {
    let obj: Value = match serde_json::from_str(raw) {
        Ok(v) => v,
        Err(_) => return (json!({}), None),
    };

    let nodes: Vec<&Value> = if let Some(arr) = obj.get("nodes").and_then(|v| v.as_array()) {
        arr.iter().collect()
    } else if let Some(map) = obj.as_object() {
        map.values().collect()
    } else {
        return (json!({}), None);
    };

    let scalar = |v: &Value| !v.is_array() && !v.is_object();
    let sv = |v: &Value| -> String {
        if let Some(s) = v.as_str() {
            s.to_owned()
        } else {
            v.to_string()
        }
    };

    let mut kv: std::collections::HashMap<&str, String> = Default::default();
    let mut model_val: Option<String> = None;

    for node in nodes {
        let Some(node) = node.as_object() else {
            continue;
        };
        let ctype = node
            .get("class_type")
            .or_else(|| node.get("type"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        let Some(inputs) = node.get("inputs").and_then(|v| v.as_object()) else {
            continue;
        };

        if ctype.contains("ksampler") && !kv.contains_key("seed") {
            for k in [
                "seed",
                "steps",
                "cfg",
                "sampler_name",
                "scheduler",
                "denoise",
            ] {
                if let Some(v) = inputs.get(k).filter(|v| scalar(v)) {
                    kv.entry(k).or_insert_with(|| sv(v));
                }
            }
        }
        if ctype.contains("checkpointloader") {
            if let Some(s) = inputs.get("ckpt_name").and_then(|v| v.as_str()) {
                if !s.is_empty() {
                    model_val.get_or_insert_with(|| s.to_owned());
                    kv.entry("ckpt_name").or_insert_with(|| s.to_owned());
                }
            }
        }
        if ctype == "unetloader" {
            if let Some(s) = inputs.get("unet_name").and_then(|v| v.as_str()) {
                if !s.is_empty() {
                    model_val.get_or_insert_with(|| s.to_owned());
                    kv.entry("diffusion_model").or_insert_with(|| s.to_owned());
                }
            }
        }
        if ctype.contains("dualcliploader") {
            for k in ["clip_name1", "clip_name2"] {
                if let Some(s) = inputs.get(k).and_then(|v| v.as_str()) {
                    if !s.is_empty() {
                        kv.entry(k).or_insert_with(|| s.to_owned());
                    }
                }
            }
            if let Some(s) = inputs.get("type").and_then(|v| v.as_str()) {
                kv.entry("clip_type").or_insert_with(|| s.to_owned());
            }
        }
        if ctype == "cliploader" {
            if let Some(s) = inputs.get("clip_name").and_then(|v| v.as_str()) {
                kv.entry("clip_name1").or_insert_with(|| s.to_owned());
            }
        }
        if ctype.contains("cliptextencodeflux") {
            if let Some(v) = inputs.get("guidance").filter(|v| scalar(v)) {
                kv.entry("guidance").or_insert_with(|| sv(v));
            }
        }
        if ctype.contains("vaeloader") {
            if let Some(s) = inputs.get("vae_name").and_then(|v| v.as_str()) {
                kv.entry("vae").or_insert_with(|| s.to_owned());
            }
        }
        if ctype.contains("emptylatent") || ctype == "emptymochilatent" {
            for k in ["width", "height"] {
                if let Some(v) = inputs.get(k).filter(|v| scalar(v)) {
                    kv.entry(k).or_insert_with(|| sv(v));
                }
            }
        }
    }

    let mut mapped = serde_json::Map::new();
    for (k, v) in &kv {
        let label = COMFY_LABELS
            .iter()
            .find(|(lk, _)| lk == k)
            .map(|(_, l)| *l)
            .unwrap_or(k);
        mapped.insert(label.to_owned(), json!(v));
    }
    (Value::Object(mapped), model_val)
}

// ---------------------------------------------------------------------------
// Simple substring capture helper
// ---------------------------------------------------------------------------

fn str_after(text: &str, prefix: &str, delims: &[char]) -> Option<String> {
    let pos = text.find(prefix)?;
    let rest = &text[pos + prefix.len()..];
    let end = rest
        .find(|c: char| delims.contains(&c))
        .unwrap_or(rest.len());
    let s = rest[..end].trim();
    if s.is_empty() {
        None
    } else {
        Some(s.to_owned())
    }
}

#[cfg(test)]
mod tests {
    use super::resolve_detail_fields;
    use serde_json::json;

    #[test]
    fn historical_comfyui_source_uses_comfy_parser() {
        let raw = json!({
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20}}
        })
        .to_string();

        let detail = resolve_detail_fields("comfyui", "", "", Some(&raw), None);

        assert_eq!(detail.parameters["Seed"], "1");
    }

    #[test]
    fn polluted_nai_v4_source_uses_nai_parser() {
        let comment = json!({
            "v4_prompt": {"caption": {"base_caption": "cat", "char_captions": []}},
            "v4_negative_prompt": {"caption": {"base_caption": "bad", "char_captions": []}},
            "width": 832,
            "height": 1216
        });
        let raw = json!({"Comment": comment.to_string()}).to_string();

        let detail = resolve_detail_fields("nai_v4", "", "", Some(&raw), None);

        assert!(detail.novelai_v4.is_some());
        assert_eq!(detail.resolution.as_deref(), Some("832x1216"));
    }
}

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
                    // Parameters and resolution are read for v3 too — NovelAI
                    // writes steps/sampler/seed/width/height regardless.
                    let params = field(&nai, "parameters");
                    resolution = params
                        .get("Size")
                        .and_then(|v| v.as_str())
                        .map(str::to_owned);
                    parameters = params;
                    // Everything below is v4-only: claiming a v4 model name or
                    // emitting a v4 payload for a v3 image would be a lie.
                    if nai.get("has_v4").and_then(Value::as_bool).unwrap_or(false) {
                        if model.is_none() {
                            model = Some("NovelAI Diffusion V4.5".to_owned());
                        }
                        if negative.is_empty() {
                            negative = join_novelai_negative(&nai);
                        }
                        novelai_v4 = Some(json!({
                            "base_caption": field(&nai, "base_caption"),
                            "character_prompts": field(&nai, "character_prompts"),
                            "negative_base": field(&nai, "negative_base"),
                            "negative_characters": field(&nai, "negative_characters"),
                            "vibe_transfer": field(&nai, "vibe_transfer"),
                            // Emitted even when null: a dropped key and an
                            // explicit null are different on the wire, and the
                            // Python side emits the key either way.
                            "use_coords": field(&nai, "use_coords"),
                            "negative_use_coords": field(&nai, "negative_use_coords"),
                            "use_order": field(&nai, "use_order"),
                        }));
                    }
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

/// Read a three-valued flag off a `v4_prompt` / `v4_negative_prompt` object.
///
/// A real bool stays; absent or any other type becomes null, meaning "the image
/// did not say". Folding that into `false` makes the viewer claim a V5 image
/// uses no coordinates.
fn tri_bool(v4: Option<&Value>, key: &str) -> Value {
    match v4.and_then(|v| v.get(key)).and_then(Value::as_bool) {
        Some(b) => json!(b),
        None => Value::Null,
    }
}

/// Read a field off the parsed payload without indexing.
///
/// A missing key and an explicit null must both come out as null: the payload
/// is re-emitted to the API and the two are different on the wire only when the
/// key is dropped entirely, which this avoids.
fn field(nai: &Value, key: &str) -> Value {
    nai.get(key).cloned().unwrap_or(Value::Null)
}

/// Normalise -0.0 to 0.0 so both implementations serialise alike.
///
/// `serde_json` writes `-0.0` and Python writes `-0.0` too, but the two sides
/// reach the value by different routes; pinning it here keeps the wire form
/// identical with no semantic change.
fn norm_centers(centers: Option<&Value>) -> Value {
    let Some(Value::Array(items)) = centers else {
        return json!([]);
    };
    Value::Array(
        items
            .iter()
            .map(|c| {
                let Value::Object(map) = c else {
                    return c.clone();
                };
                Value::Object(
                    map.iter()
                        .map(|(k, v)| {
                            // -0.0 == 0.0, so this catches both and pins the
                            // serialised form to "0.0" on either side.
                            let v = match v.as_f64() {
                                Some(0.0) => json!(0.0),
                                _ => v.clone(),
                            };
                            (k.clone(), v)
                        })
                        .collect(),
                )
            })
            .collect(),
    )
}

/// Parses the `templates.raw_meta_json` blob of a NovelAI v4 row.
///
/// Two shapes reach this function and both must be accepted. The Python
/// extractors wrap the PNG chunks in an object keyed by `Comment`, while the
/// Rust scanner (`novelai_v4.rs`) stores the bare `Comment` chunk itself, whose
/// `v4_prompt` sits at the top level. Requiring the wrapper dropped every
/// character prompt for Rust-scanned files.
fn parse_novelai_v4_metadata(raw: &str) -> Option<Value> {
    let parsed: Value = serde_json::from_str(raw).ok()?;
    if !parsed.is_object() {
        return None;
    }
    let comment: Value = match parsed.get("Comment").and_then(|v| v.as_str()) {
        Some(inner) => serde_json::from_str(inner).ok()?,
        None => parsed,
    };
    // A non-object inner Comment carries no fields worth reading, and letting it
    // through would return an empty payload that blanks out `parameters`.
    if !comment.is_object() {
        return None;
    }
    // v3 sources share `is_nai_source`, so track whether a v4 caption is present
    // rather than returning an all-empty v4 payload for them.
    //
    // The gate lives here, not at the entry: the parameter block below reads
    // `steps`/`sampler`/`seed`/`width`/`height`, which NovelAI writes for v3
    // too. Rejecting early would drop a v3 image's parameters and resolution.
    let has_v4 = comment.get("v4_prompt").is_some() || comment.get("v4_negative_prompt").is_some();

    // Three-valued: true, false, or null for "the image did not say". V5
    // replaced the 5x5 grid with free coordinates and uses `use_coords` to say
    // which applies; the coordinate values alone cannot tell the two apart.
    let use_coords = tri_bool(comment.get("v4_prompt"), "use_coords");
    let negative_use_coords = tri_bool(comment.get("v4_negative_prompt"), "use_coords");
    let use_order = tri_bool(comment.get("v4_prompt"), "use_order");

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
                            "positions": norm_centers(c.get("centers")),
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
                            "positions": norm_centers(c.get("centers")),
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
        "has_v4": has_v4,
        "use_coords": use_coords,
        "negative_use_coords": negative_use_coords,
        "use_order": use_order,
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
    use serde_json::{json, Value};

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

    /// The Rust scanner stores the bare `Comment` chunk, not the Python wrapper.
    /// This is the shape `novelai_v4.rs` actually writes to `raw_meta_json`.
    #[test]
    fn bare_comment_nai_v4_yields_character_prompts() {
        let raw = json!({
            "v4_prompt": {"caption": {
                "base_caption": "2girls",
                "char_captions": [{"char_caption": "blonde hair", "centers": [{"x": 0.25, "y": 0.5}]}],
            }},
            "v4_negative_prompt": {"caption": {
                "base_caption": "bad",
                "char_captions": [{"char_caption": "extra limbs", "centers": []}],
            }},
            "width": 832,
            "height": 1216
        })
        .to_string();

        let detail = resolve_detail_fields("novelai_v4_png", "", "", Some(&raw), None);

        let nai = detail.novelai_v4.expect("v4 payload");
        assert_eq!(nai["base_caption"], "2girls");
        assert_eq!(nai["character_prompts"][0]["prompt"], "blonde hair");
        assert_eq!(nai["character_prompts"][0]["positions"][0]["x"], 0.25);
        assert_eq!(nai["negative_characters"][0]["prompt"], "extra limbs");
        assert_eq!(detail.resolution.as_deref(), Some("832x1216"));
    }

    /// v3 rows share `is_nai_source`; they must not produce an empty v4 payload.
    #[test]
    fn bare_non_v4_comment_is_not_treated_as_v4() {
        let raw = json!({"prompt": "a fox", "uc": "bad", "steps": 28}).to_string();

        let detail = resolve_detail_fields("novelai_png", "", "", Some(&raw), None);

        assert!(detail.novelai_v4.is_none());
        assert!(detail.model.is_none());
    }

    /// NovelAI writes steps/sampler/seed/width/height for v3 as well. Gating the
    /// whole parse on `v4_prompt` dropped them — a regression this pins.
    #[test]
    fn v3_keeps_parameters_and_resolution_without_claiming_v4() {
        let comment = json!({
            "prompt": "a fox",
            "uc": "bad",
            "steps": 28,
            "sampler": "k_euler",
            "seed": 12345,
            "width": 832,
            "height": 1216
        });
        let raw = json!({"Comment": comment.to_string(), "Description": "a fox"}).to_string();

        let detail = resolve_detail_fields("novelai_png", "", "", Some(&raw), None);

        assert_eq!(detail.parameters["Steps"], "28");
        assert_eq!(detail.parameters["Sampler"], "k_euler");
        assert_eq!(detail.parameters["Seed"], "12345");
        assert_eq!(detail.resolution.as_deref(), Some("832x1216"));
        // ...but it is still not a v4 image.
        assert!(detail.novelai_v4.is_none());
        assert!(detail.model.is_none());
    }

    /// Mirrors the Python parser's `isinstance(parsed, dict)` guard. Without it a
    /// non-object blob returns an empty payload, which blanks `parameters`.
    #[test]
    fn malformed_returns_none() {
        for raw in [
            "not json",
            r#"{"Comment": "not json"}"#,
            "[1, 2, 3]",
            r#""just a string""#,
            r#"{"Comment": "[1,2,3]"}"#,
        ] {
            let detail = resolve_detail_fields("novelai_png", "", "", Some(raw), None);
            assert!(detail.novelai_v4.is_none(), "raw={raw}");
            assert_eq!(detail.parameters, json!({}), "raw={raw}");
        }
    }

    // --- Phase 1: use_coords / use_order as three-valued fields --------------
    //
    // Case names are kept in sync with tests/prompt/test_parse_novelai_v4.py.

    fn v4_with(pos: Value, neg: Value) -> String {
        json!({"Comment": json!({
            "v4_prompt": pos,
            "v4_negative_prompt": neg,
        }).to_string()})
        .to_string()
    }

    fn nai_of(raw: &str) -> Value {
        resolve_detail_fields("novelai_v4_png", "", "", Some(raw), None)
            .novelai_v4
            .expect("v4 payload")
    }

    #[test]
    fn use_coords_true() {
        let raw = v4_with(json!({"use_coords": true}), json!({}));
        assert_eq!(nai_of(&raw)["use_coords"], json!(true));
    }

    #[test]
    fn use_coords_false() {
        let raw = v4_with(json!({"use_coords": false}), json!({}));
        assert_eq!(nai_of(&raw)["use_coords"], json!(false));
    }

    /// Absent is not false. A V5 image without the field must not read as
    /// "no coords" -- that would hide its character positions.
    #[test]
    fn use_coords_absent_is_null() {
        let raw = v4_with(json!({}), json!({}));
        assert_eq!(nai_of(&raw)["use_coords"], Value::Null);
    }

    #[test]
    fn use_coords_non_bool_is_null() {
        for bad in [json!("false"), json!("true"), json!(0), json!(1), json!([])] {
            let raw = v4_with(json!({"use_coords": bad}), json!({}));
            assert_eq!(nai_of(&raw)["use_coords"], Value::Null, "bad={bad}");
        }
    }

    /// Measured on a real V5 image: positive true, negative false.
    #[test]
    fn negative_use_coords_independent() {
        let raw = v4_with(json!({"use_coords": true}), json!({"use_coords": false}));
        let nai = nai_of(&raw);
        assert_eq!(nai["use_coords"], json!(true));
        assert_eq!(nai["negative_use_coords"], json!(false));
    }

    #[test]
    fn use_order_carried() {
        let raw = v4_with(json!({"use_order": true}), json!({}));
        assert_eq!(nai_of(&raw)["use_order"], json!(true));
        let bare = v4_with(json!({}), json!({}));
        assert_eq!(nai_of(&bare)["use_order"], Value::Null);
    }

    #[test]
    fn centers_absent_is_empty() {
        let raw = v4_with(
            json!({"caption": {"char_captions": [{"char_caption": "a"}]}}),
            json!({}),
        );
        assert_eq!(nai_of(&raw)["character_prompts"][0]["positions"], json!([]));
    }

    /// The UI shows the first, but dropping the rest would be a silent loss.
    #[test]
    fn multiple_centers_all_preserved() {
        let raw = v4_with(
            json!({"caption": {"char_captions": [
                {"char_caption": "a", "centers": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}]}
            ]}}),
            json!({}),
        );
        let positions = nai_of(&raw)["character_prompts"][0]["positions"].clone();
        assert_eq!(positions.as_array().map(Vec::len), Some(2));
    }

    /// Extraction is verbatim; clamping belongs to the renderer.
    #[test]
    fn out_of_range_kept_verbatim() {
        let raw = v4_with(
            json!({"caption": {"char_captions": [
                {"char_caption": "a", "centers": [{"x": 1.5, "y": -0.2}]}
            ]}}),
            json!({}),
        );
        let p = nai_of(&raw)["character_prompts"][0]["positions"][0].clone();
        assert_eq!(p["x"], json!(1.5));
        assert_eq!(p["y"], json!(-0.2));
    }

    #[test]
    fn negative_zero_normalized() {
        let raw = v4_with(
            json!({"caption": {"char_captions": [
                {"char_caption": "a", "centers": [{"x": -0.0, "y": 0.5}]}
            ]}}),
            json!({}),
        );
        let p = nai_of(&raw)["character_prompts"][0]["positions"][0].clone();
        assert_eq!(p["x"].to_string(), "0.0", "serialised as {}", p["x"]);
    }

    #[test]
    fn length_mismatch_pairs_by_index() {
        let raw = v4_with(
            json!({"caption": {"char_captions": [{"char_caption": "a"}, {"char_caption": "b"}]}}),
            json!({"caption": {"char_captions": [{"char_caption": "na"}]}}),
        );
        let nai = nai_of(&raw);
        assert_eq!(nai["character_prompts"].as_array().map(Vec::len), Some(2));
        assert_eq!(nai["negative_characters"].as_array().map(Vec::len), Some(1));
    }

    /// A dropped key and an explicit null are different on the wire.
    #[test]
    fn null_is_serialised_as_an_explicit_key() {
        let raw = v4_with(json!({}), json!({}));
        let nai = nai_of(&raw);
        let text = serde_json::to_string(&nai).unwrap();
        assert!(text.contains(r#""use_coords":null"#), "{text}");
        assert!(text.contains(r#""use_order":null"#), "{text}");
    }
}

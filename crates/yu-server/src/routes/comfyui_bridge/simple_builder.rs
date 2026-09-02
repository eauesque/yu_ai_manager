use axum::http::StatusCode;
use axum::response::Response;
use regex::Regex;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::sync::OnceLock;

use crate::state::SharedState;

use super::{
    api_err, cfg_bool, cfg_i64, cfg_str, comfy_api_url, comfy_get, ext_config, get_api_key,
};

// ---------------------------------------------------------------------------
// TeKind — text encoder family
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TeKind {
    Clip,   // standard SD1.5 / SDXL CLIP
    Qwen3,  // Anima / Qwen-Image based encoders
    T5Only, // AuraFlow / PixArt (T5 only)
}

impl std::fmt::Display for TeKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TeKind::Clip => write!(f, "Clip"),
            TeKind::Qwen3 => write!(f, "Qwen3"),
            TeKind::T5Only => write!(f, "T5Only"),
        }
    }
}

// ---------------------------------------------------------------------------
// LoraEntry
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct LoraEntry {
    pub name: String,
    pub strength_model: f64,
    pub strength_clip: f64,
}

// ---------------------------------------------------------------------------
// SimpleParams
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct SimpleParams {
    pub ckpt_name: String,
    pub diffusion_model: String,
    pub vae_name: String,
    pub text_encoder_1: String,
    pub text_encoder_2: String,
    pub clip_type: String,
    pub weight_dtype: String,
    pub prompt: String,
    pub negative_prompt: String,
    pub steps: i64,
    pub cfg: f64,
    pub width: i64,
    pub height: i64,
    pub seed: i64,
    pub batch_size: i64,
    pub sampler_name: String,
    pub scheduler: String,
    pub a1111_mode: bool,
    pub loras: Vec<LoraEntry>,
    pub controlnet_model: String,
    pub controlnet_strength: f64,
    pub controlnet_image_name: String,
    pub upscale_model: String,
    pub skip_save: bool,
    pub te_kind: TeKind,
}

// ---------------------------------------------------------------------------
// Security guards
// ---------------------------------------------------------------------------

fn has_traversal(s: &str) -> bool {
    s.contains("..")
}

fn is_absolute_path(s: &str) -> bool {
    s.starts_with('/') || s.starts_with('\\') || s.contains(':')
}

/// For model files: subdirectory paths like 'sdxl/model.safetensors' are allowed.
pub(super) fn reject_model_name(s: &str) -> Option<&'static str> {
    if has_traversal(s) {
        Some("path traversal ('..' is not allowed)")
    } else if is_absolute_path(s) {
        Some("absolute paths are not allowed")
    } else {
        None
    }
}

/// For filename-only fields (lora, controlnet_image): no path separators allowed.
fn reject_filename(s: &str) -> Option<&'static str> {
    if has_traversal(s) {
        Some("path traversal ('..' is not allowed)")
    } else if s.contains('/') || s.contains('\\') {
        Some("must be a filename only (no path separators)")
    } else {
        None
    }
}

// ---------------------------------------------------------------------------
// parse_params
// ---------------------------------------------------------------------------

pub(crate) fn client_wildcards(body: &Value) -> BTreeMap<String, Vec<String>> {
    let Some(obj) = body.get("client_wildcards").and_then(Value::as_object) else {
        return BTreeMap::new();
    };
    obj.iter()
        .filter_map(|(name, value)| {
            let lines: Vec<String> = match value {
                Value::String(s) => vec![s.clone()],
                Value::Array(arr) => arr
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect(),
                _ => Vec::new(),
            };
            (!lines.is_empty()).then(|| (name.clone(), lines))
        })
        .collect()
}

pub fn parse_params(
    body: &Value,
    max_batch: i64,
    sweep_meta: Option<Value>,
    config_path: &str,
) -> Result<SimpleParams, Response> {
    // Hard rejections
    if body
        .get("image_base64")
        .and_then(Value::as_str)
        .is_some_and(|s| !s.is_empty())
    {
        return Err(api_err(
            "img2img (image_base64) is not yet supported",
            StatusCode::NOT_IMPLEMENTED,
        ));
    }

    macro_rules! str_param {
        ($key:literal, $default:literal) => {
            body.get($key)
                .and_then(Value::as_str)
                .unwrap_or($default)
                .trim()
                .to_string()
        };
    }
    macro_rules! clamp_i64 {
        ($key:literal, $default:expr, $lo:expr, $hi:expr) => {{
            let v = body
                .get($key)
                .and_then(|v| match v {
                    Value::Number(n) => n.as_i64(),
                    Value::String(s) => s.parse().ok(),
                    _ => None,
                })
                .unwrap_or($default);
            v.clamp($lo, $hi)
        }};
    }
    macro_rules! clamp_f64 {
        ($key:literal, $default:expr, $lo:expr, $hi:expr) => {{
            let v = body
                .get($key)
                .and_then(|v| match v {
                    Value::Number(n) => n.as_f64(),
                    Value::String(s) => s.parse().ok(),
                    _ => None,
                })
                .unwrap_or($default);
            v.clamp($lo, $hi)
        }};
    }

    let ckpt_name = str_param!("ckpt_name", "");
    let diffusion_model = str_param!("diffusion_model", "");
    let vae_name = str_param!("vae_name", "");
    let text_encoder_1 = str_param!("text_encoder_1", "");
    let text_encoder_2 = str_param!("text_encoder_2", "");
    let clip_type = str_param!("clip_type", "");
    let weight_dtype = str_param!("weight_dtype", "default");

    for (val, label) in [
        (&ckpt_name, "ckpt_name"),
        (&diffusion_model, "diffusion_model"),
        (&vae_name, "vae_name"),
        (&text_encoder_1, "text_encoder_1"),
        (&text_encoder_2, "text_encoder_2"),
    ] {
        if let Some(reason) = reject_model_name(val) {
            return Err(api_err(
                &format!("{label}: {reason}"),
                StatusCode::BAD_REQUEST,
            ));
        }
    }

    let controlnet_image_name = str_param!("controlnet_image_name", "");
    if let Some(reason) = reject_filename(&controlnet_image_name) {
        return Err(api_err(
            &format!("controlnet_image_name: {reason}"),
            StatusCode::BAD_REQUEST,
        ));
    }

    let mut prompt = str_param!("prompt", "");
    if prompt.is_empty() {
        return Err(api_err("prompt is required", StatusCode::BAD_REQUEST));
    }

    let mut negative_prompt = str_param!("negative_prompt", "");
    let sampler_name = str_param!("sampler_name", "euler");
    let scheduler = str_param!("scheduler", "normal");
    let steps = clamp_i64!("steps", 20, 1, 200);
    let cfg_val = clamp_f64!("cfg", 8.0, 0.0, 30.0);
    let width = clamp_i64!("width", 512, 64, 16384);
    let height = clamp_i64!("height", 768, 64, 16384);
    let seed = clamp_i64!("seed", -1, -1, 4_294_967_295);
    let batch_size = clamp_i64!("batch_size", 1, 1, max_batch);
    if body
        .get("expand_wildcards")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        let wildcards =
            crate::prompt_sim_core::bridge_wildcards(config_path, client_wildcards(body));
        // A negative seed is the "random" sentinel: None, never a wrapped value.
        let seed = u64::try_from(seed).ok();
        prompt = crate::prompt_sim_core::expand_dynamic_prompt(&prompt, seed, &wildcards);
        negative_prompt =
            crate::prompt_sim_core::expand_dynamic_prompt(&negative_prompt, seed, &wildcards);
    }
    let a1111_mode = body
        .get("a1111_mode")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let skip_save = body
        .get("skip_save")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let controlnet_model = str_param!("controlnet_model", "");
    let controlnet_strength = clamp_f64!("controlnet_strength", 1.0, 0.0, 100.0);
    let upscale_model = str_param!("upscale_model", "");

    // LoRA from structured `loras` array
    let mut loras: Vec<LoraEntry> = Vec::new();
    if let Some(Value::Array(arr)) = body.get("loras") {
        for entry in arr {
            let name = entry
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            if name.is_empty() {
                continue;
            }
            if let Some(reason) = reject_filename(&name) {
                return Err(api_err(
                    &format!("lora name '{name}': {reason}"),
                    StatusCode::BAD_REQUEST,
                ));
            }
            let sm = entry
                .get("strength_model")
                .and_then(Value::as_f64)
                .unwrap_or(1.0);
            let sc = entry
                .get("strength_clip")
                .and_then(Value::as_f64)
                .unwrap_or(sm);
            loras.push(LoraEntry {
                name,
                strength_model: sm,
                strength_clip: sc,
            });
        }
    }

    Ok(SimpleParams {
        ckpt_name,
        diffusion_model,
        vae_name,
        text_encoder_1,
        text_encoder_2,
        clip_type,
        weight_dtype,
        prompt,
        negative_prompt,
        steps,
        cfg: cfg_val,
        width,
        height,
        seed,
        batch_size,
        sampler_name,
        scheduler,
        a1111_mode,
        loras,
        controlnet_model,
        controlnet_strength,
        controlnet_image_name,
        upscale_model,
        skip_save,
        te_kind: TeKind::Clip, // filled later by detect_te_kind()
    })
}

// ---------------------------------------------------------------------------
// LoRA token extraction
// ---------------------------------------------------------------------------

static LORA_RE: OnceLock<Regex> = OnceLock::new();
static COMMA_RE: OnceLock<Regex> = OnceLock::new();
static SPACE_RE: OnceLock<Regex> = OnceLock::new();

fn lora_re() -> &'static Regex {
    LORA_RE.get_or_init(|| {
        Regex::new(r"<lora:([^:>]+?)(?::(-?\d+(?:\.\d+)?))?(?::(-?\d+(?:\.\d+)?))?>")
            .expect("lora regex")
    })
}

/// Strip `<lora:name:w_model:w_clip>` tokens from `text`.
/// Returns `(cleaned_text, extracted_loras)`.
pub fn extract_lora_tokens(text: &str) -> (String, Vec<LoraEntry>) {
    let mut loras = Vec::new();
    let cleaned = lora_re().replace_all(text, |caps: &regex::Captures| {
        let name = caps[1].trim().to_string();
        let sm: f64 = caps
            .get(2)
            .and_then(|m| m.as_str().parse().ok())
            .unwrap_or(1.0);
        let sc: f64 = caps
            .get(3)
            .and_then(|m| m.as_str().parse().ok())
            .unwrap_or(sm);
        if !name.is_empty() {
            loras.push(LoraEntry {
                name,
                strength_model: sm,
                strength_clip: sc,
            });
        }
        ""
    });
    let cleaned = COMMA_RE
        .get_or_init(|| Regex::new(r"(,\s*){2,}").unwrap())
        .replace_all(&cleaned, ", ");
    let cleaned = SPACE_RE
        .get_or_init(|| Regex::new(r"\s{2,}").unwrap())
        .replace_all(&cleaned, " ");
    let cleaned = cleaned.trim_matches(|c| c == ' ' || c == ',').to_string();
    (cleaned, loras)
}

// ---------------------------------------------------------------------------
// detect_te_kind — filename heuristics
// ---------------------------------------------------------------------------

/// Detect text encoder family from filename. Fallback: Clip.
pub fn detect_te_kind(name: &str) -> TeKind {
    let lower = name.to_lowercase();
    if lower.contains("qwen")
        || lower.starts_with("anima-")
        || lower.starts_with("anima_")
        || lower.starts_with("anima.")
        || lower.contains("/anima-")
        || lower.contains("/anima_")
    {
        return TeKind::Qwen3;
    }
    if lower.contains("auraflow") || lower.contains("pixart") {
        return TeKind::T5Only;
    }
    TeKind::Clip
}

// ---------------------------------------------------------------------------
// infer_unet_components — auto-fill vae_name / text_encoder_1
// ---------------------------------------------------------------------------

/// Auto-fill vae_name / text_encoder_1 from ComfyUI /object_info when absent.
/// Runs BEFORE detect_te_kind so the filled values can be used for heuristics.
pub async fn infer_unet_components(
    params: &mut SimpleParams,
    state: &SharedState,
) -> Result<(), Response> {
    let cfg = ext_config(state);
    let api_url = comfy_api_url(&cfg);
    let api_key = get_api_key(&cfg, &state.config.project_root);

    if params.vae_name.is_empty() {
        let data = comfy_get(
            &state.python_client,
            &api_url,
            "/object_info/VAELoader",
            &api_key,
        )
        .await
        .unwrap_or_default();
        let list: Vec<String> = data
            .pointer("/VAELoader/input/required/vae_name/0")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();
        if list.is_empty() {
            return Err(api_err(
                "vae_name is required but no VAE found in ComfyUI. Run comfyui_discovery_models.",
                StatusCode::BAD_REQUEST,
            ));
        }
        params.vae_name = list.into_iter().next().unwrap();
        tracing::info!("comfyui: auto-inferred vae_name={}", params.vae_name);
    }

    if params.text_encoder_1.is_empty() {
        let data = comfy_get(
            &state.python_client,
            &api_url,
            "/object_info/CLIPLoader",
            &api_key,
        )
        .await
        .unwrap_or_default();
        let list: Vec<String> = data
            .pointer("/CLIPLoader/input/required/clip_name/0")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();
        if list.is_empty() {
            return Err(api_err(
                "text_encoder_1 is required but no CLIP model found. Run comfyui_list_text_encoders.",
                StatusCode::BAD_REQUEST,
            ));
        }
        params.text_encoder_1 = list.into_iter().next().unwrap();
        tracing::info!(
            "comfyui: auto-inferred text_encoder_1={}",
            params.text_encoder_1
        );
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// check_bnk_node — BNK_CLIPTextEncodeAdvanced availability
// ---------------------------------------------------------------------------

/// Returns true if BNK_CLIPTextEncodeAdvanced is available in ComfyUI.
pub async fn check_bnk_node(state: &SharedState) -> bool {
    let cfg = ext_config(state);
    let api_url = comfy_api_url(&cfg);
    let api_key = get_api_key(&cfg, &state.config.project_root);
    comfy_get(
        &state.python_client,
        &api_url,
        "/object_info/BNK_CLIPTextEncodeAdvanced",
        &api_key,
    )
    .await
    .map(|d| d.as_object().is_some_and(|o| !o.is_empty()))
    .unwrap_or(false)
}

// ---------------------------------------------------------------------------
// resolve_sweep_xmp_target
// ---------------------------------------------------------------------------

pub fn resolve_sweep_xmp_target(cfg: &Value) -> String {
    let explicit = cfg_str(cfg, "comfy_output_root", "").trim().to_string();
    let same_as_save = cfg
        .get("comfy_output_same_as_save_folder")
        .and_then(Value::as_bool)
        .unwrap_or(explicit.is_empty());
    if same_as_save {
        cfg_str(cfg, "save_folder", "").trim().to_string()
    } else {
        explicit
    }
}

// ---------------------------------------------------------------------------
// build_workflow
// ---------------------------------------------------------------------------

/// Build a ComfyUI API-format workflow for txt2img.
///
/// `use_save_node`:
///   true  → node 9 = SaveImage (ComfyUI output/, bridge picks it up)
///   false → node 9 = PreviewImage (temp only)
pub fn build_workflow(params: &SimpleParams, loras: &[LoraEntry], use_save_node: bool) -> Value {
    let use_separate = !params.diffusion_model.is_empty();
    let is_qwen3 = params.te_kind == TeKind::Qwen3;

    let mut wf: Map<String, Value> = Map::new();

    let mut model_ref = json!(["4", 0]);
    let mut clip_ref = json!(["4", 1]);
    let mut vae_ref = json!(["4", 2]);

    // --- Model loading ---
    if use_separate {
        wf.insert("11".into(), json!({
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": params.diffusion_model,
                "weight_dtype": if params.weight_dtype.is_empty() { "default" } else { params.weight_dtype.as_str() },
            }
        }));
        model_ref = json!(["11", 0]);

        let resolved_clip_type = if !params.clip_type.is_empty() {
            params.clip_type.clone()
        } else if is_qwen3 {
            "qwen_image".to_string()
        } else {
            "stable_diffusion".to_string()
        };

        if !params.text_encoder_2.is_empty() {
            wf.insert(
                "12".into(),
                json!({
                    "class_type": "DualCLIPLoader",
                    "inputs": {
                        "clip_name1": params.text_encoder_1,
                        "clip_name2": params.text_encoder_2,
                        "type": resolved_clip_type,
                    }
                }),
            );
        } else {
            wf.insert(
                "12".into(),
                json!({
                    "class_type": "CLIPLoader",
                    "inputs": {
                        "clip_name": params.text_encoder_1,
                        "type": resolved_clip_type,
                    }
                }),
            );
        }
        clip_ref = json!(["12", 0]);

        wf.insert(
            "10".into(),
            json!({
                "class_type": "VAELoader",
                "inputs": {"vae_name": params.vae_name}
            }),
        );
        vae_ref = json!(["10", 0]);
    } else {
        wf.insert(
            "4".into(),
            json!({
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": params.ckpt_name}
            }),
        );
        if !params.vae_name.is_empty() {
            wf.insert(
                "10".into(),
                json!({
                    "class_type": "VAELoader",
                    "inputs": {"vae_name": params.vae_name}
                }),
            );
            vae_ref = json!(["10", 0]);
        }
    }

    // --- LoRA chain ---
    for (i, lora) in loras.iter().enumerate() {
        if lora.name.is_empty() {
            continue;
        }
        let nid = (40 + i).to_string();
        if use_separate {
            wf.insert(
                nid.clone(),
                json!({
                    "class_type": "LoraLoaderModelOnly",
                    "inputs": {
                        "model": model_ref,
                        "lora_name": lora.name,
                        "strength_model": lora.strength_model,
                    }
                }),
            );
            model_ref = json!([nid, 0]);
        } else {
            wf.insert(
                nid.clone(),
                json!({
                    "class_type": "LoraLoader",
                    "inputs": {
                        "model": model_ref,
                        "clip": clip_ref,
                        "lora_name": lora.name,
                        "strength_model": lora.strength_model,
                        "strength_clip": lora.strength_clip,
                    }
                }),
            );
            model_ref = json!([nid, 0]);
            clip_ref = json!([nid, 1]);
        }
    }

    // --- CLIP text encoding ---
    let use_bnk = params.a1111_mode && params.te_kind == TeKind::Clip;
    let (encode_class, bnk_extras) = if use_bnk {
        (
            "BNK_CLIPTextEncodeAdvanced",
            Some(("mean".to_string(), "A1111".to_string())),
        )
    } else {
        ("CLIPTextEncode", None)
    };

    let mut pos_inputs = Map::new();
    pos_inputs.insert("text".into(), json!(params.prompt));
    pos_inputs.insert("clip".into(), clip_ref.clone());
    let mut neg_inputs = Map::new();
    neg_inputs.insert("text".into(), json!(params.negative_prompt));
    neg_inputs.insert("clip".into(), clip_ref.clone());
    if let Some((norm, interp)) = &bnk_extras {
        pos_inputs.insert("token_normalization".into(), json!(norm));
        pos_inputs.insert("weight_interpretation".into(), json!(interp));
        neg_inputs.insert("token_normalization".into(), json!(norm));
        neg_inputs.insert("weight_interpretation".into(), json!(interp));
    }
    wf.insert(
        "6".into(),
        json!({"class_type": encode_class, "inputs": Value::Object(pos_inputs)}),
    );
    wf.insert(
        "7".into(),
        json!({"class_type": encode_class, "inputs": Value::Object(neg_inputs)}),
    );

    let mut positive_ref = json!(["6", 0]);
    let mut negative_ref = json!(["7", 0]);

    // --- ControlNet ---
    if !params.controlnet_model.is_empty() && !params.controlnet_image_name.is_empty() {
        wf.insert(
            "20".into(),
            json!({
                "class_type": "ControlNetLoader",
                "inputs": {"control_net_name": params.controlnet_model}
            }),
        );
        wf.insert(
            "21".into(),
            json!({
                "class_type": "LoadImage",
                "inputs": {"image": params.controlnet_image_name}
            }),
        );
        wf.insert(
            "22".into(),
            json!({
                "class_type": "ControlNetApplyAdvanced",
                "inputs": {
                    "positive": positive_ref,
                    "negative": negative_ref,
                    "control_net": ["20", 0],
                    "image": ["21", 0],
                    "strength": params.controlnet_strength,
                    "start_percent": 0.0,
                    "end_percent": 1.0,
                }
            }),
        );
        positive_ref = json!(["22", 0]);
        negative_ref = json!(["22", 1]);
    }

    // --- Latent ---
    wf.insert("5".into(), json!({
        "class_type": "EmptyLatentImage",
        "inputs": {"width": params.width, "height": params.height, "batch_size": params.batch_size}
    }));

    // --- KSampler ---
    wf.insert(
        "3".into(),
        json!({
            "class_type": "KSampler",
            "inputs": {
                "model": model_ref,
                "positive": positive_ref,
                "negative": negative_ref,
                "latent_image": ["5", 0],
                "seed": params.seed,
                "steps": params.steps,
                "cfg": params.cfg,
                "sampler_name": params.sampler_name,
                "scheduler": params.scheduler,
                "denoise": 1.0,
            }
        }),
    );

    // --- VAEDecode ---
    wf.insert(
        "8".into(),
        json!({
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": vae_ref}
        }),
    );

    let mut image_source = json!(["8", 0]);

    // --- Upscale ---
    if !params.upscale_model.is_empty() {
        wf.insert(
            "30".into(),
            json!({
                "class_type": "UpscaleModelLoader",
                "inputs": {"model_name": params.upscale_model}
            }),
        );
        wf.insert(
            "31".into(),
            json!({
                "class_type": "ImageUpscaleWithModel",
                "inputs": {"upscale_model": ["30", 0], "image": image_source}
            }),
        );
        image_source = json!(["31", 0]);
    }

    // --- Save / Preview ---
    // use_save_node=true → SaveImage (ComfyUI writes to output/)
    // use_save_node=false → PreviewImage (temp only, no residue)
    if use_save_node {
        wf.insert(
            "9".into(),
            json!({
                "class_type": "SaveImage",
                "inputs": {"images": image_source, "filename_prefix": "ComfyUI"}
            }),
        );
    } else {
        wf.insert(
            "9".into(),
            json!({
                "class_type": "PreviewImage",
                "inputs": {"images": image_source}
            }),
        );
    }

    Value::Object(wf)
}

// ---------------------------------------------------------------------------
// build_gen_params
// ---------------------------------------------------------------------------

pub fn build_gen_params(params: &SimpleParams, actual_seed: i64) -> Value {
    json!({
        "schema_version": 1,
        "loader_type": if params.diffusion_model.is_empty() { "checkpoint" } else { "unet" },
        "ckpt_name": params.ckpt_name,
        "diffusion_model": params.diffusion_model,
        "vae_name": params.vae_name,
        "text_encoder_1": params.text_encoder_1,
        "text_encoder_2": params.text_encoder_2,
        "clip_type": params.clip_type,
        "weight_dtype": params.weight_dtype,
        "steps": params.steps,
        "cfg": params.cfg,
        "sampler_name": params.sampler_name,
        "scheduler": params.scheduler,
        "seed": actual_seed,
        "width": params.width,
        "height": params.height,
        "denoise": 1.0,
        "loras": params.loras.iter().map(|l| json!({
            "name": l.name,
            "strength_model": l.strength_model,
            "strength_clip": l.strength_clip,
        })).collect::<Vec<_>>(),
        "text_encoder_kind": params.te_kind.to_string(),
        "a1111_mode": params.a1111_mode,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_params_expands_client_wildcards() {
        let params = parse_params(
            &json!({
                "prompt": "a __subject__",
                "negative_prompt": "__bad__",
                "expand_wildcards": true,
                "client_wildcards": {
                    "subject": ["cat"],
                    "bad": ["blur"]
                },
                "seed": 1
            }),
            4,
            None,
            "",
        )
        .expect("expand_wildcards should be accepted");

        assert_eq!(params.prompt, "a cat");
        assert_eq!(params.negative_prompt, "blur");
    }
}

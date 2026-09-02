use axum::{
    extract::{Extension, Multipart, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use base64::{engine::general_purpose::STANDARD as B64, Engine};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::Read;

use crate::config_io::{load as load_config_json, write as write_config_json};
use crate::{
    auth::scope::{require_admin_scope, AuthContext},
    secret_store,
    state::SharedState,
};

const EXT_NAME: &str = "builtin-nai-bridge";
const NAI_IMAGE_BASE: &str = "https://image.novelai.net";
const NAI_USER_AGENT: &str = "yu-ai-manager/1.0";
// Seconds to wait for /ai/generate-image. NAI charges Anlas once the request
// reaches its backend, so giving up early loses the image *and* the Anlas —
// a generous ceiling is cheaper than a premature cut. V5 spends noticeably
// longer in the tokenizer than V4.5, so 120s was no longer enough.
// Mirror: extensions/builtin_nai_bridge/core_impl/nai_client.py
// GENERATE_TIMEOUT_SEC.
const GENERATE_TIMEOUT_SEC: u64 = 300;
const MAX_VIBE_BYTES: usize = 32 * 1024 * 1024;

static MODELS: &[(&str, &str)] = &[
    ("nai-diffusion-5-full", "NAI Diffusion 5 Full"),
    ("nai-diffusion-5-curated", "NAI Diffusion 5 Curated"),
    ("nai-diffusion-4-5-full", "NAI Diffusion 4.5 Full"),
    ("nai-diffusion-4-5-curated", "NAI Diffusion 4.5 Curated"),
    ("nai-diffusion-4-full", "NAI Diffusion 4 Full"),
    ("nai-diffusion-4-curated-preview", "NAI Diffusion 4 Curated"),
];

// MODELS is ordered newest-first for the UI; the default is pinned so a newly
// added model never silently becomes the default.
const DEFAULT_MODEL: &str = "nai-diffusion-4-5-full";

// Variety+ (skip_cfg_above_sigma) uses a lower cutoff on the V4 base models.
// Anything newer (4.5, 5, ...) uses the higher one, so list the exceptions
// rather than pattern-matching the version out of the model id.
static V4_BASE_MODELS: &[&str] = &["nai-diffusion-4-full", "nai-diffusion-4-curated-preview"];

static SAMPLERS: &[(&str, &str)] = &[
    ("k_euler_ancestral", "Euler Ancestral"),
    ("k_euler", "Euler"),
    ("k_dpmpp_2m", "DPM++ 2M"),
    ("k_dpmpp_sde", "DPM++ SDE"),
    ("k_dpmpp_2s_ancestral", "DPM++ 2S Ancestral"),
    ("ddim", "DDIM"),
];

static NOISE_SCHEDULES: &[(&str, &str)] = &[
    ("karras", "Karras"),
    ("exponential", "Exponential"),
    ("polyexponential", "Polyexponential"),
    ("native", "Native"),
];

static IMAGE_FORMATS: &[&str] = &["png", "webp", "jpg"];
static SAVE_NAMING_OPTIONS: &[&str] = &["daily_folder", "flat", "by_model"];

fn ext_config(state: &SharedState) -> Value {
    let full = load_config_json(&state.config.config_path);
    full.get("extensions")
        .and_then(|e| e.get(EXT_NAME))
        .cloned()
        .unwrap_or_else(|| json!({}))
}

fn cfg_str<'a>(cfg: &'a Value, key: &str, default: &'a str) -> &'a str {
    cfg.get(key).and_then(Value::as_str).unwrap_or(default)
}

fn cfg_bool(cfg: &Value, key: &str, default: bool) -> bool {
    cfg.get(key).and_then(Value::as_bool).unwrap_or(default)
}

fn cfg_f64(cfg: &Value, key: &str, default: f64) -> f64 {
    cfg.get(key).and_then(Value::as_f64).unwrap_or(default)
}

fn get_token(state: &SharedState) -> Result<String, &'static str> {
    let cfg = ext_config(state);
    let raw = cfg_str(&cfg, "api_token", "");
    if raw.is_empty() {
        return Err("API token is not configured");
    }
    Ok(secret_store::decrypt(raw, &state.config.project_root))
}

fn mask_secret(s: &str) -> String {
    if s.is_empty() {
        return String::new();
    }
    let prefix = &s[..s.len().min(4)];
    format!("{prefix}**********")
}

// ── response helpers ──────────────────────────────────────────────────────────

// Matches Python's api_success(payload): `{"ok": True, "error": None, "data": None}`
// updated with the payload dict — so payload keys win, including `data` itself.
// The base must be inserted first for that to hold; the sibling helper in
// `sd_webui_bridge.rs` does the same.
fn api_ok(data: Value) -> Json<Value> {
    let mut body = serde_json::Map::new();
    body.insert("ok".to_string(), json!(true));
    body.insert("error".to_string(), json!(null));
    body.insert("data".to_string(), json!(null));
    if let Some(obj) = data.as_object() {
        for (k, v) in obj {
            body.insert(k.clone(), v.clone());
        }
    }
    Json(Value::Object(body))
}

fn api_err(msg: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": msg}))).into_response()
}

fn api_err_code(msg: &str, status: StatusCode, code: &str) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": msg, "code": code})),
    )
        .into_response()
}

fn admin_guard(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0))
}

// ── NAI HTTP helpers ──────────────────────────────────────────────────────────

// Byte-slicing a String at a fixed length can panic if the cut point falls
// inside a multi-byte UTF-8 character (upstream error bodies are untrusted
// and may be non-ASCII). Walk back to the nearest char boundary instead.
fn truncate_str(s: &str, max_bytes: usize) -> &str {
    if s.len() <= max_bytes {
        return s;
    }
    let mut end = max_bytes;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    &s[..end]
}

// Persistent API tokens (`pst-...`) are scoped to `image.novelai.net` --
// `api.novelai.net` rejects them with a 400 even when the token itself is
// valid, so this must hit the image host like `nai_generate_raw` below.
async fn nai_get_subscription(
    client: &reqwest::Client,
    token: &str,
) -> Result<Value, (StatusCode, String)> {
    let resp = client
        .get(format!("{NAI_IMAGE_BASE}/user/subscription"))
        .header("Authorization", format!("Bearer {token}"))
        .header("User-Agent", NAI_USER_AGENT)
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| (StatusCode::BAD_GATEWAY, e.to_string()))?;
    let status = resp.status();
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err((StatusCode::UNAUTHORIZED, "Invalid API token (401)".into()));
    }
    if !status.is_success() {
        let snip = resp.text().await.unwrap_or_default();
        let msg = format!("HTTP {status}")
            + if snip.trim().is_empty() {
                String::new()
            } else {
                format!(" — {}", truncate_str(&snip, 400))
            }
            .as_str();
        let out_status = StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
        return Err((out_status, msg));
    }
    resp.json::<Value>()
        .await
        .map_err(|e| (StatusCode::BAD_GATEWAY, e.to_string()))
}

fn extract_anlas(sub: &Value) -> i64 {
    sub.get("trainingStepsLeft")
        .and_then(|t| t.get("fixedTrainingStepsLeft"))
        .and_then(Value::as_i64)
        .unwrap_or(0)
}

/// V5 Opus Usage Limit block from the subscription response, verbatim.
///
/// Shape: `{"percent": int, "isNegative": bool, "timeUntilNextPercent": int}`.
/// Absent on non-Opus tiers or if NAI has not rolled it out to the account.
/// Also `None` if present but "percent" is missing or not a number -- a
/// block that cannot be evaluated for exhaustion must not be treated as
/// "not exhausted".
fn extract_usage(sub: &Value) -> Option<Value> {
    let usage = sub.get("usage")?;
    if !usage.is_object() {
        return None;
    }
    usage.get("percent")?.as_f64()?;
    Some(usage.clone())
}

/// Whether the V5 Opus Usage Limit is exhausted (would fall back to Anlas).
fn usage_exhausted(usage: &Value) -> bool {
    // Match extract_usage's as_f64 read: percent is guaranteed numeric by
    // extract_usage, but as_i64 rejects a float like 0.0, which would
    // silently fall back to the "not exhausted" default of 100 below and
    // let a genuinely exhausted (fractional-percent) account through.
    let percent = usage
        .get("percent")
        .and_then(Value::as_f64)
        .unwrap_or(100.0);
    let is_negative = usage
        .get("isNegative")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    percent <= 0.0 || is_negative
}

/// Whether a generation at this resolution/steps falls in the Opus free tier.
///
/// Mirrors NovelAI's Opus Usage Limit eligibility rule: normal resolution
/// (<= Normal Square pixel count) and steps <= 28. Independent of model --
/// callers must additionally check the model is V5, since the Usage Limit
/// (and its free tier) is a V5-only mechanism. Mirror of
/// `is_opus_free_generation` in `extensions/builtin_nai_bridge/core_impl/nai_cost.py`.
fn is_opus_free_generation(width: u32, height: u32, steps: u32) -> bool {
    const NORMAL_SQUARE_PX: u64 = 1024 * 1024;
    steps <= 28 && (width as u64) * (height as u64) <= NORMAL_SQUARE_PX
}

async fn nai_generate_raw(
    client: &reqwest::Client,
    token: &str,
    body: &Value,
) -> Result<Vec<u8>, String> {
    let resp = client
        .post(format!("{NAI_IMAGE_BASE}/ai/generate-image"))
        .header("Authorization", format!("Bearer {token}"))
        .header("User-Agent", NAI_USER_AGENT)
        .timeout(std::time::Duration::from_secs(GENERATE_TIMEOUT_SEC))
        .json(body)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let status = resp.status();
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err("Invalid API token (401)".into());
    }
    if status.as_u16() == 402 {
        return Err("Insufficient Anlas (402)".into());
    }
    if !status.is_success() {
        let snip = resp.text().await.unwrap_or_default();
        return Err(format!(
            "NAI API error: HTTP {status} — {}",
            truncate_str(&snip, 400)
        ));
    }
    resp.bytes()
        .await
        .map(|b| b.to_vec())
        .map_err(|e| e.to_string())
}

fn extract_images_from_zip(zip_bytes: &[u8], preferred_ext: &str) -> Result<Vec<Vec<u8>>, String> {
    let cursor = std::io::Cursor::new(zip_bytes);
    let mut archive = zip::ZipArchive::new(cursor).map_err(|e| e.to_string())?;
    let mut all: Vec<(String, Vec<u8>)> = Vec::new();
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| e.to_string())?;
        let name = file.name().to_lowercase();
        if name.ends_with(".png")
            || name.ends_with(".webp")
            || name.ends_with(".jpg")
            || name.ends_with(".jpeg")
        {
            let mut buf = Vec::new();
            file.read_to_end(&mut buf).map_err(|e| e.to_string())?;
            all.push((name, buf));
        }
    }
    if all.is_empty() {
        return Err("No images in response".into());
    }
    let ext = format!(".{preferred_ext}");
    let preferred: Vec<Vec<u8>> = all
        .iter()
        .filter(|(n, _)| n.ends_with(&ext))
        .map(|(_, b)| b.clone())
        .collect();
    Ok(if preferred.is_empty() {
        all.into_iter().map(|(_, b)| b).collect()
    } else {
        preferred
    })
}

// ── generate request body ─────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct PreciseRef {
    image: String,
    #[serde(default = "one_f64")]
    information_extracted: f64,
    #[serde(default = "one_f64")]
    strength: f64,
    #[serde(rename = "type")]
    ref_type: Option<String>,
}
fn one_f64() -> f64 {
    1.0
}

#[derive(Debug, Deserialize, Serialize)]
struct CharEntry {
    prompt: Option<String>,
    negative: Option<String>,
    center: Option<Value>,
}

#[derive(Debug, Deserialize)]
struct GenRequest {
    prompt: String,
    #[serde(default)]
    negative_prompt: String,
    model: Option<String>,
    width: Option<u32>,
    height: Option<u32>,
    steps: Option<u32>,
    scale: Option<f64>,
    sampler: Option<String>,
    noise_schedule: Option<String>,
    #[serde(default = "neg_one_i64")]
    seed: i64,
    cfg_rescale: Option<f64>,
    n_samples: Option<u32>,
    quality_toggle: Option<bool>,
    mode: Option<String>,
    uc_preset: Option<u64>,
    dynamic_thresholding: Option<bool>,
    uncond_scale: Option<f64>,
    variety_boost: Option<bool>,
    image_format: Option<String>,
    image: Option<String>,
    mask: Option<String>,
    strength: Option<f64>,
    noise: Option<f64>,
    reference_image: Option<String>,
    reference_information_extracted: Option<f64>,
    reference_strength: Option<f64>,
    reference_image_multiple: Option<Vec<PreciseRef>>,
    characters: Option<Vec<CharEntry>>,
    sweep_meta: Option<Value>,
    #[serde(default)]
    skip_save: bool,
    client_wildcards: Option<Value>,
}
fn neg_one_i64() -> i64 {
    -1
}

fn resolve_seed(seed: i64) -> u64 {
    // A negative seed is the "random" sentinel.
    u64::try_from(seed).unwrap_or_else(|_| u64::from(rand::random::<u32>()))
}

/// Round a pixel dimension to the nearest multiple of 64.
///
/// Stable Diffusion derived models (NAI included) downscale by 8 in the VAE
/// and again inside the UNet, so the API rejects dimensions that are not a
/// multiple of 64. Mirrors `_snap64` in
/// `extensions/builtin_nai_bridge/core_impl/nai_api_generate.py`.
fn snap64(val: u32) -> u32 {
    ((val + 32) / 64 * 64).max(64)
}

/// NovelAI undesired-content presets and quality tags, verbatim from the UI.
///
/// NovelAI's web UI expands both client side before sending: the UC preset
/// text is prepended to the undesired content ("Added to the beginning of
/// the UC") and the quality tags are appended to the prompt ("Added to the
/// end of the prompt"). The `ucPreset` integer and `qualityToggle` boolean
/// that travel alongside them are metadata, not instructions — a client
/// that only sends those applies neither.
///
/// Mirror: `extensions/builtin_nai_bridge/core_impl/nai_uc_presets.py`.
/// `tests/test_nai_uc_presets.py` fails if the two sides drift apart.
const UC_HEAVY: u64 = 0;
const UC_LIGHT: u64 = 1;
const UC_NONE: u64 = 2;
const UC_HUMAN_FOCUS: u64 = 3;
const UC_FURRY_FOCUS: u64 = 4;

const GEN_V5: &str = "v5";
const GEN_V45: &str = "v45";
const GEN_V4: &str = "v4";

/// V5 undesired-content presets.
static UC_PRESETS_V5: &[(u64, &str)] = &[
    (
        UC_HEAVY,
        "lowres, artistic error, film grain, scan artifacts, worst quality, \
bad quality, jpeg artifacts, very displeasing, chromatic aberration, \
dithering, halftone, screentone, multiple views, logo, \
too many watermarks, negative space, blank page",
    ),
    (
        UC_LIGHT,
        "lowres, bad hands, bad anatomy, artistic error, sepia, white haze, \
worst quality, very displeasing, jpeg artifacts, 0::ai-generated::",
    ),
    (UC_NONE, ""),
    (
        UC_HUMAN_FOCUS,
        "lowres, artistic error, film grain, scan artifacts, worst quality, \
bad quality, jpeg artifacts, very displeasing, chromatic aberration, \
dithering, halftone, screentone, multiple views, logo, \
too many watermarks, negative space, blank page, @_@, \
mismatched pupils, glowing eyes, bad anatomy",
    ),
    (
        UC_FURRY_FOCUS,
        "{worst quality}, distracting watermark, unfinished, bad quality, \
{widescreen}, upscale, {sequence}, {{grandfathered content}}, \
blurred foreground, chromatic aberration, sketch, everyone, \
[sketch background], simple, [flat colors], ych (character), \
outline, multiple scenes, [[horror (theme)]], comic",
    ),
];

/// V4.5 undesired-content presets. Furry Focus is absent because V4.5's UC
/// preset list no longer offers it — not for want of capturing it. The
/// Anime/Furry switch does not change these texts: both modes show the same
/// wording, so one table per generation is the whole story.
static UC_PRESETS_V45: &[(u64, &str)] = &[
    (
        UC_HEAVY,
        "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, \
worst quality, bad quality, jpeg artifacts, very displeasing, \
chromatic aberration, halftone, multiple views, logo, \
too many watermarks, negative space, blank page",
    ),
    (
        UC_LIGHT,
        "blurry, lowres, upscaled, artistic error, scan artifacts, \
jpeg artifacts, logo, too many watermarks, negative space, blank page",
    ),
    (UC_NONE, ""),
    (
        UC_HUMAN_FOCUS,
        "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, \
bad anatomy, bad hands, worst quality, bad quality, jpeg artifacts, \
very displeasing, chromatic aberration, halftone, multiple views, \
logo, too many watermarks, @_@, mismatched pupils, glowing eyes, \
negative space, blank page",
    ),
];

/// V4 undesired-content presets. V4 offers Heavy / Light / None only — no
/// focus presets.
static UC_PRESETS_V4: &[(u64, &str)] = &[
    (
        UC_HEAVY,
        "blurry, lowres, error, film grain, scan artifacts, worst quality, \
bad quality, jpeg artifacts, very displeasing, chromatic aberration, \
logo, dated, signature, multiple views, gigantic breasts, \
white blank page, blank page",
    ),
    (
        UC_LIGHT,
        "blurry, lowres, error, worst quality, bad quality, jpeg artifacts, \
very displeasing, logo, dated, signature, white blank page, blank page",
    ),
    (UC_NONE, ""),
];

/// Quality Tags ("Standard"), appended to the end of the prompt.
static QUALITY_TAGS: &[(&str, &str)] = &[
    (GEN_V5, "very aesthetic, masterpiece, no text"),
    (
        GEN_V45,
        "very aesthetic, masterpiece, no text, -0.8::feet::, rating:general",
    ),
    (
        GEN_V4,
        "rating:general, best quality, very aesthetic, absurdres",
    ),
];

/// Generation key for `model`.
///
/// The V4 text was captured from one V4 model and is applied to both
/// `nai-diffusion-4-full` and `nai-diffusion-4-curated-preview`.
fn model_generation(model: &str) -> Option<&'static str> {
    if model.starts_with("nai-diffusion-5") {
        Some(GEN_V5)
    } else if model.starts_with("nai-diffusion-4-5") {
        Some(GEN_V45)
    } else if model.starts_with("nai-diffusion-4") {
        Some(GEN_V4)
    } else {
        None
    }
}

fn uc_table(model: &str) -> Option<&'static [(u64, &'static str)]> {
    match model_generation(model)? {
        GEN_V5 => Some(UC_PRESETS_V5),
        GEN_V45 => Some(UC_PRESETS_V45),
        GEN_V4 => Some(UC_PRESETS_V4),
        _ => None,
    }
}

/// Prepend the UC preset to `negative_prompt`, mirroring the NovelAI UI.
///
/// Returns `(negative_prompt, uc_preset)`. The reported preset becomes
/// [`UC_NONE`] whenever text was prepended, so the server cannot apply it a
/// second time. A model whose generation has no recorded text is left alone,
/// except that selector values that generation does not offer are reported as
/// [`UC_NONE`] rather than forwarded — an unverified integer would ask for
/// some undesired preset, not for none.
fn expand_uc_preset(model: &str, uc_preset: u64, negative_prompt: &str) -> (String, u64) {
    let Some(table) = uc_table(model) else {
        let reported = if uc_preset == UC_HUMAN_FOCUS || uc_preset == UC_FURRY_FOCUS {
            UC_NONE
        } else {
            uc_preset
        };
        return (negative_prompt.to_string(), reported);
    };

    let text = table
        .iter()
        .find(|(id, _)| *id == uc_preset)
        .map(|(_, t)| *t)
        .unwrap_or("");
    if text.is_empty() {
        // Unknown-for-this-generation or explicitly None: apply nothing.
        return (negative_prompt.to_string(), UC_NONE);
    }

    let existing = negative_prompt.trim();
    let merged = if existing.is_empty() {
        text.to_string()
    } else {
        format!("{text}, {existing}")
    };
    (merged, UC_NONE)
}

/// Dataset mode. NovelAI folded the Furry model into the base model; the
/// UI's Anime/Furry switch has no API flag of its own — Furry mode simply
/// puts the `fur dataset` tag at the very start of the base prompt.
const MODE_ANIME: &str = "anime";
const MODE_FURRY: &str = "furry";

static MODE_PREFIXES: &[(&str, &str)] = &[(MODE_ANIME, ""), (MODE_FURRY, "fur dataset")];

/// Put the dataset-mode tag at the very start of `prompt`.
///
/// NovelAI documents that the tag only works from the start of the base
/// prompt. An unknown mode is treated as Anime (no prefix) rather than
/// guessed at.
fn expand_mode_prefix(mode: &str, prompt: &str) -> String {
    let prefix = MODE_PREFIXES
        .iter()
        .find(|(m, _)| *m == mode)
        .map(|(_, p)| *p)
        .unwrap_or("");
    if prefix.is_empty() {
        return prompt.to_string();
    }
    let existing = prompt.trim();
    if existing.is_empty() {
        prefix.to_string()
    } else {
        format!("{prefix}, {existing}")
    }
}

/// Append the quality tags to `prompt`, mirroring the NovelAI UI.
///
/// Returns `(prompt, quality_toggle)`. The reported toggle becomes `false`
/// once the tags are in the prompt so they cannot be applied twice. A model
/// generation with no recorded tags is left untouched.
fn expand_quality_tags(model: &str, quality_toggle: bool, prompt: &str) -> (String, bool) {
    if !quality_toggle {
        return (prompt.to_string(), false);
    }
    let tags = model_generation(model)
        .and_then(|gen| QUALITY_TAGS.iter().find(|(g, _)| *g == gen))
        .map(|(_, t)| *t)
        .unwrap_or("");
    if tags.is_empty() {
        return (prompt.to_string(), quality_toggle);
    }

    let existing = prompt.trim();
    let merged = if existing.is_empty() {
        tags.to_string()
    } else {
        format!("{existing}, {tags}")
    };
    (merged, false)
}

fn build_char_captions(chars: Option<&[CharEntry]>) -> (Vec<Value>, Vec<Value>, bool) {
    let Some(chars) = chars else {
        return (vec![], vec![], false);
    };
    let mut pos = Vec::new();
    let mut neg = Vec::new();
    let mut use_coords = false;
    for entry in chars.iter().take(6) {
        let p = entry.prompt.as_deref().unwrap_or("").trim().to_string();
        if p.is_empty() {
            continue;
        }
        let n = entry.negative.as_deref().unwrap_or("").trim().to_string();
        let center = entry
            .center
            .clone()
            .unwrap_or_else(|| json!({"x": 0.5, "y": 0.5}));
        if entry.center.is_some() {
            use_coords = true;
        }
        pos.push(json!({"char_caption": p, "centers": [center]}));
        neg.push(json!({"char_caption": n, "centers": [center]}));
    }
    (pos, neg, use_coords)
}

fn build_request_body(req: &GenRequest) -> (Value, u64, String) {
    let model = req
        .model
        .as_deref()
        .filter(|m| MODELS.iter().any(|(id, _)| id == m))
        .unwrap_or(DEFAULT_MODEL)
        .to_string();
    let seed = resolve_seed(req.seed);
    let image_format = req
        .image_format
        .as_deref()
        .filter(|f| IMAGE_FORMATS.contains(f))
        .unwrap_or("png")
        .to_string();
    let steps = req.steps.map(|s| s.clamp(1, 50)).unwrap_or(28);
    let scale = req.scale.unwrap_or(5.0).clamp(0.0, 10.0);
    let cfg_rescale = req.cfg_rescale.unwrap_or(0.0).clamp(0.0, 1.0);
    let width = snap64(req.width.map(|w| w.clamp(64, 2048)).unwrap_or(832));
    let height = snap64(req.height.map(|h| h.clamp(64, 2048)).unwrap_or(1216));
    let sampler = req
        .sampler
        .as_deref()
        .filter(|s| SAMPLERS.iter().any(|(id, _)| id == s))
        .unwrap_or(SAMPLERS[0].0)
        .to_string();
    let noise_schedule = req
        .noise_schedule
        .as_deref()
        .filter(|n| NOISE_SCHEDULES.iter().any(|(id, _)| id == n))
        .unwrap_or(NOISE_SCHEDULES[0].0)
        .to_string();
    let quality_toggle = req.quality_toggle.unwrap_or(true);
    let uc_preset = req.uc_preset.unwrap_or(0);
    // NovelAI expands the UC preset and quality tags client side — prepending
    // the preset to the undesired content and appending the tags to the
    // prompt. Sending only the integer/boolean applies neither.
    let (negative_prompt, uc_preset) = expand_uc_preset(&model, uc_preset, &req.negative_prompt);
    // NovelAI's Furry mode is just the `fur dataset` tag at the very start of
    // the base prompt, and the quality tags go at the very end.
    let mode = req.mode.as_deref().unwrap_or(MODE_ANIME);
    let prompt = expand_mode_prefix(mode, &req.prompt);
    let (prompt, quality_toggle) = expand_quality_tags(&model, quality_toggle, &prompt);
    let dynamic_thresholding = req.dynamic_thresholding.unwrap_or(false);
    let uncond_scale = req.uncond_scale.unwrap_or(1.0);
    let variety_boost = req.variety_boost.unwrap_or(false);

    let (pos_chars, neg_chars, use_coords) = build_char_captions(req.characters.as_deref());

    let v4_prompt = json!({
        "caption": { "base_caption": &prompt, "char_captions": pos_chars },
        "use_coords": use_coords, "use_order": true,
    });
    let v4_negative = json!({
        "caption": { "base_caption": &negative_prompt, "char_captions": neg_chars },
        "use_coords": use_coords, "use_order": true,
    });

    let mut parameters = json!({
        "width": width, "height": height, "scale": scale,
        "sampler": sampler, "steps": steps, "seed": seed,
        "n_samples": 1u32, "noise_schedule": noise_schedule,
        "cfg_rescale": cfg_rescale, "sm": false, "sm_dyn": false,
        "skip_cfg_above_sigma": null, "dynamic_thresholding": dynamic_thresholding,
        "controlnet_strength": 1.0, "legacy": false, "add_original_image": true,
        "uncond_scale": uncond_scale, "qualityToggle": quality_toggle,
        "ucPreset": uc_preset, "negative_prompt": &negative_prompt,
        "params_version": 3, "v4_prompt": v4_prompt,
        "v4_negative_prompt": v4_negative, "use_coords": use_coords,
        "image_format": image_format,
    });

    if variety_boost {
        let sigma = if V4_BASE_MODELS.contains(&model.as_str()) {
            19.0_f64
        } else {
            58.0_f64
        };
        parameters["skip_cfg_above_sigma"] = json!(sigma);
    }

    // Reference images (vibe transfer + precise reference)
    let mut ref_imgs: Vec<String> = Vec::new();
    let mut ref_infos: Vec<f64> = Vec::new();
    let mut ref_strengths: Vec<f64> = Vec::new();
    let mut ref_types: Vec<String> = Vec::new();
    if let Some(img) = &req.reference_image {
        ref_imgs.push(img.clone());
        ref_infos.push(req.reference_information_extracted.unwrap_or(1.0));
        ref_strengths.push(req.reference_strength.unwrap_or(0.6));
        ref_types.push("character_and_style".into());
    }
    if let Some(refs) = &req.reference_image_multiple {
        for r in refs.iter().take(4) {
            ref_imgs.push(r.image.clone());
            ref_infos.push(r.information_extracted);
            ref_strengths.push(r.strength);
            let t = r.ref_type.as_deref().unwrap_or("character_and_style");
            let valid = ["character_and_style", "character", "style"];
            ref_types.push(
                if valid.contains(&t) {
                    t
                } else {
                    "character_and_style"
                }
                .into(),
            );
        }
    }
    if !ref_imgs.is_empty() {
        let p = parameters.as_object_mut().unwrap();
        p.insert("reference_image_multiple".into(), json!(ref_imgs));
        p.insert(
            "reference_information_extracted_multiple".into(),
            json!(ref_infos),
        );
        p.insert("reference_strength_multiple".into(), json!(ref_strengths));
        p.insert("use_type_multiple".into(), json!(ref_types));
    }

    let action = match (&req.image, &req.mask) {
        (Some(img), Some(msk)) => {
            let p = parameters.as_object_mut().unwrap();
            p.insert("image".into(), json!(img));
            p.insert("mask".into(), json!(msk));
            p.insert("strength".into(), json!(req.strength.unwrap_or(0.7)));
            p.insert("noise".into(), json!(req.noise.unwrap_or(0.0)));
            p.insert("extra_noise_seed".into(), json!(seed));
            "inpaint"
        }
        (Some(img), None) => {
            let p = parameters.as_object_mut().unwrap();
            p.insert("image".into(), json!(img));
            p.insert("strength".into(), json!(req.strength.unwrap_or(0.7)));
            p.insert("noise".into(), json!(req.noise.unwrap_or(0.0)));
            p.insert("extra_noise_seed".into(), json!(seed));
            "img2img"
        }
        _ => "generate",
    };

    let body = json!({
        "input": &prompt,
        "model": model,
        "action": action,
        "parameters": parameters,
    });
    (body, seed, image_format)
}

// ── vibe file parser ──────────────────────────────────────────────────────────

const VIBE_IDENT: &str = "novelai-vibe-transfer";
const BUNDLE_IDENT: &str = "novelai-vibe-transfer-bundle";

fn short_to_model(short: &str) -> Option<&'static str> {
    match short {
        "v4-5full" => Some("nai-diffusion-4-5-full"),
        "v4-5curated" => Some("nai-diffusion-4-5-curated"),
        "v4full" => Some("nai-diffusion-4-full"),
        "v4curated" => Some("nai-diffusion-4-curated-preview"),
        _ => None,
    }
}

#[derive(Debug)]
struct VibeEntry {
    information_extracted: f64,
    blob_b64: String,
}

#[derive(Debug)]
struct ParsedVibe {
    model: String,
    source_image_b64: String,
    source_image_mime: &'static str,
    import_strength: f64,
    entries: Vec<VibeEntry>,
}

fn parse_single_vibe(data: &[u8]) -> Result<ParsedVibe, String> {
    let obj: Value = serde_json::from_slice(data).map_err(|e| format!("not valid JSON: {e}"))?;
    let map = obj.as_object().ok_or("expected JSON object")?;

    if map.get("identifier").and_then(Value::as_str) != Some(VIBE_IDENT) {
        return Err(format!("identifier mismatch: expected {VIBE_IDENT:?}"));
    }
    let img_b64 = map
        .get("image")
        .and_then(Value::as_str)
        .ok_or("missing 'image' field")?;
    let img_bytes = B64
        .decode(img_b64)
        .map_err(|e| format!("'image' not valid base64: {e}"))?;
    let mime = if img_bytes.starts_with(b"\x89PNG") {
        "image/png"
    } else {
        "image/jpeg"
    };

    let import_info_obj = map.get("importInfo").and_then(Value::as_object);
    let full_model = import_info_obj
        .and_then(|m| m.get("model"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let import_info = import_info_obj
        .and_then(|m| m.get("information_extracted"))
        .and_then(Value::as_f64)
        .unwrap_or(1.0);
    let import_strength = import_info_obj
        .and_then(|m| m.get("strength"))
        .and_then(Value::as_f64)
        .unwrap_or(0.6);

    let encodings = map
        .get("encodings")
        .and_then(Value::as_object)
        .filter(|e| !e.is_empty())
        .ok_or("missing or empty 'encodings'")?;

    let mut entries: Vec<VibeEntry> = Vec::new();
    let mut resolved_model = full_model.clone();

    for (short, enc_map) in encodings.iter().take(10) {
        let Some(enc_map) = enc_map.as_object() else {
            continue;
        };
        if let Some(m) = short_to_model(short) {
            resolved_model = m.to_string();
        } else if !full_model.is_empty() {
            resolved_model = full_model.clone();
        }
        for (_hash, enc_entry) in enc_map.iter().take(50) {
            let Some(enc) = enc_entry.as_object() else {
                continue;
            };
            let Some(b64) = enc.get("encoding").and_then(Value::as_str) else {
                continue;
            };
            if B64.decode(b64).is_err() {
                continue;
            }
            let params = enc.get("params").and_then(Value::as_object);
            let info = params
                .and_then(|p| p.get("information_extracted"))
                .and_then(Value::as_f64)
                .unwrap_or(import_info);
            let info = (info * 100.0).round() / 100.0;
            entries.push(VibeEntry {
                information_extracted: info,
                blob_b64: b64.to_string(),
            });
        }
    }
    if entries.is_empty() {
        return Err("no valid encoding entries".into());
    }
    entries.sort_by(|a, b| {
        a.information_extracted
            .partial_cmp(&b.information_extracted)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    Ok(ParsedVibe {
        model: if resolved_model.is_empty() {
            "nai-diffusion-4-5-full".into()
        } else {
            resolved_model
        },
        source_image_b64: img_b64.to_string(),
        source_image_mime: mime,
        import_strength,
        entries,
    })
}

fn parse_vibe_any(data: &[u8]) -> Result<Vec<ParsedVibe>, String> {
    if data.is_empty() {
        return Err("empty input".into());
    }
    let obj: Value = serde_json::from_slice(data).map_err(|e| format!("not valid JSON: {e}"))?;
    let ident = obj.get("identifier").and_then(Value::as_str).unwrap_or("");

    if ident == BUNDLE_IDENT {
        let vibes = obj
            .get("vibes")
            .and_then(Value::as_array)
            .filter(|v| !v.is_empty())
            .ok_or("missing or empty 'vibes'")?;
        if vibes.len() > 20 {
            return Err(format!("bundle has {} vibes; max 20", vibes.len()));
        }
        let mut out = Vec::new();
        for (i, v) in vibes.iter().enumerate() {
            match serde_json::to_vec(v)
                .map_err(|e| e.to_string())
                .and_then(|b| parse_single_vibe(&b))
            {
                Ok(p) => out.push(p),
                Err(e) => tracing::warn!("nai_bridge: bundle entry {i} invalid: {e}"),
            }
        }
        if out.is_empty() {
            return Err("bundle had no valid vibe entries".into());
        }
        Ok(out)
    } else if ident == VIBE_IDENT {
        Ok(vec![parse_single_vibe(data)?])
    } else {
        Err(format!("unrecognised identifier: {ident:?}"))
    }
}

// ── route handlers ────────────────────────────────────────────────────────────

async fn info() -> Json<Value> {
    api_ok(json!({
        "bridge_id": "nai",
        "name": "NovelAI Image Generation Bridge",
        "version": "1.0",
    }))
}

async fn test_connection(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let token = match get_token(&state) {
        Ok(t) => t,
        Err(e) => return api_err(e, StatusCode::BAD_REQUEST),
    };
    match nai_get_subscription(&state.inference_client, &token).await {
        Ok(sub) => api_ok(json!({
            "ok": true,
            "anlas": extract_anlas(&sub),
            "tier": sub.get("tier").and_then(Value::as_i64).unwrap_or(0),
            "usage": extract_usage(&sub),
        }))
        .into_response(),
        Err((status, e)) => api_err(&e, status),
    }
}

async fn anlas(State(state): State<SharedState>, auth: Option<Extension<AuthContext>>) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let token = match get_token(&state) {
        Ok(t) => t,
        Err(e) => return api_err(e, StatusCode::BAD_REQUEST),
    };
    match nai_get_subscription(&state.inference_client, &token).await {
        Ok(sub) => api_ok(json!({
            "anlas": extract_anlas(&sub),
            "usage": extract_usage(&sub),
        }))
        .into_response(),
        Err((status, e)) => api_err(&e, status),
    }
}

async fn models_list() -> Json<Value> {
    api_ok(json!({
        "models": MODELS.iter().map(|(id, name)| json!({"id": id, "name": name})).collect::<Vec<_>>()
    }))
}

async fn samplers_list() -> Json<Value> {
    api_ok(json!({
        "samplers": SAMPLERS.iter().map(|(id, name)| json!({"id": id, "name": name})).collect::<Vec<_>>()
    }))
}

async fn noise_schedules_list() -> Json<Value> {
    api_ok(json!({
        "noise_schedules": NOISE_SCHEDULES.iter().map(|(id, name)| json!({"id": id, "name": name})).collect::<Vec<_>>()
    }))
}

async fn generate(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(mut req): Json<GenRequest>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let token = match get_token(&state) {
        Ok(t) => t,
        Err(e) => return api_err(e, StatusCode::BAD_REQUEST),
    };
    if req.prompt.trim().is_empty() {
        return api_err("prompt is required", StatusCode::BAD_REQUEST);
    }
    // NAI does not interpret __wc__ or {a|b|c} syntax itself, so wildcard/dynamic-prompt
    // expansion always runs here regardless of `expand_wildcards` (mirrors Python
    // nai_api_generate.handle_generate, which calls maybe_expand_prompt(..., True, ...)
    // unconditionally). The NAI bridge frontend never sends `expand_wildcards` at all,
    // so gating on it silently sent literal `__wc__` prompts straight to NAI.
    {
        // A negative seed is the "random" sentinel: None, never a wrapped value.
        let seed = u64::try_from(req.seed).ok();
        let client_body =
            json!({"client_wildcards": req.client_wildcards.clone().unwrap_or(Value::Null)});
        let wildcards = crate::prompt_sim_core::bridge_wildcards(
            state.config.config_path.to_str().unwrap_or_default(),
            crate::routes::comfyui_bridge::simple_builder::client_wildcards(&client_body),
        );
        req.prompt = crate::prompt_sim_core::expand_dynamic_prompt(&req.prompt, seed, &wildcards);
        req.negative_prompt =
            crate::prompt_sim_core::expand_dynamic_prompt(&req.negative_prompt, seed, &wildcards);
    }

    let started_at = std::time::Instant::now();
    let expanded_prompt = req.prompt.clone();
    let final_negative = req.negative_prompt.clone();
    let characters = req.characters.as_ref().map(|chars| json!(chars));
    let (body, seed, image_format) = build_request_body(&req);

    // V5 Opus Usage Limit guard: only applies to V5 models, and only to
    // requests that would actually draw from the free usage-limit tier
    // (normal resolution, <=28 steps) -- a higher-res/step V5 request always
    // costs Anlas regardless of the usage limit, so it is not gated here.
    // Mirror of the guard in nai_api_generate.handle_generate (Python).
    if cfg_bool(&ext_config(&state), "block_anlas_on_v5_limit", false) {
        let model = body.get("model").and_then(Value::as_str).unwrap_or("");
        let params = body.get("parameters");
        let width = params
            .and_then(|p| p.get("width"))
            .and_then(Value::as_u64)
            .and_then(|v| u32::try_from(v).ok())
            .unwrap_or(832);
        let height = params
            .and_then(|p| p.get("height"))
            .and_then(Value::as_u64)
            .and_then(|v| u32::try_from(v).ok())
            .unwrap_or(1216);
        let steps = params
            .and_then(|p| p.get("steps"))
            .and_then(Value::as_u64)
            .and_then(|v| u32::try_from(v).ok())
            .unwrap_or(28);
        if model_generation(model) == Some(GEN_V5) && is_opus_free_generation(width, height, steps)
        {
            // Fail closed on subscription-fetch failure: the user opted
            // into this guard specifically to avoid spending Anlas, so a
            // check that cannot complete must not silently let a spend
            // through. Mirrors nai_api_generate.handle_generate (Python).
            match nai_get_subscription(&state.inference_client, &token).await {
                Ok(sub) => match extract_usage(&sub) {
                    // "200 OK" alone is not enough: a subscription object
                    // with no "usage" block is just as unverifiable as a
                    // failed request (e.g. NAI hasn't rolled the field out
                    // yet, or the shape changed) -- both must block, not
                    // silently pass.
                    Some(usage) if usage_exhausted(&usage) => {
                        return api_err_code(
                            "NAI V5 usage limit exhausted; generation blocked to avoid \
                             spending Anlas (disable the block-on-limit option in Settings \
                             to allow Anlas fallback).",
                            StatusCode::LOCKED,
                            "nai_usage_limit_blocked",
                        );
                    }
                    Some(_) => {}
                    None => {
                        return api_err_code(
                            "Could not verify NAI V5 usage limit; generation blocked to \
                             avoid an unverified Anlas spend (disable the block-on-limit \
                             option in Settings to allow generation without this check): \
                             subscription response had no usage field",
                            StatusCode::BAD_GATEWAY,
                            "nai_usage_check_failed",
                        );
                    }
                },
                Err((_status, e)) => {
                    return api_err_code(
                        &format!(
                            "Could not verify NAI V5 usage limit; generation blocked to \
                             avoid an unverified Anlas spend (disable the block-on-limit \
                             option in Settings to allow generation without this check): {e}"
                        ),
                        StatusCode::BAD_GATEWAY,
                        "nai_usage_check_failed",
                    );
                }
            }
        }
    }

    let zip = match nai_generate_raw(&state.inference_client, &token, &body).await {
        Ok(z) => z,
        Err(e) => return api_err(&e, StatusCode::BAD_GATEWAY),
    };
    let images = match extract_images_from_zip(&zip, &image_format) {
        Err(e) => return api_err(&e, StatusCode::BAD_GATEWAY),
        Ok(v) => v,
    };

    // Bridge-managed save + sweep XMP (mirrors Python nai_api_generate logic)
    let cfg = ext_config(&state);
    let auto_save = cfg_bool(&cfg, "auto_save", false);
    let auto_import = cfg_bool(&cfg, "auto_import", true);
    let save_folder = cfg_str(&cfg, "save_folder", "").to_string();
    let save_naming = cfg_str(&cfg, "save_naming", "daily_folder").to_string();

    let mut saved_paths: Vec<String> = vec![];
    let mut saved_items: Option<Vec<Value>> = None;

    if !req.skip_save && auto_save && !save_folder.is_empty() {
        // bridge_save takes base64 strings; NAI gives us raw bytes — encode first
        let b64_images: Vec<String> = images.iter().map(|b| B64.encode(b)).collect();
        let pairs: Vec<(&str, i64)> = b64_images
            .iter()
            .map(|s| (s.as_str(), seed as i64))
            .collect();
        let (paths, _errs) = crate::routes::bridge_save::save_images_to_disk(
            &pairs,
            &save_folder,
            &image_format,
            &save_naming,
        );
        saved_paths = paths;

        if let Some(ref sv) = req.sweep_meta {
            if let Some(meta) = crate::routes::sweep_common::validate_sweep_meta(sv) {
                if !saved_paths.is_empty() {
                    crate::routes::sweep_common::write_sweep_xmp_to_paths(&saved_paths, &meta);
                    crate::routes::sweep_common::upsert_sweep_db(&state.db, &meta, &saved_paths)
                        .await;
                }
            }
        }
        if auto_import && !saved_paths.is_empty() {
            if req.sweep_meta.is_some() {
                let file_ids =
                    crate::routes::sweep_common::upsert_files_from_paths(&state, &saved_paths)
                        .await;
                saved_items = Some(crate::routes::sweep_common::saved_items_from_file_ids(
                    &saved_paths,
                    &file_ids,
                ));
            } else {
                let state_for_import = state.clone();
                let paths_for_import = saved_paths.clone();
                tokio::spawn(async move {
                    let _ = crate::routes::sweep_common::upsert_files_from_paths(
                        &state_for_import,
                        &paths_for_import,
                    )
                    .await;
                });
            }
        }
    }

    let out: Vec<Value> = images
        .iter()
        .map(|b| json!({"base64": B64.encode(b), "seed": seed}))
        .collect();
    let mut resp = json!({
        "images": out,
        "image_format": image_format,
        "elapsed_ms": u64::try_from(started_at.elapsed().as_millis()).unwrap_or(u64::MAX),
        "expanded_prompt": expanded_prompt,
        "final_negative": final_negative,
    });
    if let Some(chars) = characters {
        resp["characters"] = chars;
    }
    if !saved_paths.is_empty() {
        resp["saved"] = json!(saved_paths);
    }
    if let Some(si) = saved_items {
        resp["saved_items"] = json!(si);
    }
    api_ok(resp).into_response()
}

// ---------------------------------------------------------------------------
// save-batch — deferred sweep save (mirrors SD WebUI / ComfyUI bridge pattern)
// ---------------------------------------------------------------------------

async fn save_batch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body_json): Json<Value>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }

    let sweep_meta = body_json
        .get("sweep_meta")
        .and_then(crate::routes::sweep_common::validate_sweep_meta);

    let images: Vec<String> = body_json
        .get("images")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(Value::as_str)
                .map(String::from)
                .collect()
        })
        .unwrap_or_default();
    if images.is_empty() {
        return api_err(
            "images array is required and must be non-empty",
            StatusCode::BAD_REQUEST,
        );
    }
    let seeds: Vec<i64> = body_json
        .get("seeds")
        .and_then(Value::as_array)
        .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_default();
    let cfg = ext_config(&state);
    let auto_import = cfg_bool(&cfg, "auto_import", true);
    let save_folder = body_json
        .get("save_folder")
        .and_then(Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "save_folder", ""))
        .to_string();
    let save_naming = body_json
        .get("save_naming")
        .and_then(Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "save_naming", "daily_folder"))
        .to_string();
    let image_format = body_json
        .get("image_format")
        .and_then(Value::as_str)
        .unwrap_or("png")
        .to_string();
    if save_folder.is_empty() {
        return api_err("save_folder is required", StatusCode::BAD_REQUEST);
    }

    let pairs: Vec<(&str, i64)> = images
        .iter()
        .enumerate()
        .map(|(i, s)| (s.as_str(), seeds.get(i).copied().unwrap_or(-1)))
        .collect();
    let (saved_paths, errs) = crate::routes::bridge_save::save_images_to_disk(
        &pairs,
        &save_folder,
        &image_format,
        &save_naming,
    );

    if let Some(ref meta) = sweep_meta {
        if !saved_paths.is_empty() {
            crate::routes::sweep_common::write_sweep_xmp_to_paths(&saved_paths, meta);
            crate::routes::sweep_common::upsert_sweep_db(&state.db, meta, &saved_paths).await;
        }
    }
    let file_ids = if auto_import && !saved_paths.is_empty() {
        crate::routes::sweep_common::upsert_files_from_paths(&state, &saved_paths).await
    } else {
        Default::default()
    };

    let count = saved_paths.len();
    let saved_items: Vec<Value> =
        crate::routes::sweep_common::saved_items_from_file_ids(&saved_paths, &file_ids);
    api_ok(json!({
        "saved": saved_paths,
        "count": count,
        "errors": errs,
        "saved_items": saved_items,
    }))
    .into_response()
}

async fn vibe_upload(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    mut multipart: Multipart,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let mut file_data: Option<Vec<u8>> = None;
    loop {
        match multipart.next_field().await {
            Ok(Some(field)) if field.name() == Some("file") => match field.bytes().await {
                Ok(b) if b.len() > MAX_VIBE_BYTES => {
                    return api_err("file exceeds 32 MB limit", StatusCode::PAYLOAD_TOO_LARGE);
                }
                Ok(b) => {
                    file_data = Some(b.to_vec());
                    break;
                }
                Err(e) => {
                    return api_err(
                        &format!("failed to read upload: {e}"),
                        StatusCode::BAD_REQUEST,
                    );
                }
            },
            Ok(Some(_)) => continue,
            Ok(None) => break,
            Err(e) => {
                return api_err(&format!("multipart error: {e}"), StatusCode::BAD_REQUEST);
            }
        }
    }
    let data = match file_data {
        Some(d) => d,
        None => return api_err("file field is required", StatusCode::BAD_REQUEST),
    };
    match parse_vibe_any(&data) {
        Err(e) => api_err(
            &format!("not a valid vibe file: {e}"),
            StatusCode::BAD_REQUEST,
        ),
        Ok(vibes) => {
            let out: Vec<Value> = vibes
                .iter()
                .map(|v| {
                    json!({
                        "model": v.model,
                        "source_image_b64": v.source_image_b64,
                        "source_image_mime": v.source_image_mime,
                        "entries": v.entries.iter().map(|e| json!({
                            "information_extracted": e.information_extracted,
                            "strength": v.import_strength,
                            "cache_key": null,
                        })).collect::<Vec<_>>(),
                    })
                })
                .collect();
            api_ok(json!({"vibes": out})).into_response()
        }
    }
}

async fn get_config(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let raw_token = cfg_str(&cfg, "api_token", "").to_string();
    let masked = if raw_token.is_empty() {
        String::new()
    } else {
        mask_secret(&secret_store::decrypt(
            &raw_token,
            &state.config.project_root,
        ))
    };
    api_ok(json!({
        "api_token": masked,
        "auto_send": cfg_bool(&cfg, "auto_send", false),
        "default_model": cfg_str(&cfg, "default_model", DEFAULT_MODEL),
        "default_sampler": cfg_str(&cfg, "default_sampler", SAMPLERS[0].0),
        "default_noise_schedule": cfg_str(&cfg, "default_noise_schedule", NOISE_SCHEDULES[0].0),
        "save_folder": cfg_str(&cfg, "save_folder", ""),
        "auto_save": cfg_bool(&cfg, "auto_save", false),
        "save_naming": cfg_str(&cfg, "save_naming", "daily_folder"),
        "default_image_format": cfg_str(&cfg, "default_image_format", "png"),
        "auto_import": cfg_bool(&cfg, "auto_import", true),
        "cache_max_size_mb": cfg_f64(&cfg, "cache_max_size_mb", 500.0),
        "block_anlas_on_v5_limit": cfg_bool(&cfg, "block_anlas_on_v5_limit", false),
    }))
    .into_response()
}

#[derive(Debug, Deserialize)]
struct SaveConfigReq {
    api_token: Option<String>,
    auto_send: Option<bool>,
    default_model: Option<String>,
    default_sampler: Option<String>,
    default_noise_schedule: Option<String>,
    save_folder: Option<String>,
    auto_save: Option<bool>,
    save_naming: Option<String>,
    default_image_format: Option<String>,
    auto_import: Option<bool>,
    cache_max_size_mb: Option<Value>,
    block_anlas_on_v5_limit: Option<bool>,
}

async fn post_config(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(req): Json<SaveConfigReq>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let mut full = load_config_json(&state.config.config_path);
    if full.get("extensions").is_none() {
        full["extensions"] = json!({});
    }
    if full["extensions"].get(EXT_NAME).is_none() {
        full["extensions"][EXT_NAME] = json!({});
    }

    let mut saved: Vec<&'static str> = Vec::new();

    if let Some(raw) = &req.api_token {
        let raw = raw.trim();
        if raw.starts_with("enc:") {
            full["extensions"][EXT_NAME]["api_token"] = json!(raw);
            saved.push("api_token");
        } else if raw.is_empty() {
            full["extensions"][EXT_NAME]["api_token"] = json!("");
            saved.push("api_token");
        } else if raw.chars().all(|c| c == '*') || raw == "***" || raw == "****" {
            // masked sentinel — keep existing
        } else if raw.starts_with("pst-") {
            let enc = secret_store::encrypt(raw, &state.config.project_root);
            full["extensions"][EXT_NAME]["api_token"] = json!(enc);
            saved.push("api_token");
        }
    }
    macro_rules! save_bool {
        ($field:ident, $key:literal) => {
            if let Some(v) = req.$field {
                full["extensions"][EXT_NAME][$key] = json!(v);
                saved.push($key);
            }
        };
    }
    save_bool!(auto_send, "auto_send");
    save_bool!(auto_save, "auto_save");
    save_bool!(auto_import, "auto_import");
    save_bool!(block_anlas_on_v5_limit, "block_anlas_on_v5_limit");

    if let Some(v) = &req.default_model {
        let v = v.trim();
        if !MODELS.iter().any(|(id, _)| *id == v) {
            return api_err("default_model is invalid", StatusCode::BAD_REQUEST);
        }
        full["extensions"][EXT_NAME]["default_model"] = json!(v);
        saved.push("default_model");
    }
    if let Some(v) = &req.default_sampler {
        let v = v.trim();
        if !SAMPLERS.iter().any(|(id, _)| *id == v) {
            return api_err("default_sampler is invalid", StatusCode::BAD_REQUEST);
        }
        full["extensions"][EXT_NAME]["default_sampler"] = json!(v);
        saved.push("default_sampler");
    }
    if let Some(v) = &req.default_noise_schedule {
        let v = v.trim();
        if !NOISE_SCHEDULES.iter().any(|(id, _)| *id == v) {
            return api_err("default_noise_schedule is invalid", StatusCode::BAD_REQUEST);
        }
        full["extensions"][EXT_NAME]["default_noise_schedule"] = json!(v);
        saved.push("default_noise_schedule");
    }
    if let Some(v) = &req.save_folder {
        full["extensions"][EXT_NAME]["save_folder"] = json!(v.trim());
        saved.push("save_folder");
    }
    if let Some(v) = &req.save_naming {
        let v = v.trim();
        if !SAVE_NAMING_OPTIONS.contains(&v) {
            return api_err("save_naming is invalid", StatusCode::BAD_REQUEST);
        }
        full["extensions"][EXT_NAME]["save_naming"] = json!(v);
        saved.push("save_naming");
    }
    if let Some(v) = &req.default_image_format {
        let v = v.trim().to_lowercase();
        if !IMAGE_FORMATS.contains(&v.as_str()) {
            return api_err("default_image_format is invalid", StatusCode::BAD_REQUEST);
        }
        full["extensions"][EXT_NAME]["default_image_format"] = json!(v);
        saved.push("default_image_format");
    }
    if let Some(v) = &req.cache_max_size_mb {
        let mb = match v {
            Value::Number(n) => n.as_f64(),
            Value::String(s) => s.parse::<f64>().ok(),
            _ => None,
        };
        let Some(mb) = mb else {
            return api_err(
                "cache_max_size_mb must be a number",
                StatusCode::BAD_REQUEST,
            );
        };
        if !(0.0..=102400.0).contains(&mb) {
            return api_err(
                "cache_max_size_mb must be 0–102400",
                StatusCode::BAD_REQUEST,
            );
        }
        full["extensions"][EXT_NAME]["cache_max_size_mb"] = json!(mb);
        saved.push("cache_max_size_mb");
    }

    if saved.is_empty() {
        return api_err("No valid config fields provided", StatusCode::BAD_REQUEST);
    }
    if let Err(e) = write_config_json(&state.config.config_path, &full) {
        tracing::error!("nai_bridge: config write failed: {e}");
        return api_err("Failed to save config", StatusCode::INTERNAL_SERVER_ERROR);
    }
    api_ok(json!({"saved": saved})).into_response()
}

pub fn routes() -> Router<SharedState> {
    Router::new()
        .route("/ext/nai-bridge/info", get(info))
        .route("/ext/nai-bridge/api/test-connection", post(test_connection))
        .route("/ext/nai-bridge/api/anlas", get(anlas))
        .route("/ext/nai-bridge/api/models", get(models_list))
        .route("/ext/nai-bridge/api/samplers", get(samplers_list))
        .route(
            "/ext/nai-bridge/api/noise-schedules",
            get(noise_schedules_list),
        )
        .route("/ext/nai-bridge/api/generate", post(generate))
        .route("/ext/nai-bridge/api/save-batch", post(save_batch))
        .route("/ext/nai-bridge/api/vibe/upload", post(vibe_upload))
        .route(
            "/ext/nai-bridge/api/config",
            get(get_config).post(post_config),
        )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        collections::{HashMap, HashSet},
        sync::{Arc, Mutex},
    };

    use axum::{
        body::{to_bytes, Body},
        http::{Method, Request, StatusCode},
        Router,
    };
    use base64::engine::general_purpose::STANDARD as B64;
    use base64::Engine;
    use serde_json::{json, Value};
    use sqlx::sqlite::SqlitePoolOptions;
    use tower::ServiceExt;

    use crate::{
        auth::{AuthContext, PinRateLimiter, QuickLock},
        groups_index::GroupsIndexCache,
        state::{AppState, Config, SharedState},
    };

    #[test]
    fn expand_mode_prefix_puts_the_furry_tag_at_the_very_start() {
        assert_eq!(
            expand_mode_prefix(MODE_FURRY, "1girl"),
            "fur dataset, 1girl"
        );
        assert_eq!(expand_mode_prefix(MODE_ANIME, "1girl"), "1girl");
        // Unknown mode is treated as Anime rather than guessed at.
        assert_eq!(expand_mode_prefix("nonsense", "1girl"), "1girl");
    }

    #[test]
    fn build_request_body_wires_uc_preset_and_snap64_into_the_payload() {
        // Guards the call sites, not just the helpers: a payload built from a
        // real GenRequest must carry the expanded UC text and 64-aligned size.
        let req: GenRequest = serde_json::from_value(json!({
            "prompt": "1girl",
            "negative_prompt": "extra tag",
            "model": "nai-diffusion-5-full",
            "uc_preset": 4,
            "mode": "furry",
            "quality_toggle": true,
            "width": 1250,
            "height": 1177,
        }))
        .unwrap();
        let (body, _seed, _fmt) = build_request_body(&req);
        let params = &body["parameters"];

        let furry = UC_PRESETS_V5
            .iter()
            .find(|(i, _)| *i == UC_FURRY_FOCUS)
            .unwrap()
            .1;
        let expected = format!("{furry}, extra tag");
        assert_eq!(params["negative_prompt"], json!(expected));
        assert_eq!(
            params["v4_negative_prompt"]["caption"]["base_caption"],
            json!(expected)
        );
        assert_eq!(params["ucPreset"], json!(UC_NONE));
        assert_eq!(params["width"], json!(1280));
        assert_eq!(params["height"], json!(1152));

        // `fur dataset` leads and the quality tags trail.
        let tags = QUALITY_TAGS.iter().find(|(g, _)| *g == GEN_V5).unwrap().1;
        let expected_prompt = format!("fur dataset, 1girl, {tags}");
        assert_eq!(body["input"], json!(expected_prompt));
        assert_eq!(
            params["v4_prompt"]["caption"]["base_caption"],
            json!(expected_prompt)
        );
        assert_eq!(params["qualityToggle"], json!(false));
    }

    #[test]
    fn expand_uc_preset_prepends_v5_text_and_reports_none() {
        let (neg, uc) = expand_uc_preset("nai-diffusion-5-full", UC_HEAVY, "extra tag");
        assert!(neg.ends_with(", extra tag"));
        assert!(neg.starts_with("lowres, artistic error, film grain"));
        assert_eq!(uc, UC_NONE);
    }

    #[test]
    fn expand_uc_preset_without_existing_negative_has_no_separator() {
        let (neg, _) = expand_uc_preset("nai-diffusion-5-curated", UC_LIGHT, "   ");
        assert_eq!(
            neg,
            UC_PRESETS_V5
                .iter()
                .find(|(i, _)| *i == UC_LIGHT)
                .unwrap()
                .1
        );
    }

    #[test]
    fn expand_uc_preset_leaves_unrecorded_generations_alone() {
        let (neg, uc) = expand_uc_preset("nai-diffusion-3", UC_HEAVY, "extra tag");
        assert_eq!(neg, "extra tag");
        assert_eq!(uc, UC_HEAVY);
    }

    #[test]
    fn expand_uc_preset_uses_each_generations_own_wording() {
        let (v5, _) = expand_uc_preset("nai-diffusion-5-full", UC_HEAVY, "");
        let (v45, _) = expand_uc_preset("nai-diffusion-4-5-full", UC_HEAVY, "");
        let (v4, _) = expand_uc_preset("nai-diffusion-4-full", UC_HEAVY, "");
        assert_ne!(v5, v45);
        assert_ne!(v45, v4);
        assert_ne!(v5, v4);
    }

    #[test]
    fn expand_uc_preset_does_not_forward_ids_a_generation_lacks() {
        // V4 has no focus presets; V4.5 has Human Focus but not Furry Focus.
        for (model, preset) in [
            ("nai-diffusion-4-full", UC_HUMAN_FOCUS),
            ("nai-diffusion-4-full", UC_FURRY_FOCUS),
            ("nai-diffusion-4-5-full", UC_FURRY_FOCUS),
        ] {
            let (neg, uc) = expand_uc_preset(model, preset, "extra tag");
            assert_eq!(neg, "extra tag");
            assert_eq!(uc, UC_NONE);
        }
    }

    #[test]
    fn expand_uc_preset_applies_nothing_for_unknown_ids() {
        let (neg, uc) = expand_uc_preset("nai-diffusion-5-full", 99, "extra tag");
        assert_eq!(neg, "extra tag");
        assert_eq!(uc, UC_NONE);
    }

    #[test]
    fn snap64_rounds_to_nearest_multiple_of_64() {
        // NAI rejects dimensions that are not a multiple of 64.
        assert_eq!(snap64(1248), 1280);
        assert_eq!(snap64(1176), 1152);
        assert_eq!(snap64(1216), 1216);
        assert_eq!(snap64(1), 64);
        assert_eq!(snap64(2048), 2048);
    }

    async fn test_state(root: &tempfile::TempDir) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        Arc::new(AppState {
            effective_port: 5000,
            gateway_keys: Vec::new(),
            gateway_loopback_bypass: true,
            settings_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            infer_notify_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            scan_roots_generation: std::sync::atomic::AtomicU64::new(0),
            config: Config {
                db_path: "sqlite::memory:".to_string(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,

                pin_boss_login_ui: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                quick_lock_enabled: false,
                pin_auth_enabled: true,
                min_pin_length: 4,
                python_url: String::new(),
                config_path: root.path().join("config.json"),
                project_root: root.path().to_path_buf(),
                app_config: json!({}),
                cache_dir: root.path().join("cache"),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                mcp_native: false,
                standalone: false,
                infer_standalone: true,
                active_profile: None,
                python_executable: String::new(),
            },
            db: pool.clone(),
            db_read: pool.clone(),
            vectors_db: pool.clone(),
            vectors_db_read: pool,
            clip_index: std::sync::Arc::new(
                crate::routes::clip_index::ClipIndex::new_default(std::env::temp_dir())
                    .expect("clip index test default"),
            ),
            clip_indexer: std::sync::Arc::new(crate::routes::clip_indexer::ClipIndexer::new()),
            caption_runner: std::sync::Arc::new(crate::routes::caption_runner::CaptionRunner::new()),
            s2t_runner: std::sync::Arc::new(crate::routes::s2t_runner::S2tRunner::new()),
            clip_runtime_cache: crate::state::TtlCache::new(crate::state::CLIP_RUNTIME_CACHE_TTL),
            inference_client: reqwest::Client::new(),
            python_client: reqwest::Client::new(),
            quick_lock: QuickLock::new(),
            rate_limiter: PinRateLimiter::new(),
            groups_index_cache: GroupsIndexCache::new(root.path().join("cache")),
            proxy_hits: Mutex::new(HashMap::new()),
            fleet_log_stream_connections: Mutex::new(HashMap::new()),
            sse_hub: Arc::new(crate::sse::SseHub::new()),
            job_manager: Arc::new(crate::jobs::JobManager::new()),
            watcher: Arc::new(crate::watcher::ScanWatcher::new()),
            log_ring: Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            mcp_sessions: Arc::new(crate::mcp::session::McpSessionStore::new(1000, 20, 256)),
            approval_gate: Mutex::new(crate::approval_gate::ApprovalGate::default()),
            env: minijinja::Environment::new(),
            dist_v: "dev".to_string(),
            version: "0.0.0".to_string(),
            start_time: std::time::Instant::now(),
            scheduler_state: std::sync::OnceLock::new(),
            wd_infer: std::sync::Arc::new(std::sync::Mutex::new(std::collections::HashMap::new())),
            infer_client: None,
            infer_child: None,
            scan_manager: std::sync::OnceLock::new(),
            hailo_yolo_stream: None,
            stats_basic_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_models_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_timeline_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_resolutions_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            checkpoints_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            server_info_stats_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
        })
    }

    fn test_app(state: SharedState, auth: Option<AuthContext>) -> Router {
        let r = routes().with_state(state);
        match auth {
            Some(ctx) => r.layer(axum::Extension(ctx)),
            None => r,
        }
    }

    fn admin() -> Option<AuthContext> {
        Some(AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["admin".to_string()]),
        })
    }

    async fn get_json(app: Router, path: &str) -> (StatusCode, Value) {
        let req = Request::builder()
            .method(Method::GET)
            .uri(path)
            .body(Body::empty())
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        let status = resp.status();
        let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        (
            status,
            serde_json::from_slice(&bytes).unwrap_or(json!(null)),
        )
    }

    async fn post_json(app: Router, path: &str, body: Value) -> (StatusCode, Value) {
        let req = Request::builder()
            .method(Method::POST)
            .uri(path)
            .header("content-type", "application/json")
            .body(Body::from(body.to_string()))
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        let status = resp.status();
        let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        (
            status,
            serde_json::from_slice(&bytes).unwrap_or(json!(null)),
        )
    }

    // ── pure logic ────────────────────────────────────────────────────────────

    #[test]
    fn test_extract_anlas_ok() {
        let sub = json!({"trainingStepsLeft": {"fixedTrainingStepsLeft": 1234}});
        assert_eq!(extract_anlas(&sub), 1234);
    }

    #[test]
    fn test_extract_anlas_missing() {
        assert_eq!(extract_anlas(&json!({})), 0);
    }

    #[test]
    fn test_extract_usage_present() {
        let sub =
            json!({"usage": {"percent": 2, "isNegative": false, "timeUntilNextPercent": 7888}});
        let usage = extract_usage(&sub).unwrap();
        assert_eq!(usage["percent"], 2);
    }

    #[test]
    fn test_extract_usage_missing() {
        assert_eq!(extract_usage(&json!({})), None);
        assert_eq!(extract_usage(&json!({"tier": 3})), None);
    }

    #[test]
    fn test_extract_usage_malformed_missing_percent() {
        // "usage" present as an object but without a numeric "percent"
        // cannot be evaluated for exhaustion -- must be unverifiable, not
        // "not exhausted".
        assert_eq!(
            extract_usage(&json!({"usage": {"isNegative": false}})),
            None
        );
    }

    #[test]
    fn test_extract_usage_malformed_percent_wrong_type() {
        assert_eq!(extract_usage(&json!({"usage": {"percent": "2"}})), None);
        assert_eq!(extract_usage(&json!({"usage": {"percent": null}})), None);
        assert_eq!(extract_usage(&json!({"usage": {"percent": true}})), None);
    }

    #[test]
    fn test_usage_exhausted_by_percent() {
        assert!(usage_exhausted(&json!({"percent": 0, "isNegative": false})));
        assert!(!usage_exhausted(
            &json!({"percent": 2, "isNegative": false})
        ));
    }

    #[test]
    fn test_usage_exhausted_by_fractional_percent() {
        // Regression: usage_exhausted used to read percent via as_i64,
        // which rejects a float like 0.0 and silently fell back to the
        // "not exhausted" default of 100 -- exactly the exhausted case a
        // fractional percent would represent.
        assert!(usage_exhausted(
            &json!({"percent": 0.0, "isNegative": false})
        ));
        assert!(!usage_exhausted(
            &json!({"percent": 0.5, "isNegative": false})
        ));
    }

    #[test]
    fn test_usage_exhausted_by_is_negative() {
        // Percent could still read positive while isNegative flags the
        // account as over its limit -- treat either signal as exhausted.
        assert!(usage_exhausted(&json!({"percent": 5, "isNegative": true})));
    }

    #[test]
    fn test_is_opus_free_generation_normal_res_low_steps() {
        assert!(is_opus_free_generation(832, 1216, 28));
        assert!(is_opus_free_generation(1024, 1024, 28));
    }

    #[test]
    fn test_is_opus_free_generation_excludes_high_steps() {
        assert!(!is_opus_free_generation(832, 1216, 29));
    }

    #[test]
    fn test_is_opus_free_generation_excludes_high_resolution() {
        assert!(!is_opus_free_generation(1536, 1024, 28));
    }

    #[test]
    fn test_mask_secret_short() {
        assert_eq!(mask_secret("ab"), "ab**********");
        assert_eq!(mask_secret(""), "");
    }

    #[test]
    fn test_mask_secret_long() {
        let s = mask_secret("pst-abc123long");
        assert!(s.starts_with("pst-"), "prefix wrong: {s}");
        assert!(s.ends_with("**********"), "suffix wrong: {s}");
        assert_eq!(s.len(), 14); // 4 + 10
    }

    #[test]
    fn test_build_request_body_defaults() {
        let req = serde_json::from_value::<GenRequest>(json!({
            "prompt": "1girl",
        }))
        .unwrap();
        let (body, _seed, fmt) = build_request_body(&req);
        assert_eq!(fmt, "png");
        assert_eq!(body["model"], json!("nai-diffusion-4-5-full"));
        assert_eq!(body["action"], json!("generate"));
        assert_eq!(body["parameters"]["n_samples"], json!(1u32));
        assert_eq!(body["parameters"]["steps"], json!(28u32));
    }

    #[test]
    fn test_build_request_body_n_samples_always_1() {
        let req = serde_json::from_value::<GenRequest>(json!({
            "prompt": "test",
            "n_samples": 99,
        }))
        .unwrap();
        let (body, _, _) = build_request_body(&req);
        assert_eq!(body["parameters"]["n_samples"], json!(1u32));
    }

    #[test]
    fn test_build_request_body_steps_clamp() {
        let req_low =
            serde_json::from_value::<GenRequest>(json!({"prompt":"x","steps":0})).unwrap();
        let req_high =
            serde_json::from_value::<GenRequest>(json!({"prompt":"x","steps":99})).unwrap();
        let (b_low, _, _) = build_request_body(&req_low);
        let (b_high, _, _) = build_request_body(&req_high);
        assert_eq!(b_low["parameters"]["steps"], json!(1u32));
        assert_eq!(b_high["parameters"]["steps"], json!(50u32));
    }

    #[test]
    fn test_build_request_body_variety_boost_sigma() {
        let req45 = serde_json::from_value::<GenRequest>(json!({
            "prompt": "x",
            "model": "nai-diffusion-4-5-full",
            "variety_boost": true,
        }))
        .unwrap();
        let req4 = serde_json::from_value::<GenRequest>(json!({
            "prompt": "x",
            "model": "nai-diffusion-4-full",
            "variety_boost": true,
        }))
        .unwrap();
        let (b45, _, _) = build_request_body(&req45);
        let (b4, _, _) = build_request_body(&req4);
        assert_eq!(b45["parameters"]["skip_cfg_above_sigma"], json!(58.0_f64));
        assert_eq!(b4["parameters"]["skip_cfg_above_sigma"], json!(19.0_f64));
    }

    #[test]
    fn test_build_request_body_variety_boost_sigma_v5() {
        // A newer model generation must get the 58 cutoff, not the V4 fallback.
        for model in ["nai-diffusion-5-full", "nai-diffusion-5-curated"] {
            let req = serde_json::from_value::<GenRequest>(json!({
                "prompt": "x",
                "model": model,
                "variety_boost": true,
            }))
            .unwrap();
            let (body, _, _) = build_request_body(&req);
            assert_eq!(body["model"], json!(model));
            assert_eq!(
                body["parameters"]["skip_cfg_above_sigma"],
                json!(58.0_f64),
                "sigma wrong for {model}"
            );
        }
    }

    #[test]
    fn test_build_request_body_action_inpaint() {
        let req = serde_json::from_value::<GenRequest>(json!({
            "prompt": "x",
            "image": "aW1h",
            "mask": "bWFzaw==",
        }))
        .unwrap();
        let (body, _, _) = build_request_body(&req);
        assert_eq!(body["action"], json!("inpaint"));
    }

    #[test]
    fn test_build_request_body_action_img2img() {
        let req = serde_json::from_value::<GenRequest>(json!({
            "prompt": "x",
            "image": "aW1h",
        }))
        .unwrap();
        let (body, _, _) = build_request_body(&req);
        assert_eq!(body["action"], json!("img2img"));
    }

    #[test]
    fn test_parse_vibe_any_wrong_ident() {
        let data = json!({"identifier": "wrong"});
        let err = parse_vibe_any(serde_json::to_vec(&data).unwrap().as_slice()).unwrap_err();
        assert!(err.contains("unrecognised"), "err={err}");
    }

    #[test]
    fn test_parse_vibe_any_empty() {
        let err = parse_vibe_any(b"").unwrap_err();
        assert_eq!(err, "empty input");
    }

    #[test]
    fn test_parse_single_vibe_valid() {
        let png_header: Vec<u8> = b"\x89PNG\r\n\x1a\n".to_vec();
        let img_b64 = B64.encode(&png_header);
        let enc_b64 = B64.encode(b"fakeencoding");
        let data = json!({
            "identifier": "novelai-vibe-transfer",
            "image": img_b64,
            "importInfo": {
                "model": "nai-diffusion-4-5-full",
                "information_extracted": 0.75,
                "strength": 0.6,
            },
            "encodings": {
                "v4-5full": {
                    "hashkey1": {
                        "encoding": enc_b64,
                        "params": {"information_extracted": 0.75},
                    }
                }
            }
        });
        let vibes = parse_vibe_any(serde_json::to_vec(&data).unwrap().as_slice()).unwrap();
        assert_eq!(vibes.len(), 1);
        assert_eq!(vibes[0].model, "nai-diffusion-4-5-full");
        assert_eq!(vibes[0].source_image_mime, "image/png");
        assert_eq!(vibes[0].entries.len(), 1);
        assert_eq!(vibes[0].entries[0].information_extracted, 0.75);
    }

    #[test]
    fn test_parse_bundle_too_many() {
        let vibes: Vec<Value> = (0..21).map(|_| json!({"identifier":"nope"})).collect();
        let data = json!({"identifier": "novelai-vibe-transfer-bundle", "vibes": vibes});
        let err = parse_vibe_any(serde_json::to_vec(&data).unwrap().as_slice()).unwrap_err();
        assert!(err.contains("max 20"), "err={err}");
    }

    // ── HTTP routes ───────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_info_returns_200() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, body) = get_json(test_app(state, None), "/ext/nai-bridge/info").await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["bridge_id"], json!("nai"));
    }

    #[tokio::test]
    async fn test_models_list() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, body) = get_json(test_app(state, None), "/ext/nai-bridge/api/models").await;
        assert_eq!(status, StatusCode::OK);
        let models = body["models"].as_array().unwrap();
        assert_eq!(models.len(), 6);
        assert_eq!(models[0]["id"], json!("nai-diffusion-5-full"));
    }

    #[tokio::test]
    async fn test_samplers_list() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, body) = get_json(test_app(state, None), "/ext/nai-bridge/api/samplers").await;
        assert_eq!(status, StatusCode::OK);
        let samplers = body["samplers"].as_array().unwrap();
        assert_eq!(samplers.len(), 6);
        assert_eq!(samplers[0]["id"], json!("k_euler_ancestral"));
    }

    #[tokio::test]
    async fn test_noise_schedules_list() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, body) =
            get_json(test_app(state, None), "/ext/nai-bridge/api/noise-schedules").await;
        assert_eq!(status, StatusCode::OK);
        let ns = body["noise_schedules"].as_array().unwrap();
        assert_eq!(ns.len(), 4);
        assert_eq!(ns[0]["id"], json!("karras"));
    }

    #[tokio::test]
    async fn test_anlas_requires_admin() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        // no auth → 403
        let (status, _) =
            get_json(test_app(state.clone(), None), "/ext/nai-bridge/api/anlas").await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        // admin but no token → 400
        let (status, body) = get_json(test_app(state, admin()), "/ext/nai-bridge/api/anlas").await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(
            body["error"].as_str().unwrap().contains("token"),
            "err={body}"
        );
    }

    #[tokio::test]
    async fn test_get_config_requires_admin() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, _) =
            get_json(test_app(state.clone(), None), "/ext/nai-bridge/api/config").await;
        assert_eq!(status, StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_get_config_defaults() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, body) = get_json(test_app(state, admin()), "/ext/nai-bridge/api/config").await;
        assert_eq!(status, StatusCode::OK);
        // `api_ok` merges the payload at the top level (Python `api_success`
        // shape); `data` stays null unless a handler puts one there.
        assert_eq!(body["data"], json!(null));
        assert_eq!(body["api_token"], json!(""));
        assert_eq!(body["default_model"], json!("nai-diffusion-4-5-full"));
        assert_eq!(body["default_image_format"], json!("png"));
    }

    #[tokio::test]
    async fn test_post_config_invalid_model_400() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, body) = post_json(
            test_app(state, admin()),
            "/ext/nai-bridge/api/config",
            json!({"default_model": "invalid-model"}),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(body["error"].as_str().unwrap().contains("default_model"));
    }

    #[tokio::test]
    async fn test_post_config_masked_sentinel_preserves() {
        let root = tempfile::tempdir().unwrap();
        // Write an existing enc: token to config
        let existing_enc = "enc:dGVzdA==";
        let cfg = json!({
            "extensions": {
                "builtin-nai-bridge": {"api_token": existing_enc}
            }
        });
        std::fs::write(
            root.path().join("config.json"),
            serde_json::to_string(&cfg).unwrap(),
        )
        .unwrap();

        let state = test_state(&root).await;
        // Send a masked sentinel — should not overwrite
        let (status, _) = post_json(
            test_app(state, admin()),
            "/ext/nai-bridge/api/config",
            json!({"api_token": "****", "auto_send": true}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);

        let written: Value = serde_json::from_str(
            &std::fs::read_to_string(root.path().join("config.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(
            written["extensions"]["builtin-nai-bridge"]["api_token"],
            json!(existing_enc),
            "masked sentinel must not overwrite existing enc: token"
        );
    }

    #[tokio::test]
    async fn test_post_config_pst_token_encrypts() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, body) = post_json(
            test_app(state, admin()),
            "/ext/nai-bridge/api/config",
            json!({"api_token": "pst-testtoken1234567890"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "body={body}");
        let written: Value = serde_json::from_str(
            &std::fs::read_to_string(root.path().join("config.json")).unwrap(),
        )
        .unwrap();
        let saved = written["extensions"]["builtin-nai-bridge"]["api_token"]
            .as_str()
            .unwrap();
        assert!(
            saved.starts_with("enc:"),
            "token must be encrypted, got: {saved}"
        );
    }

    #[tokio::test]
    async fn test_post_config_no_valid_fields_400() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        // Sending only a masked token with no other fields → no fields saved → 400
        let (status, _) = post_json(
            test_app(state, admin()),
            "/ext/nai-bridge/api/config",
            json!({"api_token": "***"}),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_post_config_requires_admin() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let (status, _) = post_json(
            test_app(state, None),
            "/ext/nai-bridge/api/config",
            json!({"auto_send": true}),
        )
        .await;
        assert_eq!(status, StatusCode::FORBIDDEN);
    }
}

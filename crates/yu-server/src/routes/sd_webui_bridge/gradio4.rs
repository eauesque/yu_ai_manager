use std::collections::HashMap;
use std::path::Path;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use base64::Engine as _;
use futures_util::StreamExt;
use serde_json::{json, Value};

use crate::state::SharedState;

use super::{api_err, api_ok, cfg_bool, cfg_str, ext_config, sd_api_url, SD_USER_AGENT};

const CACHE_TTL: Duration = Duration::from_secs(300);
static ALLOWED_IMG_EXTS: &[&str] = &["png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff", "tif"];

// ---------------------------------------------------------------------------
// Schema cache
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct GradioSchema {
    defaults: Vec<Value>,
    label_map: HashMap<String, usize>,
}

static SCHEMA_CACHE: OnceLock<Mutex<HashMap<String, (Instant, GradioSchema)>>> = OnceLock::new();

fn schema_cache() -> &'static Mutex<HashMap<String, (Instant, GradioSchema)>> {
    SCHEMA_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn get_cached(api_url: &str) -> Option<GradioSchema> {
    let c = schema_cache().lock().unwrap();
    c.get(api_url)
        .filter(|(ts, _)| ts.elapsed() < CACHE_TTL)
        .map(|(_, s)| s.clone())
}

fn set_cached(api_url: &str, schema: GradioSchema) {
    schema_cache()
        .lock()
        .unwrap()
        .insert(api_url.to_string(), (Instant::now(), schema));
}

async fn fetch_schema(
    client: &reqwest::Client,
    api_url: &str,
    auth: &Option<String>,
) -> Option<GradioSchema> {
    let mut req = client
        .get(format!("{api_url}/config"))
        .header("User-Agent", SD_USER_AGENT)
        .timeout(Duration::from_secs(15));
    if let Some(h) = auth {
        req = req.header("Authorization", h);
    }
    let config: Value = req.send().await.ok()?.json().await.ok()?;

    let deps = config.get("dependencies")?.as_array()?;
    let components: HashMap<u64, &Value> = config
        .get("components")?
        .as_array()?
        .iter()
        .filter_map(|c| c.get("id").and_then(Value::as_u64).map(|id| (id, c)))
        .collect();

    let dep = deps
        .iter()
        .find(|d| d.get("api_name").and_then(Value::as_str) == Some("txt2img"))?;
    let inputs = dep.get("inputs")?.as_array()?;

    let mut defaults = Vec::with_capacity(inputs.len());
    let mut label_map = HashMap::new();

    for (idx, id_val) in inputs.iter().enumerate() {
        let id = id_val.as_u64().unwrap_or(0);
        let props = components
            .get(&id)
            .and_then(|c| c.get("props"))
            .cloned()
            .unwrap_or(Value::Null);
        defaults.push(props.get("value").cloned().unwrap_or(Value::Null));
        if let Some(label) = props.get("label").and_then(Value::as_str) {
            if !label.is_empty() {
                label_map.insert(label.to_string(), idx);
            }
        }
    }

    Some(GradioSchema {
        defaults,
        label_map,
    })
}

// ---------------------------------------------------------------------------
// Args helpers
// ---------------------------------------------------------------------------

fn set_arg(args: &mut [Value], lm: &HashMap<String, usize>, label: &str, val: Value) {
    if let Some(&i) = lm.get(label) {
        if i < args.len() {
            args[i] = val;
        }
    }
}

fn build_args(
    s: &GradioSchema,
    prompt: &str,
    negative: &str,
    steps: i64,
    sampler: &str,
    cfg: f64,
    w: i64,
    h: i64,
    seed: i64,
) -> Vec<Value> {
    let mut args = s.defaults.clone();
    set_arg(&mut args, &s.label_map, "Prompt", json!(prompt));
    set_arg(&mut args, &s.label_map, "Negative prompt", json!(negative));
    set_arg(&mut args, &s.label_map, "Sampling steps", json!(steps));
    set_arg(&mut args, &s.label_map, "Sampling method", json!(sampler));
    set_arg(&mut args, &s.label_map, "CFG Scale", json!(cfg));
    set_arg(&mut args, &s.label_map, "Width", json!(w));
    set_arg(&mut args, &s.label_map, "Height", json!(h));
    set_arg(&mut args, &s.label_map, "Seed", json!(seed));
    args
}

// ---------------------------------------------------------------------------
// Gradio HTTP+SSE call
// ---------------------------------------------------------------------------

async fn call_gradio(
    client: &reqwest::Client,
    api_url: &str,
    args: Vec<Value>,
    auth: &Option<String>,
) -> Result<Vec<Value>, String> {
    // POST /call/txt2img
    let mut req = client
        .post(format!("{api_url}/call/txt2img"))
        .header("User-Agent", SD_USER_AGENT)
        .timeout(Duration::from_secs(30))
        .json(&json!({"data": args}));
    if let Some(h) = auth {
        req = req.header("Authorization", h);
    }
    let resp = req
        .send()
        .await
        .map_err(|e| format!("Gradio submit: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("Gradio submit HTTP {}", resp.status()));
    }
    let event_id = resp
        .json::<Value>()
        .await
        .map_err(|e| e.to_string())?
        .get("event_id")
        .and_then(Value::as_str)
        .ok_or("no event_id")?
        .to_string();

    // GET /call/txt2img/{event_id} — SSE stream
    let mut req = client
        .get(format!("{api_url}/call/txt2img/{event_id}"))
        .header("User-Agent", SD_USER_AGENT)
        .timeout(Duration::from_secs(300));
    if let Some(h) = auth {
        req = req.header("Authorization", h);
    }
    let sse = req.send().await.map_err(|e| format!("SSE connect: {e}"))?;
    let mut stream = sse.bytes_stream();
    let mut buf = String::new();
    let mut cur_event = String::new();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("SSE read: {e}"))?;
        buf.push_str(&String::from_utf8_lossy(&chunk));
        while let Some(nl) = buf.find('\n') {
            let line = buf[..nl].trim_end_matches('\r').to_string();
            buf = buf[nl + 1..].to_string();
            if let Some(ev) = line.strip_prefix("event:") {
                cur_event = ev.trim().to_string();
            } else if let Some(data) = line.strip_prefix("data:") {
                let data = data.trim();
                match cur_event.as_str() {
                    "complete" => {
                        return serde_json::from_str::<Vec<Value>>(data)
                            .map_err(|e| format!("SSE parse: {e}"))
                    }
                    "error" => {
                        return Err(format!("Gradio error: {}", &data[..data.len().min(200)]))
                    }
                    _ => {}
                }
            }
        }
    }
    Err("SSE stream ended without complete event".into())
}

// ---------------------------------------------------------------------------
// Image resolution
// ---------------------------------------------------------------------------

fn read_local_b64(path: &str) -> Option<String> {
    let ext = Path::new(path).extension()?.to_str()?.to_lowercase();
    if !ALLOWED_IMG_EXTS.contains(&ext.as_str()) {
        tracing::warn!("Rejected non-image Gradio path: {path}");
        return None;
    }
    let real = std::fs::canonicalize(path).ok()?;
    let tmp = std::fs::canonicalize(std::env::temp_dir()).unwrap_or_else(|_| std::env::temp_dir());
    if !real.starts_with(&tmp) {
        tracing::warn!("Rejected Gradio path outside temp dir: {path}");
        return None;
    }
    let bytes = std::fs::read(&real).ok()?;
    Some(base64::engine::general_purpose::STANDARD.encode(&bytes))
}

async fn fetch_url_b64(
    client: &reqwest::Client,
    api_url: &str,
    url: &str,
    auth: &Option<String>,
) -> Option<String> {
    let fetch_url = if url.starts_with("http://") || url.starts_with("https://") {
        url.to_string()
    } else {
        format!("{api_url}{url}")
    };
    let mut req = client
        .get(&fetch_url)
        .header("User-Agent", SD_USER_AGENT)
        .timeout(Duration::from_secs(30));
    if let Some(h) = auth {
        req = req.header("Authorization", h);
    }
    let bytes = req.send().await.ok()?.bytes().await.ok()?;
    Some(base64::engine::general_purpose::STANDARD.encode(&bytes))
}

async fn resolve_images(
    client: &reqwest::Client,
    api_url: &str,
    result: &[Value],
    auth: &Option<String>,
) -> Vec<String> {
    let gallery = match result.first() {
        Some(Value::Array(a)) => a.clone(),
        _ => return vec![],
    };
    let mut out = vec![];
    for item in &gallery {
        let b64 = match item {
            Value::String(s) => {
                if let Some(rest) = s.strip_prefix("data:image") {
                    rest.split_once(',')
                        .map(|x| x.1)
                        .unwrap_or(s)
                        .to_string()
                        .into()
                } else {
                    Some(s.clone())
                }
            }
            Value::Object(_) => {
                let img_info = item.get("image").unwrap_or(item);
                if let Some(p) = img_info
                    .get("path")
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty())
                {
                    read_local_b64(p)
                } else if let Some(u) = img_info
                    .get("url")
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty())
                {
                    fetch_url_b64(client, api_url, u, auth).await
                } else {
                    None
                }
            }
            _ => None,
        };
        if let Some(b) = b64 {
            out.push(b);
        }
    }
    out
}

fn transcode_b64(b64: &str, target_format: &str) -> String {
    use image::ImageFormat;
    let Ok(bytes) = base64::engine::general_purpose::STANDARD.decode(b64.trim()) else {
        return b64.to_string();
    };
    let fmt = match target_format {
        "jpg" | "jpeg" => ImageFormat::Jpeg,
        "webp" => ImageFormat::WebP,
        _ => ImageFormat::Png,
    };
    let Ok(img) = image::load_from_memory(&bytes) else {
        return b64.to_string();
    };
    let mut buf = std::io::Cursor::new(Vec::new());
    if img.write_to(&mut buf, fmt).is_ok() {
        base64::engine::general_purpose::STANDARD.encode(buf.into_inner())
    } else {
        b64.to_string()
    }
}

fn parse_seed(info_text: &str, fallback: i64) -> i64 {
    for line in info_text.replace("<br>", "\n").lines() {
        if let Some(rest) = line.trim().strip_prefix("Seed:") {
            if let Ok(n) = rest
                .trim()
                .split(',')
                .next()
                .unwrap_or("")
                .trim()
                .parse::<i64>()
            {
                return n;
            }
        }
    }
    fallback
}

// ---------------------------------------------------------------------------
// Public handler
// ---------------------------------------------------------------------------

pub async fn generate_gradio(state: SharedState, body: Value) -> Response {
    // img2img not supported on Forge/Gradio 4
    if body
        .get("init_images")
        .and_then(Value::as_array)
        .is_some_and(|a| !a.is_empty())
    {
        return api_err(
            "img2img is not supported in Gradio / Forge mode",
            StatusCode::NOT_IMPLEMENTED,
        );
    }

    let prompt = body
        .get("prompt")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if prompt.is_empty() {
        return api_err("prompt is required", StatusCode::BAD_REQUEST);
    }
    let negative = body
        .get("negative_prompt")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let steps = body
        .get("steps")
        .and_then(Value::as_i64)
        .map(|v| v.clamp(1, 200))
        .unwrap_or(28);
    let sampler = body
        .get("sampler_name")
        .and_then(Value::as_str)
        .unwrap_or("Euler a")
        .to_string();
    let cfg = body
        .get("cfg_scale")
        .and_then(Value::as_f64)
        .map(|v| v.clamp(0.0, 30.0))
        .unwrap_or(7.0);
    let width = body
        .get("width")
        .and_then(Value::as_i64)
        .map(|v| v.clamp(64, 16384))
        .unwrap_or(512);
    let height = body
        .get("height")
        .and_then(Value::as_i64)
        .map(|v| v.clamp(64, 16384))
        .unwrap_or(768);
    let seed = body
        .get("seed")
        .and_then(Value::as_i64)
        .map(|v| v.clamp(-1, u32::MAX as i64))
        .unwrap_or(-1);

    let cfg_val = ext_config(&state);
    let api_url = sd_api_url(&cfg_val);
    let bridge_managed = cfg_bool(&cfg_val, "bridge_managed_save", false);
    let auto_import = cfg_bool(&cfg_val, "auto_import", true);
    let save_folder = cfg_str(&cfg_val, "save_folder", "").to_string();
    let image_format = cfg_str(&cfg_val, "image_format", "png").to_string();
    let save_naming = cfg_str(&cfg_val, "save_naming", "daily_folder").to_string();

    // Auth header for all 3 requests (submit, SSE, file fetch)
    let auth: Option<String> = {
        let enc = cfg_str(&cfg_val, "api_key_enc", "").to_string();
        if enc.is_empty() {
            None
        } else {
            let plain = crate::secret_store::decrypt(&enc, &state.config.project_root);
            if plain.is_empty() {
                None
            } else {
                Some(format!("Bearer {plain}"))
            }
        }
    };

    let client = &state.python_client;

    // Schema (cached 300s)
    let schema = if let Some(s) = get_cached(&api_url) {
        s
    } else {
        match fetch_schema(client, &api_url, &auth).await {
            Some(s) => {
                set_cached(&api_url, s.clone());
                s
            }
            None => {
                return api_err(
                    "Failed to fetch Forge /config schema",
                    StatusCode::BAD_GATEWAY,
                )
            }
        }
    };

    // Suppress Forge's own save when bridge manages it (best-effort, ignore errors)
    // ponytail: fire-and-forget; Forge might ignore it anyway
    if bridge_managed {
        let mut req = client
            .post(format!("{api_url}/sdapi/v1/options"))
            .header("User-Agent", SD_USER_AGENT)
            .timeout(Duration::from_secs(10))
            .json(&json!({"samples_save": false, "grid_save": false}));
        if let Some(h) = &auth {
            req = req.header("Authorization", h);
        }
        let _ = req.send().await;
    }

    let job_id = uuid::Uuid::new_v4().to_string();
    let _cancel = state.job_manager.start(&job_id, "Gradio generate");

    let args = build_args(
        &schema, &prompt, &negative, steps, &sampler, cfg, width, height, seed,
    );

    match call_gradio(client, &api_url, args, &auth).await {
        Err(e) => {
            state.job_manager.finish(&job_id, None, Some(e.clone()));
            api_err(&format!("Forge/Gradio error: {e}"), StatusCode::BAD_GATEWAY)
        }
        Ok(result_data) => {
            let images_b64: Vec<String> = resolve_images(client, &api_url, &result_data, &auth)
                .await
                .into_iter()
                .map(|b| transcode_b64(&b, &image_format))
                .collect();
            let used_seed = result_data
                .get(1)
                .and_then(Value::as_str)
                .map(|s| parse_seed(s, seed))
                .unwrap_or(seed);

            let result_images: Vec<Value> = images_b64
                .iter()
                .map(|b| json!({"base64": b, "seed": used_seed}))
                .collect();

            let (saved_paths, save_errors): (Vec<String>, Vec<String>) =
                if bridge_managed && !save_folder.is_empty() {
                    let items: Vec<(&str, i64)> = result_images
                        .iter()
                        .filter_map(|img| {
                            img.get("base64")
                                .and_then(Value::as_str)
                                .map(|b| (b, used_seed))
                        })
                        .collect();
                    crate::routes::bridge_save::save_images_to_disk(
                        &items,
                        &save_folder,
                        &image_format,
                        &save_naming,
                    )
                } else {
                    (vec![], vec![])
                };

            if let Some(sv) = body.get("sweep_meta").cloned() {
                if let Some(meta) = crate::routes::sweep_common::validate_sweep_meta(&sv) {
                    if !saved_paths.is_empty() {
                        crate::routes::sweep_common::write_sweep_xmp_to_paths(&saved_paths, &meta);
                        crate::routes::sweep_common::upsert_sweep_db(
                            &state.db,
                            &meta,
                            &saved_paths,
                        )
                        .await;
                    }
                }
            }
            let file_ids = if auto_import && !saved_paths.is_empty() {
                if body.get("sweep_meta").is_some() {
                    crate::routes::sweep_common::upsert_files_from_paths(&state, &saved_paths).await
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
                    Default::default()
                }
            } else {
                Default::default()
            };

            let mut result = json!({"images": result_images, "task_id": job_id});
            if !saved_paths.is_empty() {
                result["saved_paths"] = json!(saved_paths);
                result["saved_items"] = json!(
                    crate::routes::sweep_common::saved_items_from_file_ids(&saved_paths, &file_ids,)
                );
            }
            if !save_errors.is_empty() {
                result["errors"] = json!(save_errors);
            }
            state
                .job_manager
                .finish(&job_id, Some(result.clone()), None);
            api_ok(result).into_response()
        }
    }
}

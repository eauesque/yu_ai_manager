use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use bytes::Bytes;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::config_io::{load as load_config_json, write as write_config_json};
use crate::{
    auth::scope::{require_admin_scope, AuthContext},
    secret_store,
    state::SharedState,
};

const EXT_NAME: &str = "builtin-sd-webui-bridge";
const BRIDGE_TAG: &str = "sd-webui";
const DEFAULT_API_URL: &str = "http://127.0.0.1:7860";
const SD_USER_AGENT: &str = "yu-ai-manager/1.0";

pub mod generate;
pub mod gradio4;

// Must match Python's _SAVE_NAMING_OPTIONS set
static SAVE_NAMING_OPTIONS: &[&str] = &["daily_folder", "date_prefix", "timestamp"];
static IMAGE_FORMATS: &[&str] = &["png", "webp", "jpg"];

pub(crate) fn ext_config(state: &SharedState) -> Value {
    let full = load_config_json(&state.config.config_path);
    full.get("extensions")
        .and_then(|e| e.get(EXT_NAME))
        .cloned()
        .unwrap_or_else(|| json!({}))
}

pub(super) fn cfg_str<'a>(cfg: &'a Value, key: &str, default: &'a str) -> &'a str {
    cfg.get(key).and_then(Value::as_str).unwrap_or(default)
}

pub(super) fn cfg_bool(cfg: &Value, key: &str, default: bool) -> bool {
    cfg.get(key).and_then(Value::as_bool).unwrap_or(default)
}

pub(super) fn cfg_i64(cfg: &Value, key: &str, default: i64) -> i64 {
    cfg.get(key).and_then(Value::as_i64).unwrap_or(default)
}

pub(crate) fn sd_api_url(cfg: &Value) -> String {
    cfg_str(cfg, "api_url", DEFAULT_API_URL)
        .trim_end_matches('/')
        .to_string()
}

pub(super) fn python_url(state: &SharedState) -> Option<String> {
    let url = state.config.python_url.trim();
    if url.is_empty() {
        None
    } else {
        Some(url.trim_end_matches('/').to_string())
    }
}

// Matches Python's api_success(payload) — merges payload keys at top level.
// {"ok": True, "error": None, "data": None} updated with payload dict.
pub(super) fn api_ok(payload: Value) -> Json<Value> {
    let mut body = json!({"ok": true, "error": null, "data": null});
    if let Value::Object(map) = payload {
        let obj = body.as_object_mut().unwrap();
        for (k, v) in map {
            obj.insert(k, v);
        }
    }
    Json(body)
}

pub(super) fn api_err(msg: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": msg}))).into_response()
}

fn admin_guard(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0))
}

pub(super) async fn sd_get(
    client: &reqwest::Client,
    api_url: &str,
    path: &str,
) -> Result<Value, String> {
    let resp = client
        .get(format!("{api_url}{path}"))
        .header("User-Agent", SD_USER_AGENT)
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }
    resp.json::<Value>().await.map_err(|e| e.to_string())
}

pub(super) async fn sd_post(
    client: &reqwest::Client,
    api_url: &str,
    path: &str,
    body: &Value,
) -> Result<Value, String> {
    let resp = client
        .post(format!("{api_url}{path}"))
        .header("User-Agent", SD_USER_AGENT)
        .timeout(std::time::Duration::from_secs(30))
        .json(body)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }
    let bytes = resp.bytes().await.map_err(|e| e.to_string())?;
    if bytes.is_empty() {
        return Ok(json!(null));
    }
    serde_json::from_slice(&bytes).map_err(|e| e.to_string())
}

async fn sd_list_names(
    client: &reqwest::Client,
    api_url: &str,
    path: &str,
    key: &str,
) -> Result<Vec<String>, String> {
    let data = sd_get(client, api_url, path).await?;
    let arr = data
        .as_array()
        .ok_or_else(|| "expected array".to_string())?;
    Ok(arr
        .iter()
        .filter_map(|item| item.get(key).and_then(Value::as_str).map(String::from))
        .collect())
}

// Matches Python's jsonify({"name": ..., "bridge": ..., "api_url": ...}) — no ok wrapper.
async fn info(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    Json(json!({
        "name": EXT_NAME,
        "bridge": BRIDGE_TAG,
        "api_url": cfg_str(&cfg, "api_url", DEFAULT_API_URL),
    }))
    .into_response()
}

#[derive(Debug, Deserialize)]
struct TestConnReq {
    api_url: Option<String>,
}

async fn test_connection(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(req): Json<TestConnReq>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let configured = cfg_str(&cfg, "api_url", DEFAULT_API_URL).to_string();
    let base_url = req
        .api_url
        .as_deref()
        .unwrap_or(&configured)
        .trim_end_matches('/');
    match sd_get(&state.inference_client, base_url, "/sdapi/v1/options").await {
        Ok(opts) => {
            let model = opts
                .get("sd_model_checkpoint")
                .and_then(Value::as_str)
                .unwrap_or("unknown");
            let version = opts.get("_version").and_then(Value::as_str).unwrap_or("");
            // Matches Python: api_success({"ok": True, "model": ..., "version": ..., "api_type": ...})
            api_ok(json!({
                "ok": true,
                "model": model,
                "version": version,
                "api_type": "sdapi_v1",
            }))
            .into_response()
        }
        Err(e) => api_err(&format!("Connection failed: {e}"), StatusCode::BAD_GATEWAY),
    }
}

async fn samplers(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_list_names(
        &state.inference_client,
        &api_url,
        "/sdapi/v1/samplers",
        "name",
    )
    .await
    {
        Ok(names) => api_ok(json!({"samplers": names})).into_response(),
        // Python list_names() catches BridgeConnectionError → returns [] → 200
        Err(_) => api_ok(json!({"samplers": []})).into_response(),
    }
}

async fn upscalers(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_list_names(
        &state.inference_client,
        &api_url,
        "/sdapi/v1/upscalers",
        "name",
    )
    .await
    {
        Ok(names) => api_ok(json!({"upscalers": names})).into_response(),
        Err(_) => api_ok(json!({"upscalers": []})).into_response(),
    }
}

async fn models_list(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_list_names(
        &state.inference_client,
        &api_url,
        "/sdapi/v1/sd-models",
        "title",
    )
    .await
    {
        Ok(models) => api_ok(json!({"models": models})).into_response(),
        Err(_) => api_ok(json!({"models": []})).into_response(),
    }
}

#[derive(Debug, Deserialize)]
struct SwitchModelReq {
    // Python uses "model" key: checkpoint = (data.get("model") or "").strip()
    model: String,
}

async fn models_switch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(req): Json<SwitchModelReq>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let checkpoint = req.model.trim().to_string();
    if checkpoint.is_empty() {
        return api_err("model is required", StatusCode::BAD_REQUEST);
    }
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    let body = json!({"sd_model_checkpoint": checkpoint});
    match sd_post(
        &state.inference_client,
        &api_url,
        "/sdapi/v1/options",
        &body,
    )
    .await
    {
        Ok(_) => api_ok(json!({"ok": true, "model": checkpoint})).into_response(),
        Err(e) => api_err(&format!("SD WebUI error: {e}"), StatusCode::BAD_GATEWAY),
    }
}

async fn refresh_assets(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    // Matches Python: SDWebUIClient.refresh_assets() tries each endpoint individually
    let mut results = serde_json::Map::new();
    for (label, ep) in [
        ("checkpoints", "/sdapi/v1/refresh-checkpoints"),
        ("vae", "/sdapi/v1/refresh-vae"),
        ("loras", "/sdapi/v1/refresh-loras"),
    ] {
        match sd_post(&state.inference_client, &api_url, ep, &json!({})).await {
            Ok(_) => {
                results.insert(label.to_string(), json!({"ok": true}));
            }
            Err(e) => {
                results.insert(label.to_string(), json!({"ok": false, "error": e}));
            }
        }
    }
    api_ok(json!({"results": Value::Object(results)})).into_response()
}

async fn get_config(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let masked_key = if cfg_str(&cfg, "api_key_enc", "").is_empty() {
        String::new()
    } else {
        "***".to_string()
    };
    api_ok(json!({
        "api_url": cfg_str(&cfg, "api_url", DEFAULT_API_URL),
        "auto_send": cfg_bool(&cfg, "auto_send", false),
        "default_sampler": cfg_str(&cfg, "default_sampler", "Euler a"),
        "save_folder": cfg_str(&cfg, "save_folder", ""),
        "auto_save": cfg_bool(&cfg, "auto_save", false),
        "save_naming": cfg_str(&cfg, "save_naming", "daily_folder"),
        "default_image_format": cfg_str(&cfg, "default_image_format", "png"),
        "auto_import": cfg_bool(&cfg, "auto_import", true),
        "bridge_managed_save": cfg_bool(&cfg, "bridge_managed_save", false),
        "max_batch_size": cfg.get("max_batch_size").and_then(Value::as_i64).unwrap_or(8),
        "api_key_enc": masked_key,
        "gateway_url": cfg_str(&cfg, "gateway_url", ""),
    }))
    .into_response()
}

#[derive(Debug, Deserialize)]
struct SaveSdConfigReq {
    api_url: Option<String>,
    auto_send: Option<bool>,
    default_sampler: Option<String>,
    save_folder: Option<String>,
    auto_save: Option<bool>,
    save_naming: Option<String>,
    default_image_format: Option<String>,
    auto_import: Option<bool>,
    bridge_managed_save: Option<bool>,
    max_batch_size: Option<Value>,
    api_key_enc: Option<String>,
    gateway_url: Option<String>,
}

async fn post_config(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(req): Json<SaveSdConfigReq>,
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
    // Track saved fields as dict matching Python's resp_saved
    let mut saved: serde_json::Map<String, Value> = serde_json::Map::new();

    if let Some(url) = &req.api_url {
        let url = url.trim();
        if !url.starts_with("http://") && !url.starts_with("https://") {
            return api_err(
                "api_url must use http:// or https://",
                StatusCode::BAD_REQUEST,
            );
        }
        full["extensions"][EXT_NAME]["api_url"] = json!(url);
        saved.insert("api_url".to_string(), json!(url));
    }
    if let Some(v) = req.auto_send {
        full["extensions"][EXT_NAME]["auto_send"] = json!(v);
        saved.insert("auto_send".to_string(), json!(v));
    }
    if let Some(s) = &req.default_sampler {
        let s = s.trim();
        if s.is_empty() {
            return api_err("default_sampler must not be empty", StatusCode::BAD_REQUEST);
        }
        // Python: _DEFAULT_SAMPLER_OPTIONS is None => no allowlist validation
        full["extensions"][EXT_NAME]["default_sampler"] = json!(s);
        saved.insert("default_sampler".to_string(), json!(s));
    }
    if let Some(s) = &req.save_folder {
        let s = s.trim();
        full["extensions"][EXT_NAME]["save_folder"] = json!(s);
        saved.insert("save_folder".to_string(), json!(s));
    }
    if let Some(v) = req.auto_save {
        full["extensions"][EXT_NAME]["auto_save"] = json!(v);
        saved.insert("auto_save".to_string(), json!(v));
    }
    if let Some(s) = &req.save_naming {
        if !SAVE_NAMING_OPTIONS.contains(&s.as_str()) {
            return api_err("save_naming is invalid", StatusCode::BAD_REQUEST);
        }
        full["extensions"][EXT_NAME]["save_naming"] = json!(s);
        saved.insert("save_naming".to_string(), json!(s));
    }
    if let Some(s) = &req.default_image_format {
        let s = s.trim().to_lowercase();
        if !IMAGE_FORMATS.contains(&s.as_str()) {
            return api_err("default_image_format is invalid", StatusCode::BAD_REQUEST);
        }
        full["extensions"][EXT_NAME]["default_image_format"] = json!(s);
        saved.insert("default_image_format".to_string(), json!(s));
    }
    if let Some(v) = req.auto_import {
        full["extensions"][EXT_NAME]["auto_import"] = json!(v);
        saved.insert("auto_import".to_string(), json!(v));
    }
    if let Some(v) = req.bridge_managed_save {
        full["extensions"][EXT_NAME]["bridge_managed_save"] = json!(v);
        saved.insert("bridge_managed_save".to_string(), json!(v));
    }
    if let Some(ref bs) = req.max_batch_size {
        let n = match bs {
            Value::Number(n) => n.as_i64().unwrap_or(-1),
            Value::String(s) => s.parse::<i64>().unwrap_or(-1),
            _ => -1,
        };
        if !(1..=64).contains(&n) {
            return api_err(
                "max_batch_size must be between 1 and 64",
                StatusCode::BAD_REQUEST,
            );
        }
        full["extensions"][EXT_NAME]["max_batch_size"] = json!(n);
        saved.insert("max_batch_size".to_string(), json!(n));
    }
    if let Some(k) = &req.api_key_enc {
        let k = k.trim();
        if k != "***" {
            let to_store = if k.is_empty() {
                String::new()
            } else if k.starts_with("enc:") {
                k.to_string()
            } else {
                secret_store::encrypt(k, &state.config.project_root)
            };
            full["extensions"][EXT_NAME]["api_key_enc"] = json!(to_store);
            // Redact ciphertext in response (matches Python's resp_saved)
            saved.insert(
                "api_key_enc".to_string(),
                if to_store.is_empty() {
                    json!("")
                } else {
                    json!("***")
                },
            );
        }
    }
    if let Some(gw) = &req.gateway_url {
        let gw = gw.trim();
        if !gw.is_empty() && !gw.starts_with("http://") && !gw.starts_with("https://") {
            return api_err(
                "gateway_url must use http:// or https://",
                StatusCode::BAD_REQUEST,
            );
        }
        full["extensions"][EXT_NAME]["gateway_url"] = json!(gw);
        saved.insert("gateway_url".to_string(), json!(gw));
    }
    if saved.is_empty() {
        return api_err("No valid config fields provided", StatusCode::BAD_REQUEST);
    }
    if let Err(e) = write_config_json(&state.config.config_path, &full) {
        tracing::error!("sd_webui_bridge: config write failed: {e}");
        return api_err("Failed to save config", StatusCode::INTERNAL_SERVER_ERROR);
    }
    api_ok(json!({"saved": Value::Object(saved)})).into_response()
}

// save_batch — Rust native (sweep_meta handled inline)
async fn save_batch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let body_json: serde_json::Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => return api_err("Invalid JSON body", StatusCode::BAD_REQUEST),
    };

    // Extract sweep_meta early (validated; None if absent or invalid)
    let sweep_meta = body_json
        .get("sweep_meta")
        .and_then(crate::routes::sweep_common::validate_sweep_meta);

    // Rust save
    let images: Vec<String> = body_json
        .get("images")
        .and_then(serde_json::Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(serde_json::Value::as_str)
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
        .and_then(serde_json::Value::as_array)
        .map(|arr| arr.iter().filter_map(serde_json::Value::as_i64).collect())
        .unwrap_or_default();
    let cfg = ext_config(&state);
    let auto_import = cfg_bool(&cfg, "auto_import", true);
    let save_folder = body_json
        .get("save_folder")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "save_folder", ""))
        .to_string();
    let save_naming = body_json
        .get("save_naming")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "save_naming", "daily_folder"))
        .to_string();
    let image_format = body_json
        .get("image_format")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "image_format", "png"))
        .to_string();
    if save_folder.is_empty() {
        return api_err("save_folder is required", StatusCode::BAD_REQUEST);
    }
    let items: Vec<(&str, i64)> = images
        .iter()
        .enumerate()
        .map(|(i, s)| (s.as_str(), seeds.get(i).copied().unwrap_or(-1)))
        .collect();
    let (saved_paths, errs) = crate::routes::bridge_save::save_images_to_disk(
        &items,
        &save_folder,
        &image_format,
        &save_naming,
    );

    // Sweep XMP + DB (best-effort)
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
    let saved_items: Vec<serde_json::Value> =
        crate::routes::sweep_common::saved_items_from_file_ids(&saved_paths, &file_ids);
    api_ok(json!({
        "saved": saved_paths,
        "count": count,
        "errors": errs,
        "saved_items": saved_items,
    }))
    .into_response()
}

#[derive(Debug, Deserialize)]
struct LorasQuery {
    q: Option<String>,
}

async fn loras(State(state): State<SharedState>, Query(params): Query<LorasQuery>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_get(&state.inference_client, &api_url, "/sdapi/v1/loras").await {
        Ok(data) => {
            let Value::Array(items) = data else {
                return api_err("unexpected SD WebUI response", StatusCode::BAD_GATEWAY);
            };
            let filtered: Vec<Value> =
                if let Some(q) = params.q.as_deref().map(|s| s.trim().to_lowercase()) {
                    if !q.is_empty() {
                        items
                            .into_iter()
                            .filter(|item| {
                                let name = item
                                    .get("name")
                                    .and_then(Value::as_str)
                                    .unwrap_or("")
                                    .to_lowercase();
                                // Python checks "alias" key, not "path"
                                let alias = item
                                    .get("alias")
                                    .and_then(Value::as_str)
                                    .unwrap_or("")
                                    .to_lowercase();
                                name.contains(&q) || alias.contains(&q)
                            })
                            .collect()
                    } else {
                        items
                    }
                } else {
                    items
                };
            api_ok(json!({"loras": filtered})).into_response()
        }
        // Python list_loras() catches BridgeConnectionError → returns None → {"loras": null}
        Err(_) => api_ok(json!({"loras": Value::Null})).into_response(),
    }
}

async fn embeddings(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_get(&state.inference_client, &api_url, "/sdapi/v1/embeddings").await {
        Ok(data) => {
            // Python normalizes: loaded/skipped are dicts (name→info), extract keys as lists
            let loaded: Vec<String> = data
                .get("loaded")
                .and_then(Value::as_object)
                .map(|m| m.keys().cloned().collect())
                .unwrap_or_default();
            let skipped: Vec<String> = data
                .get("skipped")
                .and_then(Value::as_object)
                .map(|m| m.keys().cloned().collect())
                .unwrap_or_default();
            api_ok(json!({"loaded": loaded, "skipped": skipped})).into_response()
        }
        // Python list_embeddings() catches BridgeConnectionError → {"loaded": [], "skipped": []}
        Err(_) => api_ok(json!({"loaded": [], "skipped": []})).into_response(),
    }
}

async fn scripts(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_get(&state.inference_client, &api_url, "/sdapi/v1/scripts").await {
        Ok(data) => {
            // Python normalizes: ensure arrays, spread at top level
            let txt2img = data
                .get("txt2img")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let img2img = data
                .get("img2img")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            api_ok(json!({"txt2img": txt2img, "img2img": img2img})).into_response()
        }
        // Python list_scripts() catches BridgeConnectionError → {"txt2img": [], "img2img": []}
        Err(_) => api_ok(json!({"txt2img": [], "img2img": []})).into_response(),
    }
}

async fn script_info(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_get(&state.inference_client, &api_url, "/sdapi/v1/script-info").await {
        Ok(data) => api_ok(json!({"scripts": data})).into_response(),
        // Python list_script_info() catches BridgeConnectionError → returns None → {"scripts": null}
        Err(_) => api_ok(json!({"scripts": Value::Null})).into_response(),
    }
}

async fn extensions_list(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_get(&state.inference_client, &api_url, "/sdapi/v1/extensions").await {
        Ok(data) => api_ok(json!({"extensions": data})).into_response(),
        // Python list_extensions() catches BridgeConnectionError → returns None → {"extensions": null}
        Err(_) => api_ok(json!({"extensions": Value::Null})).into_response(),
    }
}

// Mirrors Python's _build_response + fetch_save_state from sd_webui_api_diag_routes.py
async fn save_state_diag(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    let bridge_managed = cfg_bool(&cfg, "bridge_managed_save", false);

    match sd_get(&state.inference_client, &api_url, "/sdapi/v1/options").await {
        Ok(opts) => {
            let samples_save = opts
                .get("samples_save")
                .and_then(Value::as_bool)
                .unwrap_or(true);
            let grid_save = opts
                .get("grid_save")
                .and_then(Value::as_bool)
                .unwrap_or(true);
            let save_keys: Vec<Value> = if let Some(map) = opts.as_object() {
                let mut keys: Vec<Value> = map
                    .iter()
                    .filter(|(k, v)| k.to_lowercase().contains("save") && v.is_boolean())
                    .map(|(k, v)| json!({"key": k, "value": v.as_bool().unwrap_or(false)}))
                    .collect();
                keys.sort_by(|a, b| {
                    a["key"]
                        .as_str()
                        .unwrap_or("")
                        .cmp(b["key"].as_str().unwrap_or(""))
                });
                keys
            } else {
                vec![]
            };
            let (verdict, verdict_message_key) = if !samples_save && !grid_save {
                ("ok", "sd_bridge.diag_save_state_verdict_ok")
            } else {
                (
                    "save_still_enabled",
                    "sd_bridge.diag_save_state_verdict_save_still_enabled",
                )
            };
            api_ok(json!({
                "api_url": api_url,
                "bridge_managed_save": bridge_managed,
                "options_reachable": true,
                "api_type_guess": "sdapi_v1",
                "samples_save": samples_save,
                "grid_save": grid_save,
                "save_keys": save_keys,
                "verdict": verdict,
                "verdict_message_key": verdict_message_key,
                "error": null,
            }))
            .into_response()
        }
        Err(e) => api_ok(json!({
            "api_url": api_url,
            "bridge_managed_save": bridge_managed,
            "options_reachable": false,
            "api_type_guess": "gradio4_or_disabled",
            "samples_save": null,
            "grid_save": null,
            "save_keys": [],
            "verdict": "options_unreachable",
            "verdict_message_key": "sd_bridge.diag_save_state_verdict_options_unreachable",
            "error": e,
        }))
        .into_response(),
    }
}

pub fn routes() -> Router<SharedState> {
    Router::new()
        .route("/ext/sd-webui/info", get(info))
        .route("/ext/sd-webui/api/test-connection", post(test_connection))
        .route("/ext/sd-webui/api/samplers", get(samplers))
        .route("/ext/sd-webui/api/upscalers", get(upscalers))
        .route("/ext/sd-webui/api/models", get(models_list))
        .route("/ext/sd-webui/api/models/switch", post(models_switch))
        .route("/ext/sd-webui/api/refresh-assets", post(refresh_assets))
        .route(
            "/ext/sd-webui/api/config",
            get(get_config).post(post_config),
        )
        .route("/ext/sd-webui/api/save-batch", post(save_batch))
        .route("/ext/sd-webui/api/loras", get(loras))
        .route("/ext/sd-webui/api/embeddings", get(embeddings))
        .route("/ext/sd-webui/api/scripts", get(scripts))
        .route("/ext/sd-webui/api/script-info", get(script_info))
        .route("/ext/sd-webui/api/extensions", get(extensions_list))
        .route("/ext/sd-webui/api/save-state-diag", get(save_state_diag))
        .route("/ext/sd-webui/api/generate", post(generate::generate))
        .route("/ext/sd-webui/api/progress", get(generate::progress))
        .route("/ext/sd-webui/api/cancel", post(generate::cancel))
}

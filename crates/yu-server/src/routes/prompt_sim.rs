//! prompt_sim.rs — route handlers for /ext/prompt-sim/* endpoints.

use axum::{
    body::Bytes,
    extract::{Multipart, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde::Deserialize;
use serde_json::json;
use std::collections::BTreeMap;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::prompt_sim_core::{self as core};
use crate::state::SharedState;

const EXT_NAME: &str = "builtin-prompt-simulator";
const MAX_PROMPT: usize = 8192;

fn cfg(s: &SharedState) -> &str {
    s.config.config_path.to_str().unwrap_or_default()
}

fn admin(s: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(s.config.pin_auth_enabled, auth.map(|e| &e.0))
}

// --- Wildcard endpoints ---

#[derive(Deserialize)]
pub struct WildcardQuery {
    raw: Option<String>,
    json: Option<String>,
}

pub async fn wildcards(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Query(q): Query<WildcardQuery>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let _ = (q.raw, q.json); // reserved for future use
    let dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "wildcard_dirs");
    if dirs.is_empty() {
        return Json(json!({"wildcards": {}, "dirs": []})).into_response();
    }
    let (wildcards, sources) = core::load_wildcards(&dirs);
    Json(json!({"wildcards": wildcards, "sources": sources, "dirs": dirs})).into_response()
}

pub async fn load_wildcards_zip(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    mut multipart: Multipart,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let mut file_data: Option<Bytes> = None;
    while let Ok(Some(field)) = multipart.next_field().await {
        if field.name() == Some("file") {
            file_data = field.bytes().await.ok();
            break;
        }
    }
    let data = match file_data {
        Some(d) => d,
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "No file uploaded"})),
            )
                .into_response()
        }
    };
    match core::load_wildcards_from_zip(&data) {
        Ok(wildcards) => Json(json!({"wildcards": wildcards})).into_response(),
        Err(e) if e.contains("exceeds limit") => (
            StatusCode::PAYLOAD_TOO_LARGE,
            Json(json!({"error": "File too large (max 50MB)"})),
        )
            .into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": e}))).into_response(),
    }
}

pub async fn wildcard_file_save(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let name = body["name"].as_str().unwrap_or("").trim().to_string();
    let lines_raw = body["lines"].as_array();
    if name.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "name is required"})),
        )
            .into_response();
    }
    let lines = match lines_raw {
        Some(arr) => arr
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect::<Vec<_>>(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "lines must be a list"})),
            )
                .into_response()
        }
    };
    if lines.len() > 100000 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Too many lines (max 100000)"})),
        )
            .into_response();
    }
    let dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "wildcard_dirs");
    if dirs.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "No wildcard directories configured", "code": "no_dirs"})),
        )
            .into_response();
    }
    match core::save_wildcard_file(&name, &lines, &dirs) {
        Ok(path) => Json(json!({"saved_path": path.to_string_lossy()})).into_response(),
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": e, "code": "invalid"})),
        )
            .into_response(),
    }
}

pub async fn wildcard_rename(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let old_name = body["old_name"].as_str().unwrap_or("").trim().to_string();
    let new_name = body["new_name"].as_str().unwrap_or("").trim().to_string();
    if old_name.is_empty() || new_name.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "old_name and new_name are required"})),
        )
            .into_response();
    }
    if old_name == new_name {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "old_name and new_name are identical"})),
        )
            .into_response();
    }
    let dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "wildcard_dirs");
    match core::rename_wildcard_files(&old_name, &new_name, &dirs) {
        Ok(renamed) => Json(json!({"renamed": renamed})).into_response(),
        Err(e) if e.contains("already exists") => (
            StatusCode::CONFLICT,
            Json(json!({"error": e, "code": "collision"})),
        )
            .into_response(),
        Err(e) if e.contains("not found") => (
            StatusCode::NOT_FOUND,
            Json(json!({"error": e, "code": "not_found"})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": e, "code": "invalid"})),
        )
            .into_response(),
    }
}

pub async fn wildcard_delete(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let name = body["name"].as_str().unwrap_or("").trim().to_string();
    if name.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "name is required"})),
        )
            .into_response();
    }
    let dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "wildcard_dirs");
    match core::delete_wildcard_files(&name, &dirs) {
        Ok(removed) => Json(json!({"removed": removed})).into_response(),
        Err(e) if e.contains("not found") => (
            StatusCode::NOT_FOUND,
            Json(json!({"error": e, "code": "not_found"})),
        )
            .into_response(),
        Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"error": e}))).into_response(),
    }
}

pub async fn wildcard_dirs_save(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let dirs = match body["dirs"].as_array() {
        Some(arr) => arr
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.trim().to_string()))
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "dirs must be a list"})),
            )
                .into_response()
        }
    };
    let mut updates = serde_json::Map::new();
    updates.insert(
        "wildcard_dirs".to_string(),
        serde_json::to_value(&dirs).unwrap(),
    );
    if let Err(e) = core::save_ext_config(cfg(&s), EXT_NAME, &updates) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response();
    }
    let validation = core::validate_dirs(&dirs);
    Json(json!({"saved": dirs, "validation": validation})).into_response()
}

// --- Sweep axis endpoints ---

pub async fn sweep_axes(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let axis_dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "sweep_axis_dirs");
    let wildcard_dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "wildcard_dirs");
    let include_wc = {
        let cfg_val = core::read_config_json(cfg(&s));
        cfg_val["extensions"][EXT_NAME]["sweep_include_wildcard_dirs"]
            .as_bool()
            .unwrap_or(false)
    };
    if axis_dirs.is_empty() && (!include_wc || wildcard_dirs.is_empty()) {
        return Json(json!({"axes": {}, "sources": {}, "axis_dirs": axis_dirs, "include_wildcard_dirs": include_wc, "wildcard_dirs": wildcard_dirs})).into_response();
    }
    let (axes, sources) = core::load_sweep_axes(&axis_dirs, include_wc, &wildcard_dirs);
    Json(json!({"axes": axes, "sources": sources, "axis_dirs": axis_dirs, "include_wildcard_dirs": include_wc, "wildcard_dirs": wildcard_dirs})).into_response()
}

pub async fn sweep_axis_config_save(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let mut updates = serde_json::Map::new();
    if let Some(dirs) = body["axis_dirs"].as_array() {
        let cleaned: Vec<String> = dirs
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.trim().to_string()))
            .filter(|s| !s.is_empty())
            .collect();
        updates.insert(
            "sweep_axis_dirs".to_string(),
            serde_json::to_value(&cleaned).unwrap(),
        );
    }
    if let Some(include) = body.get("include_wildcard_dirs") {
        updates.insert(
            "sweep_include_wildcard_dirs".to_string(),
            serde_json::Value::Bool(include.as_bool().unwrap_or(false)),
        );
    }
    if updates.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "no settings provided"})),
        )
            .into_response();
    }
    if let Err(e) = core::save_ext_config(cfg(&s), EXT_NAME, &updates) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response();
    }
    let axis_dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "sweep_axis_dirs");
    let include_wc = {
        let cfg_val = core::read_config_json(cfg(&s));
        cfg_val["extensions"][EXT_NAME]["sweep_include_wildcard_dirs"]
            .as_bool()
            .unwrap_or(false)
    };
    Json(json!({"axis_dirs": axis_dirs, "include_wildcard_dirs": include_wc, "validation": core::validate_dirs(&axis_dirs)})).into_response()
}

// --- Prompt conversion / analysis endpoints ---

pub async fn convert(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let prompt = body["prompt"].as_str().unwrap_or("").to_string();
    let mode = body["mode"].as_str().unwrap_or("").to_string();
    if prompt.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "No prompt provided"})),
        )
            .into_response();
    }
    if prompt.len() > MAX_PROMPT {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": format!("Prompt too long (max {MAX_PROMPT} chars)"), "code": "prompt_too_long"}))).into_response();
    }
    let result = match mode.as_str() {
        "nai_to_sd" => core::convert_nai_to_sd(&prompt),
        "sd_to_nai" => core::convert_sd_to_nai(&prompt),
        "expand" => {
            let seed = body["seed"].as_u64();
            let wildcard_dirs = core::get_ext_dirs(cfg(&s), EXT_NAME, "wildcard_dirs");
            let user_wildcards: BTreeMap<String, Vec<String>> = body["wildcards"]
                .as_object()
                .map(|m| {
                    m.iter()
                        .filter_map(|(k, v)| {
                            v.as_array().map(|arr| {
                                (
                                    k.clone(),
                                    arr.iter()
                                        .filter_map(|s| s.as_str().map(|s| s.to_string()))
                                        .collect(),
                                )
                            })
                        })
                        .collect()
                })
                .unwrap_or_default();
            let mut wildcards = if wildcard_dirs.is_empty() {
                BTreeMap::new()
            } else {
                core::load_wildcards(&wildcard_dirs).0
            };
            wildcards.extend(user_wildcards);
            core::expand_dynamic_prompt(&prompt, seed, &wildcards)
        }
        _ => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "Invalid mode", "code": "invalid_mode"})),
            )
                .into_response()
        }
    };
    Json(json!({"result": result})).into_response()
}

pub async fn emphasis(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let prompt = body["prompt"].as_str().unwrap_or("").to_string();
    if prompt.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "No prompt provided"})),
        )
            .into_response();
    }
    if prompt.len() > MAX_PROMPT {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": format!("Prompt too long (max {MAX_PROMPT} chars)"), "code": "prompt_too_long"}))).into_response();
    }
    Json(json!({"tokens": core::analyze_emphasis(&prompt)})).into_response()
}

// --- Danbooru autocomplete ---

#[derive(Deserialize)]
pub struct DanbooruQuery {
    q: Option<String>,
    limit: Option<u32>,
}

pub async fn danbooru_ac(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Query(params): Query<DanbooruQuery>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    let q = params.q.unwrap_or_default().trim().to_string();
    if q.len() < 2 {
        return Json(json!({"tags": []})).into_response();
    }
    let limit = params.limit.unwrap_or(10).min(20);
    let url = format!(
        "https://danbooru.donmai.us/autocomplete.json?search%5Bquery%5D={}&search%5Btype%5D=tag_query&limit={}",
        urlencoding::encode(&q), limit
    );
    let result = s
        .python_client
        .get(&url)
        .header("User-Agent", "YU-AI-Manager/1.0")
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await;
    match result {
        Ok(resp) => {
            let data: Vec<serde_json::Value> = resp.json().await.unwrap_or_default();
            let tags: Vec<serde_json::Value> = data
                .iter()
                .filter_map(|item| {
                    item["label"].as_str().map(|label| {
                        json!({
                            "name": label,
                            "count": item["post_count"].as_u64().unwrap_or(0),
                        })
                    })
                })
                .collect();
            Json(json!({"tags": tags})).into_response()
        }
        Err(_) => Json(json!({"tags": []})).into_response(),
    }
}

// --- dp-analyze ---

pub async fn dp_analyze(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Option<Json<serde_json::Value>>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }

    let body = body.map(|b| b.0).unwrap_or(serde_json::Value::Null);

    let prompt = match body.get("prompt") {
        Some(serde_json::Value::String(s)) => s.clone(),
        Some(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "prompt must be a string"})),
            )
                .into_response();
        }
        None => String::new(),
    };

    if prompt.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "No prompt provided"})),
        )
            .into_response();
    }

    if prompt.chars().count() > MAX_PROMPT {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "error": format!("Prompt too long (max {} chars)", MAX_PROMPT),
                "code": "prompt_too_long",
            })),
        )
            .into_response();
    }

    Json(json!({"groups": core::analyze_dp_choices(&prompt)})).into_response()
}

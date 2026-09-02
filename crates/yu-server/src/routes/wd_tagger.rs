use std::{
    collections::{BTreeMap, HashMap, HashSet},
    fs,
    future::Future,
    path::{Path, PathBuf},
    pin::Pin,
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant},
};

use axum::{
    body::Bytes,
    extract::{Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Map, Value};
use sqlx::{Row, SqlitePool};
use tempfile::Builder;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

use super::analysis_net;
use crate::routes::auto_stubs::read_config_json;
use crate::routes::tag_reads::build_wd_tags;
use crate::routes::wd_infer::{
    call_wd_infer, call_wd_infer_temp_frame, validate_wd_infer_path, WdInferOutcome,
};
use crate::routes::wd_tagger_infer::{sanitize_model_id, NSFW_TAG_SET};
use crate::routes::wd_tagger_write::{write_wd_tags, write_wd_tags_for_retag};
use crate::routes::wd_tagger_xmp::write_wd_xmp;
use crate::routes::{
    search::{fetch_matching_ids, table_exists, SearchParams, SearchQueryRaw},
    wd_tagger_batch::{
        filter_active_in_order, query_backfill_targets, run_batch_worker_with_tagger,
        WD_TAGGER_JOB_ID,
    },
};
use futures_util::FutureExt;
use futures_util::StreamExt;
use reqwest::{header::LOCATION, StatusCode as ReqwestStatusCode, Url};

pub(crate) const ACTIVE_MODEL_KEY: &str = "wd_active_model_id";
const LEGACY_DEFAULT_FILES: [&str; 2] = ["model.onnx", "selected_tags.csv"];
const DEFAULT_MODEL: &str = "SmilingWolf/wd-swinv2-tagger-v3";
const PROFILE_JSON_MAX_BYTES: usize = 1024 * 1024;
const HF_MAX_DOWNLOAD_BYTES: u64 = 8 * 1024 * 1024 * 1024;
const HF_CHUNK_BYTES: usize = 256 * 1024;
const HF_MAX_REDIRECTS: usize = 5;
const HF_USER_AGENT: &str = "yu-ai-manager/1.0";
const HF_HOSTS: [&str; 2] = ["huggingface.co", "hf.co"];
static HF_TEMP_SEQ: AtomicU64 = AtomicU64::new(0);

pub(crate) fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": "internal_server_error"})),
    )
        .into_response()
}

pub(crate) fn api_error_code(message: &str, status: StatusCode, code: &str) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
        .into_response()
}

fn api_error_extra(message: &str, status: StatusCode, code: &str, extra: Value) -> Response {
    let mut body = Map::from_iter([
        ("ok".to_string(), Value::Bool(false)),
        ("error".to_string(), json!(message)),
        ("code".to_string(), json!(code)),
    ]);
    if let Some(extra) = extra.as_object() {
        for (key, value) in extra {
            body.insert(key.clone(), value.clone());
        }
    }
    (status, Json(Value::Object(body))).into_response()
}

pub(crate) fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn active_model_id(pool: &SqlitePool) -> Result<Option<String>, sqlx::Error> {
    let value = sqlx::query_scalar::<_, Option<String>>("SELECT value FROM kv_state WHERE key = ?")
        .bind(ACTIVE_MODEL_KEY)
        .fetch_optional(pool)
        .await?
        .flatten()
        .filter(|value| !value.is_empty());
    Ok(value)
}

async fn available_model_ids(pool: &SqlitePool) -> Result<HashSet<String>, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT DISTINCT md.model
         FROM file_wd_tags fwt
         JOIN wd_model_dict md ON md.id = fwt.model_id
         ORDER BY md.model",
    )
    .fetch_all(pool)
    .await?;
    Ok(rows
        .into_iter()
        .map(|row| row.get::<String, _>(0))
        .collect())
}

async fn available_models(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT md.model, COUNT(DISTINCT fwt.file_id) AS file_count
         FROM file_wd_tags fwt
         JOIN wd_model_dict md ON md.id = fwt.model_id
         GROUP BY fwt.model_id, md.model
         ORDER BY md.model",
    )
    .fetch_all(pool)
    .await?;
    Ok(Value::Array(
        rows.into_iter()
            .map(|row| {
                json!({
                    "model_id": row.get::<String, _>(0),
                    "file_count": row.get::<i64, _>(1),
                })
            })
            .collect(),
    ))
}

fn builtin_profiles_dir(project_root: &Path) -> PathBuf {
    project_root.join("extensions/builtin_wd_tagger/core_impl/profiles")
}

fn user_profiles_dir(project_root: &Path) -> PathBuf {
    project_root.join("profiles/wd_tagger")
}

fn valid_profile_id(id: &str) -> bool {
    let mut chars = id.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if id.len() > 64 || !first.is_ascii_lowercase() && !first.is_ascii_digit() {
        return false;
    }
    chars.all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '_' || ch == '-')
}

fn sorted_json_files(dir: &Path) -> Vec<PathBuf> {
    let Ok(read_dir) = fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut paths = read_dir
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .collect::<Vec<_>>();
    paths.sort();
    paths
}

fn read_profile(path: &Path, builtin: bool) -> Option<Value> {
    let raw = fs::read(path).ok()?;
    if raw.len() > 1024 * 1024 {
        return None;
    }
    let text = String::from_utf8_lossy(raw.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(&raw));
    let mut value = serde_json::from_str::<Value>(&text).ok()?;
    value["builtin"] = Value::Bool(builtin);
    Some(value)
}

fn read_profile_result(path: &Path, builtin: bool) -> Result<Value, String> {
    let raw = fs::read(path).map_err(|error| error.to_string())?;
    if raw.len() > PROFILE_JSON_MAX_BYTES {
        return Err("profile too large".to_string());
    }
    let text = String::from_utf8_lossy(raw.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(&raw));
    let mut value = serde_json::from_str::<Value>(&text).map_err(|error| error.to_string())?;
    value["builtin"] = Value::Bool(builtin);
    Ok(value)
}

pub(crate) fn load_full_profiles(
    project_root: &Path,
) -> BTreeMap<String, (Value, &'static str, bool)> {
    let mut builtin_ids = HashSet::new();
    let mut profiles = BTreeMap::new();
    for path in sorted_json_files(&builtin_profiles_dir(project_root)) {
        if let Ok(profile) = read_profile_result(&path, true) {
            if let Some(id) = profile.get("id").and_then(Value::as_str) {
                builtin_ids.insert(id.to_string());
                profiles.insert(id.to_string(), (profile, "builtin", false));
            }
        }
    }
    for path in sorted_json_files(&user_profiles_dir(project_root)) {
        if let Ok(profile) = read_profile_result(&path, false) {
            if let Some(id) = profile.get("id").and_then(Value::as_str) {
                let overrides = builtin_ids.contains(id);
                profiles.insert(id.to_string(), (profile, "user", overrides));
            }
        }
    }
    profiles
}

fn validate_profile_body(body: &Value) -> Result<Value, Vec<Value>> {
    let Some(obj) = body.as_object() else {
        return Err(vec![
            json!({"path": "", "message": "body must be a JSON object"}),
        ]);
    };
    let required = [
        "profile_version",
        "id",
        "display_name",
        "model_id",
        "adapter_family",
        "backend",
        "files",
        "preprocess_spec",
        "tag_source",
        "threshold_source",
        "supports_categories",
        "default_thresholds",
    ];
    let mut errors = Vec::new();
    for key in required {
        if !obj.contains_key(key) {
            errors.push(json!({"path": key, "message": format!("profile field missing: {key}")}));
        }
    }
    if body.get("profile_version").and_then(Value::as_str) != Some("2") {
        errors.push(json!({"path": "profile_version", "message": "user drop-in profile must be profile_version=\"2\""}));
    }
    if let Some(id) = body.get("id").and_then(Value::as_str) {
        if !valid_profile_id(id) {
            errors.push(json!({"path": "id", "message": "invalid profile id"}));
        }
    }
    if body
        .get("files")
        .and_then(Value::as_array)
        .is_none_or(|files| files.is_empty())
    {
        errors.push(json!({"path": "files", "message": "files must be a non-empty list"}));
    }
    if !errors.is_empty() {
        return Err(errors);
    }
    let mut normalized = body.clone();
    normalized["builtin"] = Value::Bool(false);
    normalized["source_profile_version"] = normalized
        .get("profile_version")
        .cloned()
        .unwrap_or_else(|| json!("2"));
    Ok(normalized)
}

fn profile_api_payload(profile: Value, origin: &str, overrides_builtin: bool) -> Value {
    json!({"profile": profile, "origin": origin, "overrides_builtin": overrides_builtin})
}

fn user_profile_path(project_root: &Path, id: &str) -> Result<PathBuf, Response> {
    if !valid_profile_id(id) {
        return Err(api_error_code(
            "invalid id",
            StatusCode::BAD_REQUEST,
            "invalid_id",
        ));
    }
    let root = user_profiles_dir(project_root);
    let candidate = root.join(format!("{id}.json"));
    Ok(candidate)
}

fn atomic_write_json(path: &Path, value: &Value) -> Result<(), std::io::Error> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    let tmp = path.with_extension("json.tmp");
    let text = serde_json::to_string_pretty(value)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;
    fs::write(&tmp, format!("{text}\n"))?;
    fs::rename(&tmp, path)
}

fn notify_wd_profiles_changed(state: &SharedState) {
    if state.config.python_url.is_empty() {
        return;
    }
    let url = format!(
        "{}/_internal/wd-tagger/profiles-changed",
        state.config.python_url.trim_end_matches('/')
    );
    let client = state.python_client.clone();
    tokio::spawn(async move {
        let _ = client.post(&url).send().await;
    });
}

fn profile_summary(profile: &Value, origin: &str, overrides_builtin: bool) -> Option<Value> {
    let threshold_type = profile
        .get("threshold_source")
        .and_then(|source| source.get("type"))
        .cloned()
        .or_else(|| {
            if profile.get("profile_version").and_then(Value::as_str) == Some("1") {
                Some(json!("global_per_category"))
            } else {
                None
            }
        })
        .unwrap_or(Value::Null);
    Some(json!({
        "id": profile.get("id")?.as_str()?,
        "display_name": profile.get("display_name")?.as_str()?,
        "model_id": profile.get("model_id")?.as_str()?,
        "adapter_family": profile.get("adapter_family")?.as_str()?,
        "backend": profile.get("backend")?.as_str()?,
        "builtin": profile.get("builtin").and_then(Value::as_bool).unwrap_or(false),
        "categories_mode": profile
            .get("categories_mode")
            .and_then(Value::as_str)
            .unwrap_or("from_tag_source"),
        "threshold_source": {"type": threshold_type},
        "origin": origin,
        "overrides_builtin": overrides_builtin,
    }))
}

fn load_profile_summaries(project_root: &Path) -> Vec<Value> {
    let mut builtin_ids = HashSet::new();
    let mut profiles = BTreeMap::new();
    for path in sorted_json_files(&builtin_profiles_dir(project_root)) {
        if let Some(profile) = read_profile(&path, true) {
            if let Some(id) = profile.get("id").and_then(Value::as_str) {
                builtin_ids.insert(id.to_string());
                if let Some(summary) = profile_summary(&profile, "builtin", false) {
                    profiles.insert(id.to_string(), summary);
                }
            }
        }
    }
    for path in sorted_json_files(&user_profiles_dir(project_root)) {
        if let Some(profile) = read_profile(&path, false) {
            if let Some(id) = profile.get("id").and_then(Value::as_str) {
                if let Some(summary) = profile_summary(&profile, "user", builtin_ids.contains(id)) {
                    profiles.insert(id.to_string(), summary);
                }
            }
        }
    }
    profiles.into_values().collect()
}

pub async fn profiles(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let active = match active_model_id(&state.db_read).await {
        Ok(value) => value,
        Err(error) => return internal_error(error, "failed to get active WD model id"),
    };
    let available = match available_model_ids(&state.db_read).await {
        Ok(value) => value,
        Err(error) => return internal_error(error, "failed to list available WD models"),
    };
    let mut profiles = load_profile_summaries(&state.config.project_root);
    for profile in &mut profiles {
        let has_tags = profile
            .get("id")
            .and_then(Value::as_str)
            .is_some_and(|id| available.contains(id))
            || profile
                .get("model_id")
                .and_then(Value::as_str)
                .is_some_and(|id| available.contains(id));
        profile["has_tags"] = Value::Bool(has_tags);
    }
    api_result(json!({"profiles": profiles, "active_model_id": active}))
}

pub async fn profile_get(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(id): AxumPath<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if !valid_profile_id(&id) {
        return api_error_code("invalid id", StatusCode::BAD_REQUEST, "invalid_id");
    }
    let profiles = load_full_profiles(&state.config.project_root);
    let Some((profile, origin, overrides_builtin)) = profiles.get(&id) else {
        return api_error_code("not found", StatusCode::NOT_FOUND, "not_found");
    };
    api_result(profile_api_payload(
        profile.clone(),
        origin,
        *overrides_builtin,
    ))
}

pub async fn profile_create(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(id) = body.get("id").and_then(Value::as_str) else {
        return api_error_code("invalid id", StatusCode::BAD_REQUEST, "invalid_id");
    };
    let path = match user_profile_path(&state.config.project_root, id) {
        Ok(path) => path,
        Err(response) => return response,
    };
    let profile = match validate_profile_body(&body) {
        Ok(profile) => profile,
        Err(errors) => {
            return api_error_extra(
                "validation failed",
                StatusCode::BAD_REQUEST,
                "validation_failed",
                json!({"errors": errors}),
            )
        }
    };
    if path.exists() {
        return api_error_code(
            &format!("id conflict: {id}"),
            StatusCode::CONFLICT,
            "id_conflict",
        );
    }
    let overrides_builtin = load_full_profiles(&state.config.project_root)
        .get(id)
        .is_some_and(|(_, origin, _)| *origin == "builtin");
    if let Err(error) = atomic_write_json(&path, &profile) {
        return internal_error(error, "failed to write WD profile");
    }
    notify_wd_profiles_changed(&state);
    api_result(profile_api_payload(profile, "user", overrides_builtin))
}

pub async fn profile_update(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(id): AxumPath<String>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let path = match user_profile_path(&state.config.project_root, &id) {
        Ok(path) => path,
        Err(response) => return response,
    };
    if body.get("id").and_then(Value::as_str) != Some(id.as_str()) {
        return api_error_code("id immutable", StatusCode::BAD_REQUEST, "id_immutable");
    }
    let existing = load_full_profiles(&state.config.project_root);
    let Some((_, origin, overrides_builtin)) = existing.get(&id) else {
        return api_error_code("not found", StatusCode::NOT_FOUND, "not_found");
    };
    if *origin == "builtin" && !path.exists() {
        return api_error_code(
            "builtin is read-only",
            StatusCode::FORBIDDEN,
            "builtin_read_only",
        );
    }
    let profile = match validate_profile_body(&body) {
        Ok(profile) => profile,
        Err(errors) => {
            return api_error_extra(
                "validation failed",
                StatusCode::BAD_REQUEST,
                "validation_failed",
                json!({"errors": errors}),
            )
        }
    };
    if let Err(error) = atomic_write_json(&path, &profile) {
        return internal_error(error, "failed to write WD profile");
    }
    notify_wd_profiles_changed(&state);
    api_result(profile_api_payload(profile, "user", *overrides_builtin))
}

pub async fn profile_delete(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(id): AxumPath<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let path = match user_profile_path(&state.config.project_root, &id) {
        Ok(path) => path,
        Err(response) => return response,
    };
    let existing = load_full_profiles(&state.config.project_root);
    let Some((_, origin, _)) = existing.get(&id) else {
        return api_error_code("not found", StatusCode::NOT_FOUND, "not_found");
    };
    if *origin == "builtin" && !path.exists() {
        return api_error_code(
            "builtin is read-only",
            StatusCode::FORBIDDEN,
            "builtin_read_only",
        );
    }
    match active_model_id(&state.db_read).await {
        Ok(Some(active)) if active == id => {
            return api_error_extra(
                "profile is active model",
                StatusCode::CONFLICT,
                "in_use",
                json!({"active_model_id": active}),
            )
        }
        Ok(_) => {}
        Err(error) => return internal_error(error, "failed to get active WD model id"),
    }
    if path.exists() {
        if let Err(error) = fs::remove_file(&path) {
            return internal_error(error, "failed to delete WD profile");
        }
    }
    notify_wd_profiles_changed(&state);
    api_result(json!({"deleted": true}))
}

pub async fn active_model(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let active = match active_model_id(&state.db_read).await {
        Ok(value) => value,
        Err(error) => return internal_error(error, "failed to get active WD model id"),
    };
    let models = match available_models(&state.db_read).await {
        Ok(value) => value,
        Err(error) => return internal_error(error, "failed to list available WD models"),
    };
    api_result(json!({"active_model_id": active, "available_models": models}))
}

fn validate_model_id_value(raw: Option<&Value>) -> Result<Option<String>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    if raw.is_null() {
        return Ok(None);
    }
    let Some(model_id) = raw.as_str() else {
        return Err("model_id must be a string or null".to_string());
    };
    let model_id = model_id.trim();
    if model_id.is_empty() {
        return Ok(None);
    }
    if model_id.len() > 128 || model_id.chars().any(|ch| ch.is_control()) {
        return Err(if model_id.len() > 128 {
            "model_id is too long".to_string()
        } else {
            "model_id contains disallowed control characters".to_string()
        });
    }
    Ok(Some(model_id.to_string()))
}

async fn model_is_known_for_activation(
    state: &SharedState,
    model_id: &str,
) -> Result<bool, sqlx::Error> {
    let profiles = load_full_profiles(&state.config.project_root);
    if profiles.iter().any(|(id, (profile, _, _))| {
        id == model_id || profile.get("model_id").and_then(Value::as_str) == Some(model_id)
    }) {
        return Ok(true);
    }
    let Some(mid) = sqlx::query_scalar::<_, i64>("SELECT id FROM wd_model_dict WHERE model = ?")
        .bind(model_id)
        .fetch_optional(&state.db_read)
        .await?
    else {
        return Ok(false);
    };
    let row = sqlx::query_scalar::<_, i64>("SELECT 1 FROM file_wd_tags WHERE model_id = ? LIMIT 1")
        .bind(mid)
        .fetch_optional(&state.db_read)
        .await?;
    Ok(row.is_some())
}

pub(crate) async fn set_active_model_id(
    pool: &SqlitePool,
    model_id: Option<&str>,
) -> Result<(), sqlx::Error> {
    if let Some(model_id) = model_id {
        sqlx::query(
            "INSERT INTO kv_state(key, value) VALUES(?, ?)
             ON CONFLICT(key) DO UPDATE SET
             value = excluded.value,
             updated_at = strftime('%s','now')",
        )
        .bind(ACTIVE_MODEL_KEY)
        .bind(model_id)
        .execute(pool)
        .await?;
    } else {
        sqlx::query("DELETE FROM kv_state WHERE key = ?")
            .bind(ACTIVE_MODEL_KEY)
            .execute(pool)
            .await?;
    }
    Ok(())
}

pub async fn active_model_update(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let model_id = match validate_model_id_value(body.get("model_id")) {
        Ok(model_id) => model_id,
        Err(error) => {
            return api_error_code(&error, StatusCode::BAD_REQUEST, "invalid_model_id");
        }
    };
    if let Some(model_id) = model_id.as_deref() {
        match model_is_known_for_activation(&state, model_id).await {
            Ok(true) => {}
            Ok(false) => {
                return api_error_code("Unknown WD model", StatusCode::BAD_REQUEST, "unknown_model")
            }
            Err(error) => return internal_error(error, "failed to validate active WD model"),
        }
    }
    if let Err(error) = set_active_model_id(&state.db, model_id.as_deref()).await {
        return internal_error(error, "failed to update active WD model");
    }
    api_result(json!({"active_model_id": model_id}))
}

fn wd_config_from_state(state: &SharedState) -> Map<String, Value> {
    let mut config = Map::from_iter([
        ("model".to_string(), json!(DEFAULT_MODEL)),
        ("general_threshold".to_string(), json!(0.35)),
        ("character_threshold".to_string(), json!(0.85)),
        ("write_xmp".to_string(), json!(true)),
        ("auto_download".to_string(), json!(true)),
        ("engine_type".to_string(), json!("onnx")),
        ("vlm_url".to_string(), json!("http://localhost:11434")),
        ("vlm_model".to_string(), json!("")),
        ("vlm_timeout".to_string(), json!(60)),
        ("nsfw_filter".to_string(), json!(false)),
    ]);
    if let Some(user) = state
        .config
        .app_config
        .get("wd_tagger")
        .and_then(Value::as_object)
    {
        for (key, value) in user {
            config.insert(key.clone(), value.clone());
        }
    }
    config
}

fn read_config_file(config_path: &Path) -> Result<Value, std::io::Error> {
    if !config_path.exists() {
        return Ok(json!({}));
    }
    let text = fs::read_to_string(config_path)?;
    crate::config_io::parse_strict(config_path, &text)
}

fn validated_wd_config_patch(body: &Value) -> Result<Map<String, Value>, Response> {
    let Some(obj) = body.as_object() else {
        return Err(api_error_code(
            "JSON object required",
            StatusCode::BAD_REQUEST,
            "invalid_json",
        ));
    };
    let allowed = [
        "model",
        "general_threshold",
        "character_threshold",
        "write_xmp",
        "auto_download",
        "engine_type",
        "vlm_url",
        "vlm_model",
        "vlm_timeout",
        "nsfw_filter",
    ];
    let mut out = Map::new();
    for key in allowed {
        let Some(value) = obj.get(key) else {
            continue;
        };
        match key {
            "general_threshold" | "character_threshold" => {
                let Some(number) = value.as_f64() else {
                    return Err(api_error_code(
                        "Invalid WD-Tagger config",
                        StatusCode::BAD_REQUEST,
                        "invalid_value",
                    ));
                };
                if !(0.0..=1.0).contains(&number) {
                    return Err(api_error_code(
                        "Invalid WD-Tagger config",
                        StatusCode::BAD_REQUEST,
                        "invalid_value",
                    ));
                }
                out.insert(key.to_string(), json!(round_two(number)));
            }
            "model" | "vlm_url" | "vlm_model" => {
                if !value.is_string() {
                    return Err(api_error_code(
                        "Invalid WD-Tagger config",
                        StatusCode::BAD_REQUEST,
                        "invalid_value",
                    ));
                }
                out.insert(key.to_string(), value.clone());
            }
            "write_xmp" | "auto_download" | "nsfw_filter" => {
                if !value.is_boolean() {
                    return Err(api_error_code(
                        "Invalid WD-Tagger config",
                        StatusCode::BAD_REQUEST,
                        "invalid_value",
                    ));
                }
                out.insert(key.to_string(), value.clone());
            }
            "engine_type" => {
                let engine = value.as_str().unwrap_or("");
                if !matches!(engine, "onnx" | "vlm" | "both") {
                    return Err(api_error_code(
                        "Invalid WD-Tagger config",
                        StatusCode::BAD_REQUEST,
                        "invalid_value",
                    ));
                }
                out.insert(key.to_string(), value.clone());
            }
            "vlm_timeout" => {
                let Some(timeout) = value
                    .as_i64()
                    .or_else(|| value.as_f64().map(crate::num::sat_i64))
                else {
                    return Err(api_error_code(
                        "Invalid WD-Tagger config",
                        StatusCode::BAD_REQUEST,
                        "invalid_value",
                    ));
                };
                if !(10..=300).contains(&timeout) {
                    return Err(api_error_code(
                        "Invalid WD-Tagger config",
                        StatusCode::BAD_REQUEST,
                        "invalid_value",
                    ));
                }
                out.insert(key.to_string(), json!(timeout));
            }
            _ => {}
        }
    }
    Ok(out)
}

fn safe_name(repo: &str) -> String {
    repo.chars()
        .map(|ch| {
            if ch.is_alphanumeric() || ch == '_' || ch == '-' || ch == '.' {
                ch
            } else {
                '_'
            }
        })
        .collect()
}

fn round_two(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

pub async fn model_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let wd_config = wd_config_from_state(&state);
    let key = params
        .get("profile_id")
        .or_else(|| params.get("model_id"))
        .or_else(|| params.get("repo"))
        .cloned()
        .or_else(|| {
            wd_config
                .get("model")
                .and_then(Value::as_str)
                .map(str::to_string)
        })
        .unwrap_or_else(|| DEFAULT_MODEL.to_string());

    let profiles = load_full_profiles(&state.config.project_root);
    let profile = profiles.values().find_map(|(profile, _, _)| {
        let id = profile.get("id").and_then(Value::as_str);
        let model_id = profile.get("model_id").and_then(Value::as_str);
        if id == Some(key.as_str()) || model_id == Some(key.as_str()) {
            Some(profile)
        } else {
            None
        }
    });

    let (repo, cache_dir, file_names, required) = if let Some(profile) = profile {
        let repo = profile
            .get("model_id")
            .and_then(Value::as_str)
            .unwrap_or(&key)
            .to_string();
        let mut cache_dir = state
            .config
            .project_root
            .join("cache/wd_tagger")
            .join(safe_name(&repo));
        if let Some(subdir) = profile.get("hf_subdir").and_then(Value::as_str) {
            if !subdir.is_empty() {
                cache_dir = cache_dir.join(subdir);
            }
        }
        let files = profile
            .get("files")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let mut names = Vec::new();
        let mut required = HashSet::new();
        for file in files {
            if let Some(name) = file.get("name").and_then(Value::as_str) {
                names.push(name.to_string());
                if file
                    .get("required")
                    .and_then(Value::as_bool)
                    .unwrap_or(true)
                {
                    required.insert(name.to_string());
                }
            }
        }
        (repo, cache_dir, names, required)
    } else {
        let cache_dir = state
            .config
            .project_root
            .join("cache/wd_tagger")
            .join(safe_name(&key));
        let names = LEGACY_DEFAULT_FILES
            .iter()
            .map(|name| (*name).to_string())
            .collect::<Vec<_>>();
        let required = names.iter().cloned().collect::<HashSet<_>>();
        (key, cache_dir, names, required)
    };

    let mut files = Map::new();
    let mut ready = true;
    for file_name in file_names {
        let path = cache_dir.join(&file_name);
        let exists = fs::metadata(&path).ok();
        if exists.is_none() && required.contains(&file_name) {
            ready = false;
        }
        let mut value = match exists {
            Some(metadata) => json!({
                "exists": true,
                "size_mb": round_two(metadata.len() as f64 / (1024.0 * 1024.0)),
            }),
            None => json!({"exists": false, "size_mb": 0}),
        };
        if let Some(obj) = value.as_object_mut() {
            obj.insert("required".to_string(), json!(required.contains(&file_name)));
        }
        files.insert(file_name, value);
    }

    api_result(json!({
        "repo": repo,
        "ready": ready,
        "cache_dir": cache_dir.to_string_lossy(),
        "files": files,
        "known_models": {
            "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 v3 (recommended)",
            "SmilingWolf/wd-vit-tagger-v3": "ViT v3",
            "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt v3",
            "SmilingWolf/wd-eva02-large-tagger-v3": "EVA02-Large v3",
            "Camais03/camie-tagger-v2": "Camie Tagger v2",
        }
    }))
}

async fn active_model_db_id(pool: &SqlitePool) -> Result<Option<i64>, sqlx::Error> {
    let Some(active) = active_model_id(pool).await? else {
        return Ok(None);
    };
    sqlx::query_scalar::<_, i64>("SELECT id FROM wd_model_dict WHERE model = ?")
        .bind(active)
        .fetch_optional(pool)
        .await
}

async fn count_untagged(pool: &SqlitePool, active_mid: Option<i64>) -> Result<i64, sqlx::Error> {
    if let Some(mid) = active_mid {
        sqlx::query_scalar(
            "SELECT COUNT(*)
             FROM files f
             WHERE f.is_deleted = 0
               AND NOT EXISTS (
                 SELECT 1 FROM file_wd_tags w
                 WHERE w.file_id = f.id AND w.model_id = ?
               )",
        )
        .bind(mid)
        .fetch_one(pool)
        .await
    } else {
        sqlx::query_scalar(
            "SELECT COUNT(*)
             FROM files f
             WHERE f.is_deleted = 0
               AND NOT EXISTS (
                 SELECT 1 FROM file_wd_tags w
                 WHERE w.file_id = f.id
               )",
        )
        .fetch_one(pool)
        .await
    }
}

async fn build_wd_stats(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if let Ok(Some(row)) = sqlx::query("SELECT stats_json FROM wd_tag_stats_cache WHERE id=1")
        .fetch_optional(pool)
        .await
    {
        if let Ok(raw) = row.try_get::<String, _>(0) {
            if !raw.is_empty() && raw != "{}" {
                if let Ok(value) = serde_json::from_str::<Value>(&raw) {
                    return Ok(value);
                }
            }
        }
    }

    let total_tags = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM file_wd_tags")
        .fetch_one(pool)
        .await?;
    let tagged_files = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM (SELECT DISTINCT file_id FROM file_wd_tags)",
    )
    .fetch_one(pool)
    .await?;
    let unique_tags = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM (SELECT DISTINCT tag_id FROM file_wd_tags)",
    )
    .fetch_one(pool)
    .await?;

    let mut by_category = Map::new();
    for row in sqlx::query(
        "SELECT cd.category, COUNT(*)
         FROM file_wd_tags fwt
         JOIN wd_category_dict cd ON cd.id = fwt.category_id
         GROUP BY fwt.category_id, cd.category
         ORDER BY cd.category",
    )
    .fetch_all(pool)
    .await?
    {
        by_category.insert(row.get::<String, _>(0), json!(row.get::<i64, _>(1)));
    }

    let mut by_model = Map::new();
    for row in sqlx::query(
        "SELECT md.model, COUNT(*)
         FROM (SELECT DISTINCT model_id, file_id FROM file_wd_tags) x
         JOIN wd_model_dict md ON md.id = x.model_id
         GROUP BY x.model_id, md.model
         ORDER BY md.model",
    )
    .fetch_all(pool)
    .await?
    {
        by_model.insert(row.get::<String, _>(0), json!(row.get::<i64, _>(1)));
    }

    let untagged_unknown = count_untagged(pool, active_model_db_id(pool).await?).await?;
    Ok(json!({
        "total_tags": total_tags,
        "tagged_files": tagged_files,
        "unique_tags": unique_tags,
        "by_category": by_category,
        "by_model": by_model,
        "untagged_unknown": untagged_unknown,
    }))
}
pub async fn stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_wd_stats(&state.db_read).await {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "failed to build WD tagger stats"),
    }
}

fn parse_limit(params: &HashMap<String, String>) -> i64 {
    params
        .get("limit")
        .and_then(|raw| raw.parse::<i64>().ok())
        .map(|value| value.clamp(1, 500))
        .unwrap_or(100)
}

fn parse_offset(params: &HashMap<String, String>) -> i64 {
    params
        .get("offset")
        .and_then(|raw| raw.parse::<i64>().ok())
        .map(|value| value.max(0))
        .unwrap_or(0)
}

async fn fetch_untagged(pool: &SqlitePool, limit: i64, offset: i64) -> Result<Value, sqlx::Error> {
    let active_mid = active_model_db_id(pool).await?;
    let rows = if let Some(mid) = active_mid {
        sqlx::query(
            "SELECT f.id, f.path, f.meta_source
             FROM files f
             WHERE f.is_deleted = 0
               AND NOT EXISTS (
                 SELECT 1 FROM file_wd_tags w
                 WHERE w.file_id = f.id AND w.model_id = ?
               )
             ORDER BY f.id
             LIMIT ? OFFSET ?",
        )
        .bind(mid)
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT f.id, f.path, f.meta_source
             FROM files f
             WHERE f.is_deleted = 0
               AND NOT EXISTS (
                 SELECT 1 FROM file_wd_tags w
                 WHERE w.file_id = f.id
               )
             ORDER BY f.id
             LIMIT ? OFFSET ?",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    };
    let files = rows
        .into_iter()
        .map(|row| {
            json!({
                "id": row.get::<i64, _>(0),
                "path": row.get::<String, _>(1),
                "meta_source": row.try_get::<Option<String>, _>(2).ok().flatten(),
            })
        })
        .collect::<Vec<_>>();
    let total = count_untagged(pool, active_mid).await?;
    Ok(json!({"files": files, "total": total}))
}

pub async fn untagged(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match fetch_untagged(&state.db_read, parse_limit(&params), parse_offset(&params)).await {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "failed to list untagged WD files"),
    }
}

pub async fn config(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    api_result(json!({"config": wd_config_from_state(&state)}))
}

pub async fn config_save(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let patch = match validated_wd_config_patch(&body) {
        Ok(patch) => patch,
        Err(response) => return response,
    };
    let model_id = match patch
        .get("model")
        .map(|value| validate_model_id_value(Some(value)))
        .transpose()
    {
        Ok(value) => value.flatten(),
        Err(error) => return api_error_code(&error, StatusCode::BAD_REQUEST, "invalid_value"),
    };
    if let Some(model_id) = model_id.as_deref() {
        match model_is_known_for_activation(&state, model_id).await {
            Ok(true) => {}
            Ok(false) => {
                return api_error_code("Unknown WD model", StatusCode::BAD_REQUEST, "unknown_model")
            }
            Err(error) => return internal_error(error, "failed to validate WD config model"),
        }
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config_file(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    if !config.is_object() {
        config = json!({});
    }
    if !config.get("wd_tagger").is_some_and(Value::is_object) {
        config["wd_tagger"] = json!({});
    }
    let wd = config["wd_tagger"].as_object_mut().unwrap();
    for (key, value) in patch {
        wd.insert(key, value);
    }
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write config");
    }
    // The read-modify-write is complete; release the global config lock before
    // touching the database.
    drop(_guard);
    if body.get("model").is_some() {
        if let Err(error) = set_active_model_id(&state.db, model_id.as_deref()).await {
            return internal_error(error, "failed to sync active WD model");
        }
    }
    let mut saved = Map::from_iter([
        ("model".to_string(), json!(DEFAULT_MODEL)),
        ("general_threshold".to_string(), json!(0.35)),
        ("character_threshold".to_string(), json!(0.85)),
        ("write_xmp".to_string(), json!(true)),
        ("auto_download".to_string(), json!(true)),
        ("engine_type".to_string(), json!("onnx")),
        ("vlm_url".to_string(), json!("http://localhost:11434")),
        ("vlm_model".to_string(), json!("")),
        ("vlm_timeout".to_string(), json!(60)),
        ("nsfw_filter".to_string(), json!(false)),
    ]);
    if let Some(user) = config.get("wd_tagger").and_then(Value::as_object) {
        for (key, value) in user {
            saved.insert(key.clone(), value.clone());
        }
    }
    api_result(json!({"config": saved}))
}

fn sidecar_xmp_path(image_path: &Path) -> PathBuf {
    PathBuf::from(format!("{}.xmp", image_path.to_string_lossy()))
}

fn extract_xml_list(raw: &str, list_name: &str) -> Vec<String> {
    if !raw.contains(list_name) {
        return Vec::new();
    }
    let mut out = Vec::new();
    let mut rest = raw;
    while let Some(start) = rest.find("<rdf:li>") {
        rest = &rest[start + "<rdf:li>".len()..];
        let Some(end) = rest.find("</rdf:li>") else {
            break;
        };
        out.push(rest[..end].to_string());
        rest = &rest[end + "</rdf:li>".len()..];
    }
    out
}

fn extract_wdtag_attrs(raw: &str) -> Map<String, Value> {
    let mut attrs = Map::new();
    let mut rest = raw;
    while let Some(start) = rest.find("wdtag:") {
        rest = &rest[start + "wdtag:".len()..];
        let name_end = rest
            .char_indices()
            .find_map(|(idx, ch)| {
                (!ch.is_ascii_alphanumeric() && ch != '_' && ch != '-').then_some(idx)
            })
            .unwrap_or(rest.len());
        let name = &rest[..name_end];
        let after_name = &rest[name_end..];
        let Some(eq_pos) = after_name.find('=') else {
            break;
        };
        let after_eq = after_name[eq_pos + 1..].trim_start();
        let Some(quote) = after_eq
            .chars()
            .next()
            .filter(|ch| *ch == '"' || *ch == '\'')
        else {
            rest = after_eq;
            continue;
        };
        let value_start = quote.len_utf8();
        let Some(value_end) = after_eq[value_start..].find(quote) else {
            break;
        };
        attrs.insert(
            name.to_string(),
            json!(&after_eq[value_start..value_start + value_end]),
        );
        rest = &after_eq[value_start + value_end + quote.len_utf8()..];
    }
    attrs
}

pub async fn xmp(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let path = match sqlx::query_scalar::<_, String>(
        "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(Some(path)) => path,
        Ok(None) => {
            return api_error_code("File not found", StatusCode::NOT_FOUND, "file_not_found")
        }
        Err(error) => return internal_error(error, "failed to read file path for xmp"),
    };
    let sidecar = sidecar_xmp_path(Path::new(&path));
    let xmp = if let Ok(raw_xml) = fs::read_to_string(sidecar) {
        json!({
            "raw_xml": raw_xml,
            "dc_subject": extract_xml_list(&raw_xml, "dc:subject"),
            "wdtag": extract_wdtag_attrs(&raw_xml),
        })
    } else {
        json!({"raw_xml": null, "dc_subject": [], "wdtag": {}})
    };
    api_result(json!({"file_id": file_id, "xmp": xmp}))
}

pub async fn vlm_test(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let url = params.get("url").map(|url| url.trim()).unwrap_or("");
    if url.is_empty() {
        return api_error_code(
            "url parameter required",
            StatusCode::BAD_REQUEST,
            "missing_url",
        );
    }
    if let Some(error) = analysis_net::validate_openai_compat_url(url, true) {
        return api_error_code(&error, StatusCode::BAD_REQUEST, "invalid_url");
    }
    api_result(analysis_net::check_openai_compat_connection_without_key(url).await)
}

pub async fn vlm_models(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let url = params.get("url").map(|url| url.trim()).unwrap_or("");
    if url.is_empty() {
        return api_error_code(
            "url parameter required",
            StatusCode::BAD_REQUEST,
            "missing_url",
        );
    }
    if let Some(error) = analysis_net::validate_openai_compat_url(url, true) {
        return api_error_code(&error, StatusCode::BAD_REQUEST, "invalid_url");
    }
    match analysis_net::list_openai_compat_models(url).await {
        Ok(models) => api_result(json!({"models": models})),
        Err(error) => {
            tracing::warn!(?error, url, "WD-Tagger VLM model listing failed");
            api_error_code(
                "VLM connection failed",
                StatusCode::BAD_GATEWAY,
                "vlm_connection_error",
            )
        }
    }
}

// ---------------------------------------------------------------------------
// Python forwarder helpers (admin scope gate + proxy to python_url)
// ---------------------------------------------------------------------------

async fn fwd_post_wt(state: &SharedState, path: &str, body: Bytes) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "python backend not configured"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
        .body(body)
        .send()
        .await
    {
        Ok(resp) => {
            let status =
                StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            match resp.bytes().await {
                Ok(b) => (status, b).into_response(),
                Err(_) => StatusCode::BAD_GATEWAY.into_response(),
            }
        }
        Err(e) => {
            tracing::warn!(%url, ?e, "wd-tagger python forward error");
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({"ok": false, "error": "python_backend_unavailable"})),
            )
                .into_response()
        }
    }
}

const NATIVE_IMAGE_EXTENSIONS: &[&str] = &[
    "png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff", "tif", "svg", "avif",
];

fn requires_image_transcode(path: &str) -> bool {
    std::path::Path::new(path)
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| {
            matches!(
                ext.to_ascii_lowercase().as_str(),
                "bmp" | "gif" | "tiff" | "tif" | "svg" | "avif"
            )
        })
        .unwrap_or(false)
}

fn has_extension(path: &Path, wanted: &str) -> bool {
    path.extension()
        .and_then(|ext| ext.to_str())
        .is_some_and(|ext| ext.eq_ignore_ascii_case(wanted))
}

/// Decodes an AVIF into `output` as PNG.
///
/// A decode failure is reported as a `BackendError`, not forwarded to Python.
/// `avif-rust` fails closed on profiles it does not implement, so such a file
/// is not tagged and the caller sees an explicit error rather than silently
/// falling back. Measured before choosing this: every AVIF Pillow can write
/// (15 variants: all four subsamplings, alpha, greyscale, limited/full range,
/// odd dimensions, 1x1, 1024x768, quality extremes) decodes here, as do 10-bit
/// 4:4:4 and 12-bit 4:2:0 built with rav1e. grid/tiled and animated could not
/// be tested — no tool on the build host can produce them — and `avif-rust`
/// claims grid support. If one turns up undecodable, the fix is to widen the
/// decoder or restore a fallback here; see the avif entry in TODO.md.
fn transcode_avif(path: &Path, output: &Path) -> Result<(), String> {
    let decoded = avif_rust::image_from_file(path).map_err(|error| format!("{error:?}"))?;
    // `avif-rust` reports dimensions as usize; reject anything that will not fit
    // rather than truncating, which would silently mis-shape the buffer.
    let width = u32::try_from(decoded.width).map_err(|_| "avif width out of range".to_string())?;
    let height =
        u32::try_from(decoded.height).map_err(|_| "avif height out of range".to_string())?;
    let buffer: image::RgbaImage = image::ImageBuffer::from_raw(width, height, decoded.rgba)
        .ok_or_else(|| "avif buffer does not match its dimensions".to_string())?;
    buffer
        .save_with_format(output, image::ImageFormat::Png)
        .map_err(|error| error.to_string())
}

async fn call_wd_infer_image(
    state: &SharedState,
    path: &Path,
    model_id: &str,
    general_thr: f32,
    character_thr: f32,
) -> WdInferOutcome {
    if !requires_image_transcode(&path.to_string_lossy()) {
        return call_wd_infer(state, path, model_id, general_thr, character_thr).await;
    }
    // Validate BEFORE transcoding: `call_wd_infer_temp_frame` deliberately skips
    // the scan_roots check (wd_infer.rs), so transcoding first would let every
    // widened format bypass it.
    if validate_wd_infer_path(state, path).is_err() {
        return WdInferOutcome::PathRejected;
    }
    let temp = match fs::create_dir_all(&state.config.cache_dir).and_then(|()| {
        Builder::new()
            .prefix("yu_wd_tagger_")
            .suffix(".png")
            .tempfile_in(&state.config.cache_dir)
    }) {
        Ok(temp) => temp,
        Err(error) => return WdInferOutcome::BackendError(error.to_string()),
    };
    let result = if has_extension(path, "svg") {
        rasterize_svg(path, temp.path())
    } else if has_extension(path, "avif") {
        transcode_avif(path, temp.path())
    } else {
        image::open(path)
            .and_then(|image| image.save_with_format(temp.path(), image::ImageFormat::Png))
            .map_err(|error| error.to_string())
    };
    if let Err(error) = result {
        return WdInferOutcome::BackendError(error);
    }
    call_wd_infer_temp_frame(state, temp.path(), model_id, general_thr, character_thr).await
}

fn rasterize_svg(path: &Path, output: &Path) -> Result<(), String> {
    let data = fs::read(path).map_err(|error| error.to_string())?;
    let tree = resvg::usvg::Tree::from_data(&data, &resvg::usvg::Options::default())
        .map_err(|error| error.to_string())?;
    let width = crate::num::sat_u32(f64::from(tree.size().width().ceil()));
    let height = crate::num::sat_u32(f64::from(tree.size().height().ceil()));
    let mut pixmap = resvg::tiny_skia::Pixmap::new(width, height)
        .ok_or_else(|| "invalid SVG raster size".to_string())?;
    resvg::render(
        &tree,
        resvg::tiny_skia::Transform::identity(),
        &mut pixmap.as_mut(),
    );
    pixmap.save_png(output).map_err(|error| error.to_string())
}

fn is_native_image_format(path: &str) -> bool {
    std::path::Path::new(path)
        .extension()
        .and_then(|e| e.to_str())
        .map(|ext| NATIVE_IMAGE_EXTENSIONS.contains(&ext.to_lowercase().as_str()))
        .unwrap_or(false)
}

#[derive(Debug)]
pub(crate) enum TagOutcome {
    Tagged(serde_json::Value),
    Skipped(serde_json::Value),
    Fallback,
    Rejected(serde_json::Value),
    Fatal(FatalReason),
}

#[derive(Debug)]
pub(crate) enum FatalReason {
    InferSidecarUnavailable,
    ModelNotDownloaded,
    BackendError(String),
    Unreachable(String),
}

/// Core (Rust) implementation of the WD-Tagger single-file tag operation.
/// Returns `TagOutcome::Fallback` when the request must fall back to the
/// Python sidecar (`fwd_post_wt`): unsupported formats only.
/// Standalone without yu-infer and `WdInferOutcome::PathRejected` are native errors.
/// All such fallback checks happen before any DB write or XMP write, so the
/// native and fallback paths can never both mutate state for the same
/// request.
pub(crate) fn configured_model_id_string(state: &SharedState) -> String {
    let config_model = read_config_json(state)["extensions"]["builtin-wd-tagger"]["model"]
        .as_str()
        .unwrap_or("SmilingWolf/wd-swinv2-tagger-v3")
        .to_string();
    sanitize_model_id(&config_model)
}

/// Resolves the currently configured WD-Tagger model to its integer FK in
/// `wd_model_dict`, using the exact same config path + sanitization as
/// `tag_file_native_core`. Read-only: if the model has no row yet (nobody
/// has tagged with it), returns `None` rather than inserting one.
pub(crate) async fn resolve_configured_model_id(state: &SharedState) -> Option<i64> {
    let model_id = configured_model_id_string(state);
    sqlx::query_scalar::<_, i64>("SELECT id FROM wd_model_dict WHERE model = ?")
        .bind(&model_id)
        .fetch_optional(&state.db_read)
        .await
        .ok()
        .flatten()
}

pub(crate) async fn tag_file_native_core(
    state: &SharedState,
    file_id: i64,
    force: bool,
) -> TagOutcome {
    // 1. DB active判定
    let row: Option<(String,)> =
        match sqlx::query_as("SELECT path FROM files WHERE id = ? AND is_deleted = 0")
            .bind(file_id)
            .fetch_optional(&state.db_read)
            .await
        {
            Ok(row) => row,
            Err(error) => {
                tracing::error!(?error, file_id, "wd tag file lookup failed");
                return TagOutcome::Rejected(
                    json!({"ok": false, "error": "internal_server_error"}),
                );
            }
        };
    let Some((path,)) = row else {
        return TagOutcome::Rejected(
            json!({"error": "File not found or deleted", "code": "file_not_found"}),
        );
    };

    // 2. on-disk存在確認
    if !std::path::Path::new(&path).exists() {
        return TagOutcome::Rejected(
            json!({"error": "File not found on disk", "code": "file_missing"}),
        );
    }

    // 3. フォーマット判定(非対応ならPythonへfallback)
    if !is_native_image_format(&path) {
        if crate::routes::wd_tagger_video::is_native_video_format(&path) {
            return tag_video_core(state, file_id, &path, force).await;
        }
        // Python answers the same thing for these, so forwarding buys nothing:
        // `single_ops.py::tag_one_file` gates on `is_taggable_file()` and returns
        // `unsupported_type`. The native image set (10) and video set (7) match
        // Python's effective sets exactly -- heif/heic/jxl sit in Python's source
        // but behind `HEIF_AVAILABLE`/`JXL_AVAILABLE`, both False here. If those
        // packages are ever installed, Python gains formats Rust lacks and this
        // branch has to become a forward again; see TODO.md.
        return TagOutcome::Rejected(
            json!({"error": "File type not supported for tagging", "code": "unsupported_type"}),
        );
    }

    // Standalone mode has no Python backend to forward to.
    if state.infer_client.is_none() && state.config.infer_standalone {
        return TagOutcome::Fatal(FatalReason::InferSidecarUnavailable);
    }

    // (skip判定) force=falseかつ既存タグありならskipped応答
    if !force {
        match build_wd_tags(&state.db_read, file_id, None, false).await {
            Ok(existing) if !existing.is_empty() => {
                return TagOutcome::Skipped(json!({
                    "skipped": true,
                    "reason": "already_tagged",
                    "tag_count": existing.len(),
                }));
            }
            Ok(_) => {}
            Err(error) => {
                tracing::warn!(
                    ?error,
                    file_id,
                    "wd tag already-tagged check failed, proceeding to (re-)tag"
                );
            }
        }
    }

    let model_id = configured_model_id_string(state);

    let general_thr = read_config_json(state)["extensions"]["builtin-wd-tagger"]
        ["general_threshold"]
        .as_f64()
        .map(crate::num::narrow_f32)
        .unwrap_or(0.35_f32);
    let character_thr = read_config_json(state)["extensions"]["builtin-wd-tagger"]
        ["character_threshold"]
        .as_f64()
        .map(crate::num::narrow_f32)
        .unwrap_or(0.85_f32);

    // 5. サイドカー呼出
    let outcome = call_wd_infer_image(
        state,
        std::path::Path::new(&path),
        &model_id,
        general_thr,
        character_thr,
    )
    .await;
    let tag_result = match outcome {
        WdInferOutcome::Success(result) => result,
        WdInferOutcome::PathRejected => {
            return TagOutcome::Rejected(json!({"ok": false, "error": "internal_server_error"}));
        }
        WdInferOutcome::ModelNotDownloaded => {
            return TagOutcome::Fatal(FatalReason::ModelNotDownloaded)
        }
        WdInferOutcome::BackendError(msg) => {
            return TagOutcome::Fatal(FatalReason::BackendError(msg))
        }
        WdInferOutcome::Unreachable(msg) => {
            return TagOutcome::Fatal(FatalReason::Unreachable(msg))
        }
    };

    // NSFWフィルタ + dedup(先勝ち)
    let nsfw_filter = read_config_json(state)["extensions"]["builtin-wd-tagger"]["nsfw_filter"]
        .as_bool()
        .unwrap_or(false);
    let filtered = filter_and_dedupe_tags(&tag_result.tags, nsfw_filter);

    // 6. DB書込
    let tag_count = match write_wd_tags(&state.db, file_id, &model_id, &filtered).await {
        Ok(count) => count,
        Err(error) => {
            tracing::error!(?error, file_id, "wd tag write failed");
            return TagOutcome::Rejected(json!({"ok": false, "error": "internal_server_error"}));
        }
    };

    // 7. XMP書込(PNG/JPEG/WebP、best-effort)
    let write_xmp_enabled = read_config_json(state)["extensions"]["builtin-wd-tagger"]["write_xmp"]
        .as_bool()
        .unwrap_or(true);
    let xmp_format_supported = std::path::Path::new(&path)
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| {
            let e = e.to_ascii_lowercase();
            e == "png" || e == "jpg" || e == "jpeg" || e == "webp"
        })
        .unwrap_or(false);
    let tag_names: Vec<String> = filtered.iter().map(|(name, _, _)| name.clone()).collect();
    let xmp_written = write_xmp_enabled
        && xmp_format_supported
        && write_wd_xmp(
            std::path::Path::new(&path),
            &tag_names,
            &model_id,
            general_thr,
            character_thr,
        );

    TagOutcome::Tagged(json!({
        "file_id": file_id,
        "filepath": path,
        "tag_count": tag_count,
        "rating": tag_result.rating,
        "xmp_written": xmp_written,
        "tags": filtered.iter().map(|(tag, confidence, category)| json!({
            "tag": tag, "confidence": confidence, "category": category,
        })).collect::<Vec<_>>(),
    }))
}

struct AutoTagImportGuard {
    file_id: i64,
    in_flight: std::sync::Arc<std::sync::Mutex<HashSet<i64>>>,
    _permit: tokio::sync::OwnedSemaphorePermit,
}

impl Drop for AutoTagImportGuard {
    fn drop(&mut self) {
        self.in_flight
            .lock()
            .expect("auto-tag in-flight lock poisoned")
            .remove(&self.file_id);
    }
}

struct AutoTagImportQueue {
    permits: std::sync::Arc<tokio::sync::Semaphore>,
    in_flight: std::sync::Arc<std::sync::Mutex<HashSet<i64>>>,
}

fn auto_tag_import_queue() -> &'static AutoTagImportQueue {
    static QUEUE: std::sync::OnceLock<AutoTagImportQueue> = std::sync::OnceLock::new();
    QUEUE.get_or_init(|| AutoTagImportQueue {
        permits: std::sync::Arc::new(tokio::sync::Semaphore::new(2)),
        in_flight: std::sync::Arc::new(std::sync::Mutex::new(HashSet::new())),
    })
}

pub(crate) fn auto_tag_on_import_enabled(state: &SharedState) -> bool {
    read_config_json(state)["extensions"]["builtin-wd-tagger"]["auto_tag_on_import"]
        .as_bool()
        .unwrap_or(false)
}

/// Schedules a best-effort native tag after bridge import without allowing an
/// unbounded number of inference tasks to accumulate. The caller has already
/// checked `auto_tag_on_import_enabled` once for its whole import batch.
pub(crate) fn schedule_auto_tag_on_import(state: SharedState, file_id: i64) {
    let queue = auto_tag_import_queue();
    let permit = match queue.permits.clone().try_acquire_owned() {
        Ok(permit) => permit,
        Err(_) => {
            tracing::info!(file_id, reason = "queue_full", "wd auto-tag import skipped");
            return;
        }
    };
    let inserted = queue
        .in_flight
        .lock()
        .expect("auto-tag in-flight lock poisoned")
        .insert(file_id);
    if !inserted {
        drop(permit);
        tracing::info!(
            file_id,
            reason = "already_in_flight",
            "wd auto-tag import skipped"
        );
        return;
    }
    let in_flight = queue.in_flight.clone();
    tokio::spawn(async move {
        let _guard = AutoTagImportGuard {
            file_id,
            in_flight,
            _permit: permit,
        };
        match tag_file_native_core(&state, file_id, false).await {
            TagOutcome::Tagged(_) => tracing::info!(file_id, "wd auto-tag import completed"),
            TagOutcome::Skipped(_) => tracing::info!(
                file_id,
                reason = "already_tagged",
                "wd auto-tag import skipped"
            ),
            TagOutcome::Fallback => tracing::info!(
                file_id,
                reason = "native_unavailable",
                "wd auto-tag import skipped"
            ),
            TagOutcome::Rejected(error) => tracing::warn!(
                file_id,
                ?error,
                reason = "rejected",
                "wd auto-tag import failed"
            ),
            TagOutcome::Fatal(error) => tracing::warn!(
                file_id,
                ?error,
                reason = "inference_failed",
                "wd auto-tag import failed"
            ),
        }
    });
}

/// POST /api/wd-tagger/auto-tag-on-import
pub async fn auto_tag_on_import_config_save(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(request): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth.as_ref()) {
        return response;
    }
    let Some(object) = request.as_object() else {
        return api_error_code(
            "request body must be an object",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    if object.len() != 1
        || !object.contains_key("auto_tag_on_import")
        || !object["auto_tag_on_import"].is_boolean()
    {
        return api_error_code(
            "auto_tag_on_import must be the only boolean field",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    }
    if let Err(error) = crate::prompt_sim_core::save_ext_config(
        state.config.config_path.to_string_lossy().as_ref(),
        "builtin-wd-tagger",
        object,
    ) {
        return internal_error(error, "failed to save auto-tag-on-import config");
    }
    api_result(json!({"auto_tag_on_import": object["auto_tag_on_import"]}))
}

fn filter_and_dedupe_tags(
    tags: &[infer_core::engine::TagPrediction],
    nsfw_filter: bool,
) -> Vec<(String, f64, String)> {
    let mut seen = std::collections::HashSet::new();
    let mut filtered = Vec::new();
    for tag in tags {
        let normalized_preview = tag.tag.trim().to_lowercase().replace(' ', "_");
        if !seen.insert(normalized_preview.clone()) {
            continue;
        }
        if nsfw_filter && NSFW_TAG_SET.contains(&normalized_preview.as_str()) {
            continue;
        }
        filtered.push((tag.tag.clone(), tag.confidence as f64, tag.category.clone()));
    }
    filtered
}

/// Writes per-keyframe tagger results, mirroring
/// `core/files_core/video_keyframe_store.py::save_keyframe_results`.
///
/// The SQL is the same upsert keyed on `(file_id, keyframe_idx, model)`, and
/// `timestamp_ms` is 0 for the same reason Python writes 0: the keyframe
/// extractor does not return the position alongside the frame. `vector` stays
/// NULL — that column belongs to the CLIP path, not this one.
async fn save_keyframe_results(
    db: &sqlx::SqlitePool,
    file_id: i64,
    frames: &[Vec<(String, f32, String)>],
    model: &str,
) -> Result<(), sqlx::Error> {
    if frames.is_empty() {
        return Ok(());
    }
    let mut tx = db.begin().await?;
    for (index, tags) in frames.iter().enumerate() {
        let payload: Vec<Value> = tags
            .iter()
            .map(|(tag, confidence, category)| {
                json!({"tag": tag, "confidence": confidence, "category": category})
            })
            .collect();
        let wd_tags_json = if payload.is_empty() {
            None
        } else {
            Some(serde_json::to_string(&payload).unwrap_or_else(|_| "[]".to_string()))
        };
        sqlx::query(
            "INSERT INTO file_keyframes \
                 (file_id, keyframe_idx, timestamp_ms, vector, wd_tags_json, model) \
             VALUES (?, ?, 0, NULL, ?, ?) \
             ON CONFLICT(file_id, keyframe_idx, model) DO UPDATE SET \
                 timestamp_ms = excluded.timestamp_ms, \
                 vector = excluded.vector, \
                 wd_tags_json = excluded.wd_tags_json, \
                 created_at = strftime('%s','now')",
        )
        .bind(file_id)
        .bind(index as i64)
        .bind(wd_tags_json)
        .bind(model)
        .execute(&mut *tx)
        .await?;
    }
    tx.commit().await
}

async fn tag_video_core(state: &SharedState, file_id: i64, path: &str, force: bool) -> TagOutcome {
    let full_config = read_config_json(state);
    let video_config = crate::routes::video_analysis::merged_video_config(&full_config);
    let keyframe_count = video_config["keyframe_count"]
        .as_u64()
        .and_then(|value| u32::try_from(value).ok())
        .unwrap_or(4);
    let strategy = video_config["strategy"]
        .as_str()
        .unwrap_or("uniform")
        .to_string();
    let store_per_keyframe = video_config["store_per_keyframe"]
        .as_bool()
        .unwrap_or(false);
    let scene_threshold = video_config["scene_threshold"].as_f64().unwrap_or(0.4);

    if !crate::routes::video_analysis::check_ffmpeg() {
        // Python needs ffmpeg for the same extraction, so it answers
        // `keyframe_error` here too (single_ops.py). Forwarding gains nothing.
        return TagOutcome::Rejected(
            json!({"error": "Failed to extract keyframes", "code": "keyframe_error"}),
        );
    }

    // standalone mode has no Python backend to forward to.
    if state.infer_client.is_none() && state.config.infer_standalone {
        return TagOutcome::Fatal(FatalReason::InferSidecarUnavailable);
    }

    // (skip判定) force=falseかつ既存タグありならskipped応答
    if !force {
        match build_wd_tags(&state.db_read, file_id, None, false).await {
            Ok(existing) if !existing.is_empty() => {
                return TagOutcome::Skipped(json!({
                    "skipped": true,
                    "reason": "already_tagged",
                    "tag_count": existing.len(),
                }));
            }
            Ok(_) => {}
            Err(error) => {
                tracing::warn!(
                    ?error,
                    file_id,
                    "wd tag already-tagged check failed, proceeding to (re-)tag"
                );
            }
        }
    }

    let model_id = configured_model_id_string(state);

    let general_thr = read_config_json(state)["extensions"]["builtin-wd-tagger"]
        ["general_threshold"]
        .as_f64()
        .map(crate::num::narrow_f32)
        .unwrap_or(0.35_f32);
    let character_thr = read_config_json(state)["extensions"]["builtin-wd-tagger"]
        ["character_threshold"]
        .as_f64()
        .map(crate::num::narrow_f32)
        .unwrap_or(0.85_f32);

    let temp_dir = match Builder::new().prefix("yu_keyframes_").tempdir() {
        Ok(temp_dir) => temp_dir,
        Err(error) => {
            tracing::error!(?error, file_id, "wd tag keyframe temp dir creation failed");
            return TagOutcome::Rejected(json!({"ok": false, "error": "internal_server_error"}));
        }
    };
    let frames = crate::routes::wd_tagger_video::extract_keyframes_with_threshold(
        std::path::Path::new(path),
        temp_dir.path(),
        keyframe_count,
        &strategy,
        scene_threshold,
    )
    .await;
    if frames.is_empty() {
        return TagOutcome::Rejected(
            json!({"error": "Failed to extract keyframes", "code": "keyframe_error"}),
        );
    }

    let mut collected_results = Vec::new();
    for frame_path in frames {
        match call_wd_infer_temp_frame(state, &frame_path, &model_id, general_thr, character_thr)
            .await
        {
            WdInferOutcome::Success(result) => collected_results.push(result),
            WdInferOutcome::PathRejected => {
                tracing::error!(
                    file_id,
                    frame_path = %frame_path.display(),
                    "wd tag temporary keyframe path rejected"
                );
                return TagOutcome::Rejected(
                    json!({"ok": false, "error": "internal_server_error"}),
                );
            }
            WdInferOutcome::ModelNotDownloaded => {
                return TagOutcome::Fatal(FatalReason::ModelNotDownloaded)
            }
            WdInferOutcome::BackendError(msg) => {
                return TagOutcome::Fatal(FatalReason::BackendError(msg))
            }
            WdInferOutcome::Unreachable(msg) => {
                return TagOutcome::Fatal(FatalReason::Unreachable(msg))
            }
        }
    }

    // Snapshot what per-keyframe storage needs before the merge consumes the
    // frame results; `TagResult` is not `Clone`.
    let per_keyframe: Option<Vec<Vec<(String, f32, String)>>> = store_per_keyframe.then(|| {
        collected_results
            .iter()
            .map(|result| {
                result
                    .tags
                    .iter()
                    .map(|tag| (tag.tag.clone(), tag.confidence, tag.category.clone()))
                    .collect()
            })
            .collect()
    });

    let merged = crate::routes::wd_tagger_video::merge_tag_results(collected_results);

    if let Some(frames) = per_keyframe {
        // Mirrors single_ops.py: timestamp_ms is written as 0 there too, because
        // the extractor does not hand the position back with the frame.
        if let Err(error) =
            save_keyframe_results(&state.db, file_id, &frames, &merged.model_id).await
        {
            tracing::error!(
                ?error,
                file_id,
                "failed to store per-keyframe tagger results"
            );
        }
    }

    // NSFWフィルタ + dedup(先勝ち)
    let nsfw_filter = read_config_json(state)["extensions"]["builtin-wd-tagger"]["nsfw_filter"]
        .as_bool()
        .unwrap_or(false);
    let filtered = filter_and_dedupe_tags(&merged.tags, nsfw_filter);

    // DB書込
    let tag_count = match write_wd_tags(&state.db, file_id, &model_id, &filtered).await {
        Ok(count) => count,
        Err(error) => {
            tracing::error!(?error, file_id, "wd tag write failed");
            return TagOutcome::Rejected(json!({"ok": false, "error": "internal_server_error"}));
        }
    };

    TagOutcome::Tagged(json!({
        "file_id": file_id,
        "filepath": path,
        "tag_count": tag_count,
        "rating": merged.rating,
        "xmp_written": false,
        "tags": filtered.iter().map(|(tag, confidence, category)| json!({
            "tag": tag, "confidence": confidence, "category": category,
        })).collect::<Vec<_>>(),
    }))
}

/// Native (Rust) implementation of the WD-Tagger single-file tag endpoint.
///
/// No longer forwards: every format Python can tag is native (10 image + 7
/// video, matching Python's effective sets), and the branches that used to
/// forward now return the answer Python itself would give —
/// `unsupported_type` and `keyframe_error`. Standalone without a sidecar is a
/// typed `infer_sidecar_unavailable`, and `PathRejected` is a rejection rather
/// than a forward that would have defeated the scan-root check.
async fn tag_file_native(state: &SharedState, file_id: i64, force: bool) -> Response {
    match tag_file_native_core(state, file_id, force).await {
        TagOutcome::Tagged(body) | TagOutcome::Skipped(body) => api_result(body),
        TagOutcome::Rejected(body) => {
            // "code" キーで判別する("reason" ではない)。file_not_found/file_missing は
            // 既存コードでは両方とも 400 BAD_REQUEST であり 404 ではない。
            // internal_error 由来(DB参照/書込失敗)は "code" キー自体を持たないため
            // デフォルト分岐で 500 に落ちる。
            let status = rejected_status_from_body(&body);
            (status, Json(body)).into_response()
        }
        // `tag_file_native_core` no longer produces `Fallback`: every format
        // Python handles is native, and the cases where it used to forward now
        // return the same answer Python would (`unsupported_type`,
        // `keyframe_error`). Kept as a compile-time exhaustive arm so adding a
        // new forward has to be a deliberate edit here.
        TagOutcome::Fallback => {
            tracing::error!(
                file_id,
                "tag_file_native_core returned an unexpected Fallback"
            );
            api_error_code(
                "File type not supported for tagging",
                StatusCode::BAD_REQUEST,
                "unsupported_type",
            )
        }
        TagOutcome::Fatal(reason) => fatal_reason_to_response(reason),
    }
}

fn rejected_status_from_body(body: &serde_json::Value) -> StatusCode {
    match body.get("code").and_then(|v| v.as_str()) {
        // `unsupported_type` mirrors Python's `api_error(..., 400,
        // code="unsupported_type")`. Without it the native branch fell through
        // to 500, which is the wrong status and would have been a parity
        // regression.
        Some("file_not_found" | "file_missing" | "keyframe_error" | "unsupported_type") => {
            StatusCode::BAD_REQUEST
        }
        _ => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

fn fatal_reason_to_response(reason: FatalReason) -> Response {
    match reason {
        FatalReason::InferSidecarUnavailable => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "code": "infer_sidecar_unavailable"})),
        )
            .into_response(),
        FatalReason::ModelNotDownloaded => (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Model not downloaded", "code": "model_not_available"})),
        )
            .into_response(),
        // BackendError / Unreachable は既存コード(旧 tag_file_native L1520-1528)では区別されず
        // 同一の 400 BAD_REQUEST + code:"infer_unavailable" を返す。ここでも区別しない。
        FatalReason::BackendError(_) | FatalReason::Unreachable(_) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Inference backend unavailable", "code": "infer_unavailable"})),
        )
            .into_response(),
    }
}

/// POST /api/wd-tagger/tag/{file_id}
pub async fn tag_file(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    let force = serde_json::from_slice::<Value>(&body)
        .ok()
        .and_then(|v| v.get("force").and_then(|f| f.as_bool()))
        .unwrap_or(false);
    tag_file_native(&state, file_id, force).await
}

#[derive(Debug)]
enum HfError {
    Ssrf(String),
    Request(String),
    TooLarge(String),
    Path(String),
}

impl std::fmt::Display for HfError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Ssrf(message)
            | Self::Request(message)
            | Self::TooLarge(message)
            | Self::Path(message) => f.write_str(message),
        }
    }
}

fn hf_path_encode(value: &str) -> String {
    value.bytes().fold(String::new(), |mut output, byte| {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~' | b'/') {
            output.push(byte as char);
        } else {
            use std::fmt::Write;
            write!(output, "%{byte:02X}").expect("writing to String cannot fail");
        }
        output
    })
}

fn build_hf_url(profile: &Value, file_name: &str) -> Result<Url, HfError> {
    let model_id = profile
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| HfError::Request("profile missing model_id".into()))?;
    let rel_path = match profile
        .get("hf_subdir")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
    {
        Some(subdir) => format!("{subdir}/{file_name}"),
        None => file_name.to_string(),
    };
    Url::parse(&format!(
        "https://huggingface.co/{}/resolve/main/{}",
        hf_path_encode(model_id),
        hf_path_encode(&rel_path)
    ))
    .map_err(|error| HfError::Request(format!("invalid HuggingFace URL: {error}")))
}

fn validate_hf_url(url: &Url) -> Result<(), HfError> {
    if !matches!(url.scheme(), "http" | "https") {
        return Err(HfError::Ssrf("only http/https URLs are allowed".into()));
    }
    if !url.username().is_empty() || url.password().is_some() {
        // Url::host_str excludes userinfo, so the host allowlist also rejects it;
        // retain this explicit check to document and enforce the security intent.
        return Err(HfError::Ssrf("URL userinfo is not allowed".into()));
    }
    let host = url
        .host_str()
        .ok_or_else(|| HfError::Ssrf("URL missing hostname".into()))?;
    if !HF_HOSTS
        .iter()
        .any(|allowed| host == *allowed || host.ends_with(&format!(".{allowed}")))
    {
        return Err(HfError::Ssrf(format!(
            "host is not an allowed HuggingFace host: {host}"
        )));
    }
    Ok(())
}

type HfClientFuture = Pin<Box<dyn Future<Output = Result<reqwest::Client, HfError>> + Send>>;
type HfResponseFuture = Pin<Box<dyn Future<Output = Result<reqwest::Response, HfError>> + Send>>;

async fn hf_request_with_client(
    method: reqwest::Method,
    initial_url: Url,
    timeout: Duration,
    client_for: &(dyn Fn(&Url, Duration) -> HfClientFuture + Send + Sync),
) -> Result<reqwest::Response, HfError> {
    let mut url = initial_url;
    for redirect_count in 0..=HF_MAX_REDIRECTS {
        validate_hf_url(&url)?;
        let client = client_for(&url, timeout).await?;
        let response = client
            .request(method.clone(), url.clone())
            .header(reqwest::header::USER_AGENT, HF_USER_AGENT)
            .send()
            .await
            .map_err(|error| HfError::Request(error.to_string()))?;
        if !response.status().is_redirection() {
            return Ok(response);
        }
        if redirect_count == HF_MAX_REDIRECTS {
            return Err(HfError::Ssrf(format!(
                "too many redirects (>{HF_MAX_REDIRECTS})"
            )));
        }
        let location = response
            .headers()
            .get(LOCATION)
            .ok_or_else(|| HfError::Request("redirect without Location".into()))?
            .to_str()
            .map_err(|_| HfError::Request("invalid redirect Location".into()))?;
        url = url
            .join(location)
            .map_err(|error| HfError::Request(format!("invalid redirect Location: {error}")))?;
    }
    // The loop returns on its last iteration (`redirect_count ==
    // HF_MAX_REDIRECTS`), so this is dead. Repeating the verdict costs a line
    // and keeps a bounded-redirect fetch from unwinding a request thread.
    Err(HfError::Ssrf(format!(
        "too many redirects (>{HF_MAX_REDIRECTS})"
    )))
}

async fn hf_request(
    method: reqwest::Method,
    initial_url: Url,
    timeout: Duration,
) -> Result<reqwest::Response, HfError> {
    hf_request_with_client(method, initial_url, timeout, &|url, timeout| {
        let url = url.to_string();
        Box::pin(async move {
            crate::analysis_engines::http_client::build_pinned_client(&url, false, timeout)
                .await
                .map_err(|error| HfError::Ssrf(error.to_string()))
        })
    })
    .await
}

fn secure_model_path(base: &Path, name: &str) -> Result<PathBuf, HfError> {
    // Python accepts profile file names verbatim; native downloads additionally
    // canonicalize every created directory so profile JSON cannot escape cache.
    fs::create_dir_all(base).map_err(|error| HfError::Path(error.to_string()))?;
    let root = base
        .canonicalize()
        .map_err(|error| HfError::Path(error.to_string()))?;
    let relative = Path::new(name);
    if relative.as_os_str().is_empty()
        || relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return Err(HfError::Path("unsafe model file name".into()));
    }
    let mut parent = root.clone();
    let components = relative.components().collect::<Vec<_>>();
    for component in &components[..components.len() - 1] {
        let std::path::Component::Normal(part) = component else {
            // The `!matches!(component, Component::Normal(_))` check above
            // already rejected the path. Reject again instead of unwinding: the
            // model file name comes from a remote manifest.
            return Err(HfError::Path("unsafe model file name".into()));
        };
        parent.push(part);
        fs::create_dir_all(&parent).map_err(|error| HfError::Path(error.to_string()))?;
        parent = parent
            .canonicalize()
            .map_err(|error| HfError::Path(error.to_string()))?;
        if !parent.starts_with(&root) {
            return Err(HfError::Path("model path escapes cache directory".into()));
        }
    }
    let std::path::Component::Normal(file) = components.last().expect("nonempty path") else {
        // Same guard as above; same reason not to panic on a remote manifest.
        return Err(HfError::Path("unsafe model file name".into()));
    };
    let destination = parent.join(file);
    if !destination
        .parent()
        .is_some_and(|path| path.starts_with(&root))
    {
        return Err(HfError::Path("model path escapes cache directory".into()));
    }
    Ok(destination)
}

fn profile_model_dir(state: &SharedState, profile: &Value) -> Result<PathBuf, HfError> {
    let model_id = profile
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| HfError::Request("profile missing model_id".into()))?;
    let mut base = state
        .config
        .project_root
        .join("cache/wd_tagger")
        .join(model_id.replace('/', "_"));
    if let Some(subdir) = profile
        .get("hf_subdir")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
    {
        let marker = secure_model_path(&base, &format!("{subdir}/.wd-tagger-dir"))?;
        base = marker
            .parent()
            .expect("secure path has parent")
            .to_path_buf();
    }
    Ok(base)
}

fn hf_content_length_allowed(content_length: Option<u64>) -> bool {
    content_length.is_none_or(|length| length <= HF_MAX_DOWNLOAD_BYTES)
}

fn hf_declared_content_length(response: &reqwest::Response) -> Option<u64> {
    // Python reads Content-Length; reqwest's body size hint is 0 for a constructed
    // response, so read the header to match Python and keep this guard testable.
    response
        .headers()
        .get(reqwest::header::CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<u64>().ok())
}

fn profile_test_status(code: &str) -> StatusCode {
    match code {
        "timeout" => StatusCode::REQUEST_TIMEOUT,
        "ssrf_blocked" | "hf_unavailable" => StatusCode::BAD_GATEWAY,
        _ => StatusCode::BAD_REQUEST,
    }
}

fn profile_test_error(message: &str, code: &str, extra: Value) -> Response {
    api_error_extra(message, profile_test_status(code), code, extra)
}

fn hf_temporary_path(destination: &Path) -> PathBuf {
    // Cached files are trusted by existence only, so unique temporary names
    // prevent concurrent writers from persisting a corrupt cached model.
    destination.with_file_name(format!(
        "{}.{}.{}.tmp",
        destination
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("download"),
        std::process::id(),
        HF_TEMP_SEQ.fetch_add(1, Ordering::Relaxed),
    ))
}

async fn download_hf_file(
    state: &SharedState,
    profile: &Value,
    file_name: &str,
    timeout: Duration,
) -> Result<Value, HfError> {
    download_hf_file_with_request(
        state,
        profile,
        file_name,
        timeout,
        &|method, url, timeout| Box::pin(hf_request(method, url, timeout)),
    )
    .await
}

async fn download_hf_file_with_request(
    state: &SharedState,
    profile: &Value,
    file_name: &str,
    timeout: Duration,
    request: &(dyn Fn(reqwest::Method, Url, Duration) -> HfResponseFuture + Send + Sync),
) -> Result<Value, HfError> {
    let base = profile_model_dir(state, profile)?;
    let destination = secure_model_path(&base, file_name)?;
    if destination.exists() {
        return Ok(
            json!({"name": file_name, "status": "cached", "size": fs::metadata(destination).map_err(|error| HfError::Path(error.to_string()))?.len()}),
        );
    }
    let response = request(
        reqwest::Method::GET,
        build_hf_url(profile, file_name)?,
        timeout,
    )
    .await?;
    if !response.status().is_success() {
        return Err(HfError::Request(format!(
            "hf returned {} for {file_name}",
            response.status()
        )));
    }
    if !hf_content_length_allowed(hf_declared_content_length(&response)) {
        return Err(HfError::TooLarge(format!(
            "{file_name} exceeds max download size"
        )));
    }
    let temporary = hf_temporary_path(&destination);
    let mut output = tokio::fs::File::create(&temporary)
        .await
        .map_err(|error| HfError::Path(error.to_string()))?;
    let mut stream = response.bytes_stream();
    let mut size = 0_u64;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|error| HfError::Request(error.to_string()))?;
        size = size.saturating_add(chunk.len() as u64);
        if size > HF_MAX_DOWNLOAD_BYTES {
            let _ = tokio::fs::remove_file(&temporary).await;
            return Err(HfError::TooLarge(format!(
                "{file_name} exceeds max download size"
            )));
        }
        for part in chunk.chunks(HF_CHUNK_BYTES) {
            tokio::io::AsyncWriteExt::write_all(&mut output, part)
                .await
                .map_err(|error| HfError::Path(error.to_string()))?;
        }
    }
    tokio::io::AsyncWriteExt::flush(&mut output)
        .await
        .map_err(|error| HfError::Path(error.to_string()))?;
    drop(output);
    tokio::fs::rename(&temporary, &destination)
        .await
        .map_err(|error| HfError::Path(error.to_string()))?;
    Ok(json!({"name": file_name, "status": "downloaded", "size": size}))
}

/// POST /api/wd-tagger/model/download
pub async fn model_download(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    let Ok(request) = serde_json::from_slice::<Value>(&body) else {
        return api_error_code("Invalid JSON body", StatusCode::BAD_REQUEST, "invalid_json");
    };
    let profile_id = request.get("profile_id").and_then(Value::as_str);
    let legacy_id = request
        .get("model_id")
        .or_else(|| request.get("repo"))
        .and_then(Value::as_str);
    let Some(requested_id) = profile_id.or(legacy_id) else {
        return api_error_code(
            "profile_id required (model_id legacy bridge also accepted)",
            StatusCode::BAD_REQUEST,
            "missing_id",
        );
    };
    let profiles = load_full_profiles(&state.config.project_root);
    let (profile, deprecated) = if let Some(id) = profile_id {
        let Some((profile, _, _)) = profiles.get(id) else {
            return api_error_extra(
                &format!("Unknown profile_id: {id:?}"),
                StatusCode::NOT_FOUND,
                "profile_not_found",
                json!({"profile_id": id}),
            );
        };
        (profile, false)
    } else {
        let matches = profiles
            .values()
            .filter_map(|(profile, _, _)| {
                (profile.get("model_id").and_then(Value::as_str) == Some(requested_id))
                    .then_some(profile)
            })
            .collect::<Vec<_>>();
        match matches.len() {
            0 => return api_error_extra(&format!("Unknown model_id: {requested_id:?}"), StatusCode::NOT_FOUND, "profile_not_found", json!({"profile_id": requested_id})),
            1 => (matches[0], true),
            count => return api_error_extra(&format!("Ambiguous model_id {requested_id:?}: {count} profiles match. Use profile_id instead."), StatusCode::BAD_REQUEST, "ambiguous_model_id", json!({"profile_id": requested_id, "matches": matches.iter().filter_map(|profile| profile.get("id")).collect::<Vec<_>>() })),
        }
    };
    let Some(files) = profile.get("files").and_then(Value::as_array) else {
        return api_error_code(
            "profile files invalid",
            StatusCode::BAD_REQUEST,
            "download_failed",
        );
    };
    let mut downloaded = Vec::new();
    let mut skipped_optional = Vec::new();
    let mut failed_optional = Vec::new();
    for spec in files {
        let Some(name) = spec.get("name").and_then(Value::as_str) else {
            return api_error_code(
                "profile file invalid",
                StatusCode::BAD_REQUEST,
                "download_failed",
            );
        };
        let required = spec
            .get("required")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        match download_hf_file(&state, profile, name, Duration::from_secs(30)).await {
            Ok(result) => downloaded.push(result["name"].clone()),
            Err(HfError::Request(message)) if !required && message.contains("404") => {
                skipped_optional.push(json!([name, "404"]))
            }
            Err(HfError::Request(message))
                if !required && (message.contains("403") || message.contains("410")) =>
            {
                failed_optional.push(json!([name, message]))
            }
            Err(error) => {
                return api_error_code(
                    &format!("Model download failed: {error}"),
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "download_failed",
                )
            }
        }
    }
    let mut response = api_result(
        json!({"profile_id": profile.get("id"), "cache_dir": profile_model_dir(&state, profile).ok().map(|path| path.to_string_lossy().to_string()), "downloaded": downloaded, "skipped_optional": skipped_optional, "failed_optional": failed_optional}),
    );
    if deprecated {
        let headers = response.headers_mut();
        headers.insert(
            "Deprecation",
            reqwest::header::HeaderValue::from_static("true"),
        );
        headers.insert(
            "Sunset",
            reqwest::header::HeaderValue::from_static("v4.196.0"),
        );
        let warning = format!("299 - \"model_id={requested_id:?} is deprecated; use profile_id. Removed in v4.196.0.\"");
        if let Ok(value) = reqwest::header::HeaderValue::from_str(&warning) {
            headers.insert("Warning", value);
        }
    }
    response
}

/// POST /api/wd-tagger/profiles/{id}/test. This endpoint downloads required files, not only HEADs them.
pub async fn profile_test(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(id): AxumPath<String>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    if !valid_profile_id(&id) {
        return api_error_code("invalid id", StatusCode::BAD_REQUEST, "invalid_id");
    }
    let profiles = load_full_profiles(&state.config.project_root);
    let Some((profile, _, _)) = profiles.get(&id) else {
        return api_error_code("not found", StatusCode::NOT_FOUND, "not_found");
    };
    let Some(files) = profile.get("files").and_then(Value::as_array) else {
        return api_error_code(
            "profile files invalid",
            StatusCode::BAD_REQUEST,
            "required_missing",
        );
    };
    let started = Instant::now();
    let mut output = Vec::new();
    for spec in files {
        let Some(name) = spec.get("name").and_then(Value::as_str) else {
            return api_error_code(
                "profile file invalid",
                StatusCode::BAD_REQUEST,
                "required_missing",
            );
        };
        let required = spec
            .get("required")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        let remaining = Duration::from_secs(60).checked_sub(started.elapsed());
        let Some(remaining) = remaining else {
            return profile_test_error(
                "profile test timed out",
                "timeout",
                json!({"files": output}),
            );
        };
        let timeout = remaining.clamp(Duration::from_secs(1), Duration::from_secs(30));
        let head = hf_request(
            reqwest::Method::HEAD,
            match build_hf_url(profile, name) {
                Ok(url) => url,
                Err(HfError::Ssrf(detail)) => {
                    return profile_test_error(
                        "SSRF blocked",
                        "ssrf_blocked",
                        json!({"files": output, "detail": detail}),
                    )
                }
                Err(error) => {
                    return api_error_extra(
                        "required file missing",
                        StatusCode::BAD_REQUEST,
                        "required_missing",
                        json!({"files": output, "detail": error.to_string()}),
                    )
                }
            },
            timeout,
        )
        .await;
        let response = match head {
            Ok(response) => response,
            Err(HfError::Ssrf(detail)) => {
                return profile_test_error(
                    "SSRF blocked",
                    "ssrf_blocked",
                    json!({"files": output, "detail": detail}),
                )
            }
            Err(error) if required => {
                return api_error_extra(
                    "required file missing",
                    StatusCode::BAD_REQUEST,
                    "required_missing",
                    json!({"files": output, "detail": format!("HEAD failed for {name}: {error}")}),
                )
            }
            Err(_) => {
                output.push(json!({"name": name, "status": "skipped_optional", "size": null}));
                continue;
            }
        };
        let status = response.status();
        let size = response.content_length();
        if status == ReqwestStatusCode::NOT_FOUND || status.is_client_error() {
            if required {
                return api_error_extra(
                    "required file missing",
                    StatusCode::BAD_REQUEST,
                    "required_missing",
                    json!({"files": output, "detail": format!("hf returned {status} for {name}")}),
                );
            }
            output.push(json!({"name": name, "status": "skipped_optional", "size": size}));
            continue;
        }
        if status.is_server_error() {
            return profile_test_error(
                "HuggingFace unavailable",
                "hf_unavailable",
                json!({"files": output, "detail": format!("hf {status} for {name}")}),
            );
        }
        if required {
            let remaining = Duration::from_secs(60).checked_sub(started.elapsed());
            let Some(remaining) = remaining else {
                return profile_test_error(
                    "profile test timed out",
                    "timeout",
                    json!({"files": output}),
                );
            };
            match download_hf_file(
                &state,
                profile,
                name,
                remaining.clamp(Duration::from_secs(1), Duration::from_secs(30)),
            )
            .await
            {
                Ok(file) => output.push(file),
                Err(HfError::Ssrf(detail)) => {
                    return profile_test_error(
                        "SSRF blocked",
                        "ssrf_blocked",
                        json!({"files": output, "detail": detail}),
                    )
                }
                Err(error) => {
                    return api_error_extra(
                        "required file missing",
                        StatusCode::BAD_REQUEST,
                        "required_missing",
                        json!({"files": output, "detail": error.to_string()}),
                    )
                }
            }
        } else {
            output.push(json!({"name": name, "status": "available", "size": size}));
        }
    }
    api_result(json!({"files": output}))
}

/// POST /api/wd-tagger/retag/single
#[allow(clippy::result_large_err)]
pub async fn retag_single(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    let start = std::time::Instant::now();
    let Ok(request) = serde_json::from_slice::<Value>(&body) else {
        return api_error_code(
            "invalid JSON body",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    let Some(file_id) = request.get("file_id").and_then(Value::as_i64) else {
        return api_error_code("file_id required", StatusCode::BAD_REQUEST, "invalid_input");
    };
    let Some(model_input) = request.get("model_id").and_then(Value::as_str) else {
        return api_error_code(
            "model_id required",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    let threshold = |name: &str, default: f32| -> Result<f32, Response> {
        let Some(thresholds) = request.get("thresholds") else {
            return Ok(default);
        };
        let Some(thresholds) = thresholds.as_object() else {
            return Err(api_error_code(
                "thresholds must be an object",
                StatusCode::BAD_REQUEST,
                "invalid_input",
            ));
        };
        match thresholds.get(name) {
            None => Ok(default),
            Some(value) => value
                .as_f64()
                .map(crate::num::narrow_f32)
                .filter(|v| v.is_finite() && (0.0..=1.0).contains(v))
                .ok_or_else(|| {
                    api_error_code(
                        "threshold must be a number between 0 and 1",
                        StatusCode::BAD_REQUEST,
                        "invalid_input",
                    )
                }),
        }
    };
    let general_thr = match threshold("general", 0.35) {
        Ok(value) => value,
        Err(response) => return response,
    };
    let character_thr = match threshold("character", 0.85) {
        Ok(value) => value,
        Err(response) => return response,
    };
    let parse_bool = |name: &str, default: bool| -> Result<bool, Response> {
        match request.get(name) {
            None => Ok(default),
            Some(value) => value.as_bool().ok_or_else(|| {
                api_error_code(
                    "boolean field required",
                    StatusCode::BAD_REQUEST,
                    "invalid_input",
                )
            }),
        }
    };
    let overwrite = match parse_bool("overwrite_same_model", true) {
        Ok(value) => value,
        Err(response) => return response,
    };
    let set_active = match parse_bool("set_active", true) {
        Ok(value) => value,
        Err(response) => return response,
    };
    let profiles = load_full_profiles(&state.config.project_root);
    let Some((profile, _, _)) = profiles.get(model_input).or_else(|| {
        profiles
            .values()
            .find(|(profile, _, _)| profile["model_id"].as_str() == Some(model_input))
    }) else {
        return api_error_code(
            "File not found or deleted",
            StatusCode::NOT_FOUND,
            "file_not_found",
        );
    };
    let profile_id = profile["id"].as_str().unwrap_or(model_input);
    // Families other than `wd`, and variants living in an `hf_subdir`, used to
    // be forwarded to Python because the sidecar knew exactly one recipe in
    // exactly one directory. It now takes both from the profile. A non-ONNX
    // backend has no local weights at all, so it is refused rather than
    // forwarded — Python cannot run it either.
    if profile["backend"].as_str() != Some("onnx") {
        return api_error_code(
            "model backend is not supported for retag",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    }
    if state.infer_client.is_none() && state.config.infer_standalone {
        return fatal_reason_to_response(FatalReason::InferSidecarUnavailable);
    }
    let model_cache_id = sanitize_model_id(profile["model_id"].as_str().unwrap_or(profile_id));
    match retag_file_native_core(
        &state,
        file_id,
        &model_cache_id,
        general_thr,
        character_thr,
        overwrite,
        set_active,
    )
    .await
    {
        TagOutcome::Tagged(mut body) => {
            body["elapsed_ms"] =
                json!((start.elapsed().as_secs_f64() * 1000.0 * 100.0).round() / 100.0);
            api_result(json!({"data": body}))
        }
        // `retag_file_native_core` never produces `Fallback`; every outcome it
        // can reach is Tagged / Rejected / Fatal / Skipped. Kept as a
        // compile-time exhaustive arm so reintroducing a forward has to be a
        // deliberate edit here.
        TagOutcome::Fallback => {
            tracing::error!(
                file_id,
                "retag_file_native_core returned an unexpected Fallback"
            );
            api_error_code(
                "model is not supported by native retag",
                StatusCode::BAD_REQUEST,
                "invalid_input",
            )
        }
        TagOutcome::Rejected(body) => {
            (rejected_status_from_body(&body), Json(body)).into_response()
        }
        TagOutcome::Fatal(reason) => fatal_reason_to_response(reason),
        TagOutcome::Skipped(body) => api_result(json!({"data": body})),
    }
}

async fn retag_file_native_core(
    state: &SharedState,
    file_id: i64,
    model_id: &str,
    general_thr: f32,
    character_thr: f32,
    overwrite: bool,
    set_active: bool,
) -> TagOutcome {
    let path: String = match sqlx::query_scalar(
        "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(Some(path)) => path,
        Ok(None) => {
            return TagOutcome::Rejected(
                json!({"ok": false, "error": "File not found or deleted", "code": "file_not_found"}),
            )
        }
        Err(error) => {
            tracing::error!(?error, "wd retag file lookup failed");
            return TagOutcome::Rejected(json!({"ok": false, "error": "internal_server_error"}));
        }
    };
    if !is_native_image_format(&path) {
        // Same reasoning as tag_file_native_core: Python returns
        // `unsupported_type` for these, so a forward adds a hop and no answer.
        return TagOutcome::Rejected(
            json!({"error": "File type not supported for tagging", "code": "unsupported_type"}),
        );
    }
    if !Path::new(&path).exists() {
        return TagOutcome::Rejected(
            json!({"ok": false, "error": "File not found on disk", "code": "file_missing"}),
        );
    }
    let outcome = call_wd_infer_image(
        state,
        Path::new(&path),
        model_id,
        general_thr,
        character_thr,
    )
    .await;
    let result = match outcome {
        WdInferOutcome::Success(result) => result,
        WdInferOutcome::PathRejected => {
            return TagOutcome::Rejected(json!({"ok": false, "error": "internal_server_error"}));
        }
        WdInferOutcome::ModelNotDownloaded => {
            return TagOutcome::Fatal(FatalReason::ModelNotDownloaded)
        }
        WdInferOutcome::BackendError(error) => {
            return TagOutcome::Fatal(FatalReason::BackendError(error))
        }
        WdInferOutcome::Unreachable(error) => {
            return TagOutcome::Fatal(FatalReason::Unreachable(error))
        }
    };
    let tags = filter_and_dedupe_tags(
        &result.tags,
        read_config_json(state)["extensions"]["builtin-wd-tagger"]["nsfw_filter"]
            .as_bool()
            .unwrap_or(false),
    );
    let inserted = match write_wd_tags_for_retag(
        &state.db,
        file_id,
        model_id,
        &tags,
        overwrite,
        set_active.then_some(model_id),
    )
    .await
    {
        Ok(value) => value,
        Err(error) => {
            tracing::error!(?error, "wd retag write failed");
            return TagOutcome::Rejected(json!({"ok": false, "error": "internal_server_error"}));
        }
    };
    if read_config_json(state)["extensions"]["builtin-wd-tagger"]["write_xmp"]
        .as_bool()
        .unwrap_or(true)
    {
        write_wd_xmp(
            Path::new(&path),
            &tags
                .iter()
                .map(|(tag, _, _)| tag.clone())
                .collect::<Vec<_>>(),
            model_id,
            general_thr,
            character_thr,
        );
    }
    TagOutcome::Tagged(
        json!({"file_id": file_id, "model_id": model_id, "tags": tags.iter().map(|(tag, confidence, category)| json!({"tag": tag, "confidence": confidence, "category": category})).collect::<Vec<_>>(), "rating": result.rating, "inserted": inserted}),
    )
}

/// POST /api/wd-tagger/retag/batch
pub async fn retag_batch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    retag_async(state, body, "batch").await
}

/// POST /api/wd-tagger/retag/backfill
pub async fn retag_backfill(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    retag_async(state, body, "backfill").await
}

/// POST /api/wd-tagger/retag/query
pub async fn retag_query(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    retag_async(state, body, "query").await
}

/// POST /api/wd-tagger/retag/cancel
pub async fn retag_cancel(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    if state.job_manager.cancel_job(WD_TAGGER_JOB_ID) {
        api_result(json!({"data": {"status": "cancelling"}}))
    } else {
        api_error_code(
            "No running retag job",
            StatusCode::NOT_FOUND,
            "job_not_running",
        )
    }
}

/// Rust query retag intentionally uses every condition match, unlike the former
/// Python route which retagged one paginated search response.
async fn retag_async(state: SharedState, body: Bytes, scope: &'static str) -> Response {
    let Ok(payload) = serde_json::from_slice::<Value>(&body) else {
        return api_error_code(
            "invalid JSON body",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    let Some(payload) = payload.as_object() else {
        return api_error_code(
            "request body must be a JSON object",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    let Some(model_input) = payload
        .get("model_id")
        .and_then(Value::as_str)
        .filter(|v| !v.is_empty())
    else {
        return api_error_code(
            "model_id required",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    };
    let thresholds = match payload.get("thresholds") {
        None => None,
        Some(Value::Object(v)) => Some(v),
        Some(_) => {
            return api_error_code(
                "thresholds must be an object",
                StatusCode::BAD_REQUEST,
                "invalid_input",
            )
        }
    };
    let threshold = |name, default| match thresholds.and_then(|v| v.get(name)) {
        None => Ok(default),
        Some(value) => value
            .as_f64()
            .map(crate::num::narrow_f32)
            .filter(|v| v.is_finite() && (0.0..=1.0).contains(v))
            .ok_or_else(|| {
                api_error_code(
                    "threshold must be a number between 0 and 1",
                    StatusCode::BAD_REQUEST,
                    "invalid_input",
                )
            }),
    };
    let (general_thr, character_thr) =
        match (threshold("general", 0.35), threshold("character", 0.85)) {
            (Ok(general), Ok(character)) => (general, character),
            (Err(response), _) | (_, Err(response)) => return response,
        };
    let _batch_size = match payload
        .get("batch_size")
        .map(Value::as_i64)
        .unwrap_or(Some(8))
    {
        Some(value @ 1..=64) => usize::try_from(value).unwrap_or(8),
        _ => {
            return api_error_code(
                "batch_size must be between 1 and 64",
                StatusCode::BAD_REQUEST,
                "invalid_input",
            )
        }
    };
    let limit = match payload.get("limit").map(Value::as_i64).unwrap_or(Some(0)) {
        Some(value @ 0..=1_000_000) => value,
        _ => {
            return api_error_code(
                "limit must be between 0 and 1000000",
                StatusCode::BAD_REQUEST,
                "invalid_input",
            )
        }
    };
    let set_active = match payload.get("set_active") {
        None => true,
        Some(v) => match v.as_bool() {
            Some(v) => v,
            None => {
                return api_error_code(
                    "set_active must be a boolean",
                    StatusCode::BAD_REQUEST,
                    "invalid_input",
                )
            }
        },
    };
    let overwrite = match payload.get("overwrite_same_model") {
        None => true,
        Some(v) => match v.as_bool() {
            Some(v) => v,
            None => {
                return api_error_code(
                    "overwrite_same_model must be a boolean",
                    StatusCode::BAD_REQUEST,
                    "invalid_input",
                )
            }
        },
    };
    let profiles = load_full_profiles(&state.config.project_root);
    let Some((profile, _, _)) = profiles.get(model_input).or_else(|| {
        profiles
            .values()
            .find(|(p, _, _)| p["model_id"].as_str() == Some(model_input))
    }) else {
        return api_error_code(
            "model_id not found",
            StatusCode::NOT_FOUND,
            "model_not_found",
        );
    };
    if profile["adapter_family"].as_str() != Some("wd")
        || profile["backend"].as_str() != Some("onnx")
        || !profile["hf_subdir"].is_null()
    {
        return api_error_code(
            "model is not supported by native retag",
            StatusCode::BAD_REQUEST,
            "invalid_input",
        );
    }
    let model_id = sanitize_model_id(profile["model_id"].as_str().unwrap_or(model_input));
    if let Err(error) = sqlx::query("INSERT OR IGNORE INTO wd_model_dict(model) VALUES (?)")
        .bind(&model_id)
        .execute(&state.db)
        .await
    {
        return internal_error(error, "wd retag model setup failed");
    }
    let model_db_id = match sqlx::query_scalar("SELECT id FROM wd_model_dict WHERE model = ?")
        .bind(&model_id)
        .fetch_one(&state.db_read)
        .await
    {
        Ok(id) => id,
        Err(error) => return internal_error(error, "wd retag model lookup failed"),
    };
    let targets = match scope {
        "batch" => {
            let Some(values) = payload.get("file_ids").and_then(Value::as_array) else {
                return api_error_code(
                    "file_ids must be a list",
                    StatusCode::BAD_REQUEST,
                    "invalid_input",
                );
            };
            if values.len() > 500 {
                return api_error_code(
                    "file_ids max 500",
                    StatusCode::BAD_REQUEST,
                    "batch_too_large",
                );
            }
            let Some(ids) = values.iter().map(Value::as_i64).collect::<Option<Vec<_>>>() else {
                return api_error_code(
                    "file_ids must be a list",
                    StatusCode::BAD_REQUEST,
                    "invalid_input",
                );
            };
            let ids = filter_active_in_order(&state.db_read, &ids).await;
            if limit > 0 {
                ids.into_iter()
                    .take(usize::try_from(limit).unwrap_or(0))
                    .collect()
            } else {
                ids
            }
        }
        "backfill" => {
            let scan_root = match payload.get("scan_root") {
                None => "",
                Some(Value::String(v)) => v,
                Some(_) => {
                    return api_error_code(
                        "scan_root must be a string",
                        StatusCode::BAD_REQUEST,
                        "invalid_input",
                    )
                }
            };
            let force = match payload.get("force") {
                None => false,
                Some(v) => match v.as_bool() {
                    Some(v) => v,
                    None => {
                        return api_error_code(
                            "force must be a boolean",
                            StatusCode::BAD_REQUEST,
                            "invalid_input",
                        )
                    }
                },
            };
            query_backfill_targets(&state, scan_root, limit, force, Some(model_db_id)).await
        }
        "query" => {
            let Some(params) = payload.get("query_params").filter(|v| v.is_object()) else {
                return api_error_code(
                    "query_params must be an object",
                    StatusCode::BAD_REQUEST,
                    "invalid_input",
                );
            };
            let raw: SearchQueryRaw =
                match serde_json::from_value(normalize_search_query_params(params)) {
                    Ok(raw) => raw,
                    Err(_) => {
                        return api_error_code(
                            "query_params invalid",
                            StatusCode::BAD_REQUEST,
                            "invalid_input",
                        )
                    }
                };
            let mut search_params = SearchParams::from(raw);
            let mut ids: Vec<i64> = if !table_exists(&state.db_read, "files").await.unwrap_or(false)
            {
                Vec::new()
            } else {
                if search_params.also_path
                    && !table_exists(&state.db_read, "files_path_fts")
                        .await
                        .unwrap_or(false)
                {
                    search_params.also_path = false;
                }
                match fetch_matching_ids(&state.db_read, &search_params).await {
                    Ok(Some(ids)) => ids.into_iter().collect(),
                    Ok(None) => Vec::new(),
                    Err(error) => return internal_error(error, "wd retag query lookup failed"),
                }
            };
            ids.sort_unstable();
            let ids = filter_active_in_order(&state.db_read, &ids).await;
            if limit > 0 {
                ids.into_iter()
                    .take(usize::try_from(limit).unwrap_or(0))
                    .collect()
            } else {
                ids
            }
        }
        // `scope` is a `&'static str` the four route wrappers pass as a literal,
        // so only the three arms above occur. A new wrapper that forgets an arm
        // should get a 500 it can read, not a panicked request thread.
        other => {
            return internal_error(
                format!("unknown retag scope: {other}"),
                "wd retag scope is not one of batch/backfill/query",
            )
        }
    };
    if targets.is_empty() {
        return api_result(
            json!({"data": {"started": false, "reason": "no_targets", "scope": scope}}),
        );
    }
    let Some(cancel) = state
        .job_manager
        .start_if_idle(WD_TAGGER_JOB_ID, "WD-Tagger retag")
    else {
        return api_error_code(
            "WD-Tagger retag job already running",
            StatusCode::CONFLICT,
            "job_running",
        );
    };
    state.job_manager.set_phase(WD_TAGGER_JOB_ID, "running");
    let worker_state = state.clone();
    tokio::spawn(async move {
        // Python chunks by batch_size because one adapter inference handles a whole chunk and cannot be interrupted mid-chunk. Rust infers one file at a time, so chunking would only delay cancellation; the token is checked before every file. batch_size is validated for API compatibility but has no effect here.
        run_batch_worker_with_tagger(
            worker_state,
            WD_TAGGER_JOB_ID.to_string(),
            targets,
            overwrite,
            cancel,
            move |state, file_id, overwrite| {
                let model_id = model_id.clone();
                Box::pin(async move {
                    retag_file_native_core(
                        state,
                        file_id,
                        &model_id,
                        general_thr,
                        character_thr,
                        overwrite,
                        set_active,
                    )
                    .await
                })
            },
        )
        .await;
    });
    api_result(json!({"data": {"started": true, "job_id": WD_TAGGER_JOB_ID}}))
}

fn normalize_search_query_params(params: &Value) -> Value {
    let Value::Object(params) = params else {
        return Value::Object(Map::new());
    };
    Value::Object(
        params
            .iter()
            .filter_map(|(key, value)| {
                let value = match value {
                    Value::String(value) => Some(Value::String(value.clone())),
                    Value::Number(value) => Some(Value::String(value.to_string())),
                    Value::Bool(value) => Some(Value::String(value.to_string())),
                    Value::Null | Value::Array(_) | Value::Object(_) => None,
                }?;
                Some((key.clone(), value))
            })
            .collect(),
    )
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::{
        collections::{HashMap, HashSet},
        fs,
        path::{Path, PathBuf},
        str::FromStr,
        sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        },
        time::{SystemTime, UNIX_EPOCH},
    };

    use axum::{
        body::to_bytes,
        extract::{Path as AxumPath, State},
        http::{header, StatusCode},
        routing::get,
        Router,
    };
    use serde_json::{json, Value};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use super::{build_hf_url, secure_model_path, validate_hf_url, HfError};
    use crate::state::{AppState, Config, SharedState};

    async fn hf_stub_client(
        router: Router,
    ) -> Option<(reqwest::Client, String, tokio::task::JoinHandle<()>)> {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.ok()?;
        let address = listener.local_addr().ok()?;
        let server = tokio::spawn(async move {
            axum::serve(listener, router).await.unwrap();
        });
        let client = reqwest::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .resolve("huggingface.co", address)
            .build()
            .ok()?;
        Some((
            client,
            format!("http://huggingface.co:{}/", address.port()),
            server,
        ))
    }

    #[tokio::test]
    async fn hf_redirects_revalidate_each_hop_and_stop_at_limit() {
        let Some((client, base, server)) = hf_stub_client(Router::new().route(
            "/",
            get(|| async {
                (
                    StatusCode::FOUND,
                    [(header::LOCATION, "http://127.0.0.1/private")],
                )
            }),
        ))
        .await
        else {
            return;
        };
        let result = hf_request_with_client(
            reqwest::Method::GET,
            reqwest::Url::parse(&base).unwrap(),
            Duration::from_secs(1),
            &move |_, _| Box::pin(std::future::ready(Ok(client.clone()))),
        )
        .await;
        assert!(
            matches!(result, Err(HfError::Ssrf(message)) if message.contains("allowed HuggingFace host"))
        );
        server.abort();

        let hops = Arc::new(AtomicUsize::new(0));
        let state = hops.clone();
        let Some((client, base, server)) = hf_stub_client(Router::new().route(
            "/",
            get(move || {
                let state = state.clone();
                async move {
                    state.fetch_add(1, Ordering::SeqCst);
                    (StatusCode::FOUND, [(header::LOCATION, "/")])
                }
            }),
        ))
        .await
        else {
            return;
        };
        let result = hf_request_with_client(
            reqwest::Method::GET,
            reqwest::Url::parse(&base).unwrap(),
            Duration::from_secs(1),
            &move |_, _| Box::pin(std::future::ready(Ok(client.clone()))),
        )
        .await;
        assert!(
            matches!(result, Err(HfError::Ssrf(message)) if message.contains("too many redirects"))
        );
        assert_eq!(hops.load(Ordering::SeqCst), HF_MAX_REDIRECTS + 1);
        server.abort();
    }

    #[test]
    fn hf_content_length_limit_rejects_eight_gib_excess() {
        assert!(!hf_content_length_allowed(Some(HF_MAX_DOWNLOAD_BYTES + 1)));
        assert!(hf_content_length_allowed(Some(HF_MAX_DOWNLOAD_BYTES)));
    }

    #[test]
    fn hf_temporary_paths_are_unique_per_download() {
        let destination = Path::new("/tmp/model.onnx");
        assert_ne!(
            hf_temporary_path(destination),
            hf_temporary_path(destination)
        );
    }

    #[test]
    fn profile_test_status_mapping_and_response_use_same_mapper() {
        assert_eq!(profile_test_status("timeout"), StatusCode::REQUEST_TIMEOUT);
        assert_eq!(profile_test_status("ssrf_blocked"), StatusCode::BAD_GATEWAY);
        assert_eq!(
            profile_test_status("hf_unavailable"),
            StatusCode::BAD_GATEWAY
        );
        assert_eq!(
            profile_test_status("required_missing"),
            StatusCode::BAD_REQUEST
        );
        let response = profile_test_error("profile test timed out", "timeout", json!({}));
        assert_eq!(response.status(), StatusCode::REQUEST_TIMEOUT);
    }

    #[tokio::test]
    async fn hf_download_uses_cached_file_without_http() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        let profile = json!({"id":"cached", "model_id":"cached/model"});
        let cache = dirs.root.join("cache/wd_tagger/cached_model");
        fs::create_dir_all(&cache).unwrap();
        fs::write(cache.join("model.onnx"), b"cached").unwrap();
        let result = download_hf_file(&state, &profile, "model.onnx", Duration::from_secs(1))
            .await
            .unwrap();
        assert_eq!(
            result,
            json!({"name":"model.onnx", "status":"cached", "size":6})
        );
    }

    #[tokio::test]
    async fn hf_download_rejects_oversized_content_length_through_download_seam() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        let profile = json!({"id":"oversized", "model_id":"oversized/model"});
        let result = download_hf_file_with_request(
            &state,
            &profile,
            "model.onnx",
            Duration::from_secs(1),
            &|_, _, _| {
                Box::pin(async {
                    let fake = axum::http::Response::builder()
                        .status(200)
                        .header(axum::http::header::CONTENT_LENGTH, "9000000000")
                        .body(reqwest::Body::from(Vec::new()))
                        .unwrap();
                    Ok(reqwest::Response::from(fake))
                })
            },
        )
        .await;
        assert!(matches!(result, Err(HfError::TooLarge(_))));
    }

    #[test]
    fn hf_url_guard_rejects_spoofs_and_accepts_exact_hosts() {
        for url in [
            "file:///etc/passwd",
            "https://huggingface.co@169.254.169.254/x",
            "https://evil-huggingface.co/x",
            "https://huggingface.co.evil.com/x",
        ] {
            assert!(
                matches!(
                    validate_hf_url(&reqwest::Url::parse(url).unwrap()),
                    Err(HfError::Ssrf(_))
                ),
                "{url}"
            );
        }
        for url in [
            "https://huggingface.co/x",
            "https://hf.co/x",
            "https://cdn-lfs.huggingface.co/x",
        ] {
            assert!(
                validate_hf_url(&reqwest::Url::parse(url).unwrap()).is_ok(),
                "{url}"
            );
        }
    }

    #[test]
    fn hf_url_keeps_slashes_and_path_guard_rejects_escape() {
        let url = build_hf_url(
            &json!({"model_id":"org/model", "hf_subdir":"v1"}),
            "../model file.onnx",
        )
        .unwrap();
        assert_eq!(
            url.as_str(),
            "https://huggingface.co/org/model/resolve/main/model%20file.onnx"
        );
        let root = tempfile::tempdir().unwrap();
        assert!(matches!(
            secure_model_path(root.path(), "../../etc/passwd"),
            Err(HfError::Path(_))
        ));
    }

    pub(crate) struct TestDirs {
        pub(crate) root: PathBuf,
    }

    impl Drop for TestDirs {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    pub(crate) fn test_dirs() -> TestDirs {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("yu-server-wd-tagger-test-{suffix}"));
        fs::create_dir_all(root.join("extensions/builtin_wd_tagger/core_impl/profiles")).unwrap();
        fs::create_dir_all(root.join("profiles/wd_tagger")).unwrap();
        fs::create_dir_all(root.join("cache/wd_tagger")).unwrap();
        TestDirs { root }
    }

    fn write_profile(path: &Path, id: &str, display_name: &str, model_id: &str) {
        fs::write(
            path,
            json!({
                "id": id,
                "display_name": display_name,
                "model_id": model_id,
                "adapter_family": "wd",
                "backend": "onnx",
                "builtin": true,
                "files": [
                    {"name": "model.onnx", "required": true},
                    {"name": "selected_tags.csv", "required": true}
                ],
                "categories_mode": "all",
                "threshold_source": {"type": "profile"}
            })
            .to_string(),
        )
        .unwrap();
    }

    fn full_profile(id: &str, display_name: &str, model_id: &str) -> Value {
        json!({
            "profile_version": "2",
            "id": id,
            "display_name": display_name,
            "model_id": model_id,
            "adapter_family": "wd",
            "backend": "onnx",
            "builtin": false,
            "files": [
                {"name": "model.onnx", "required": true},
                {"name": "selected_tags.csv", "required": true}
            ],
            "preprocess_spec": {"size": 448},
            "tag_source": {"type": "csv", "filename": "selected_tags.csv"},
            "threshold_source": {"type": "profile"},
            "categories_mode": "from_tag_source",
            "supports_categories": ["general"],
            "default_thresholds": {"general": 0.35}
        })
    }

    pub(crate) async fn test_state(dirs: &TestDirs, app_config: Value) -> SharedState {
        test_state_ex(dirs, app_config, None, true, PathBuf::from(".")).await
    }

    pub(crate) async fn test_state_ex(
        dirs: &TestDirs,
        app_config: Value,
        infer_client: Option<crate::infer_client::InferClient>,
        infer_standalone: bool,
        cache_dir: PathBuf,
    ) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL,
               is_deleted INTEGER NOT NULL DEFAULT 0,
               meta_source TEXT
             );
             CREATE TABLE kv_state (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER);
             CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL UNIQUE);
             CREATE TABLE wd_category_dict (id INTEGER PRIMARY KEY, category TEXT NOT NULL UNIQUE);
             CREATE TABLE wd_tag_dict (id INTEGER PRIMARY KEY, tag_name TEXT NOT NULL UNIQUE, tag_name_normalized TEXT NOT NULL);
             CREATE TABLE file_wd_tags (
               id INTEGER PRIMARY KEY,
               file_id INTEGER NOT NULL,
               tag_id INTEGER NOT NULL,
               category_id INTEGER NOT NULL,
               model_id INTEGER NOT NULL,
               confidence_milli INTEGER NOT NULL,
                created_at INTEGER,
                UNIQUE(file_id, tag_id, model_id)
             );
             CREATE TABLE wd_tag_stats_cache (id INTEGER PRIMARY KEY, stats_json TEXT, computed_at INTEGER);
             INSERT INTO files(id, path, is_deleted, meta_source) VALUES
               (1, '/img/a.png', 0, 'unknown'),
               (2, '/img/b.png', 0, 'novelai'),
               (3, '/img/deleted.png', 1, 'unknown');
             INSERT INTO kv_state(key, value, updated_at) VALUES
               ('wd_active_model_id', 'model-a', 100);
             INSERT INTO wd_model_dict(id, model) VALUES
               (1, 'model-a'), (2, 'model-b');
             INSERT INTO wd_category_dict(id, category) VALUES
               (1, 'general'), (2, 'character');
             INSERT INTO wd_tag_dict(id, tag_name, tag_name_normalized) VALUES
               (1, '1girl', '1girl'), (2, 'solo', 'solo');
             INSERT INTO file_wd_tags(file_id, tag_id, category_id, model_id, confidence_milli, created_at) VALUES
               (1, 1, 1, 1, 900, 10),
               (1, 2, 2, 1, 800, 10),
               (2, 1, 1, 2, 700, 11);",
        )
        .execute(&pool)
        .await
        .unwrap();

        Arc::new(
            AppState::new_with_infer(
                Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: HashSet::new(),
                    trusted_peer_ips: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: dirs.root.join("config.json"),
                    project_root: dirs.root.clone(),
                    app_config,
                    cache_dir,
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
                infer_client,
                None,
            )
            .await,
        )
    }

    async fn json_body(response: axum::response::Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    async fn auto_tag_test_lock() -> tokio::sync::OwnedMutexGuard<()> {
        static LOCK: std::sync::OnceLock<Arc<tokio::sync::Mutex<()>>> = std::sync::OnceLock::new();
        LOCK.get_or_init(|| Arc::new(tokio::sync::Mutex::new(())))
            .clone()
            .lock_owned()
            .await
    }

    #[tokio::test]
    async fn retag_single_rejects_invalid_input() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        for body in [
            b"not json".as_slice(),
            br#"{"file_id":1}"#,
            br#"{"file_id":1,"model_id":"a","thresholds":false}"#,
        ] {
            let response =
                retag_single(State(state.clone()), None, Bytes::copy_from_slice(body)).await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        }
    }

    #[tokio::test]
    async fn retag_async_validates_input_and_shared_job_exclusion() {
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/a.json"),
            "profile-a",
            "A",
            "model-a",
        );
        let state = test_state(&dirs, json!({})).await;
        for body in [
            br#"{"model_id":"","file_ids":[]}"#.as_slice(),
            br#"{"model_id":"profile-a","file_ids":{},"batch_size":8}"#,
            br#"{"model_id":"profile-a","file_ids":[],"batch_size":0}"#,
            br#"{"model_id":"profile-a","file_ids":[],"batch_size":65}"#,
            br#"{"model_id":"profile-a","file_ids":[],"thresholds":false}"#,
        ] {
            assert_eq!(
                retag_batch(State(state.clone()), None, Bytes::copy_from_slice(body))
                    .await
                    .status(),
                StatusCode::BAD_REQUEST
            );
        }
        let file_ids: Vec<i64> = (0..=500).collect();
        assert_eq!(
            retag_batch(
                State(state.clone()),
                None,
                Bytes::from(json!({"model_id":"profile-a","file_ids":file_ids}).to_string())
            )
            .await
            .status(),
            StatusCode::BAD_REQUEST
        );
        state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");
        let response = retag_batch(
            State(state),
            None,
            Bytes::from_static(br#"{"model_id":"profile-a","file_ids":[1]}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::CONFLICT);
        assert_eq!(json_body(response).await["code"], "job_running");
    }

    #[tokio::test]
    async fn retag_cancel_uses_shared_wd_tagger_job() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");
        let response = retag_cancel(State(state.clone()), None, Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(json_body(response).await["data"]["status"], "cancelling");
        let idle_state = test_state(&dirs, json!({})).await;
        let response = retag_cancel(State(idle_state), None, Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(json_body(response).await["code"], "job_not_running");
    }

    #[tokio::test]
    async fn retag_query_normalizes_json_scalar_params_and_empty_query_has_no_targets() {
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/a.json"),
            "profile-a",
            "A",
            "model-a",
        );
        let state = test_state(&dirs, json!({})).await;
        sqlx::raw_sql("CREATE TABLE favorites (file_id INTEGER NOT NULL, collection_id INTEGER); CREATE TABLE tags (id INTEGER PRIMARY KEY, tag TEXT); CREATE TABLE file_tags (file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL);")
            .execute(&state.db)
            .await
            .unwrap();
        let response = retag_query(
            State(state.clone()),
            None,
            Bytes::from(
                json!({"model_id":"profile-a","query_params":{"q":"no-match","also_path":true,"limit":50,"fav_only":true}})
                    .to_string(),
            ),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(json_body(response).await["data"]["reason"], "no_targets");
        sqlx::query("DROP TABLE files")
            .execute(&state.db)
            .await
            .unwrap();
        let response = retag_query(
            State(state.clone()),
            None,
            Bytes::from_static(
                br#"{"model_id":"profile-a","query_params":{"q":"no-match","also_path":true}}"#,
            ),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(json_body(response).await["data"]["reason"], "no_targets");
        let response = retag_query(
            State(state),
            None,
            Bytes::from_static(br#"{"model_id":"profile-a","query_params":{}}"#),
        )
        .await;
        assert_eq!(
            json_body(response).await["data"],
            json!({"started":false,"reason":"no_targets","scope":"query"})
        );
    }

    #[tokio::test]
    async fn backfill_targets_use_requested_model_while_batch_keeps_configured_model() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        sqlx::query("UPDATE files SET is_deleted = 1")
            .execute(&state.db)
            .await
            .unwrap();
        for id in [501_i64, 502] {
            sqlx::query("INSERT INTO files(id, path, is_deleted) VALUES (?, ?, 0)")
                .bind(id)
                .bind(format!("/img/{id}.png"))
                .execute(&state.db)
                .await
                .unwrap();
        }
        sqlx::query(
            "INSERT OR IGNORE INTO wd_model_dict(model) VALUES ('SmilingWolf_wd-swinv2-tagger-v3')",
        )
        .execute(&state.db)
        .await
        .unwrap();
        let configured_model_id: i64 = sqlx::query_scalar(
            "SELECT id FROM wd_model_dict WHERE model = 'SmilingWolf_wd-swinv2-tagger-v3'",
        )
        .fetch_one(&state.db)
        .await
        .unwrap();
        sqlx::query("INSERT INTO file_wd_tags(file_id, tag_id, category_id, model_id, confidence_milli) VALUES (501, 1, 1, 2, 900), (?, 1, 1, ?, 900)")
            .bind(502).bind(configured_model_id)
            .execute(&state.db).await.unwrap();
        let requested =
            crate::routes::wd_tagger_batch::query_backfill_targets(&state, "", 0, false, Some(2))
                .await;
        assert_eq!(requested, vec![502]);
        let configured =
            crate::routes::wd_tagger_batch::query_backfill_targets(&state, "", 0, false, None)
                .await;
        assert_eq!(configured, vec![501]);
    }

    #[tokio::test]
    async fn retag_start_blocks_native_batch_start() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger retag");
        let result = crate::routes::wd_tagger_batch::start_batch_job(
            state.clone(),
            crate::routes::wd_tagger_batch::BatchRequest {
                file_ids: Some(vec![1]),
                scan_root: None,
                limit: 1,
                force: false,
            },
        )
        .await
        .unwrap();
        assert!(matches!(
            result,
            crate::routes::wd_tagger_batch::StartResult::AlreadyRunning
        ));
        state.job_manager.cancel_job(WD_TAGGER_JOB_ID);
    }

    #[tokio::test]
    async fn retag_single_fallback_does_not_write_tags() {
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/a.json"),
            "profile-a",
            "A",
            "model-a",
        );
        let path = dirs.root.join("fallback.pdf");
        fs::write(&path, b"not an image").unwrap();
        let state = test_state(&dirs, json!({})).await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (99, ?, 0)")
            .bind(path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        let response = retag_single(
            State(state.clone()),
            None,
            Bytes::from_static(br#"{"file_id":99,"model_id":"profile-a"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(
            sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM file_wd_tags WHERE file_id = 99")
                .fetch_one(&state.db)
                .await
                .unwrap(),
            0
        );
    }

    #[tokio::test]
    async fn retag_single_native_success_uses_sanitized_model_and_nested_data() {
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            return;
        };
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(listener, axum::Router::new().route("/v1/infer/wd", axum::routing::post(|| async {
                Json(json!({"data":{"tags":[{"tag":"Blue Eyes","confidence":0.9,"category":"general"}],"rating":"general","path":"irrelevant","model_id":"irrelevant"}}))
            }))).await.unwrap()
        });
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/a.json"),
            "profile-a",
            "A",
            "Repo/Name",
        );
        let image = dirs.root.join("retag.png");
        image::RgbImage::new(1, 1).save(&image).unwrap();
        let root = fs::canonicalize(&dirs.root).unwrap();
        let state = test_state_ex(
            &dirs,
            json!({"scan_roots":[{"path":root.to_string_lossy()}]}),
            Some(crate::infer_client::InferClient::new(
                format!("http://{address}"),
                String::new(),
            )),
            true,
            PathBuf::from("."),
        )
        .await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (88, ?, 0)")
            .bind(image.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        let response = retag_single(
            State(state.clone()),
            None,
            Bytes::from_static(br#"{"file_id":88,"model_id":"profile-a"}"#),
        )
        .await;
        let body = json_body(response).await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["data"]["model_id"], "Repo_Name");
        assert_eq!(body["data"]["inserted"], 1);
        let elapsed = body["data"]["elapsed_ms"].as_f64().unwrap();
        // `elapsed` is a measured duration, so exact equality after scaling is
        // not guaranteed even when the production code rounded correctly:
        // binary floating point can't represent every 2-decimal value exactly
        // (e.g. 4.27 * 100.0 == 426.99999999999994). Compare within an
        // epsilon instead of demanding bit-exact equality.
        let scaled = elapsed * 100.0;
        assert!(
            (scaled - scaled.round()).abs() < 1e-6,
            "elapsed_ms should be rounded to 2 decimal places, got {elapsed}"
        );
        let response = retag_single(
            State(state.clone()),
            None,
            Bytes::from_static(
                br#"{"file_id":88,"model_id":"profile-a","overwrite_same_model":false}"#,
            ),
        )
        .await;
        assert_eq!(json_body(response).await["data"]["inserted"], 0);
        assert_eq!(
            sqlx::query_scalar::<_, String>(
                "SELECT model FROM wd_model_dict WHERE model = 'Repo_Name'"
            )
            .fetch_one(&state.db)
            .await
            .unwrap(),
            "Repo_Name"
        );
        server.abort();
    }

    #[tokio::test]
    async fn auto_tag_queue_full_leaves_no_in_flight_entry() {
        let _test_lock = auto_tag_test_lock().await;
        let dirs = test_dirs();
        fs::write(
            dirs.root.join("config.json"),
            json!({"extensions":{"builtin-wd-tagger":{"auto_tag_on_import":true}}}).to_string(),
        )
        .unwrap();
        let state = test_state(&dirs, json!({})).await;
        let queue = auto_tag_import_queue();
        let held = vec![
            queue.permits.clone().try_acquire_owned().unwrap(),
            queue.permits.clone().try_acquire_owned().unwrap(),
        ];
        schedule_auto_tag_on_import(state, 42);
        assert!(!queue.in_flight.lock().unwrap().contains(&42));
        drop(held);
    }

    #[tokio::test]
    async fn auto_tag_scheduler_dedupes_and_releases_queue_after_completion() {
        let _test_lock = auto_tag_test_lock().await;
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            return;
        };
        let address = listener.local_addr().unwrap();
        let started = Arc::new(tokio::sync::Notify::new());
        let release = Arc::new(tokio::sync::Notify::new());
        let server = tokio::spawn({
            let started = started.clone();
            let release = release.clone();
            async move {
                axum::serve(listener, axum::Router::new().route("/v1/infer/wd", axum::routing::post(move || {
                    let started = started.clone();
                    let release = release.clone();
                    async move {
                        started.notify_one();
                        release.notified().await;
                        Json(json!({"data":{"tags":[],"rating":"general","path":"irrelevant","model_id":"irrelevant"}}))
                    }
                }))).await.unwrap()
            }
        });
        let dirs = test_dirs();
        let image = dirs.root.join("auto.png");
        image::RgbImage::new(1, 1).save(&image).unwrap();
        let root = fs::canonicalize(&dirs.root).unwrap();
        let state = test_state_ex(
            &dirs,
            json!({"scan_roots":[{"path":root.to_string_lossy()}]}),
            Some(crate::infer_client::InferClient::new(
                format!("http://{address}"),
                String::new(),
            )),
            true,
            PathBuf::from("."),
        )
        .await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (77, ?, 0)")
            .bind(image.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        let queue = auto_tag_import_queue();
        schedule_auto_tag_on_import(state.clone(), 77);
        tokio::time::timeout(std::time::Duration::from_secs(1), started.notified())
            .await
            .unwrap();
        schedule_auto_tag_on_import(state, 77);
        assert!(queue.in_flight.lock().unwrap().contains(&77));
        release.notify_one();
        tokio::time::timeout(std::time::Duration::from_secs(1), async {
            while queue.in_flight.lock().unwrap().contains(&77) {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        let permits = [
            queue.permits.clone().try_acquire_owned().unwrap(),
            queue.permits.clone().try_acquire_owned().unwrap(),
        ];
        drop(permits);
        server.abort();
    }

    #[tokio::test]
    async fn profiles_returns_registry_profiles_with_active_model_and_tag_flags() {
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/a.json"),
            "builtin-a",
            "Builtin A",
            "model-a",
        );
        let state = test_state(&dirs, json!({})).await;

        let response = profiles(State(state), None).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["active_model_id"], "model-a");
        assert_eq!(value["profiles"][0]["id"], "builtin-a");
        assert_eq!(value["profiles"][0]["has_tags"], true);
        assert_eq!(value["profiles"][0]["origin"], "builtin");
    }

    #[tokio::test]
    async fn active_model_returns_kv_state_and_available_models() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;

        let response = active_model(State(state), None).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["active_model_id"], "model-a");
        assert_eq!(value["available_models"][0]["model_id"], "model-a");
        assert_eq!(value["available_models"][0]["file_count"], 1);
        assert_eq!(value["available_models"][1]["model_id"], "model-b");
        assert_eq!(value["available_models"][1]["file_count"], 1);
    }

    #[tokio::test]
    async fn model_status_reports_legacy_cache_files_and_known_models() {
        let dirs = test_dirs();
        let cache_dir = dirs
            .root
            .join("cache/wd_tagger/SmilingWolf_wd-swinv2-tagger-v3");
        fs::create_dir_all(&cache_dir).unwrap();
        fs::write(cache_dir.join("model.onnx"), vec![0_u8; 1024 * 1024]).unwrap();
        let state = test_state(
            &dirs,
            json!({"wd_tagger": {"model": "SmilingWolf/wd-swinv2-tagger-v3"}}),
        )
        .await;

        let response = model_status(State(state), None, axum::extract::Query(HashMap::new())).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["repo"], "SmilingWolf/wd-swinv2-tagger-v3");
        assert_eq!(value["ready"], false);
        assert_eq!(value["files"]["model.onnx"]["exists"], true);
        assert_eq!(value["files"]["model.onnx"]["size_mb"], 1.0);
        assert_eq!(value["files"]["selected_tags.csv"]["exists"], false);
        assert_eq!(
            value["known_models"]["Camais03/camie-tagger-v2"],
            "Camie Tagger v2"
        );
    }

    #[tokio::test]
    async fn model_status_resolves_selected_profile_model_id() {
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/builtin-a.json"),
            "builtin-a",
            "Builtin A",
            "model-a",
        );
        let cache_dir = dirs.root.join("cache/wd_tagger/model-a");
        fs::create_dir_all(&cache_dir).unwrap();
        fs::write(cache_dir.join("model.onnx"), b"x").unwrap();
        fs::write(cache_dir.join("selected_tags.csv"), b"name,category\na,0\n").unwrap();
        let state = test_state(&dirs, json!({})).await;

        let response = model_status(
            State(state),
            None,
            axum::extract::Query(HashMap::from([(
                "model_id".to_string(),
                "builtin-a".to_string(),
            )])),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["repo"], "model-a");
        assert_eq!(value["ready"], true);
        assert_eq!(value["files"]["model.onnx"]["exists"], true);
    }
    #[tokio::test]
    async fn wd_stats_recomputes_when_cache_is_empty_and_includes_untagged_unknown() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;

        let response = stats(State(state), None).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["total_tags"], 3);
        assert_eq!(value["tagged_files"], 2);
        assert_eq!(value["unique_tags"], 2);
        assert_eq!(value["by_category"]["general"], 2);
        assert_eq!(value["by_model"]["model-a"], 1);
        assert_eq!(value["untagged_unknown"], 1);
    }

    #[tokio::test]
    async fn untagged_filters_by_active_model_and_clamps_pagination() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;

        let response = untagged(
            State(state),
            None,
            axum::extract::Query(HashMap::from([
                ("limit".to_string(), "bad".to_string()),
                ("offset".to_string(), "-9".to_string()),
            ])),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["total"], 1);
        assert_eq!(value["files"][0]["id"], 2);
        assert_eq!(value["files"][0]["path"], "/img/b.png");
    }

    #[tokio::test]
    async fn config_returns_default_wd_tagger_config_merged_with_app_config() {
        let dirs = test_dirs();
        let state = test_state(
            &dirs,
            json!({"wd_tagger": {"model": "custom/model", "write_xmp": false}}),
        )
        .await;

        let response = config(State(state), None).await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["config"]["model"], "custom/model");
        assert_eq!(value["config"]["write_xmp"], false);
        assert_eq!(value["config"]["general_threshold"], 0.35);
        assert_eq!(value["config"]["engine_type"], "onnx");
    }

    #[tokio::test]
    async fn vlm_test_requires_url_parameter() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;

        let response = vlm_test(State(state), None, axum::extract::Query(HashMap::new())).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["error"], "url parameter required");
        assert_eq!(value["code"], "missing_url");
    }

    #[tokio::test]
    async fn vlm_test_rejects_invalid_scheme() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;

        let response = vlm_test(
            State(state),
            None,
            axum::extract::Query(HashMap::from([(
                "url".to_string(),
                "file:///tmp/socket".to_string(),
            )])),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value["error"], "Only http/https URLs are allowed");
        assert_eq!(value["code"], "invalid_url");
    }

    #[tokio::test]
    async fn vlm_test_rejects_metadata_hostname_even_when_local_is_allowed() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;

        let response = vlm_test(
            State(state),
            None,
            axum::extract::Query(HashMap::from([(
                "url".to_string(),
                "http://metadata.google.internal".to_string(),
            )])),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value["error"], "Blocked address");
        assert_eq!(value["code"], "invalid_url");
    }

    #[tokio::test]
    async fn profile_get_create_update_and_delete_use_user_registry_files() {
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/builtin-a.json"),
            "builtin-a",
            "Builtin A",
            "model-a",
        );
        let state = test_state(&dirs, json!({})).await;

        let missing = profile_get(
            State(Arc::clone(&state)),
            None,
            AxumPath("missing".to_string()),
        )
        .await;
        assert_eq!(missing.status(), StatusCode::NOT_FOUND);

        let created = json_body(
            profile_create(
                State(Arc::clone(&state)),
                None,
                Json(full_profile("user-a", "User A", "model-user")),
            )
            .await,
        )
        .await;
        assert_eq!(created["profile"]["id"], json!("user-a"));
        assert_eq!(created["origin"], json!("user"));
        assert_eq!(created["overrides_builtin"], json!(false));

        let fetched = json_body(
            profile_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("user-a".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(fetched["profile"]["display_name"], json!("User A"));

        let updated = json_body(
            profile_update(
                State(Arc::clone(&state)),
                None,
                AxumPath("user-a".to_string()),
                Json(full_profile("user-a", "User A2", "model-user")),
            )
            .await,
        )
        .await;
        assert_eq!(updated["profile"]["display_name"], json!("User A2"));

        let deleted =
            json_body(profile_delete(State(state), None, AxumPath("user-a".to_string())).await)
                .await;
        assert_eq!(deleted["deleted"], json!(true));
    }

    #[tokio::test]
    async fn profile_delete_rejects_active_profile() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        profile_create(
            State(Arc::clone(&state)),
            None,
            Json(full_profile("model-a", "Active Profile", "model-a")),
        )
        .await;

        let response = profile_delete(State(state), None, AxumPath("model-a".to_string())).await;
        assert_eq!(response.status(), StatusCode::CONFLICT);
        let value = json_body(response).await;
        assert_eq!(value["code"], json!("in_use"));
        assert_eq!(value["active_model_id"], json!("model-a"));
    }

    #[tokio::test]
    async fn active_model_put_validates_and_updates_kv_state() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;

        let unknown = active_model_update(
            State(Arc::clone(&state)),
            None,
            Json(json!({"model_id": "missing"})),
        )
        .await;
        assert_eq!(unknown.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(unknown).await["code"], json!("unknown_model"));

        let value = json_body(
            active_model_update(
                State(Arc::clone(&state)),
                None,
                Json(json!({"model_id": "model-b"})),
            )
            .await,
        )
        .await;
        assert_eq!(value["active_model_id"], json!("model-b"));

        let cleared = json_body(
            active_model_update(State(state), None, Json(json!({"model_id": null}))).await,
        )
        .await;
        assert!(cleared["active_model_id"].is_null());
    }

    #[tokio::test]
    async fn config_save_writes_wd_tagger_section_and_syncs_active_model() {
        let dirs = test_dirs();
        fs::write(dirs.root.join("config.json"), "{}\n").unwrap();
        let state = test_state(&dirs, json!({})).await;

        let value = json_body(
            config_save(
                State(Arc::clone(&state)),
                None,
                Json(json!({
                    "model": "model-b",
                    "general_threshold": 0.456,
                    "character_threshold": 0.8,
                    "engine_type": "onnx",
                    "write_xmp": false,
                    "vlm_url": "http://localhost:11434",
                    "vlm_model": "llava",
                    "vlm_timeout": 60,
                    "nsfw_filter": true
                })),
            )
            .await,
        )
        .await;
        assert_eq!(value["config"]["model"], json!("model-b"));
        assert_eq!(value["config"]["general_threshold"], json!(0.46));
        let saved: Value =
            serde_json::from_str(&fs::read_to_string(dirs.root.join("config.json")).unwrap())
                .unwrap();
        assert_eq!(saved["wd_tagger"]["model"], json!("model-b"));
        assert_eq!(
            active_model_id(&state.db).await.unwrap(),
            Some("model-b".to_string())
        );
    }

    #[tokio::test]
    async fn xmp_returns_sidecar_metadata_next_to_file() {
        let dirs = test_dirs();
        let image = dirs.root.join("img.png");
        fs::write(&image, b"image").unwrap();
        fs::write(
            dirs.root.join("img.png.xmp"),
            r#"<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:wdtag="https://github.com/yu/wdtag/"><rdf:RDF><rdf:Description wdtag:model="model-a"><dc:subject><rdf:Bag><rdf:li>1girl</rdf:li></rdf:Bag></dc:subject></rdf:Description></rdf:RDF></x:xmpmeta>"#,
        )
        .unwrap();
        let state = test_state(&dirs, json!({})).await;
        sqlx::query("UPDATE files SET path = ? WHERE id = 1")
            .bind(image.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        let value = json_body(xmp(State(state), None, AxumPath(1)).await).await;
        assert_eq!(value["file_id"], json!(1));
        assert!(value["xmp"]["raw_xml"]
            .as_str()
            .unwrap()
            .contains("xmpmeta"));
        assert_eq!(value["xmp"]["dc_subject"], json!(["1girl"]));
        assert_eq!(value["xmp"]["wdtag"]["model"], json!("model-a"));
    }

    #[tokio::test]
    async fn tag_file_native_core_returns_tagged_with_response_payload() {
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            // Restricted CI sandboxes may prohibit loopback listeners.
            return;
        };
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(
                listener,
                axum::Router::new().route(
                    "/v1/infer/wd",
                    axum::routing::post(|| async {
                        Json(json!({
                            "data": {
                                "tags": [{"tag": "1girl", "confidence": 0.9, "category": "general"}],
                                "rating": "general",
                                "path": "irrelevant",
                                "model_id": "irrelevant",
                            }
                        }))
                    }),
                ),
            )
            .await
            .unwrap()
        });

        let dirs = test_dirs();
        let image_path = dirs.root.join("tagme.png");
        image::RgbImage::new(1, 1).save(&image_path).unwrap();
        let real_root = fs::canonicalize(&dirs.root).unwrap();
        let app_config = json!({
            "scan_roots": [{"path": real_root.to_string_lossy()}],
        });
        let infer_client =
            crate::infer_client::InferClient::new(format!("http://{address}"), String::new());
        let state = test_state_ex(
            &dirs,
            app_config,
            Some(infer_client),
            true,
            PathBuf::from("."),
        )
        .await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (201, ?, 0)")
            .bind(image_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        let outcome = tag_file_native_core(&state, 201, false).await;
        match outcome {
            TagOutcome::Tagged(v) => {
                assert!(v.get("tag_count").is_some());
            }
            other => panic!("expected Tagged, got {other:?}"),
        }
        server.abort();
    }

    #[tokio::test]
    async fn tag_file_native_core_returns_skipped_when_already_tagged_and_not_forced() {
        let dirs = test_dirs();
        // infer_standalone=false so step 4's sidecar-not-running fallback check
        // (state.infer_client.is_none() && state.config.infer_standalone) does not
        // short-circuit before the already-tagged skip check is reached.
        let state = test_state_ex(&dirs, json!({}), None, false, PathBuf::from(".")).await;
        // file_id=1 already has file_wd_tags rows seeded by test_state_ex(), but its
        // seeded path ('/img/a.png') does not exist on disk. Point it at a real
        // file so the on-disk existence check (step 2) passes and the flow can
        // reach the already-tagged skip check (step "skip判定").
        let image_path = dirs.root.join("already-tagged.png");
        fs::write(&image_path, b"fake").unwrap();
        sqlx::query("UPDATE files SET path = ? WHERE id = 1")
            .bind(image_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        let outcome = tag_file_native_core(&state, 1, false).await;
        match outcome {
            TagOutcome::Skipped(v) => {
                assert_eq!(
                    v.get("reason").and_then(|x| x.as_str()),
                    Some("already_tagged")
                );
            }
            other => panic!("expected Skipped, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn tag_file_native_core_reports_unsupported_format_without_forwarding() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        let video_path = dirs.root.join("unsupported.pdf");
        fs::write(&video_path, b"fake").unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (103, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        // Matches Python's own answer (`single_ops.py` -> unsupported_type), so
        // there is nothing to forward for.
        match tag_file_native_core(&state, 103, false).await {
            TagOutcome::Rejected(body) => {
                assert_eq!(body["code"], "unsupported_type");
                assert_eq!(body["error"], "File type not supported for tagging");
            }
            other => panic!("unsupported format must be reported, not forwarded: {other:?}"),
        }
    }

    #[tokio::test]
    async fn tag_file_native_wrapper_unchanged_behavior_for_fallback() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        let video_path = dirs.root.join("unsupported2.mp4");
        fs::write(&video_path, b"fake").unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (104, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        let response = tag_file_native(&state, 104, false).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(
            json_body(response).await["code"],
            "infer_sidecar_unavailable"
        );
    }

    #[tokio::test]
    async fn tag_file_native_rejects_path_rejected_without_python_fallback() {
        let dirs = test_dirs();
        let outside = tempfile::tempdir().unwrap();
        let image_path = outside.path().join("outside.png");
        image::RgbImage::new(1, 1).save(&image_path).unwrap();
        let scan_root = fs::canonicalize(&dirs.root).unwrap();
        let state = test_state_ex(
            &dirs,
            json!({"scan_roots": [{"path": scan_root.to_string_lossy()}]}),
            None,
            false,
            PathBuf::from("."),
        )
        .await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (105, ?, 0)")
            .bind(image_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        assert!(matches!(
            tag_file_native_core(&state, 105, false).await,
            TagOutcome::Rejected(_)
        ));
        // A response at all means it did not forward; the wrapper is infallible now.
        let _ = tag_file_native(&state, 105, false).await;
    }

    #[tokio::test]
    async fn widened_gif_rejects_outside_scan_roots_before_transcoding() {
        let requests = Arc::new(AtomicUsize::new(0));
        let request_count = requests.clone();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().route(
                    "/v1/infer/wd",
                    axum::routing::post(move || {
                        let request_count = request_count.clone();
                        async move {
                            request_count.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"data":{"tags":[],"rating":"general","path":"irrelevant","model_id":"irrelevant"}}))
                        }
                    }),
                ),
            )
            .await
            .unwrap();
        });
        let dirs = test_dirs();
        let cache_dir = dirs.root.join("transcode");
        fs::create_dir(&cache_dir).unwrap();
        let outside = tempfile::tempdir().unwrap();
        let outside_gif = outside.path().join("outside.gif");
        image::RgbImage::new(1, 1)
            .save_with_format(&outside_gif, image::ImageFormat::Gif)
            .unwrap();
        let inside_gif = dirs.root.join("inside.gif");
        image::RgbImage::new(1, 1)
            .save_with_format(&inside_gif, image::ImageFormat::Gif)
            .unwrap();
        let root = fs::canonicalize(&dirs.root).unwrap();
        let state = test_state_ex(
            &dirs,
            json!({"scan_roots":[{"path":root.to_string_lossy()}]}),
            Some(crate::infer_client::InferClient::new(
                format!("http://{address}"),
                String::new(),
            )),
            true,
            cache_dir.clone(),
        )
        .await;
        for (id, path) in [(108, &outside_gif), (109, &inside_gif)] {
            sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (?, ?, 0)")
                .bind(id)
                .bind(path.to_string_lossy().to_string())
                .execute(&state.db)
                .await
                .unwrap();
        }

        assert!(matches!(
            tag_file_native_core(&state, 108, false).await,
            TagOutcome::Rejected(_)
        ));
        assert_eq!(requests.load(Ordering::SeqCst), 0);
        assert!(fs::read_dir(&cache_dir).unwrap().next().is_none());
        match tag_file_native_core(&state, 109, false).await {
            TagOutcome::Tagged(_) => {}
            other => panic!("inside widened GIF must reach native transcode: {other:?}"),
        }
        assert_eq!(requests.load(Ordering::SeqCst), 1);
        server.abort();
    }

    #[tokio::test]
    async fn widened_formats_use_native_transcode_and_undecodable_avif_forwards() {
        let requests = Arc::new(AtomicUsize::new(0));
        let request_count = requests.clone();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().route(
                    "/v1/infer/wd",
                    axum::routing::post(move || {
                        let request_count = request_count.clone();
                        async move {
                            request_count.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"data":{"tags":[],"rating":"general","path":"irrelevant","model_id":"irrelevant"}}))
                        }
                    }),
                ),
            )
            .await
            .unwrap();
        });
        let dirs = test_dirs();
        let cache_dir = dirs.root.join("transcode");
        fs::create_dir(&cache_dir).unwrap();
        let root = fs::canonicalize(&dirs.root).unwrap();
        let state = test_state_ex(
            &dirs,
            json!({"scan_roots":[{"path":root.to_string_lossy()}]}),
            Some(crate::infer_client::InferClient::new(
                format!("http://{address}"),
                String::new(),
            )),
            true,
            cache_dir,
        )
        .await;
        for (id, extension, format) in [
            (110, "bmp", image::ImageFormat::Bmp),
            (111, "gif", image::ImageFormat::Gif),
            (112, "tiff", image::ImageFormat::Tiff),
            (113, "tif", image::ImageFormat::Tiff),
        ] {
            let path = dirs.root.join(format!("native.{extension}"));
            image::RgbImage::new(1, 1)
                .save_with_format(&path, format)
                .unwrap();
            sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (?, ?, 0)")
                .bind(id)
                .bind(path.to_string_lossy().to_string())
                .execute(&state.db)
                .await
                .unwrap();
            assert!(matches!(
                tag_file_native_core(&state, id, false).await,
                TagOutcome::Tagged(_)
            ));
        }
        let svg = dirs.root.join("native.svg");
        fs::write(
            &svg,
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>"#,
        )
        .unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (114, ?, 0)")
            .bind(svg.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        assert!(matches!(
            tag_file_native_core(&state, 114, false).await,
            TagOutcome::Tagged(_)
        ));
        // A real AVIF decodes natively via avif-rust and must NOT reach Python.
        let avif_ok = dirs.root.join("native.avif");
        image::RgbImage::from_pixel(8, 8, image::Rgb([200, 120, 40]))
            .save_with_format(&avif_ok, image::ImageFormat::Avif)
            .unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (116, ?, 0)")
            .bind(avif_ok.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        assert!(matches!(
            tag_file_native_core(&state, 116, false).await,
            TagOutcome::Tagged(_)
        ));
        assert_eq!(requests.load(Ordering::SeqCst), 6);

        // An AVIF avif-rust cannot decode is reported, not forwarded: the whole
        // point of v4.659.0 is that no format reaches Python any more.
        let avif = dirs.root.join("undecodable.avif");
        fs::write(&avif, b"not an avif").unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (115, ?, 0)")
            .bind(avif.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        match tag_file_native_core(&state, 115, false).await {
            TagOutcome::Fatal(FatalReason::BackendError(_)) => {}
            other => panic!("undecodable avif must be reported, not forwarded: {other:?}"),
        }
        assert_eq!(requests.load(Ordering::SeqCst), 6);
        server.abort();
    }

    #[tokio::test]
    async fn tag_file_native_returns_typed_error_without_standalone_sidecar() {
        let dirs = test_dirs();
        let image_path = dirs.root.join("standalone.png");
        image::RgbImage::new(1, 1).save(&image_path).unwrap();
        let state = test_state(&dirs, json!({})).await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (106, ?, 0)")
            .bind(image_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        assert!(matches!(
            tag_file_native_core(&state, 106, false).await,
            TagOutcome::Fatal(FatalReason::InferSidecarUnavailable)
        ));
        let response = tag_file_native(&state, 106, false).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(
            json_body(response).await["code"],
            "infer_sidecar_unavailable"
        );
    }

    #[tokio::test]
    async fn retag_single_returns_typed_error_without_standalone_sidecar() {
        let dirs = test_dirs();
        write_profile(
            &dirs
                .root
                .join("extensions/builtin_wd_tagger/core_impl/profiles/a.json"),
            "profile-a",
            "A",
            "model-a",
        );
        let image_path = dirs.root.join("retag-standalone.png");
        image::RgbImage::new(1, 1).save(&image_path).unwrap();
        let state = test_state(&dirs, json!({})).await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (107, ?, 0)")
            .bind(image_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        let response = retag_single(
            State(state),
            None,
            Bytes::from_static(br#"{"file_id":107,"model_id":"profile-a"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(
            json_body(response).await["code"],
            "infer_sidecar_unavailable"
        );
    }

    // 既存のリグレッションテスト(下記 tag_file_native_* 系)は成功/skip/fallback系のみを検証しており、
    // Fatal 3経路(ModelNotDownloaded/BackendError/Unreachable)の応答形状はカバーされていない。
    // 以下2件を追加する。

    #[tokio::test]
    async fn tag_file_native_core_returns_fatal_model_not_downloaded_when_model_absent() {
        // infer_client=None かつ config.infer_standalone=false のとき、wd_infer::call_wd_infer は
        // HTTPモック無しで infer_core::is_model_downloaded(&wd_cache, model_id) を直接チェックし、
        // キャッシュにモデルファイルが無ければ WdInferOutcome::ModelNotDownloaded を返す
        // (wd_infer.rs L112-116)。これを使えばHTTPモックなしでFatal経路をテストできる。
        let dirs = test_dirs();
        let image_path = dirs.root.join("no-model.png");
        image::RgbImage::new(1, 1).save(&image_path).unwrap();
        let real_root = fs::canonicalize(&dirs.root).unwrap();
        let app_config = json!({
            "scan_roots": [{"path": real_root.to_string_lossy()}],
        });
        // infer_client=None, infer_standalone=false, cache_dir配下に該当モデルのファイルを
        // 一切置かない状態を作る(test_dirs()が作るcache/wd_tagger配下は空のまま)。
        let cache_dir = dirs.root.join("cache");
        let state = test_state_ex(&dirs, app_config, None, false, cache_dir).await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (301, ?, 0)")
            .bind(image_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        let outcome = tag_file_native_core(&state, 301, false).await;
        assert!(matches!(
            outcome,
            TagOutcome::Fatal(FatalReason::ModelNotDownloaded)
        ));

        // ラッパーの実際のHTTPレスポンス形状も検証する(wd_tagger.rs 内 fatal_reason_to_response と一致すること)
        let resp = tag_file_native(&state, 301, false).await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
        let body_bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let body: Value = serde_json::from_slice(&body_bytes).unwrap();
        assert_eq!(body["code"], "model_not_available");
    }

    #[test]
    fn fatal_reason_to_response_maps_backend_error_and_unreachable_identically() {
        // 既存実装では BackendError と Unreachable は区別されず
        // 同一の 400 + code:"infer_unavailable" を返す。fatal_reason_to_response は純粋関数なので
        // HTTPモック無しで直接この等価性を検証できる。
        for reason in [
            FatalReason::BackendError("boom".to_string()),
            FatalReason::Unreachable("boom".to_string()),
        ] {
            let resp = fatal_reason_to_response(reason);
            assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
        }
    }

    #[tokio::test]
    async fn tag_file_native_rejects_missing_file() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        let response = tag_file_native(&state, 9999, false).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn tag_file_native_reports_non_image_format_without_forwarding() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        let video_path = dirs.root.join("document.pdf");
        fs::write(&video_path, b"fake").unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (101, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        // The wrapper answers directly now; assert the answer, not its presence.
        let response = tag_file_native(&state, 101, false).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn tag_file_native_performs_no_db_writes_on_fallback() {
        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        let video_path = dirs.root.join("video2.mp4");
        fs::write(&video_path, b"fake").unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (102, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();
        tag_file_native(&state, 102, false).await;
        let count: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM file_wd_tags WHERE file_id = 102")
                .fetch_one(&state.db)
                .await
                .unwrap();
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn tag_video_core_no_longer_forwards_when_strategy_is_scene() {
        let dirs = test_dirs();
        fs::write(
            dirs.root.join("config.json"),
            json!({"video_analysis": {"strategy": "scene"}}).to_string(),
        )
        .unwrap();
        let state = test_state_ex(&dirs, json!({}), None, false, PathBuf::from(".")).await;
        let video_path = dirs.root.join("scene.mp4");
        fs::write(&video_path, b"fake").unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (401, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        // Scene strategy is native as of v4.659.0. The fixture is a fake mp4, so
        // extraction fails and we get `keyframe_error` -- the point of the test
        // is that it is no longer `Fallback`, i.e. nothing reaches Python.
        match tag_file_native_core(&state, 401, false).await {
            TagOutcome::Rejected(body) => assert_eq!(body["code"], "keyframe_error"),
            TagOutcome::Fallback => panic!("scene strategy must not forward to Python"),
            other => panic!("unexpected outcome: {other:?}"),
        }
    }

    #[tokio::test]
    async fn tag_video_core_no_longer_forwards_when_store_per_keyframe_is_true() {
        let dirs = test_dirs();
        fs::write(
            dirs.root.join("config.json"),
            json!({"video_analysis": {"store_per_keyframe": true}}).to_string(),
        )
        .unwrap();
        let state = test_state_ex(&dirs, json!({}), None, false, PathBuf::from(".")).await;
        let video_path = dirs.root.join("per-keyframe.mp4");
        fs::write(&video_path, b"fake").unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (402, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        // Per-keyframe storage is native as of v4.659.0; same reasoning as the
        // scene test above.
        match tag_file_native_core(&state, 402, false).await {
            TagOutcome::Rejected(body) => assert_eq!(body["code"], "keyframe_error"),
            TagOutcome::Fallback => panic!("per-keyframe storage must not forward to Python"),
            other => panic!("unexpected outcome: {other:?}"),
        }
    }

    #[tokio::test]
    async fn tag_video_core_extracts_frames_tags_and_merges_via_real_ffmpeg() {
        if !crate::routes::video_analysis::check_ffmpeg() {
            return;
        }

        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            // Restricted CI sandboxes may prohibit loopback listeners.
            return;
        };
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(
                listener,
                axum::Router::new().route(
                    "/v1/infer/wd",
                    axum::routing::post(|| async {
                        Json(json!({
                            "data": {
                                "tags": [{"tag": "1girl", "confidence": 0.9, "category": "general"}],
                                "rating": "general",
                                "path": "irrelevant",
                                "model_id": "irrelevant",
                            }
                        }))
                    }),
                ),
            )
            .await
            .unwrap()
        });

        let dirs = test_dirs();
        let video_path = dirs.root.join("real.mp4");
        let status = tokio::process::Command::new("ffmpeg")
            .args(["-f", "lavfi", "-i", "color=c=blue:s=64x64:d=2", "-y"])
            .arg(&video_path)
            .status()
            .await
            .unwrap();
        assert!(status.success());

        let real_root = fs::canonicalize(&dirs.root).unwrap();
        let app_config = json!({
            "scan_roots": [{"path": real_root.to_string_lossy()}],
        });
        let infer_client =
            crate::infer_client::InferClient::new(format!("http://{address}"), String::new());
        let state = test_state_ex(
            &dirs,
            app_config,
            Some(infer_client),
            true,
            PathBuf::from("."),
        )
        .await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (403, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        let outcome = tag_file_native_core(&state, 403, false).await;
        match outcome {
            TagOutcome::Tagged(v) => {
                assert!(v["tag_count"].as_i64().unwrap_or(0) > 0);
                assert_eq!(v["xmp_written"], json!(false));
                let tags = v["tags"].as_array().expect("tags must be an array");
                assert!(tags
                    .iter()
                    .any(|tag| tag.get("tag").and_then(Value::as_str) == Some("1girl")));
            }
            other => panic!("expected Tagged, got {other:?}"),
        }
        server.abort();
    }

    #[tokio::test]
    async fn tag_video_core_returns_keyframe_error_when_extraction_yields_zero_frames() {
        if !crate::routes::video_analysis::check_ffmpeg() {
            return;
        }

        let dirs = test_dirs();
        let state = test_state_ex(&dirs, json!({}), None, false, PathBuf::from(".")).await;
        let video_path = dirs.root.join("corrupt.mp4");
        fs::write(
            &video_path,
            b"this is not a real video file, just garbage bytes",
        )
        .unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (404, ?, 0)")
            .bind(video_path.to_string_lossy().to_string())
            .execute(&state.db)
            .await
            .unwrap();

        let outcome = tag_file_native_core(&state, 404, false).await;
        assert!(matches!(
            outcome,
            TagOutcome::Rejected(ref body)
                if body.get("code").and_then(|code| code.as_str()) == Some("keyframe_error")
        ));

        let response = tag_file_native(&state, 404, false).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }
}

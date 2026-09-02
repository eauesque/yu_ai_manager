use axum::{
    body::Bytes,
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use meta_extract::{is_a1111_source, is_comfy_source, is_nai_source};
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    ext_config,
    state::SharedState,
};

const SCHEMA: &str = "yu://recipe/1";
const MAX_BODY_BYTES: usize = 4 * 1024 * 1024; // 4 MB
const MAX_IMPORT_BATCH: usize = 100;
const MAX_EXPORT_BATCH: usize = 500;

fn meta_source_to_bridge_id(meta_source: &str) -> Option<&'static str> {
    if is_nai_source(meta_source) {
        return Some("nai");
    }
    if is_a1111_source(meta_source) || meta_source == "tensor_art" {
        return Some("sd-webui");
    }
    if is_comfy_source(meta_source) {
        return Some("comfyui");
    }
    None
}

fn normalize_parameters(
    params: &serde_json::Map<String, Value>,
) -> (serde_json::Map<String, Value>, Vec<String>) {
    let mut fields = serde_json::Map::new();
    let mut warnings = Vec::new();
    for (key, val) in params {
        match key.as_str() {
            "CFG scale" | "scale" => {
                if let Some(f) = val.as_f64() {
                    fields.insert("cfg".into(), json!(f));
                } else if let Some(s) = val.as_str() {
                    if let Ok(f) = s.parse::<f64>() {
                        fields.insert("cfg".into(), json!(f));
                    } else {
                        warnings.push(key.clone());
                    }
                } else {
                    warnings.push(key.clone());
                }
            }
            "Size" => {
                if let Some(s) = val.as_str() {
                    if let Some((w, h)) = s.split_once('x') {
                        match (w.parse::<i64>(), h.parse::<i64>()) {
                            (Ok(w), Ok(h)) => {
                                fields.insert("width".into(), json!(w));
                                fields.insert("height".into(), json!(h));
                            }
                            _ => warnings.push(key.clone()),
                        }
                    } else {
                        warnings.push(key.clone());
                    }
                } else {
                    warnings.push(key.clone());
                }
            }
            "Seed" => {
                if let Some(n) = val.as_i64() {
                    fields.insert("seed".into(), json!(n));
                } else if let Some(s) = val.as_str() {
                    if let Ok(n) = s.parse::<i64>() {
                        fields.insert("seed".into(), json!(n));
                    } else {
                        warnings.push(key.clone());
                    }
                } else {
                    warnings.push(key.clone());
                }
            }
            "Steps" => {
                if let Some(n) = val.as_i64() {
                    fields.insert("steps".into(), json!(n));
                } else if let Some(s) = val.as_str() {
                    if let Ok(n) = s.parse::<i64>() {
                        fields.insert("steps".into(), json!(n));
                    } else {
                        warnings.push(key.clone());
                    }
                } else {
                    warnings.push(key.clone());
                }
            }
            "Sampler" => {
                if let Some(s) = val.as_str() {
                    fields.insert("sampler".into(), json!(s));
                }
            }
            "Model" | "model_name" => {
                if let Some(s) = val.as_str() {
                    fields.insert("model".into(), json!(s));
                }
            }
            _ => warnings.push(key.clone()),
        }
    }
    (fields, warnings)
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn fwd_post(state: &SharedState, path: &str, body: Bytes) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "unavailable"})),
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
        Ok(r) => {
            let s = r.status();
            r.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |b| (s, b).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

// ---------------------------------------------------------------------------
// Response shaping. Mirrors `core/infra_core/api_errors.py::api_result`.
// ---------------------------------------------------------------------------

/// `api_error(message, status)` — no `code`/`detail`/`hint`/`extra` used by
/// these routes, so the body is always `{"ok": false, "error": message}`.
fn api_error(message: impl Into<String>, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message.into()}))).into_response()
}

/// `api_result(payload, status)` for a **dict** payload at `status < 400`:
/// `api_success(payload, status, data=payload.get("data"))` — the payload's
/// own `data` key (usually absent -> null) seeds the envelope, then the
/// payload's keys are spread on top (`body.update(payload)`).
fn api_success_dict(payload: Value, status: StatusCode) -> Response {
    let mut body = serde_json::Map::new();
    body.insert("ok".into(), json!(true));
    body.insert("error".into(), Value::Null);
    let data_val = payload.get("data").cloned().unwrap_or(Value::Null);
    body.insert("data".into(), data_val);
    if let Value::Object(map) = payload {
        body.extend(map);
    }
    (status, Json(Value::Object(body))).into_response()
}

/// `api_result(payload, status)` for a **non-dict** payload (e.g. a list):
/// `api_success(status=status, data=payload)` — no spreading.
fn api_success_data(data: Value, status: StatusCode) -> Response {
    (
        status,
        Json(json!({"ok": true, "error": null, "data": data})),
    )
        .into_response()
}

/// Matches the body Python's global `@app.errorhandler(Exception)` sends for
/// `/api/*` on an unhandled exception (`core/web/error_handlers.py:178-199`,
/// English locale: `_ERROR_I18N["en"]["internal_error"]`). DB errors in
/// `build_recipe`/`fill_recipe` are not caught anywhere in the Python route
/// bodies, so they surface through this handler as a 500.
fn internal_server_error() -> Response {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({
            "ok": false,
            "error": "Internal server error",
            "code": "internal_error",
        })),
    )
        .into_response()
}

/// Python `repr()` of a string: single-quoted unless the string contains a
/// single quote and no double quote, in which case double quotes are used.
fn python_repr_str(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// `{value!r}` for the `schema` field pulled out of a JSON body with
/// `data.get("schema", "")` (Python default is the empty string).
fn schema_repr(value: Option<&Value>) -> String {
    match value {
        None => python_repr_str(""),
        Some(Value::String(s)) => python_repr_str(s),
        Some(Value::Null) => "None".to_string(),
        Some(Value::Bool(true)) => "True".to_string(),
        Some(Value::Bool(false)) => "False".to_string(),
        Some(other) => other.to_string(),
    }
}

fn schema_matches(value: Option<&Value>) -> bool {
    matches!(value, Some(Value::String(s)) if s == SCHEMA)
}

/// Python truthiness (`bool(x)`), used for `_is_extension_enabled`'s
/// `bool(enabled)` and `fill_recipe`'s `if sampler:` / `if scheduler:` checks.
fn python_truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(true),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// `int(fid)` for a single `file_ids` element. Numbers truncate toward zero
/// (matching Python's `int(float)`), bools become 0/1, numeric strings parse
/// (leading/trailing whitespace trimmed, as Python's `int(str)` does), and
/// anything else (null, array, object, non-numeric string) is `None` —
/// matching the `(TypeError, ValueError)` catch in `routes/recipe.py`.
fn json_value_to_i64(v: &Value) -> Option<i64> {
    match v {
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Some(i)
            } else if let Some(u) = n.as_u64() {
                i64::try_from(u).ok()
            } else {
                n.as_f64().map(|f| crate::num::sat_i64(f.trunc()))
            }
        }
        Value::Bool(b) => Some(i64::from(*b)),
        Value::String(s) => s.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn generate_url_for(bridge_id: &str) -> Option<&'static str> {
    match bridge_id {
        "nai" => Some("/ext/nai-bridge/api/generate"),
        "sd-webui" => Some("/ext/sd-webui/api/generate"),
        "comfyui" => Some("/ext/comfyui-bridge/api/generate"),
        _ => None,
    }
}

fn extension_name_for(bridge_id: &str) -> Option<&'static str> {
    match bridge_id {
        "nai" => Some("builtin-nai-bridge"),
        "sd-webui" => Some("builtin-sd-webui-bridge"),
        "comfyui" => Some("builtin-comfyui-bridge"),
        _ => None,
    }
}

/// Ported from `core/recipe_api/bridge_fill.py::_is_extension_enabled`.
/// `None` (config key not set) means "enabled" (`unwrap_or(true)`,
/// `ext_config.rs:74`), matching the Python comment at `bridge_fill.py:27-28`.
fn is_extension_enabled(state: &SharedState, bridge_id: &str) -> bool {
    let Some(ext_name) = extension_name_for(bridge_id) else {
        return false;
    };
    let config = ext_config::read_config(&state.config.config_path).unwrap_or_else(|_| json!({}));
    match ext_config::extension_value(&config, ext_name, "enabled") {
        Some(v) => python_truthy(&v),
        None => true,
    }
}

/// Insert `value` under `key` only if present and non-null, mirroring
/// Python's `if x is not None: body[key] = x` guards in `fill_recipe`.
fn insert_present(map: &mut serde_json::Map<String, Value>, key: &str, value: Option<&Value>) {
    if let Some(v) = value {
        if !v.is_null() {
            map.insert(key.to_string(), v.clone());
        }
    }
}

/// Ported from `core/recipe_api/bridge_fill.py::fill_recipe`. Returns `Err`
/// with the Python `ValueError` message for the two callers to turn into a
/// 422 (single import) or an `invalid_recipe: {exc}` batch entry.
fn fill_recipe(state: &SharedState, recipe: &Value) -> Result<Value, String> {
    let schema = recipe.get("schema");
    if !schema_matches(schema) {
        return Err(format!("unsupported schema: {}", schema_repr(schema)));
    }

    let bridge_id_str = recipe
        .get("bridge_id")
        .and_then(Value::as_str)
        .unwrap_or("");
    if bridge_id_str.is_empty() {
        return Err("recipe is missing bridge_id".to_string());
    }
    let Some(generate_url) = generate_url_for(bridge_id_str) else {
        return Err(format!(
            "unknown bridge_id: {}",
            python_repr_str(bridge_id_str)
        ));
    };
    let bridge_id = bridge_id_str;

    if !is_extension_enabled(state, bridge_id) {
        // tensor_art and other content warnings are intentionally omitted
        // when the extension is disabled — the caller cannot generate anyway.
        return Ok(json!({
            "bridge_id": bridge_id,
            "generate_url": Value::Null,
            "generate_body": Value::Null,
            "import_warnings": ["extension_disabled"],
        }));
    }

    let mut import_warnings: Vec<String> = Vec::new();

    let positive = recipe.get("positive").cloned().unwrap_or(json!(""));
    let negative = recipe.get("negative").cloned().unwrap_or(json!(""));
    let sampler = recipe.get("sampler").cloned().unwrap_or(json!(""));
    let model = recipe.get("model").cloned().unwrap_or(json!(""));
    let meta_source = recipe
        .get("_meta_source")
        .and_then(Value::as_str)
        .unwrap_or("");

    if meta_source == "tensor_art" {
        import_warnings.push("model_likely_unavailable_locally".to_string());
    }

    let mut body = serde_json::Map::new();
    match bridge_id {
        "nai" => {
            body.insert("prompt".into(), positive);
            body.insert("negative_prompt".into(), negative);
            body.insert("model".into(), model);
            insert_present(&mut body, "seed", recipe.get("seed"));
            insert_present(&mut body, "steps", recipe.get("steps"));
            insert_present(&mut body, "scale", recipe.get("cfg"));
            if python_truthy(&sampler) {
                body.insert("sampler".into(), sampler);
            }
            insert_present(&mut body, "width", recipe.get("width"));
            insert_present(&mut body, "height", recipe.get("height"));
        }
        "sd-webui" => {
            body.insert("prompt".into(), positive);
            body.insert("negative_prompt".into(), negative);
            insert_present(&mut body, "seed", recipe.get("seed"));
            insert_present(&mut body, "steps", recipe.get("steps"));
            insert_present(&mut body, "cfg_scale", recipe.get("cfg"));
            if python_truthy(&sampler) {
                body.insert("sampler_name".into(), sampler);
            }
            insert_present(&mut body, "width", recipe.get("width"));
            insert_present(&mut body, "height", recipe.get("height"));
            import_warnings.push("model_switch_required".to_string());
        }
        "comfyui" => {
            body.insert("prompt".into(), positive);
            body.insert("negative_prompt".into(), negative);
            insert_present(&mut body, "seed", recipe.get("seed"));
            insert_present(&mut body, "steps", recipe.get("steps"));
            insert_present(&mut body, "cfg", recipe.get("cfg"));
            if python_truthy(&sampler) {
                body.insert("sampler_name".into(), sampler);
            }
            let scheduler = recipe.get("scheduler").cloned().unwrap_or(Value::Null);
            if python_truthy(&scheduler) {
                body.insert("scheduler".into(), scheduler);
            }
            import_warnings.push("model_switch_unsupported".to_string());
        }
        // `generate_url_for` above already rejected anything else, so this arm
        // is dead -- but it is dead by a check twenty lines up, not by the type
        // system, and the function can say so without panicking in a handler.
        _ => return Err(format!("unsupported bridge_id: {bridge_id}")),
    }

    Ok(json!({
        "bridge_id": bridge_id,
        "generate_url": generate_url,
        "generate_body": Value::Object(body),
        "import_warnings": import_warnings,
    }))
}

/// Ported from `core/recipe_api/recipe_payload.py::build_recipe`, shared by
/// the single-file export route and the export-batch route so the recipe
/// shape is defined exactly once. `Ok(None)` means "no gen metadata" (the
/// file is missing/deleted, or its `meta_source` doesn't map to a bridge);
/// `Err` is a DB failure, which Python never catches -- it propagates to the
/// global exception handler as a 500, so callers must not count it as
/// "skipped".
async fn fetch_recipe(state: &SharedState, file_id: i64) -> Result<Option<Value>, Response> {
    let row = sqlx::query(
        "SELECT f.meta_source, tm.raw_prompt, tm.raw_negative, tm.raw_meta_json, tm.model_name, tm.model_hash \
         FROM files f \
         LEFT JOIN templates tm ON tm.file_id = f.id \
         WHERE f.id = ? AND f.is_deleted = 0",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    .map_err(|e| {
        tracing::error!("recipe fetch db error: {e}");
        internal_server_error()
    })?;

    let Some(row) = row else {
        return Ok(None);
    };

    let meta_source: Option<String> = row.try_get("meta_source").ok().flatten();
    let Some(bridge_id) = meta_source.as_deref().and_then(meta_source_to_bridge_id) else {
        return Ok(None);
    };

    let raw_prompt: Option<String> = row.try_get("raw_prompt").ok().flatten();
    let raw_negative: Option<String> = row.try_get("raw_negative").ok().flatten();
    let model_name: Option<String> = row.try_get("model_name").ok().flatten();
    let model_hash: Option<String> = row.try_get("model_hash").ok().flatten();
    let raw_meta_json: Option<String> = row.try_get("raw_meta_json").ok().flatten();

    let mut recipe = serde_json::Map::new();
    recipe.insert("schema".into(), json!(SCHEMA));
    recipe.insert("bridge_id".into(), json!(bridge_id));
    recipe.insert("positive".into(), json!(raw_prompt.unwrap_or_default()));
    recipe.insert("negative".into(), json!(raw_negative.unwrap_or_default()));

    let mut capture_warnings: Vec<String> = Vec::new();

    if let Some(name) = model_name {
        recipe.insert("model".into(), json!(name));
    }
    if bridge_id != "nai" {
        if let Some(hash) = model_hash {
            recipe.insert("model_hash".into(), json!(hash));
        }
    }

    if let Some(raw) = raw_meta_json {
        match serde_json::from_str::<Value>(&raw) {
            Ok(meta) => {
                if let Some(params) = meta.get("parameters").and_then(|p| p.as_object()) {
                    let (fields, warns) = normalize_parameters(params);
                    recipe.extend(fields);
                    capture_warnings.extend(warns);
                }
            }
            Err(_) => capture_warnings.push("parse_error".into()),
        }
    }

    recipe.insert("capture_warnings".into(), json!(capture_warnings));
    Ok(Some(Value::Object(recipe)))
}

/// GET /api/recipe/export/<file_id> — admin scope required.
///
/// Ported from `routes/recipe.py::api_recipe_export`. Previously this
/// handler returned `Json(...).into_response()` for both the "no metadata"
/// and "database error" cases, which is always HTTP 200 -- Python returns
/// 404 (`api_error("no gen metadata for this file", 404)`) and, on a DB
/// exception, 500 via the global handler. Fixed here as part of the
/// `/api/recipe/import*` + `/api/recipe/export/batch` port so the shared
/// `fetch_recipe` helper has one true status mapping.
pub async fn recipe_export(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    match fetch_recipe(&state, file_id).await {
        Ok(Some(recipe)) => api_success_dict(recipe, StatusCode::OK),
        Ok(None) => api_error("no gen metadata for this file", StatusCode::NOT_FOUND),
        Err(response) => response,
    }
}

/// POST /api/recipe/export/batch — admin scope required.
///
/// Ported from `routes/recipe.py::api_recipe_export_batch`. `skipped` only
/// counts `fetch_recipe` returning `None` (no gen metadata); a DB error
/// aborts the whole batch with a 500, matching Python's unhandled-exception
/// propagation (build_recipe never catches its own DB errors).
pub async fn recipe_export_batch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    if body.len() > MAX_BODY_BYTES {
        return api_error("payload too large", StatusCode::PAYLOAD_TOO_LARGE);
    }

    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => return api_error("invalid JSON", StatusCode::BAD_REQUEST),
    };

    let Some(file_ids_raw) = data.as_object().and_then(|m| m.get("file_ids")) else {
        return api_error(r#"expected {"file_ids": [...]}"#, StatusCode::BAD_REQUEST);
    };
    let Value::Array(raw_ids) = file_ids_raw else {
        return api_error("file_ids must be an array", StatusCode::BAD_REQUEST);
    };
    if raw_ids.len() > MAX_EXPORT_BATCH {
        return api_error(
            format!("too many IDs (max {MAX_EXPORT_BATCH})"),
            StatusCode::BAD_REQUEST,
        );
    }

    let mut file_ids = Vec::with_capacity(raw_ids.len());
    for raw in raw_ids {
        match json_value_to_i64(raw) {
            Some(id) => file_ids.push(id),
            None => return api_error("file_ids must be integers", StatusCode::BAD_REQUEST),
        }
    }

    let mut recipes = Vec::with_capacity(file_ids.len());
    let mut skipped: i64 = 0;
    for fid in file_ids {
        match fetch_recipe(&state, fid).await {
            Ok(Some(recipe)) => recipes.push(recipe),
            Ok(None) => skipped += 1,
            Err(response) => return response,
        }
    }

    api_success_dict(
        json!({"recipes": recipes, "skipped": skipped}),
        StatusCode::OK,
    )
}

/// POST /api/recipe/import — admin scope required.
///
/// Ported from `routes/recipe.py::api_recipe_import` +
/// `core/recipe_api/bridge_fill.py::fill_recipe`. The Rust handler
/// previously returned an unconditional 501 while `fwd_post` above sat
/// unused; `python_url` is empty by default (and forced empty in
/// standalone, `main.rs:771-775`), so forwarding could never have served
/// this route.
pub async fn recipe_import(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    if body.len() > MAX_BODY_BYTES {
        return api_error(
            "payload too large (max 4 MB)",
            StatusCode::PAYLOAD_TOO_LARGE,
        );
    }

    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => return api_error("invalid JSON", StatusCode::BAD_REQUEST),
    };
    let Value::Object(_) = &data else {
        return api_error("expected a recipe object", StatusCode::BAD_REQUEST);
    };

    let schema = data.get("schema");
    if !schema_matches(schema) {
        return api_error(
            format!("unsupported schema: {}", schema_repr(schema)),
            StatusCode::UNPROCESSABLE_ENTITY,
        );
    }

    match fill_recipe(&state, &data) {
        Ok(result) => api_success_dict(result, StatusCode::OK),
        Err(message) => api_error(message, StatusCode::UNPROCESSABLE_ENTITY),
    }
}

/// POST /api/recipe/import/batch — admin scope required.
///
/// Ported from `routes/recipe.py::api_recipe_import_batch`. Each element is
/// resolved independently -- a bad element never aborts the batch, its
/// failure is recorded in that element's `import_warnings` instead
/// (`invalid_schema` for a schema mismatch, `invalid_recipe: {exc}` for a
/// `fill_recipe` `ValueError`).
pub async fn recipe_import_batch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth.as_ref()) {
        return r;
    }
    if body.len() > MAX_BODY_BYTES {
        return api_error(
            "payload too large (max 4 MB)",
            StatusCode::PAYLOAD_TOO_LARGE,
        );
    }

    let data: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => return api_error("invalid JSON", StatusCode::BAD_REQUEST),
    };
    let Value::Array(items) = &data else {
        return api_error("expected a JSON array", StatusCode::BAD_REQUEST);
    };
    if items.len() > MAX_IMPORT_BATCH {
        return api_error(
            format!("too many recipes (max {MAX_IMPORT_BATCH})"),
            StatusCode::BAD_REQUEST,
        );
    }

    let mut results = Vec::with_capacity(items.len());
    for item in items {
        let is_obj = item.is_object();
        let schema_ok = is_obj && schema_matches(item.get("schema"));
        if !schema_ok {
            let bridge_id = if is_obj {
                item.get("bridge_id").cloned().unwrap_or(Value::Null)
            } else {
                Value::Null
            };
            results.push(json!({
                "bridge_id": bridge_id,
                "generate_url": Value::Null,
                "generate_body": Value::Null,
                "import_warnings": ["invalid_schema"],
            }));
            continue;
        }

        match fill_recipe(&state, item) {
            Ok(result) => results.push(result),
            Err(exc) => {
                let bridge_id = item.get("bridge_id").cloned().unwrap_or(Value::Null);
                results.push(json!({
                    "bridge_id": bridge_id,
                    "generate_url": Value::Null,
                    "generate_body": Value::Null,
                    "import_warnings": [format!("invalid_recipe: {exc}")],
                }));
            }
        }
    }

    api_success_data(Value::Array(results), StatusCode::OK)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    async fn test_state(config_body: &str) -> (SharedState, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        std::fs::write(&config_path, config_body).unwrap();

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               meta_source TEXT,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );
             CREATE TABLE templates (
               file_id INTEGER,
               raw_prompt TEXT,
               raw_negative TEXT,
               raw_meta_json TEXT,
               model_name TEXT,
               model_hash TEXT
             );
             INSERT INTO files(id, meta_source, is_deleted) VALUES
               (1, 'novelai_v4_png', 0),
               (2, 'a1111_png', 0),
               (3, 'comfyui', 0),
               (4, 'unknown_source', 0),
               (5, 'novelai_v4_png', 1);
             INSERT INTO templates(file_id, raw_prompt, raw_negative, raw_meta_json, model_name, model_hash) VALUES
               (1, 'positive one', 'negative one', NULL, 'nai-diffusion-4', 'hash-nai'),
               (2, 'positive two', 'negative two', NULL, 'sd15', 'hash-sd'),
               (3, 'positive three', 'negative three', NULL, 'sdxl', 'hash-sdxl');",
        )
        .execute(&pool)
        .await
        .unwrap();

        let state = Arc::new(
            AppState::new(
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
                    config_path,
                    project_root: dir.path().to_path_buf(),
                    app_config: json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        );
        (state, dir)
    }

    async fn json_body(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    fn nai_recipe() -> Value {
        json!({
            "schema": SCHEMA,
            "bridge_id": "nai",
            "positive": "a cat",
            "negative": "blurry",
            "seed": 123,
            "steps": 28,
            "cfg": 5.0,
            "sampler": "k_euler",
            "width": 832,
            "height": 1216,
            "model": "nai-diffusion-4",
        })
    }

    // ---- fetch_recipe / recipe_export -------------------------------------

    #[tokio::test]
    async fn recipe_export_returns_recipe_for_nai_source() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_export(State(state), None, Path(1)).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["ok"], true);
        assert_eq!(body["bridge_id"], "nai");
        assert_eq!(body["positive"], "positive one");
        assert_eq!(body["schema"], SCHEMA);
        // nai never carries model_hash in the recipe.
        assert!(body.get("model_hash").is_none());
    }

    #[tokio::test]
    async fn recipe_export_404_when_file_missing() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_export(State(state), None, Path(999)).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let body = json_body(response).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "no gen metadata for this file");
    }

    #[tokio::test]
    async fn recipe_export_404_when_meta_source_unmapped() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_export(State(state), None, Path(4)).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let body = json_body(response).await;
        assert_eq!(body["error"], "no gen metadata for this file");
    }

    #[tokio::test]
    async fn recipe_export_404_when_file_soft_deleted() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_export(State(state), None, Path(5)).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn recipe_export_500_on_db_error() {
        let (state, _dir) = test_state("{}").await;
        // Drop the templates table so the join fails at query time.
        sqlx::raw_sql("DROP TABLE templates;")
            .execute(&state.db_read)
            .await
            .unwrap();
        let response = recipe_export(State(state), None, Path(1)).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let body = json_body(response).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Internal server error");
        assert_eq!(body["code"], "internal_error");
    }

    // ---- recipe_export_batch ------------------------------------------------

    #[tokio::test]
    async fn export_batch_returns_recipes_in_input_order_and_counts_skipped() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_export_batch(
            State(state),
            None,
            Bytes::from(r#"{"file_ids": [3, 999, 1]}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["skipped"], 1);
        assert_eq!(body["recipes"].as_array().unwrap().len(), 2);
        // Order follows the input file_ids: 3 then 1 (999 skipped).
        assert_eq!(body["recipes"][0]["bridge_id"], "comfyui");
        assert_eq!(body["recipes"][1]["bridge_id"], "nai");
        // Envelope uses `recipes`, not `data`, at top level (data stays null).
        assert_eq!(body["data"], serde_json::Value::Null);
    }

    #[tokio::test]
    async fn export_batch_requires_file_ids_key() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_export_batch(State(state), None, Bytes::from(r#"{}"#)).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body["error"], r#"expected {"file_ids": [...]}"#);
    }

    #[tokio::test]
    async fn export_batch_rejects_non_array_file_ids() {
        let (state, _dir) = test_state("{}").await;
        let response =
            recipe_export_batch(State(state), None, Bytes::from(r#"{"file_ids": "1"}"#)).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body["error"], "file_ids must be an array");
    }

    #[tokio::test]
    async fn export_batch_rejects_non_integer_ids() {
        let (state, _dir) = test_state("{}").await;
        let response =
            recipe_export_batch(State(state), None, Bytes::from(r#"{"file_ids": [1, "x"]}"#)).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body["error"], "file_ids must be integers");
    }

    #[tokio::test]
    async fn export_batch_boundary_500_ids_ok_501_rejected() {
        let (state, _dir) = test_state("{}").await;
        let ids_500: Vec<i64> = (1..=500).collect();
        let response = recipe_export_batch(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&json!({"file_ids": ids_500})).unwrap()),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "500 ids must be accepted"
        );

        let (state, _dir) = test_state("{}").await;
        let ids_501: Vec<i64> = (1..=501).collect();
        let response = recipe_export_batch(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&json!({"file_ids": ids_501})).unwrap()),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::BAD_REQUEST,
            "501 ids must be rejected"
        );
        let body = json_body(response).await;
        assert_eq!(body["error"], "too many IDs (max 500)");
    }

    #[tokio::test]
    async fn export_batch_413_over_4mb() {
        let (state, _dir) = test_state("{}").await;
        let oversized = vec![b'x'; 4 * 1024 * 1024 + 1];
        let response = recipe_export_batch(State(state), None, Bytes::from(oversized)).await;
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        let body = json_body(response).await;
        assert_eq!(body["error"], "payload too large");
    }

    #[tokio::test]
    async fn export_batch_db_error_aborts_without_counting_as_skipped() {
        let (state, _dir) = test_state("{}").await;
        sqlx::raw_sql("DROP TABLE templates;")
            .execute(&state.db_read)
            .await
            .unwrap();
        let response =
            recipe_export_batch(State(state), None, Bytes::from(r#"{"file_ids": [1, 999]}"#)).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let body = json_body(response).await;
        assert_eq!(body["error"], "Internal server error");
    }

    // ---- recipe_import --------------------------------------------------

    #[tokio::test]
    async fn import_fills_nai_generate_body() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&nai_recipe()).unwrap()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["bridge_id"], "nai");
        assert_eq!(body["generate_url"], "/ext/nai-bridge/api/generate");
        assert_eq!(body["generate_body"]["prompt"], "a cat");
        assert_eq!(body["generate_body"]["scale"], 5.0);
        assert_eq!(body["import_warnings"], json!([]));
        assert_eq!(body["data"], serde_json::Value::Null);
    }

    /// The whole point of `fill_recipe` is the per-bridge key mapping, but only
    /// the `nai` branch was pinned. Verified 2026-08-13 by deleting
    /// `import_warnings.push("model_switch_required")` from the `sd-webui`
    /// branch: all 28 tests stayed green. These three tests close that gap —
    /// each bridge renames `cfg`/`sampler` differently and appends its own
    /// warning (`bridge_fill.py:89-117`).
    #[tokio::test]
    async fn import_fills_sd_webui_generate_body_with_its_own_key_names() {
        let (state, _dir) = test_state("{}").await;
        let mut recipe = nai_recipe();
        recipe["bridge_id"] = json!("sd-webui");
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&recipe).unwrap()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["bridge_id"], "sd-webui");
        assert_eq!(body["generate_url"], "/ext/sd-webui/api/generate");
        // `cfg` -> `cfg_scale`, `sampler` -> `sampler_name` (bridge_fill.py:96,98)
        assert_eq!(body["generate_body"]["cfg_scale"], 5.0);
        assert_eq!(body["generate_body"]["sampler_name"], "k_euler");
        assert_eq!(body["generate_body"]["width"], 832);
        assert!(
            body["generate_body"]["scale"].is_null(),
            "nai key must not leak"
        );
        assert_eq!(body["import_warnings"], json!(["model_switch_required"]));
    }

    #[tokio::test]
    async fn import_fills_comfyui_generate_body_and_keeps_scheduler() {
        let (state, _dir) = test_state("{}").await;
        let mut recipe = nai_recipe();
        recipe["bridge_id"] = json!("comfyui");
        recipe["scheduler"] = json!("karras");
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&recipe).unwrap()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["bridge_id"], "comfyui");
        assert_eq!(body["generate_url"], "/ext/comfyui-bridge/api/generate");
        // comfyui keeps `cfg` as-is and is the only bridge carrying `scheduler`
        // (bridge_fill.py:112,116). It also drops width/height entirely.
        assert_eq!(body["generate_body"]["cfg"], 5.0);
        assert_eq!(body["generate_body"]["sampler_name"], "k_euler");
        assert_eq!(body["generate_body"]["scheduler"], "karras");
        assert!(
            body["generate_body"]["width"].is_null(),
            "comfyui body carries no width/height"
        );
        assert_eq!(body["import_warnings"], json!(["model_switch_unsupported"]));
    }

    /// `_meta_source == "tensor_art"` adds its warning *before* the per-bridge
    /// one, so order matters (`bridge_fill.py:71-72` runs ahead of the match).
    #[tokio::test]
    async fn import_tensor_art_source_warns_before_the_bridge_warning() {
        let (state, _dir) = test_state("{}").await;
        let mut recipe = nai_recipe();
        recipe["bridge_id"] = json!("sd-webui");
        recipe["_meta_source"] = json!("tensor_art");
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&recipe).unwrap()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(
            body["import_warnings"],
            json!(["model_likely_unavailable_locally", "model_switch_required"])
        );
    }

    #[tokio::test]
    async fn import_disabled_extension_yields_null_generate_fields() {
        let config = json!({"extensions": {"builtin-nai-bridge": {"enabled": false}}});
        let (state, _dir) = test_state(&config.to_string()).await;
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&nai_recipe()).unwrap()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["generate_url"], serde_json::Value::Null);
        assert_eq!(body["generate_body"], serde_json::Value::Null);
        assert_eq!(body["import_warnings"], json!(["extension_disabled"]));
    }

    #[tokio::test]
    async fn import_unset_extension_config_defaults_to_enabled() {
        // No "extensions" key at all -> _is_extension_enabled must default true.
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&nai_recipe()).unwrap()),
        )
        .await;
        let body = json_body(response).await;
        assert_eq!(body["generate_url"], "/ext/nai-bridge/api/generate");
    }

    #[tokio::test]
    async fn import_invalid_json_400() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(State(state), None, Bytes::from("not json")).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body["error"], "invalid JSON");
    }

    #[tokio::test]
    async fn import_non_object_body_400() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(State(state), None, Bytes::from("[1,2,3]")).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body["error"], "expected a recipe object");
    }

    #[tokio::test]
    async fn import_unsupported_schema_422_with_python_repr_quoting() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(r#"{"schema": "yu://recipe/0"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let body = json_body(response).await;
        assert_eq!(body["error"], "unsupported schema: 'yu://recipe/0'");
    }

    #[tokio::test]
    async fn import_missing_schema_422_uses_empty_string_repr() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(State(state), None, Bytes::from(r#"{}"#)).await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let body = json_body(response).await;
        assert_eq!(body["error"], "unsupported schema: ''");
    }

    #[tokio::test]
    async fn import_missing_bridge_id_422() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(format!(r#"{{"schema": "{SCHEMA}"}}"#)),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let body = json_body(response).await;
        assert_eq!(body["error"], "recipe is missing bridge_id");
    }

    #[tokio::test]
    async fn import_unknown_bridge_id_422() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import(
            State(state),
            None,
            Bytes::from(format!(r#"{{"schema": "{SCHEMA}", "bridge_id": "foo"}}"#)),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let body = json_body(response).await;
        assert_eq!(body["error"], "unknown bridge_id: 'foo'");
    }

    #[tokio::test]
    async fn import_413_over_4mb() {
        let (state, _dir) = test_state("{}").await;
        let oversized = vec![b'x'; 4 * 1024 * 1024 + 1];
        let response = recipe_import(State(state), None, Bytes::from(oversized)).await;
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        let body = json_body(response).await;
        assert_eq!(body["error"], "payload too large (max 4 MB)");
    }

    // ---- recipe_import_batch ---------------------------------------------

    #[tokio::test]
    async fn import_batch_processes_each_element_independently() {
        let (state, _dir) = test_state("{}").await;
        let payload = json!([
            nai_recipe(),
            {"schema": "wrong", "bridge_id": "nai"},
            {"schema": SCHEMA, "bridge_id": "unknown-bridge"},
            "not an object",
        ]);
        let response = recipe_import_batch(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&payload).unwrap()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        let data = body["data"].as_array().unwrap();
        assert_eq!(data.len(), 4);

        assert_eq!(data[0]["bridge_id"], "nai");
        assert_eq!(data[0]["generate_url"], "/ext/nai-bridge/api/generate");

        assert_eq!(data[1]["bridge_id"], "nai");
        assert_eq!(data[1]["generate_url"], serde_json::Value::Null);
        assert_eq!(data[1]["import_warnings"], json!(["invalid_schema"]));

        assert_eq!(data[2]["generate_url"], serde_json::Value::Null);
        assert_eq!(
            data[2]["import_warnings"],
            json!(["invalid_recipe: unknown bridge_id: 'unknown-bridge'"])
        );

        assert_eq!(data[3]["bridge_id"], serde_json::Value::Null);
        assert_eq!(data[3]["import_warnings"], json!(["invalid_schema"]));
        // One bad element (invalid_schema/invalid_recipe cases above) did not
        // abort the whole batch -- all 4 results were produced.
    }

    #[tokio::test]
    async fn import_batch_non_array_400() {
        let (state, _dir) = test_state("{}").await;
        let response = recipe_import_batch(State(state), None, Bytes::from(r#"{}"#)).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body["error"], "expected a JSON array");
    }

    #[tokio::test]
    async fn import_batch_boundary_100_ok_101_rejected() {
        let (state, _dir) = test_state("{}").await;
        let items_100: Vec<Value> = (0..100).map(|_| nai_recipe()).collect();
        let response = recipe_import_batch(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&items_100).unwrap()),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "100 items must be accepted"
        );

        let (state, _dir) = test_state("{}").await;
        let items_101: Vec<Value> = (0..101).map(|_| nai_recipe()).collect();
        let response = recipe_import_batch(
            State(state),
            None,
            Bytes::from(serde_json::to_vec(&items_101).unwrap()),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::BAD_REQUEST,
            "101 items must be rejected"
        );
        let body = json_body(response).await;
        assert_eq!(body["error"], "too many recipes (max 100)");
    }

    #[tokio::test]
    async fn import_batch_413_over_4mb() {
        let (state, _dir) = test_state("{}").await;
        let oversized = vec![b'x'; 4 * 1024 * 1024 + 1];
        let response = recipe_import_batch(State(state), None, Bytes::from(oversized)).await;
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        let body = json_body(response).await;
        assert_eq!(body["error"], "payload too large (max 4 MB)");
    }

    // ---- helper unit coverage ---------------------------------------------

    #[test]
    fn python_repr_str_quotes_like_python() {
        assert_eq!(python_repr_str(""), "''");
        assert_eq!(python_repr_str("abc"), "'abc'");
        assert_eq!(python_repr_str("it's"), "\"it's\"");
    }

    #[test]
    fn json_value_to_i64_matches_python_int_coercion() {
        assert_eq!(json_value_to_i64(&json!(5)), Some(5));
        assert_eq!(json_value_to_i64(&json!(5.9)), Some(5));
        assert_eq!(json_value_to_i64(&json!(-5.9)), Some(-5));
        assert_eq!(json_value_to_i64(&json!(true)), Some(1));
        assert_eq!(json_value_to_i64(&json!("42")), Some(42));
        assert_eq!(json_value_to_i64(&json!(" 42 ")), Some(42));
        assert_eq!(json_value_to_i64(&json!("4.2")), None);
        assert_eq!(json_value_to_i64(&json!(null)), None);
        assert_eq!(json_value_to_i64(&json!([1])), None);
    }
}

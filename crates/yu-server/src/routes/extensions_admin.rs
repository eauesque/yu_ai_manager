//! `/api/extensions/*` admin surface — git-based lifecycle (Rust native) + forwarders.
//!
//! Git lifecycle (install/update/uninstall) runs Rust-native; no Python compat.
//! Author tools, marketplace, and metadata routes remain Python forwarders.

use std::{collections::HashSet, net::SocketAddr, path::PathBuf};

use axum::{
    body::Bytes,
    extract::{ConnectInfo, Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use tokio::process::Command as Cmd;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    routes::tools_fs::is_local,
    state::SharedState,
};

// ── envelope helpers (mirrors Python core/infra_core/api_errors.py::api_result) ─

/// Success branch: `{"ok": true, "error": null, "data": null, ...payload}`.
fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

/// Error branch: `{"ok": false, "error": <message>, ...extra payload keys}` at
/// the given status. Mirrors Python's `api_error`/`api_result` merging every
/// extra payload key onto the top level, not just `error`.
fn api_result_status(payload: Value, status: StatusCode) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            let mut map = serde_json::Map::new();
            map.insert("error".to_string(), other);
            map
        }
    };
    body.insert("ok".to_string(), Value::Bool(false));
    body.entry("error".to_string()).or_insert(Value::Null);
    (status, Json(Value::Object(body))).into_response()
}

// ── helpers ──────────────────────────────────────────────────────────────────

fn admin_gate(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0))
}

/// Mirrors Python `core/web/auth_helpers.py::require_local`, which every
/// mutating extension route calls *in addition to* the admin-scope check
/// (`routes/extensions_api/routes.py`: install, update, update-all, uninstall,
/// and the five `author/*` routes). Admin scope alone is not enough for these:
/// installing or authoring an extension puts executable code on the box, so
/// Python refuses them from off-box callers even with valid credentials.
///
/// This is loopback-only, which is *stricter* than Python. Python's
/// `is_local_request()` (`core/web/auth_restart.py:97`) also accepts the
/// host's own non-loopback interface addresses via `_hostname_local_ips()`.
/// The stricter side is the safe side to differ on, and it matches the
/// existing Rust precedent in `routes/mcp_client.rs::require_local`.
fn local_gate(connect: Option<&ConnectInfo<SocketAddr>>, label: &str) -> Option<Response> {
    if is_local(connect) {
        return None;
    }
    Some(api_result_status(
        json!({"error": format!("{label} is only available from localhost")}),
        StatusCode::FORBIDDEN,
    ))
}

fn ext_dir(state: &SharedState) -> PathBuf {
    state.config.project_root.join("extensions")
}

/// HTTPS only, must have a non-empty host segment.
fn validate_git_url(url: &str) -> Option<&'static str> {
    if !url.starts_with("https://") {
        return Some("Only HTTPS URLs are allowed");
    }
    let rest = &url["https://".len()..];
    if rest.is_empty() || rest.starts_with('/') {
        return Some("URL must have a valid host");
    }
    None
}

/// Last path segment of a git URL, with .git suffix stripped.
fn repo_name_from_url(url: &str) -> Option<String> {
    let seg = url.trim_end_matches('/').rsplit('/').next()?;
    let name = seg.strip_suffix(".git").unwrap_or(seg);
    if name.is_empty() {
        None
    } else {
        Some(name.to_string())
    }
}

/// Reject names that could escape the extensions directory.
fn safe_ext_name(name: &str) -> bool {
    !name.is_empty() && !name.contains('/') && !name.contains('\\') && !name.starts_with('.')
}

/// Scan the extensions directory for a manifest whose `name` field matches
/// `name`. Python's `ExtensionManager.manifests` is keyed by the manifest's
/// own `name` field (`extensions_loader_manifest.py::load_manifest`,
/// `ext_name = raw["name"]`), not by directory basename, so this scans and
/// matches on the parsed field rather than assuming `ext_dir/name` is the
/// manifest's home directory. Entries are sorted by path before scanning so
/// the result is deterministic regardless of the filesystem's raw readdir
/// order (which is unspecified — e.g. hash-ordered on some filesystems).
fn find_extension_manifest(state: &SharedState, name: &str) -> Option<(PathBuf, Value)> {
    let dir = ext_dir(state);
    let mut entries: Vec<PathBuf> = std::fs::read_dir(&dir)
        .ok()?
        .flatten()
        .map(|e| e.path())
        .collect();
    entries.sort();
    for path in entries {
        if !path.is_dir() {
            continue;
        }
        let Ok(text) = std::fs::read_to_string(path.join("extension.json")) else {
            continue;
        };
        let Ok(v) = serde_json::from_str::<Value>(&text) else {
            continue;
        };
        if v.get("name").and_then(Value::as_str) == Some(name) {
            return Some((path, v));
        }
    }
    None
}

/// Names of all locally-installed extensions (dir scan, keyed by manifest
/// `name` — same rationale as `find_extension_manifest`). Mirrors Python's
/// `set(mgr.manifests.keys())` used to compute marketplace `installed` flags.
fn installed_extension_names(state: &SharedState) -> HashSet<String> {
    let dir = ext_dir(state);
    std::fs::read_dir(&dir)
        .into_iter()
        .flatten()
        .flatten()
        .filter_map(|e| {
            let text = std::fs::read_to_string(e.path().join("extension.json")).ok()?;
            let v: Value = serde_json::from_str(&text).ok()?;
            v.get("name").and_then(Value::as_str).map(str::to_string)
        })
        .collect()
}

/// Only canonical bundled `builtin-*` directories are "trusted" — mirrors
/// Python `extensions_loader_manifest.py::determine_trust_level`. Everything
/// else (including a directory merely *named* `builtin-...`) is "untrusted";
/// Rust has no VERIFIED (L1, signature-based) tier either, matching Python's
/// current state (planned Phase 2+, not implemented there either).
fn trust_level(state: &SharedState, name: &str, found_dir: &std::path::Path) -> &'static str {
    if !name.starts_with("builtin-") {
        return "untrusted";
    }
    let underscored = name.replace('-', "_");
    let dir_name_matches = found_dir
        .file_name()
        .map(|n| n == underscored.as_str())
        .unwrap_or(false);
    let bundled_dir = ext_dir(state).join(&underscored);
    if !dir_name_matches || !bundled_dir.is_dir() {
        return "untrusted";
    }
    let found_canon = std::fs::canonicalize(found_dir).ok();
    let bundled_canon = std::fs::canonicalize(&bundled_dir).ok();
    if found_canon.is_some() && found_canon == bundled_canon {
        "trusted"
    } else {
        "untrusted"
    }
}

fn is_secret_field(field_name: &str) -> bool {
    let lowered = field_name.to_lowercase();
    ["secret", "token", "password", "api_key", "apikey"]
        .iter()
        .any(|t| lowered.contains(t))
}

/// `string`/`boolean`/`number`/`integer` alias to `str`/`bool`/`float`/`int`;
/// any other type name (or empty) passes through / defaults to `str` —
/// mirrors Python's `_CONFIG_TYPE_ALIASES.get(raw_type, raw_type or "str")`.
fn alias_config_type(raw: &str) -> String {
    match raw {
        "string" | "" => "str".to_string(),
        "boolean" => "bool".to_string(),
        "number" => "float".to_string(),
        "integer" => "int".to_string(),
        other => other.to_string(),
    }
}

fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
        Value::String(s) => !s.is_empty(),
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(true),
    }
}

/// `type(value).__name__` for the JSON types `validate_config_value` cares
/// about — mirrors Python's dynamic type name used in "Expected X, got Y"
/// messages. A JSON integer literal (no fractional part) maps to `int`;
/// anything with a fractional part (or written with a decimal point) maps
/// to `float`, matching how Python's own `json.loads` distinguishes them.
fn python_type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => {
            if n.is_i64() || n.is_u64() {
                "int"
            } else {
                "float"
            }
        }
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// Python `repr()` for the JSON value types that can appear in a
/// `config_schema` `options`/value slot — used for `Allowed: [...]` enum
/// error messages, which format each option through `repr`.
fn python_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".to_string(),
        Value::Bool(b) => {
            if *b {
                "True".to_string()
            } else {
                "False".to_string()
            }
        }
        Value::Number(n) => n.to_string(),
        Value::String(s) => format!("'{}'", s.replace('\\', "\\\\").replace('\'', "\\'")),
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(python_repr).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(map) => format!(
            "{{{}}}",
            map.iter()
                .map(|(k, v)| format!("'{}': {}", k, python_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

/// Python `str()` — identical to `repr()` except a top-level string value
/// prints unquoted. Used for the `Invalid option '{value}'.` message, which
/// Python builds via an f-string (`str()`), not `repr()`.
fn python_str(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        other => python_repr(other),
    }
}

/// Mirrors Python `extensions_core/lifecycle/extensions_admin.py::validate_config_value`.
/// `field_type` must already be alias-normalized (see `alias_config_type`)
/// and lowercased, matching how `cf.type` is resolved once at manifest
/// parse time in Python (`extensions_loader_manifest.py::parse_config_schema`)
/// before `validate_config_value` re-lowercases it.
///
/// Deliberately diverges from CPython here. Because `bool` subclasses `int`
/// in Python, `isinstance(True, int)` is true, so Python's `int`/`number`
/// branches **accept a JSON boolean** and persist `True` into a field the
/// manifest declares numeric. `serde_json::Value::Bool` is a distinct variant
/// from `Value::Number`, so matching on `Number` rejects it.
///
/// The divergence is kept on purpose, not inherited by accident:
/// `routes/settings.rs::coerce_value` already refuses booleans for numeric
/// settings, so accepting one here would be inconsistent within this crate,
/// and storing `true` in an int-typed config field is a latent Python defect
/// rather than a contract anyone depends on. Pinned by
/// `extension_config_post_bool_value_rejected_for_int_field`. If parity with
/// Python is ever required for this case, change both sides together.
fn validate_config_value(
    field_type: &str,
    value: &Value,
    options: &[Value],
    range: Option<&(Value, Value)>,
) -> Option<String> {
    let check_range = |v: &Value| -> Option<String> {
        let (lo, hi) = range?;
        let lo_f = lo.as_f64().unwrap_or(f64::NEG_INFINITY);
        let hi_f = hi.as_f64().unwrap_or(f64::INFINITY);
        let v_f = v.as_f64().unwrap_or(0.0);
        if v_f < lo_f || v_f > hi_f {
            Some(format!("Out of range [{}, {}]", lo, hi))
        } else {
            None
        }
    };
    // Each type has a guard arm that rejects a mismatched value and a no-op arm
    // that accepts a matching one. Those no-op arms read the same as the final
    // wildcard, but they are what marks a type name as *recognised*; the
    // wildcard is "any other type passes through unchecked".
    #[allow(
        clippy::match_same_arms,
        reason = "the no-op arms list recognised type names"
    )]
    match field_type {
        "bool" | "boolean" if !matches!(value, Value::Bool(_)) => {
            return Some(format!("Expected bool, got {}", python_type_name(value)));
        }
        "bool" | "boolean" => {}
        "enum" => {
            if !options.iter().any(|o| o == value) {
                return Some(format!(
                    "Invalid option '{}'. Allowed: [{}]",
                    python_str(value),
                    options
                        .iter()
                        .map(python_repr)
                        .collect::<Vec<_>>()
                        .join(", ")
                ));
            }
        }
        "int" | "integer" => {
            if !matches!(value, Value::Number(n) if n.is_i64() || n.is_u64()) {
                return Some(format!("Expected int, got {}", python_type_name(value)));
            }
            if let Some(err) = check_range(value) {
                return Some(err);
            }
        }
        "float" | "number" => {
            if !matches!(value, Value::Number(_)) {
                return Some(format!("Expected number, got {}", python_type_name(value)));
            }
            if let Some(err) = check_range(value) {
                return Some(err);
            }
        }
        "str" | "string" if !matches!(value, Value::String(_)) => {
            return Some(format!("Expected str, got {}", python_type_name(value)));
        }
        "str" | "string" => {}
        _ => {}
    }
    None
}

/// `manifest_to_dict`-equivalent config_schema: `type`/`default`/`label`/
/// `cli_flag` always present; `options`/`range`/`description` only when
/// truthy (matches Python's conditional `if cf.options: ...` etc).
fn build_manifest_config_schema(schema_raw: &Value) -> Value {
    let mut out = serde_json::Map::new();
    if let Some(obj) = schema_raw.as_object() {
        for (field_name, spec) in obj {
            let empty = serde_json::Map::new();
            let spec_obj = spec.as_object().unwrap_or(&empty);
            let raw_type = spec_obj
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or("str")
                .trim()
                .to_lowercase();
            let default = spec_obj.get("default").cloned().unwrap_or(Value::Null);
            let label = spec_obj
                .get("label")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| field_name.clone());
            let cli_flag = spec_obj
                .get("cli_flag")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let mut field = json!({
                "type": alias_config_type(&raw_type),
                "default": default,
                "label": label,
                "cli_flag": cli_flag,
            });
            if let Some(options) = spec_obj.get("options") {
                if truthy(options) {
                    field["options"] = options.clone();
                }
            }
            if let Some(range) = spec_obj.get("range") {
                if truthy(range) {
                    field["range"] = range.clone();
                }
            }
            if let Some(description) = spec_obj.get("description") {
                if truthy(description) {
                    field["description"] = description.clone();
                }
            }
            out.insert(field_name.clone(), field);
        }
    }
    Value::Object(out)
}

/// `build_config_schema`-equivalent config_schema: every key unconditional,
/// plus a resolved `value` (config.json override → schema default), with
/// secret-named fields masked to `null` regardless of stored value — mirrors
/// `extensions_api_config_ops.py::build_config_schema` + `_is_secret_field`.
fn build_config_schema_with_values(config: &Value, ext_name: &str, schema_raw: &Value) -> Value {
    let mut out = serde_json::Map::new();
    if let Some(obj) = schema_raw.as_object() {
        for (field_name, spec) in obj {
            let empty = serde_json::Map::new();
            let spec_obj = spec.as_object().unwrap_or(&empty);
            let raw_type = spec_obj
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or("str")
                .trim()
                .to_lowercase();
            let default = spec_obj.get("default").cloned().unwrap_or(Value::Null);
            let label = spec_obj
                .get("label")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| field_name.clone());
            let cli_flag = spec_obj
                .get("cli_flag")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let options = spec_obj.get("options").cloned().unwrap_or(json!([]));
            let range = spec_obj.get("range").cloned().unwrap_or(Value::Null);
            let description = spec_obj
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let value = if is_secret_field(field_name) {
                Value::Null
            } else {
                crate::ext_config::extension_value(config, ext_name, field_name)
                    .unwrap_or_else(|| default.clone())
            };
            out.insert(
                field_name.clone(),
                json!({
                    "type": alias_config_type(&raw_type),
                    "default": default,
                    "label": label,
                    "cli_flag": cli_flag,
                    "options": options,
                    "range": range,
                    "description": description,
                    "value": value,
                }),
            );
        }
    }
    Value::Object(out)
}

// ── Python forwarder plumbing (author/marketplace/metadata routes) ────────────

fn extensions_unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "extensions_unavailable"})),
    )
        .into_response()
}

async fn fwd_get(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return extensions_unavailable();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .get(&url)
        .header("X-Remote-User", "yu-proxy-auth")
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

async fn fwd_post(state: &SharedState, path: &str, body: Bytes) -> Response {
    if state.config.python_url.is_empty() {
        return extensions_unavailable();
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

// ── Git lifecycle — Rust native ───────────────────────────────────────────────

/// POST /api/extensions/install — git clone --depth 1
pub async fn install(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension install") {
        return r;
    }

    let data: serde_json::Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "invalid JSON"})),
            )
                .into_response()
        }
    };
    let url = match data
        .get("url")
        .or_else(|| data.get("git"))
        .or_else(|| data.get("repo"))
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
    {
        Some(u) => u.to_string(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "url is required"})),
            )
                .into_response()
        }
    };

    if let Some(err) = validate_git_url(&url) {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": err}))).into_response();
    }
    let repo_name = match repo_name_from_url(&url) {
        Some(n) => n,
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "cannot extract repository name from URL"})),
            )
                .into_response()
        }
    };

    let extensions_dir = ext_dir(&state);
    let target = extensions_dir.join(&repo_name);
    if target.components().any(|c| c.as_os_str() == "..") {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Invalid repository name (path traversal blocked)"})),
        )
            .into_response();
    }
    if target.exists() {
        return (
            StatusCode::CONFLICT,
            Json(json!({"error": format!("Extension '{}' already exists", repo_name)})),
        )
            .into_response();
    }
    if let Err(e) = tokio::fs::create_dir_all(&extensions_dir).await {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("Failed to create extensions directory: {}", e)})),
        )
            .into_response();
    }

    match Cmd::new("git").args(["clone", "--depth", "1", &url, target.to_str().unwrap_or("")]).output().await {
        Ok(out) if out.status.success() =>
            (StatusCode::OK, Json(json!({"message": format!("Extension '{}' installed successfully", repo_name), "name": repo_name}))).into_response(),
        Ok(out) => {
            let stderr = String::from_utf8_lossy(&out.stderr);
            (StatusCode::BAD_GATEWAY, Json(json!({"error": format!("git clone failed: {}", stderr.trim())}))).into_response()
        }
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("Failed to run git: {}", e)}))).into_response(),
    }
}

/// POST /api/extensions/{name}/update — git pull --ff-only
pub async fn update_git(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension update") {
        return r;
    }
    if !safe_ext_name(&name) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Invalid extension name"})),
        )
            .into_response();
    }
    let ext_path = ext_dir(&state).join(&name);
    if !ext_path.exists() {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": format!("Extension '{}' not found", name)})),
        )
            .into_response();
    }
    if !ext_path.join(".git").exists() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": format!("Extension '{}' is not a git repository", name)})),
        )
            .into_response();
    }

    match Cmd::new("git")
        .args(["-C", ext_path.to_str().unwrap_or(""), "pull", "--ff-only"])
        .output()
        .await
    {
        Ok(out) if out.status.success() => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let status = if stdout.contains("Already up to date") {
                "unchanged"
            } else {
                "updated"
            };
            (StatusCode::OK, Json(json!({"message": format!("Extension '{}' {}", name, status), "name": name, "status": status}))).into_response()
        }
        Ok(out) => {
            let stderr = String::from_utf8_lossy(&out.stderr);
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({"error": format!("git pull failed: {}", stderr.trim())})),
            )
                .into_response()
        }
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("Failed to run git: {}", e)})),
        )
            .into_response(),
    }
}

/// POST /api/extensions/update-all — git pull --ff-only for each git extension
pub async fn update_all_git(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension update") {
        return r;
    }

    let extensions_dir = ext_dir(&state);
    let mut results: Vec<serde_json::Value> = Vec::new();
    let mut updated_count = 0usize;
    let mut total = 0usize;

    if let Ok(mut entries) = tokio::fs::read_dir(&extensions_dir).await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let name = path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();
            if name.starts_with('.') {
                continue;
            }
            total += 1;

            if !path.join(".git").exists() {
                results.push(
                    json!({"name": name, "status": "skipped", "message": "not a git repository"}),
                );
                continue;
            }

            match Cmd::new("git")
                .args(["-C", path.to_str().unwrap_or(""), "pull", "--ff-only"])
                .output()
                .await
            {
                Ok(out) if out.status.success() => {
                    let stdout = String::from_utf8_lossy(&out.stdout);
                    let already = stdout.contains("Already up to date");
                    if !already {
                        updated_count += 1;
                    }
                    results.push(json!({"name": name, "status": if already { "unchanged" } else { "updated" }}));
                }
                Ok(out) => {
                    let stderr = String::from_utf8_lossy(&out.stderr);
                    results
                        .push(json!({"name": name, "status": "error", "message": stderr.trim()}));
                }
                Err(e) => {
                    results.push(json!({"name": name, "status": "error", "message": e.to_string()}))
                }
            }
        }
    }

    (
        StatusCode::OK,
        Json(json!({
            "message": format!("{} extension(s) updated", updated_count),
            "total": total,
            "updated": updated_count,
            "results": results,
        })),
    )
        .into_response()
}

/// DELETE /api/extensions/{name}/uninstall — remove extension directory
pub async fn uninstall_ext(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension uninstall") {
        return r;
    }
    if !safe_ext_name(&name) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "Invalid extension name"})),
        )
            .into_response();
    }
    let ext_path = ext_dir(&state).join(&name);
    if !ext_path.exists() {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": format!("Extension '{}' not found", name)})),
        )
            .into_response();
    }
    match tokio::fs::remove_dir_all(&ext_path).await {
        Ok(()) => (
            StatusCode::OK,
            Json(json!({"message": format!("Extension '{}' uninstalled", name)})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("Failed to remove extension: {}", e)})),
        )
            .into_response(),
    }
}

// ── Python forwarder routes ───────────────────────────────────────────────────

/// GET /api/extensions/hooks
pub async fn hooks(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    (
        StatusCode::OK,
        Json(json!({"ok": true, "hooks": [], "definitions": {}})),
    )
        .into_response()
}

/// GET /api/extensions/isolation
///
/// Mirrors Python `core/extensions_api/handlers_security.py::get_isolation_status`,
/// which reports on Python's in-process extension sandbox
/// (`core.extensions_core.sandbox.process_isolation`). Rust standalone runs no
/// Python interpreter and has no equivalent in-process sandbox to report on,
/// so `available` is honestly `false` and `processes` is empty — the same
/// explicit "not available" answer as the `os_isolation` handler above,
/// rather than fabricating a positive status.
pub async fn isolation(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    api_result(json!({"available": false, "processes": {}}))
}

// ── Extension authoring (Rust native) ────────────────────────────────────────
//
// Mirrors Python `core/extensions_core/authoring_rules.py` and
// `core/extensions_core/authoring_ops.py`. Every route below is admin-scoped
// *and* localhost-only, matching `routes/extensions_api/routes.py`.
//
// One deliberate divergence: Python resolves the extensions root from the
// `extensions_dir` config key (`authoring_rules.py::extensions_dir`, falling
// back to `"extensions"`), while this port uses this module's own `ext_dir()`
// (`project_root/extensions`). Authored extensions must land where Rust's own
// install/list/uninstall look for them; reading a config key those routes
// ignore would let authoring write into a directory the Rust loader never
// scans.

/// `(key, subdirectory, extension, max_size_bytes)`, mirroring Python
/// `FILE_TYPES`.
const FILE_TYPES: &[(&str, &str, &str, usize)] = &[
    ("entrypoint", ".", ".py", 51200),
    ("template", "templates", ".html", 51200),
    ("static_css", "static", ".css", 51200),
    ("static_js", "static", ".js", 51200),
    ("config", ".", ".json", 10240),
    ("readme", ".", ".md", 20480),
];

const NAME_MAX: usize = 50;
const FILENAME_MAX: usize = 100;
const PROHIBITED_PREFIXES: &[&str] = &["builtin-"];
const UNTRUSTED_LEVEL: &str = "untrusted";

/// Mirrors Python `_NAME_RE = ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`: lowercase
/// alphanumeric at both ends, hyphens permitted only in between.
fn name_matches(name: &str) -> bool {
    fn edge(c: u8) -> bool {
        c.is_ascii_lowercase() || c.is_ascii_digit()
    }
    match name.as_bytes() {
        [] => false,
        [only] => edge(*only),
        [first, mid @ .., last] => {
            edge(*first) && edge(*last) && mid.iter().all(|c| edge(*c) || *c == b'-')
        }
    }
}

/// Mirrors Python `_FILENAME_RE = ^[a-zA-Z0-9][a-zA-Z0-9_-]*$`. Note that this
/// admits neither `.` nor any separator, so a validated filename cannot walk
/// out of the resolved directory.
fn filename_matches(filename: &str) -> bool {
    let mut bytes = filename.bytes();
    let Some(first) = bytes.next() else {
        return false;
    };
    first.is_ascii_alphanumeric()
        && bytes.all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
}

/// Mirrors Python `validate_name`, including the order of the checks: the
/// length limit is applied before the character rule, so an over-long name
/// reports its length rather than its charset.
fn validate_name(name: &str) -> Option<String> {
    if name.is_empty() {
        return Some("Extension name must not be empty".to_string());
    }
    if name.chars().count() > NAME_MAX {
        return Some(format!(
            "Extension name too long (max {NAME_MAX} characters)"
        ));
    }
    if !name_matches(name) {
        return Some(
            "Extension name must contain only lowercase letters, numbers, and hyphens".to_string(),
        );
    }
    for prefix in PROHIBITED_PREFIXES {
        if name.starts_with(prefix) {
            return Some(format!("Extension name must not start with '{prefix}'"));
        }
    }
    None
}

fn file_type_entry(
    file_type: &str,
) -> Option<&'static (&'static str, &'static str, &'static str, usize)> {
    FILE_TYPES.iter().find(|(key, _, _, _)| *key == file_type)
}

/// Mirrors Python `validate_file_type`; the valid-value list is sorted, as
/// Python's `", ".join(sorted(FILE_TYPES.keys()))` is.
fn validate_file_type(file_type: &str) -> Option<String> {
    if file_type_entry(file_type).is_some() {
        return None;
    }
    let mut keys: Vec<&str> = FILE_TYPES.iter().map(|(key, _, _, _)| *key).collect();
    keys.sort_unstable();
    Some(format!(
        "Invalid file_type '{file_type}'. Must be one of: {}",
        keys.join(", ")
    ))
}

/// Mirrors Python `validate_filename`.
fn validate_filename(filename: &str, file_type: &str) -> Option<String> {
    if filename.is_empty() {
        return Some("Filename must not be empty".to_string());
    }
    if !filename_matches(filename) {
        return Some(
            "Filename must contain only letters, numbers, hyphens, and underscores".to_string(),
        );
    }
    if filename.chars().count() > FILENAME_MAX {
        return Some(format!("Filename too long (max {FILENAME_MAX} characters)"));
    }
    if file_type == "config" && filename != "extension" {
        return Some("Config file must be named 'extension' (extension.json)".to_string());
    }
    if file_type == "readme" && filename != "README" {
        return Some("Readme file must be named 'README' (README.md)".to_string());
    }
    None
}

/// Mirrors Python `ext_dir(name)` — the on-disk home of `custom-<name>`.
fn author_ext_dir(state: &SharedState, name: &str) -> PathBuf {
    ext_dir(state).join(format!("custom-{name}"))
}

/// Mirrors Python `resolve_file_path`. Templates live under a per-extension
/// subdirectory whose name has hyphens replaced by underscores.
fn resolve_file_path(
    state: &SharedState,
    name: &str,
    file_type: &str,
    filename: &str,
) -> Option<PathBuf> {
    let (_, subdir, ext, _) = file_type_entry(file_type)?;
    let base = author_ext_dir(state, name);
    if *subdir == "." {
        return Some(base.join(format!("{filename}{ext}")));
    }
    if file_type == "template" {
        return Some(
            base.join(subdir)
                .join(name.replace('-', "_"))
                .join(format!("{filename}{ext}")),
        );
    }
    Some(base.join(subdir).join(format!("{filename}{ext}")))
}

/// Python's `api_result` maps a `{"ok": false, ...}` payload to `api_error`
/// at the *caller's* status, which for every authoring route is the default
/// 200. Business failures therefore carry HTTP 200 with `ok: false`.
fn author_error(message: String) -> Response {
    api_result_status(json!({ "error": message }), StatusCode::OK)
}

fn json_str(data: &Value, key: &str) -> String {
    data.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string()
}

/// Relative path of `path` under `base`, with `\` normalized to `/`.
fn rel_slash(path: &std::path::Path, base: &std::path::Path) -> String {
    path.strip_prefix(base)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

/// Mirrors Python `create_extension`.
fn create_extension(state: &SharedState, name: &str, description: &str) -> Response {
    if let Some(err) = validate_name(name) {
        return author_error(err);
    }
    let base = author_ext_dir(state, name);
    if base.exists() {
        return author_error(format!("Extension 'custom-{name}' already exists"));
    }

    let py_name = name.replace('-', "_");
    if std::fs::create_dir_all(&base).is_err()
        || std::fs::create_dir_all(base.join("templates").join(&py_name)).is_err()
        || std::fs::create_dir_all(base.join("static")).is_err()
    {
        return author_error(format!("Failed to create extension directory for '{name}'"));
    }

    let entrypoint = format!("{py_name}_ext.py");
    let manifest = json!({
        "name": format!("custom-{name}"),
        "version": "0.1.0",
        "description": if description.is_empty() {
            format!("Custom extension: {name}")
        } else {
            description.to_string()
        },
        "entry": entrypoint,
        "author": "user",
        "trust_level": UNTRUSTED_LEVEL,
        "has_blueprint": true,
        "blueprint_prefix": format!("/ext/custom-{name}"),
        "permissions": {"required": [], "optional": []},
    });
    let manifest_path = base.join("extension.json");
    // Python writes `json.dumps(..., ensure_ascii=False, indent=2) + "\n"`.
    let Ok(manifest_text) = serde_json::to_string_pretty(&manifest) else {
        return author_error("Failed to render extension.json".to_string());
    };
    if std::fs::write(&manifest_path, format!("{manifest_text}\n")).is_err() {
        return author_error("Failed to write extension.json".to_string());
    }

    let entrypoint_path = base.join(&entrypoint);
    let scaffold = format!(
        "\"\"\"Custom extension: {name}.\"\"\"\n\nfrom quart import Blueprint\n\nbp = Blueprint(\"custom_{py_name}\", __name__,\n               template_folder=\"templates\",\n               static_folder=\"static\")\n\n\ndef get_blueprint():\n    \"\"\"Return the Blueprint for this extension.\"\"\"\n    return bp\n"
    );
    if std::fs::write(&entrypoint_path, scaffold).is_err() {
        return author_error(format!("Failed to write {entrypoint}"));
    }

    api_result(json!({
        "name": format!("custom-{name}"),
        "path": base.to_string_lossy(),
        "files": [rel_slash(&manifest_path, &base), rel_slash(&entrypoint_path, &base)],
    }))
}

/// POST /api/extensions/author/create
pub async fn author_create(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension authoring") {
        return r;
    }
    // Python uses `get_json(force=True, silent=True) or {}`: a malformed or
    // absent body is an empty object, not a 400.
    let data: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
    create_extension(
        &state,
        &json_str(&data, "name"),
        &json_str(&data, "description"),
    )
}

/// GET /api/extensions/author/:name/files — mirrors Python
/// `list_extension_files`.
pub async fn author_files(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension authoring") {
        return r;
    }
    if let Some(err) = validate_name(&name) {
        return author_error(err);
    }
    let base = author_ext_dir(&state, &name);
    if !base.exists() {
        return author_error(format!("Extension 'custom-{name}' does not exist"));
    }

    // Python walks `sorted(extension_path.rglob("*"))` and keeps regular
    // files. `rglob` does not follow directory symlinks, so neither does this.
    let mut paths: Vec<PathBuf> = Vec::new();
    let mut stack = vec![base.clone()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            match entry.file_type() {
                Ok(ft) if ft.is_dir() => stack.push(path),
                Ok(ft) if ft.is_file() => paths.push(path),
                _ => {}
            }
        }
    }
    paths.sort();

    let mut files: Vec<Value> = Vec::new();
    let mut total_size: u64 = 0;
    for path in &paths {
        let size = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);
        total_size += size;
        files.push(json!({"path": rel_slash(path, &base), "size": size}));
    }

    api_result(json!({
        "name": format!("custom-{name}"),
        "files": files,
        "total_size": total_size,
    }))
}

#[derive(serde::Deserialize)]
pub struct AuthorReadQuery {
    #[serde(default)]
    file_type: String,
    #[serde(default)]
    filename: String,
}

/// GET /api/extensions/author/:name/read — mirrors Python
/// `read_extension_file`.
pub async fn author_read(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    AxumPath(name): AxumPath<String>,
    Query(q): Query<AuthorReadQuery>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension authoring") {
        return r;
    }
    let file_type = q.file_type.trim();
    let filename = q.filename.trim();
    if let Some(err) = validate_name(&name) {
        return author_error(err);
    }
    if let Some(err) = validate_file_type(file_type) {
        return author_error(err);
    }
    if let Some(err) = validate_filename(filename, file_type) {
        return author_error(err);
    }
    let base = author_ext_dir(&state, &name);
    if !base.exists() {
        return author_error(format!("Extension 'custom-{name}' does not exist"));
    }
    let Some(file_path) = resolve_file_path(&state, &name, file_type, filename) else {
        return author_error(format!("Invalid file_type '{file_type}'"));
    };
    if !file_path.exists() {
        let shown = file_path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        return author_error(format!("File not found: {shown}"));
    }
    // Python's `read_text` raises `UnicodeDecodeError` on non-UTF-8 bytes and
    // the route turns that into a business error rather than a 500.
    let Ok(content) = std::fs::read(&file_path) else {
        return author_error("File could not be read".to_string());
    };
    let Ok(content) = String::from_utf8(content) else {
        return author_error("File contains binary data and cannot be read as text".to_string());
    };

    let size = content.len();
    api_result(json!({
        "file": rel_slash(&file_path, &base),
        "content": content,
        "size": size,
    }))
}

/// POST /api/extensions/author/:name/write — mirrors Python
/// `write_extension_file`.
pub async fn author_write(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
    AxumPath(name): AxumPath<String>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension authoring") {
        return r;
    }
    let data: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
    let file_type = json_str(&data, "file_type");
    let filename = json_str(&data, "filename");
    // Python reads `data.get("content", "")` without trimming; a non-string
    // value would fail later on `.encode`, so treat non-strings as empty.
    let content = data
        .get("content")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();

    if let Some(err) = validate_name(&name) {
        return author_error(err);
    }
    if let Some(err) = validate_file_type(&file_type) {
        return author_error(err);
    }
    if let Some(err) = validate_filename(&filename, &file_type) {
        return author_error(err);
    }
    let base = author_ext_dir(&state, &name);
    if !base.exists() {
        return author_error(format!(
            "Extension 'custom-{name}' does not exist. Create it first."
        ));
    }
    let Some((_, _, _, max_size)) = file_type_entry(&file_type) else {
        return author_error(format!("Invalid file_type '{file_type}'"));
    };
    let byte_len = content.len();
    if byte_len > *max_size {
        return author_error(format!(
            "Content too large ({byte_len} bytes, max {max_size})"
        ));
    }
    if content.contains('\0') {
        return author_error("Binary content is not allowed".to_string());
    }

    let Some(file_path) = resolve_file_path(&state, &name, &file_type, &filename) else {
        return author_error(format!("Invalid file_type '{file_type}'"));
    };
    if let Some(parent) = file_path.parent() {
        if std::fs::create_dir_all(parent).is_err() {
            return author_error("Failed to create the target directory".to_string());
        }
    }
    if std::fs::write(&file_path, &content).is_err() {
        return author_error("Failed to write the file".to_string());
    }

    api_result(json!({
        "file": rel_slash(&file_path, &base),
        "size": byte_len,
    }))
}

/// POST /api/extensions/author/:name/validate
///
/// Still unimplemented. Python's `validate_extension` runs `CodeVerifier`
/// (`core/extensions_core/validation/code_verifier.py`), a Python-AST scanner
/// with no Rust counterpart, and rejects the extension when it finds dangerous
/// patterns. Reporting only the manifest checks — which do port trivially —
/// would answer `ok: true` for code the Python verifier would have rejected,
/// so this route returns 501 rather than a weaker verdict wearing the same
/// response shape.
pub async fn author_validate(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if let Some(r) = local_gate(connect.as_ref().map(|e| &e.0), "Extension authoring") {
        return r;
    }
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(json!({"ok": false, "error": "not implemented"})),
    )
        .into_response()
}

/// GET /api/tauri-shell/tabs
pub async fn tauri_shell_tabs(State(_state): State<SharedState>) -> Response {
    extensions_unavailable()
}

#[derive(serde::Deserialize)]
pub struct MarketplaceQuery {
    #[serde(default)]
    q: String,
}

/// GET /api/extensions/marketplace
///
/// Mirrors Python `handlers.py::marketplace_search` /
/// `_marketplace_search_sync` and `extensions_marketplace.py::search_index`.
/// The index URL comes from config's `extension_index_url`; when unset (the
/// default) no network fetch is attempted and the result is an empty list,
/// matching Python's `fetch_index` early-return on empty `get_index_url()`.
/// `total` is `results.len()` (not the extension-count pattern used elsewhere
/// in this codebase for the installed-extensions list), matching Python's
/// `len(results)` in `_marketplace_search_sync`.
pub async fn marketplace(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Query(q): Query<MarketplaceQuery>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    let extensions = fetch_marketplace_index(&state).await;
    let installed = installed_extension_names(&state);
    let extensions = filter_and_annotate_marketplace(extensions, &q.q, &installed);
    let total = extensions.len();
    api_result(json!({"extensions": extensions, "total": total}))
}

/// Fetch the raw extension index, mirroring Python
/// `extensions_marketplace.py::fetch_index`: the URL comes from config's
/// `extension_index_url`, an unset URL means an empty list, a bare array is
/// the index itself, an object is unwrapped by its `extensions` key, and
/// every failure degrades to an empty list rather than an error (Python logs
/// a warning and returns `[]`).
///
/// The empty-URL branch mirrors Python's `if not url` but is not load-bearing
/// here: a request to `""` fails before reaching the network and lands on the
/// same empty list, so removing the branch would change nothing observable.
///
/// Shared by [`marketplace`] and [`marketplace_refresh`] so the two cannot
/// disagree about what the index is.
async fn fetch_marketplace_index(state: &SharedState) -> Vec<Value> {
    let config = crate::ext_config::read_config(&state.config.config_path).unwrap_or(json!({}));
    let index_url = config
        .get("extension_index_url")
        .and_then(Value::as_str)
        .unwrap_or("");
    if index_url.is_empty() {
        return Vec::new();
    }
    match state.python_client.get(index_url).send().await {
        Ok(resp) => match resp.json::<Value>().await {
            Ok(Value::Array(items)) => items,
            Ok(Value::Object(map)) => map
                .get("extensions")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default(),
            _ => Vec::new(),
        },
        Err(_) => Vec::new(),
    }
}

/// Pure marketplace post-processing, extracted from [`marketplace`] so it is
/// testable without a network fetch: case-insensitive substring filter over
/// name/description/author (mirrors `search_index`), then `installed`
/// annotation — only added at all when `installed` is non-empty, matching
/// Python's behavior of never emitting the key when nothing is installed
/// locally rather than emitting it as `false`.
fn filter_and_annotate_marketplace(
    mut extensions: Vec<Value>,
    query: &str,
    installed: &HashSet<String>,
) -> Vec<Value> {
    if !query.is_empty() {
        let needle = query.to_lowercase();
        extensions.retain(|ext| {
            let name = ext
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase();
            let desc = ext
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase();
            let author = ext
                .get("author")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase();
            name.contains(&needle) || desc.contains(&needle) || author.contains(&needle)
        });
    }
    if !installed.is_empty() {
        for ext in extensions.iter_mut() {
            let name = ext
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            if let Some(obj) = ext.as_object_mut() {
                obj.insert(
                    "installed".to_string(),
                    Value::Bool(installed.contains(&name)),
                );
            }
        }
    }
    extensions
}

/// POST /api/extensions/marketplace/refresh
///
/// Mirrors Python `handlers.py::marketplace_refresh`: `clear_cache()` then
/// `fetch_index(force=True)`, answering `{"refreshed": true, "total": N}`.
///
/// Python keeps a 24-hour in-process cache of the index
/// (`extensions_marketplace.py::_cache`) and this route exists to drop it.
/// The Rust port has no such cache — [`marketplace`] fetches on every request
/// — so the clearing half is already satisfied and only the re-fetch remains.
/// The route still does the fetch rather than answering `total: 0` without
/// one: `total` is the size of the index the operator just pulled, and
/// reporting it without asking would make the number a guess.
///
/// `total` counts the whole index, not a filtered view: Python takes
/// `len(extensions)` straight from `fetch_index`, before `search_index`'s
/// query filter or `installed` annotation ever run.
pub async fn marketplace_refresh(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    let extensions = fetch_marketplace_index(&state).await;
    api_result(json!({"refreshed": true, "total": extensions.len()}))
}

/// GET /api/extensions/os-isolation
pub async fn os_isolation(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    (
        StatusCode::OK,
        Json(json!({
            "ok": true,
            "os_isolation": {"available": false},
            "config": {
                "enabled": false, "apparmor": false,
                "macos_sandbox_exec": false, "macos_user_isolation": false,
                "windows_restricted_token": false, "windows_job_object": false
            },
            "processes": {}
        })),
    )
        .into_response()
}

/// GET /api/extensions/{name}
///
/// Mirrors Python `handlers.py::get_extension` → `ExtensionManagerView.get_extension_info`
/// → `extensions_manifest_view.py::manifest_to_dict`. `status`/`status_message`
/// are always the manifest's load-time defaults (`"loaded"`/`""`) and `health`
/// is always `null`: Rust standalone has no module-loading pipeline and no
/// health-probe capability (Python's `compute_health` never runs here), so
/// reporting anything else would be dishonest — same rationale as the
/// `isolation`/`os_isolation` handlers' explicit "not available" answers.
pub async fn extension_detail(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    let Some((dir, manifest)) = find_extension_manifest(&state, &name) else {
        return api_result_status(
            json!({"error": format!("Extension '{}' not found", name)}),
            StatusCode::NOT_FOUND,
        );
    };
    let config = crate::ext_config::read_config(&state.config.config_path).unwrap_or(json!({}));
    let enabled = crate::ext_config::resolve_extension_enabled(&config, &name, &manifest);
    let priority = crate::ext_config::extension_value(&config, &name, "priority")
        .and_then(|v| v.as_i64())
        .unwrap_or_else(|| {
            manifest
                .get("config")
                .and_then(|c| c.get("priority"))
                .and_then(Value::as_i64)
                .unwrap_or(100)
        });
    let empty_schema = json!({});
    let config_schema =
        build_manifest_config_schema(manifest.get("config_schema").unwrap_or(&empty_schema));
    let trust = trust_level(&state, &name, &dir);
    let version = manifest
        .get("version")
        .map(|v| match v {
            Value::String(s) => s.clone(),
            other => other.to_string(),
        })
        .unwrap_or_else(|| "0.0.0".to_string());
    let blueprint_prefix = manifest
        .get("blueprint_prefix")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty());
    api_result(json!({
        "name": name,
        "version": version,
        "description": manifest.get("description").and_then(Value::as_str).unwrap_or(""),
        "type": manifest.get("type").and_then(Value::as_str).unwrap_or("general"),
        "category": manifest.get("category").and_then(Value::as_str).unwrap_or(""),
        "entry": manifest.get("entry").and_then(Value::as_str).unwrap_or(""),
        "hooks": manifest.get("hooks").cloned().unwrap_or(json!([])),
        "enabled": enabled,
        "priority": priority,
        "config_schema": config_schema,
        "source": "local",
        "has_blueprint": manifest.get("has_blueprint").and_then(Value::as_bool).unwrap_or(false),
        "blueprint_prefix": blueprint_prefix,
        "nav": manifest.get("nav").cloned().unwrap_or(json!({})),
        "status": "loaded",
        "status_message": "",
        "trust_level": trust,
        "health": Value::Null,
    }))
}

// ── manifest review (Rust native) ────────────────────────────────────────────

/// Mirrors Python `core/extensions_core/extensions_defs_constants.py::VALID_PERMISSIONS`.
const VALID_PERMISSIONS: &[&str] = &[
    "blueprint:api",
    "blueprint:page",
    "config:read",
    "config:write",
    "db:read",
    "db:write",
    "event_bus",
    "fs:read:any",
    "fs:read:own",
    "fs:read:scan_roots",
    "fs:write:any",
    "fs:write:data",
    "fs:write:own",
    "network:internet",
    "network:local",
    "subprocess",
];

/// Mirrors Python `manifest_authority.py::DANGEROUS_COMBINATIONS`. The
/// messages are reproduced verbatim because they are what the operator reads
/// in the permissions dialog.
const DANGEROUS_COMBINATIONS: &[(&[&str], &str)] = &[
    (
        &["fs:write:any", "network:internet"],
        "ネットワーク通信 + 任意ファイル書き込みはデータ送信・改ざんリスク",
    ),
    (
        &["network:internet", "subprocess"],
        "外部プロセス実行 + ネットワーク通信はリモートコード実行リスク",
    ),
    (
        &["fs:write:any", "subprocess"],
        "外部プロセス実行 + 任意ファイル書き込みはシステム改ざんリスク",
    ),
    (
        &["db:write", "network:internet"],
        "DB 書き込み + ネットワーク通信はデータ漏洩・改ざんリスク",
    ),
];

/// Mirrors Python `ManifestAuthority.review`. Returns `(approved, issues)`
/// where each issue is `{"severity", "message"}`.
///
/// The whole review is pure manifest logic — no filesystem, no runtime state —
/// so unlike `CodeVerifier` it ports exactly.
fn review_manifest(trust_level: &str, manifest: &Value) -> (bool, Vec<Value>) {
    let mut issues: Vec<Value> = Vec::new();
    let block = |m: String| json!({"severity": "block", "message": m});
    let warn = |m: String| json!({"severity": "warn", "message": m});

    // L0: builtin bypasses every check.
    if trust_level == "trusted" {
        return (true, issues);
    }

    let Some((required, optional)) = parse_permissions(manifest) else {
        issues.push(block(
            "permissions フィールドが未定義です。非 builtin Extension は権限宣言が必須です"
                .to_string(),
        ));
        return (false, issues);
    };

    // Python collects into a set and then iterates `sorted(all_perms)`, so
    // duplicates report once and the order is lexicographic.
    let mut all_perms: Vec<&str> = required
        .iter()
        .chain(optional.iter())
        .map(|d| d.name.as_str())
        .collect();
    all_perms.sort_unstable();
    all_perms.dedup();

    let mut approved = true;
    let valid_list = VALID_PERMISSIONS.join(", ");
    for perm in &all_perms {
        if !VALID_PERMISSIONS.contains(perm) {
            approved = false;
            issues.push(block(format!(
                "未知の権限 '{perm}' が宣言されています。有効な権限: {valid_list}"
            )));
        }
    }

    for (combo, reason) in DANGEROUS_COMBINATIONS {
        if combo.iter().all(|p| all_perms.contains(p)) {
            issues.push(warn(format!(
                "危険な権限の組み合わせ: {} — {reason}",
                combo.join(", ")
            )));
        }
    }

    // Python's truthiness: an empty `hooks` list does not trigger this.
    let has_hooks = manifest.get("hooks").is_some_and(|h| {
        !matches!(h, Value::Null | Value::Bool(false)) && h.as_array().is_none_or(|a| !a.is_empty())
    });
    if has_hooks && !all_perms.contains(&"event_bus") {
        issues.push(warn(
            "hooks を使用していますが event_bus 権限が宣言されていません".to_string(),
        ));
    }

    if manifest
        .get("has_blueprint")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        && !all_perms.contains(&"blueprint:api")
        && !all_perms.contains(&"blueprint:page")
    {
        issues.push(warn(
            "Blueprint を持っていますが blueprint:api/blueprint:page 権限が宣言されていません"
                .to_string(),
        ));
    }

    (approved, issues)
}

/// GET /api/extensions/{name}/scan-results
///
/// Mirrors Python `handlers_security.py::scan_extension_code`, with one half
/// of the verdict deliberately absent.
///
/// Python's answer has two independent parts: a `ManifestAuthority` review of
/// the declared permissions, and a `CodeVerifier` pass over the extension's
/// Python source. The review ports exactly — it is pure manifest logic. The
/// code scan does not: `CodeVerifier` walks a Python AST, and Rust has no
/// Python parser here.
///
/// So this reports the review it actually performed and sets `code_scan` to
/// `null` — the same value Python emits when it has no directory to scan
/// (`if manifest.directory` guards the CodeVerifier call). Inventing an
/// empty-but-approved `code_scan` would be a positive claim about code
/// nobody read.
pub async fn extension_scan_results(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    scan_results_body(&state, &name)
}

/// POST /api/extensions/{name}/rescan
///
/// Python's `rescan_extension` is a straight delegation to
/// `scan_extension_code`, so this shares the same body rather than
/// re-deriving it.
pub async fn extension_rescan(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    scan_results_body(&state, &name)
}

fn scan_results_body(state: &SharedState, name: &str) -> Response {
    let Some((ext_path, manifest)) = find_extension_manifest(state, name) else {
        return api_result_status(
            json!({"error": format!("Extension '{name}' not found")}),
            StatusCode::NOT_FOUND,
        );
    };
    let trust_level = determine_trust_level(state, name, &ext_path);
    let (approved, issues) = review_manifest(trust_level, &manifest);
    api_result(json!({
        "name": name,
        "trust_level": trust_level,
        "manifest_review": {"approved": approved, "issues": issues},
        "code_scan": Value::Null,
    }))
}

/// GET /api/extensions/{name}/tokens
///
/// Mirrors Python `handlers_security.py::get_extension_tokens`.
///
/// The capability-token enforcer keeps its store in process memory
/// (`capability_token.py::RuntimeEnforcer._token_store`) and issues tokens
/// only while it is mediating calls from a loaded extension. Standalone Rust
/// never runs it, so no token is ever outstanding — and an empty summary is
/// exactly what Python returns from a freshly started process. This is the
/// true answer, not a placeholder.
pub async fn extension_tokens(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if find_extension_manifest(&state, &name).is_none() {
        return api_result_status(
            json!({"error": format!("Extension '{name}' not found")}),
            StatusCode::NOT_FOUND,
        );
    }
    api_result(json!({"name": name, "token_count": 0, "tokens": []}))
}

/// GET /api/extensions/{name}/integrity
///
/// Mirrors Python `handlers_security.py::get_extension_integrity`.
///
/// Every field here comes from in-process monitors that standalone Rust does
/// not run, so the reply is the one Python gives for an extension with no
/// baseline registered (`integrity_monitor.py::get_status`: `monitored` is
/// `baseline is not None`).
///
/// **`monitored: false` is the load-bearing part.** The permissions dialog
/// renders the whole Runtime Monitoring panel only when `monitored` is true
/// (`src/ts/extensions-page/permissions-render.ts::renderRuntimeHtml`), so a
/// false value shows nothing. Reporting `monitored: true` with
/// `tampered: false` would paint a green "Integrity: OK" for files no monitor
/// ever hashed — the reading is not merely unhelpful, it is the opposite of
/// the truth.
pub async fn extension_integrity(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    if find_extension_manifest(&state, &name).is_none() {
        return api_result_status(
            json!({"error": format!("Extension '{name}' not found")}),
            StatusCode::NOT_FOUND,
        );
    }
    api_result(json!({
        "name": name,
        "integrity": {
            "monitored": false,
            "file_count": 0,
            "tampered": false,
            "tampered_files": [],
        },
        "revocation": {"denial_count": 0, "last_access": Value::Null},
        "import_guard": {"import_denial_count": 0},
    }))
}

/// Python computes an extension's trust level from its *name and directory*,
/// never from the `trust_level` field in its `extension.json`
/// (`extensions_loader_manifest.py::determine_trust_level`). A directory only
/// earns `trusted` when all four hold: the name starts with `builtin-`, the
/// directory's basename is the name with `-` replaced by `_`, that directory
/// exists under the bundled extensions root, and it resolves to the same path
/// (so a symlink pointing elsewhere does not inherit the trust).
///
/// This matters for the permission record: reading the manifest's own
/// `trust_level` would let any extension declare itself `trusted` simply by
/// writing the word into a file it controls — and the authoring scaffold
/// writes that field, so a naive port would also mislabel every custom
/// extension it created.
fn determine_trust_level(
    state: &SharedState,
    ext_name: &str,
    ext_path: &std::path::Path,
) -> &'static str {
    if !ext_name.starts_with("builtin-") {
        return UNTRUSTED_LEVEL;
    }
    let underscored = ext_name.replace('-', "_");
    if ext_path.file_name().and_then(|n| n.to_str()) != Some(underscored.as_str()) {
        return UNTRUSTED_LEVEL;
    }
    let bundled = ext_dir(state).join(&underscored);
    if !bundled.is_dir() {
        return UNTRUSTED_LEVEL;
    }
    match (ext_path.canonicalize(), bundled.canonicalize()) {
        (Ok(a), Ok(b)) if a == b => "trusted",
        _ => UNTRUSTED_LEVEL,
    }
}

/// One extension's entry in the top-level `extension_permissions` section,
/// mirroring Python's `GrantedPermissions` dataclass and the exact key set
/// `save_extension_permissions` writes.
fn granted_entry(config: &Value, ext_name: &str) -> Option<Value> {
    let data = config
        .get("extension_permissions")
        .and_then(Value::as_object)?
        .get(ext_name)?;
    // Python's `load_extension_permissions` skips non-dict entries entirely,
    // so a malformed record reads as "no approval on file" rather than as a
    // partially-populated grant.
    let data = data.as_object()?;
    let field = |key: &str, fallback: Value| data.get(key).cloned().unwrap_or(fallback);
    Some(json!({
        "granted": field("granted", json!([])),
        "denied": field("denied", json!([])),
        "granted_at": field("granted_at", json!("")),
        "auto_approved": field("auto_approved", json!(false)),
    }))
}

/// The permission declarations an extension asks for, as
/// `parse_permissions` shapes them: `{"required": [...], "optional": [...]}`
/// with each entry reduced to `name` and `reason`.
/// One entry of a manifest's `permissions.required` / `.optional` list.
struct PermissionDecl {
    name: String,
    reason: String,
}

/// Mirrors Python `parse_permissions`
/// (`extensions_loader_manifest.py:68`) exactly, including two rules that are
/// easy to miss:
///
/// * A **bare string** entry is a valid declaration with an empty reason —
///   `"required": ["db:read"]` parses the same as
///   `[{"name": "db:read"}]`. Accepting only objects silently under-reports
///   what an extension asked for.
/// * An **empty or non-object** `permissions` value is `None`, not an empty
///   set. `ManifestAuthority` treats that as "no declaration at all" and
///   blocks, so `{"permissions": {}}` and
///   `{"permissions": {"required": [], "optional": []}}` are *not* the same
///   thing.
///
/// Returned as `Option` so both callers see that distinction; the
/// permissions route and the manifest review must not drift on it.
fn parse_permissions(manifest: &Value) -> Option<(Vec<PermissionDecl>, Vec<PermissionDecl>)> {
    let raw = manifest.get("permissions")?.as_object()?;
    if raw.is_empty() {
        return None;
    }
    fn decls(list: Option<&Value>) -> Vec<PermissionDecl> {
        let Some(items) = list.and_then(Value::as_array) else {
            return Vec::new();
        };
        items
            .iter()
            .filter_map(|item| match item {
                Value::String(name) => Some(PermissionDecl {
                    name: name.clone(),
                    reason: String::new(),
                }),
                Value::Object(map) => {
                    let name = map.get("name")?.as_str()?;
                    Some(PermissionDecl {
                        name: name.to_string(),
                        reason: map
                            .get("reason")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_string(),
                    })
                }
                _ => None,
            })
            .collect()
    }
    Some((decls(raw.get("required")), decls(raw.get("optional"))))
}

/// The permission declarations an extension asks for, in the shape the
/// permissions route reports: `{"required": [...], "optional": [...]}` with
/// each entry reduced to `name` and `reason`.
fn declared_permissions(manifest: &Value) -> Value {
    fn render(list: &[PermissionDecl]) -> Vec<Value> {
        list.iter()
            .map(|d| json!({"name": d.name, "reason": d.reason}))
            .collect()
    }
    let (required, optional) = parse_permissions(manifest).unwrap_or_default();
    json!({
        "required": render(&required),
        "optional": render(&optional),
    })
}

/// GET /api/extensions/{name}/permissions
///
/// Mirrors Python `core/extensions_api/handlers_security.py::get_extension_permissions`.
pub async fn extension_permissions_get(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    let Some((ext_path, manifest)) = find_extension_manifest(&state, &name) else {
        return api_result_status(
            json!({"error": format!("Extension '{name}' not found")}),
            StatusCode::NOT_FOUND,
        );
    };
    let config = crate::ext_config::read_config(&state.config.config_path).unwrap_or(json!({}));
    let granted = granted_entry(&config, &name);

    api_result(json!({
        "name": name,
        "trust_level": determine_trust_level(&state, &name, &ext_path),
        // Python's `has_user_approval` is membership in the section, so an
        // entry recording only denials still counts as "the user answered".
        "approved": granted.is_some(),
        "permissions": declared_permissions(&manifest),
        "granted": granted.unwrap_or(Value::Null),
    }))
}

/// POST /api/extensions/{name}/permissions
///
/// Mirrors Python `approve_extension_permissions`: `action` is `approve`
/// (default) or `revoke`.
pub async fn extension_permissions_post(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    let Some((ext_path, _manifest)) = find_extension_manifest(&state, &name) else {
        return api_result_status(
            json!({"error": format!("Extension '{name}' not found")}),
            StatusCode::NOT_FOUND,
        );
    };

    // Mirrors Python `require_json_dict`.
    let data: Value = match serde_json::from_slice::<Value>(&body) {
        Ok(v) if v.is_object() => v,
        Ok(_) => {
            return api_result_status(
                json!({"error": "JSON object body is required", "code": "invalid_json_object"}),
                StatusCode::BAD_REQUEST,
            )
        }
        Err(_) => {
            return api_result_status(
                json!({"error": "Invalid JSON body", "code": "invalid_json"}),
                StatusCode::BAD_REQUEST,
            )
        }
    };

    let action = data
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("approve");
    if action != "approve" && action != "revoke" {
        // Python formats the offending value with `!r`, i.e. Python repr.
        return api_result_status(
            json!({"error": format!("invalid action: '{action}'")}),
            StatusCode::BAD_REQUEST,
        );
    }

    // Serialize the read-modify-write, as `extension_config_post` does: two
    // concurrent grants would otherwise each write a config built from the
    // pre-edit file and one would be lost.
    let _guard = state.settings_lock.lock().await;

    if action == "revoke" {
        return match crate::ext_config::save_section_entry(
            &state.config.config_path,
            "extension_permissions",
            &name,
            None,
        ) {
            Ok(_) => api_result(json!({"name": name, "action": "revoked"})),
            Err(_) => api_result_status(
                json!({"error": "設定の保存に失敗しました"}),
                StatusCode::INTERNAL_SERVER_ERROR,
            ),
        };
    }

    // Python defaults both lists to `[]` when absent but 400s when either is
    // present and not a list — a JSON string is not silently wrapped.
    let list_field = |key: &str| -> Result<Vec<Value>, ()> {
        match data.get(key) {
            None | Some(Value::Null) => Ok(Vec::new()),
            Some(Value::Array(items)) => Ok(items.clone()),
            Some(_) => Err(()),
        }
    };
    let Ok(granted_perms) = list_field("granted") else {
        return api_result_status(
            json!({"error": "granted must be a list"}),
            StatusCode::BAD_REQUEST,
        );
    };
    let Ok(denied_perms) = list_field("denied") else {
        return api_result_status(
            json!({"error": "denied must be a list"}),
            StatusCode::BAD_REQUEST,
        );
    };

    let record = json!({
        "trust_level": determine_trust_level(&state, &name, &ext_path),
        "granted": granted_perms,
        "denied": denied_perms,
        "granted_at": chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros, false),
        "auto_approved": false,
    });
    match crate::ext_config::save_section_entry(
        &state.config.config_path,
        "extension_permissions",
        &name,
        Some(record),
    ) {
        Ok(_) => api_result(json!({
            "name": name,
            "action": "approved",
            "granted": granted_perms,
            "denied": denied_perms,
        })),
        Err(_) => api_result_status(
            json!({"error": "設定の保存に失敗しました"}),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

/// POST /api/extensions/{name}/toggle
///
/// Mirrors Python `handlers.py::toggle_extension` (56-70 行) +
/// `extensions_admin.py::persist_extension_state`. Python's version also
/// flips a live in-process `ExtensionManager` (hook registry, isolated
/// process stop) — this server has no such in-process extension runtime, so
/// only the persistence-layer effect (`config.extensions.<name>.enabled`) is
/// reproduced, matching what the already-native GET routes
/// (`extension_detail`, `extension_config_get`) already read back via
/// `ext_config::resolve_extension_enabled`.
///
/// Python checks manifest existence lazily (only on the "key absent" branch
/// directly, and via `mgr.set_enabled` returning `False` on the "key
/// present" branch); both branches 404 identically, so this checks once
/// up front for the same externally-observable result.
pub async fn extension_toggle(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }

    // Mirrors Python `require_json_dict` (core/infra_core/api_request.py).
    let data: Value = match serde_json::from_slice::<Value>(&body) {
        Ok(v) if v.is_object() => v,
        Ok(_) => {
            return api_result_status(
                json!({"error": "JSON object body is required", "code": "invalid_json_object"}),
                StatusCode::BAD_REQUEST,
            )
        }
        Err(_) => {
            return api_result_status(
                json!({"error": "Invalid JSON body", "code": "invalid_json"}),
                StatusCode::BAD_REQUEST,
            )
        }
    };

    let Some((_, manifest)) = find_extension_manifest(&state, &name) else {
        return api_result_status(
            json!({"error": format!("Extension '{}' not found", name)}),
            StatusCode::NOT_FOUND,
        );
    };

    // `get_arg(data, ("enabled", "on"), None)`: first key whose value is not
    // JSON null wins; both absent/null falls through to "invert current".
    let requested = data
        .get("enabled")
        .filter(|v| !v.is_null())
        .or_else(|| data.get("on").filter(|v| !v.is_null()));

    let enabled = match requested {
        // `bool(enabled)` in Python is a truthiness coercion, not a type
        // check — any JSON value (string/number/etc) is accepted.
        Some(v) => truthy(v),
        None => {
            let config =
                crate::ext_config::read_config(&state.config.config_path).unwrap_or(json!({}));
            !crate::ext_config::resolve_extension_enabled(&config, &name, &manifest)
        }
    };

    let _guard = state.settings_lock.lock().await;
    if let Err(e) = crate::ext_config::save_extension_value(
        &state.config.config_path,
        &name,
        "enabled",
        Value::Bool(enabled),
    ) {
        return api_result_status(
            json!({"error": format!("failed to save extension state: {}", e)}),
            StatusCode::INTERNAL_SERVER_ERROR,
        );
    }

    api_result(json!({
        "name": name,
        "enabled": enabled,
        "message": format!(
            "Extension '{}' {}",
            name,
            if enabled { "enabled" } else { "disabled" }
        ),
    }))
}

/// GET /api/extensions/{name}/config
///
/// Mirrors Python `handlers.py::extension_config` (GET branch) →
/// `extensions_api_config_ops.py::build_config_schema`: every schema field is
/// included unconditionally (unlike `manifest_to_dict`'s conditional
/// `options`/`range`/`description`), plus a resolved `value` (config.json
/// override → schema default), with secret-named fields
/// (`secret`/`token`/`password`/`api_key`/`apikey` substring) masked to
/// `null` regardless of their stored value.
pub async fn extension_config_get(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }
    let Some((_, manifest)) = find_extension_manifest(&state, &name) else {
        return api_result_status(
            json!({"error": format!("Extension '{}' not found", name)}),
            StatusCode::NOT_FOUND,
        );
    };
    let config = crate::ext_config::read_config(&state.config.config_path).unwrap_or(json!({}));
    let empty_schema = json!({});
    let schema_raw = manifest.get("config_schema").unwrap_or(&empty_schema);
    let config_schema = build_config_schema_with_values(&config, &name, schema_raw);
    api_result(json!({"name": name, "config_schema": config_schema}))
}

/// POST /api/extensions/{name}/config
///
/// Mirrors Python `handlers.py::extension_config` (POST branch) →
/// `extensions_api_config_ops.py::validate_and_save_config` →
/// `extensions_admin.py::validate_config_value` / `save_extension_config_values`
/// (secret-field encryption in `save_extension_config_values` is not
/// reproduced — out of scope for this route pair and would need a new crate
/// dependency; values are persisted as given, matching the response shape
/// `{"saved": values}` which always echoes the raw request payload anyway,
/// never the encrypted-at-rest form).
pub async fn extension_config_post(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(name): AxumPath<String>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_gate(&state, auth.as_ref()) {
        return r;
    }

    let Some((_, manifest)) = find_extension_manifest(&state, &name) else {
        return api_result_status(
            json!({"error": format!("Extension '{}' not found", name)}),
            StatusCode::NOT_FOUND,
        );
    };

    // Mirrors Python `require_json_dict`.
    let data: Value = match serde_json::from_slice::<Value>(&body) {
        Ok(v) if v.is_object() => v,
        Ok(_) => {
            return api_result_status(
                json!({"error": "JSON object body is required", "code": "invalid_json_object"}),
                StatusCode::BAD_REQUEST,
            )
        }
        Err(_) => {
            return api_result_status(
                json!({"error": "Invalid JSON body", "code": "invalid_json"}),
                StatusCode::BAD_REQUEST,
            )
        }
    };
    let values: serde_json::Map<String, Value> = data
        .get("values")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();

    let empty_schema = json!({});
    let schema_raw = manifest.get("config_schema").unwrap_or(&empty_schema);
    let schema_obj = schema_raw.as_object();

    let mut errors: Vec<String> = Vec::new();
    for (field_name, value) in &values {
        let Some(spec) = schema_obj.and_then(|o| o.get(field_name)) else {
            errors.push(format!("Unknown config field: {}", field_name));
            continue;
        };
        let empty = serde_json::Map::new();
        let spec_obj = spec.as_object().unwrap_or(&empty);
        let raw_type = spec_obj
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or("str")
            .trim()
            .to_lowercase();
        let field_type = alias_config_type(&raw_type).to_lowercase();
        let options: Vec<Value> = spec_obj
            .get("options")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let range_arr = spec_obj.get("range").and_then(Value::as_array);
        let range = range_arr
            .filter(|a| a.len() == 2)
            .map(|a| (a[0].clone(), a[1].clone()));

        if let Some(err) = validate_config_value(&field_type, value, &options, range.as_ref()) {
            errors.push(format!("{}: {}", field_name, err));
        }
    }

    if !errors.is_empty() {
        return api_result_status(
            json!({"error": "Validation failed", "details": errors}),
            StatusCode::BAD_REQUEST,
        );
    }

    let _guard = state.settings_lock.lock().await;
    for (field_name, value) in &values {
        if let Err(e) = crate::ext_config::save_extension_value(
            &state.config.config_path,
            &name,
            field_name,
            value.clone(),
        ) {
            return api_result_status(
                json!({"error": format!("failed to save config: {}", e)}),
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    }

    api_result(json!({"name": name, "saved": Value::Object(values)}))
}

#[cfg(test)]
mod tests {
    use std::{collections::HashSet, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tempfile::TempDir;

    use super::*;
    use crate::state::{AppState, Config};

    fn write_file(path: &std::path::Path, body: &str) {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, body).unwrap();
    }

    async fn test_state(project_root: PathBuf, config_body: &str) -> SharedState {
        write_file(&project_root.join("config.json"), config_body);
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(
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
                    config_path: project_root.join("config.json"),
                    project_root,
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
        )
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    fn write_extension(root: &std::path::Path, dir_name: &str, manifest: &str) {
        write_file(
            &root
                .join("extensions")
                .join(dir_name)
                .join("extension.json"),
            manifest,
        );
    }

    // ── extension_detail ────────────────────────────────────────────────────

    #[tokio::test]
    async fn extension_detail_404_when_manifest_missing() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = extension_detail(
            State(Arc::clone(&state)),
            None,
            AxumPath("nonexistent-ext".to_string()),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Extension 'nonexistent-ext' not found");
    }

    #[tokio::test]
    async fn extension_detail_config_json_override_wins_over_manifest_default() {
        // Pins the resolve_extension_enabled precedence: a config.json
        // per-extension override must beat the extension.json manifest's
        // own config.enabled, not the other way around.
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config": {"enabled": true}}"#,
        );
        let state = test_state(
            temp.path().to_path_buf(),
            r#"{"extensions": {"sample": {"enabled": false}}}"#,
        )
        .await;

        let resp = extension_detail(
            State(Arc::clone(&state)),
            None,
            AxumPath("sample".to_string()),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = json_body(resp).await;
        assert_eq!(body["ok"], true);
        assert_eq!(body["enabled"], false);
    }

    #[tokio::test]
    async fn extension_detail_falls_back_to_manifest_default_without_override() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config": {"enabled": false}}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_detail(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["enabled"], false);
        assert_eq!(body["trust_level"], "untrusted");
        assert_eq!(body["health"], Value::Null);
        assert_eq!(body["status"], "loaded");
    }

    #[tokio::test]
    async fn extension_detail_scan_survives_unreadable_manifest_in_earlier_directory() {
        // Regression test for a bug caught in self-review: find_extension_manifest
        // originally used `.ok()?` inside the scan loop, which aborted the ENTIRE
        // directory scan (returning None early) the moment it hit any directory
        // without a readable/parseable extension.json — not just skipped that one
        // entry. A decoy directory ("aaa-decoy" sorts before "sample" on most
        // filesystems) with no extension.json at all must not prevent the target
        // extension, scanned later, from being found.
        let temp = TempDir::new().unwrap();
        std::fs::create_dir_all(temp.path().join("extensions").join("aaa-decoy")).unwrap();
        write_extension(temp.path(), "sample", r#"{"name": "sample"}"#);
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = extension_detail(
            State(Arc::clone(&state)),
            None,
            AxumPath("sample".to_string()),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = json_body(resp).await;
        assert_eq!(body["name"], "sample");
    }

    // ── extension_config_get ────────────────────────────────────────────────

    #[tokio::test]
    async fn extension_config_get_404_when_manifest_missing() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = extension_config_get(
            State(Arc::clone(&state)),
            None,
            AxumPath("nonexistent-ext".to_string()),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn extension_config_get_masks_secret_fields_and_resolves_value() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "api_key": {"type": "string", "default": "unset"},
                "threshold": {"type": "number", "default": 5}
            }}"#,
        );
        let state = test_state(
            temp.path().to_path_buf(),
            r#"{"extensions": {"sample": {"api_key": "real-secret", "threshold": 9}}}"#,
        )
        .await;

        let body = json_body(
            extension_config_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        let schema = &body["config_schema"];
        // Secret-named field: value masked to null even though config.json has a stored value.
        assert_eq!(schema["api_key"]["value"], Value::Null);
        assert_eq!(schema["api_key"]["type"], "str");
        // Non-secret field: value resolves from config.json override.
        assert_eq!(schema["threshold"]["value"], 9);
        assert_eq!(schema["threshold"]["type"], "float");
    }

    // ── extension_toggle ────────────────────────────────────────────────────

    fn body_json(v: Value) -> Bytes {
        Bytes::from(serde_json::to_vec(&v).unwrap())
    }

    #[tokio::test]
    async fn extension_toggle_404_when_manifest_missing() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = extension_toggle(
            State(Arc::clone(&state)),
            None,
            AxumPath("nonexistent-ext".to_string()),
            body_json(json!({})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Extension 'nonexistent-ext' not found");
    }

    #[tokio::test]
    async fn extension_toggle_inverts_current_value_when_key_absent() {
        // Manifest defaults enabled=true (no config override) — an empty
        // body must invert it to false and persist that inversion, not
        // default to any fixed value.
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "sample", r#"{"name": "sample"}"#);
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_toggle(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({})),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true);
        assert_eq!(body["enabled"], false);
        assert_eq!(body["message"], "Extension 'sample' disabled");

        // Persisted: re-reading config.json directly must reflect the flip.
        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert_eq!(config["extensions"]["sample"]["enabled"], false);
    }

    #[tokio::test]
    async fn extension_toggle_explicit_enabled_key_overrides_current_value() {
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "sample", r#"{"name": "sample"}"#);
        // Already enabled=true; an explicit {"enabled": true} must still be
        // honored (not treated as "absent" and inverted).
        let state = test_state(
            temp.path().to_path_buf(),
            r#"{"extensions": {"sample": {"enabled": true}}}"#,
        )
        .await;

        let body = json_body(
            extension_toggle(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"enabled": true})),
            )
            .await,
        )
        .await;
        assert_eq!(body["enabled"], true);
        assert_eq!(body["message"], "Extension 'sample' enabled");
    }

    #[tokio::test]
    async fn extension_toggle_accepts_on_alias_key() {
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "sample", r#"{"name": "sample"}"#);
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_toggle(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"on": false})),
            )
            .await,
        )
        .await;
        assert_eq!(body["enabled"], false);
    }

    #[tokio::test]
    async fn extension_toggle_coerces_truthy_non_bool_values() {
        // Python's `bool(enabled)` is truthiness coercion, not a type
        // check — a non-empty string is truthy.
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "sample", r#"{"name": "sample"}"#);
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_toggle(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"enabled": ""})),
            )
            .await,
        )
        .await;
        // Empty string is falsy.
        assert_eq!(body["enabled"], false);
    }

    // ── extension_config_post ───────────────────────────────────────────────

    #[tokio::test]
    async fn extension_config_post_404_when_manifest_missing() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = extension_config_post(
            State(Arc::clone(&state)),
            None,
            AxumPath("nonexistent-ext".to_string()),
            body_json(json!({"values": {}})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn extension_config_post_unknown_field_400_details_and_no_save() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "threshold": {"type": "number", "default": 5}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = extension_config_post(
            State(Arc::clone(&state)),
            None,
            AxumPath("sample".to_string()),
            body_json(json!({"values": {"nope": 1}})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
        let body = json_body(resp).await;
        assert_eq!(body["error"], "Validation failed");
        assert_eq!(body["details"], json!(["Unknown config field: nope"]));

        // Nothing saved.
        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert_eq!(config.get("extensions"), None);
    }

    #[tokio::test]
    async fn extension_config_post_bool_type_mismatch_message() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "flag": {"type": "bool", "default": false}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_config_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"values": {"flag": 1}})),
            )
            .await,
        )
        .await;
        assert_eq!(body["details"], json!(["flag: Expected bool, got int"]));
    }

    #[tokio::test]
    async fn extension_config_post_bool_value_rejected_for_int_field() {
        // Deliberate divergence from CPython's isinstance(bool, int)
        // subclassing quirk — see `validate_config_value` doc comment.
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "count": {"type": "int", "default": 1}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_config_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"values": {"count": true}})),
            )
            .await,
        )
        .await;
        assert_eq!(body["details"], json!(["count: Expected int, got bool"]));
    }

    #[tokio::test]
    async fn extension_config_post_int_out_of_range_message() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "count": {"type": "int", "default": 1, "range": [0, 10]}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_config_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"values": {"count": 42}})),
            )
            .await,
        )
        .await;
        assert_eq!(body["details"], json!(["count: Out of range [0, 10]"]));
    }

    #[tokio::test]
    async fn extension_config_post_float_type_mismatch_message() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "ratio": {"type": "float", "default": 0.5}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_config_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"values": {"ratio": "nope"}})),
            )
            .await,
        )
        .await;
        assert_eq!(body["details"], json!(["ratio: Expected number, got str"]));
    }

    #[tokio::test]
    async fn extension_config_post_str_type_mismatch_message() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "label": {"type": "str", "default": "x"}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_config_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"values": {"label": 5}})),
            )
            .await,
        )
        .await;
        assert_eq!(body["details"], json!(["label: Expected str, got int"]));
    }

    /// `type(value).__name__` must render Python's names, not Rust/JSON ones.
    /// Verified 2026-08-13: swapping `list`/`dict` for `array`/`object` left all
    /// 25 tests green, so the array/object/null arms were entirely unpinned —
    /// a silent divergence in a message this port matches word for word.
    #[tokio::test]
    async fn extension_config_post_reports_python_type_names_for_every_json_kind() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "label": {"type": "str", "default": "x"}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        for (value, python_name) in [
            (json!(null), "NoneType"),
            (json!(true), "bool"),
            (json!(5), "int"),
            (json!(1.5), "float"),
            (json!([1, 2]), "list"),
            (json!({"k": 1}), "dict"),
        ] {
            let body = json_body(
                extension_config_post(
                    State(Arc::clone(&state)),
                    None,
                    AxumPath("sample".to_string()),
                    body_json(json!({"values": {"label": value}})),
                )
                .await,
            )
            .await;
            assert_eq!(
                body["details"],
                json!([format!("label: Expected str, got {python_name}")]),
                "value {value}"
            );
        }
    }

    #[tokio::test]
    async fn extension_config_post_enum_invalid_option_message() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "mode": {"type": "enum", "default": "a", "options": ["a", "b"]}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_config_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"values": {"mode": "c"}})),
            )
            .await,
        )
        .await;
        assert_eq!(
            body["details"],
            json!(["mode: Invalid option 'c'. Allowed: ['a', 'b']"])
        );
    }

    #[tokio::test]
    async fn extension_config_post_saves_on_success_and_echoes_values() {
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "threshold": {"type": "int", "default": 1},
                "label": {"type": "str", "default": "x"}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            extension_config_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                body_json(json!({"values": {"threshold": 7, "label": "hi"}})),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true);
        assert_eq!(body["name"], "sample");
        assert_eq!(body["saved"], json!({"threshold": 7, "label": "hi"}));

        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert_eq!(config["extensions"]["sample"]["threshold"], 7);
        assert_eq!(config["extensions"]["sample"]["label"], "hi");
    }

    #[tokio::test]
    async fn extension_config_post_partial_failure_saves_nothing() {
        // One valid field alongside one invalid field: Python's
        // validate_and_save_config never calls save_extension_config_values
        // when `errors` is non-empty, so even the valid field must not be
        // persisted.
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "config_schema": {
                "threshold": {"type": "int", "default": 1},
                "flag": {"type": "bool", "default": false}
            }}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = extension_config_post(
            State(Arc::clone(&state)),
            None,
            AxumPath("sample".to_string()),
            body_json(json!({"values": {"threshold": 7, "flag": "not-a-bool"}})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);

        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert_eq!(config.get("extensions"), None);
    }

    // ── marketplace ──────────────────────────────────────────────────────────

    #[tokio::test]
    async fn marketplace_empty_index_url_returns_empty_no_network() {
        // No extension_index_url configured — must not attempt a fetch.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(
            marketplace(
                State(Arc::clone(&state)),
                None,
                Query(MarketplaceQuery { q: String::new() }),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true);
        assert_eq!(body["extensions"], json!([]));
        assert_eq!(body["total"], 0);
    }

    #[tokio::test]
    async fn marketplace_installed_flag_reflects_local_extension_dir() {
        // Pins the `installed` flag computation through the same pure helper
        // marketplace() calls: a result whose name matches a locally
        // installed extension is flagged true, a non-match false.
        let mut installed = HashSet::new();
        installed.insert("sample".to_string());
        let extensions = vec![json!({"name": "sample"}), json!({"name": "other"})];
        let out = filter_and_annotate_marketplace(extensions, "", &installed);
        assert_eq!(out[0]["installed"], true);
        assert_eq!(out[1]["installed"], false);
    }

    #[tokio::test]
    async fn marketplace_installed_key_absent_when_nothing_installed_locally() {
        // Python only adds the "installed" key at all when the local
        // installed-set is non-empty; with zero local extensions no result
        // gets an "installed" key, not even `false`.
        let extensions = vec![json!({"name": "sample"})];
        let out = filter_and_annotate_marketplace(extensions, "", &HashSet::new());
        assert!(out[0].get("installed").is_none());
    }

    // ── isolation ────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn isolation_reports_unavailable_honestly() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let body = json_body(isolation(State(Arc::clone(&state)), None).await).await;
        assert_eq!(body["ok"], true);
        assert_eq!(body["available"], false);
        assert_eq!(body["processes"], json!({}));
    }

    // ── authoring: validation rules ─────────────────────────────────────────

    #[test]
    fn name_rule_pins_the_hyphen_placement() {
        // Mirrors Python `_NAME_RE = ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`: hyphens
        // are legal only between two alphanumerics, never at either edge.
        assert!(validate_name("a").is_none());
        assert!(validate_name("my-ext").is_none());
        assert!(validate_name("a--b").is_none());
        assert!(validate_name("-lead").is_some());
        assert!(validate_name("trail-").is_some());
        assert!(validate_name("-").is_some());
        assert!(validate_name("Upper").is_some());
        assert!(validate_name("under_score").is_some());
        assert!(validate_name("").is_some());
    }

    #[test]
    fn name_rule_rejects_traversal_and_separators() {
        // The charset is what closes path traversal for every authoring
        // route, so it is pinned directly rather than only through a handler.
        for bad in ["..", "../evil", "a/b", "a\\b", "a.b", "custom-x/../.."] {
            assert!(
                validate_name(bad).is_some(),
                "name {bad:?} must be rejected"
            );
        }
    }

    #[test]
    fn name_rule_rejects_the_builtin_prefix() {
        assert_eq!(
            validate_name("builtin-thing").as_deref(),
            Some("Extension name must not start with 'builtin-'")
        );
    }

    #[test]
    fn name_length_is_checked_before_the_charset() {
        // Python checks length first, so an over-long *and* malformed name
        // reports the length. Swapping the order changes the message.
        let long = "A".repeat(NAME_MAX + 1);
        assert_eq!(
            validate_name(&long).as_deref(),
            Some("Extension name too long (max 50 characters)")
        );
    }

    #[test]
    fn filename_rule_rejects_traversal_and_dots() {
        for bad in ["..", "../x", "a/b", "a.b", ".hidden", "-lead", ""] {
            assert!(
                validate_filename(bad, "entrypoint").is_some(),
                "filename {bad:?} must be rejected"
            );
        }
        assert!(validate_filename("my_file-1", "entrypoint").is_none());
    }

    #[test]
    fn filename_rule_pins_the_fixed_names() {
        assert!(validate_filename("extension", "config").is_none());
        assert!(validate_filename("other", "config").is_some());
        assert!(validate_filename("README", "readme").is_none());
        assert!(validate_filename("readme", "readme").is_some());
    }

    #[test]
    fn file_type_error_lists_every_type_sorted() {
        let msg = validate_file_type("nope").expect("unknown type rejected");
        assert_eq!(
            msg,
            "Invalid file_type 'nope'. Must be one of: config, entrypoint, readme, static_css, static_js, template"
        );
        for (key, _, _, _) in FILE_TYPES {
            assert!(validate_file_type(key).is_none(), "{key} must be valid");
        }
    }

    // ── authoring: path resolution ──────────────────────────────────────────

    #[tokio::test]
    async fn template_path_uses_the_underscored_extension_subdir() {
        // Python: base/templates/<name with '-' -> '_'>/<filename>.html.
        // Dropping the per-extension subdir would make two extensions collide.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let path = resolve_file_path(&state, "my-ext", "template", "page").unwrap();
        let base = temp.path().join("extensions").join("custom-my-ext");
        assert_eq!(
            path,
            base.join("templates").join("my_ext").join("page.html")
        );
    }

    #[tokio::test]
    async fn each_file_type_lands_in_its_own_subdir_with_its_own_extension() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let base = temp.path().join("extensions").join("custom-e");
        let cases = [
            ("entrypoint", "main", base.join("main.py")),
            ("config", "extension", base.join("extension.json")),
            ("readme", "README", base.join("README.md")),
            ("static_css", "style", base.join("static").join("style.css")),
            ("static_js", "app", base.join("static").join("app.js")),
        ];
        for (file_type, filename, expected) in cases {
            assert_eq!(
                resolve_file_path(&state, "e", file_type, filename).unwrap(),
                expected,
                "{file_type} resolved to the wrong path"
            );
        }
    }

    // ── authoring: the localhost gate ───────────────────────────────────────

    fn remote() -> Option<Extension<ConnectInfo<SocketAddr>>> {
        Some(Extension(ConnectInfo(SocketAddr::from((
            [203, 0, 113, 7],
            5555,
        )))))
    }

    fn loopback() -> Option<Extension<ConnectInfo<SocketAddr>>> {
        Some(Extension(ConnectInfo(SocketAddr::from((
            [127, 0, 0, 1],
            5555,
        )))))
    }

    #[tokio::test]
    async fn every_mutating_extension_route_refuses_a_remote_caller() {
        // Python calls `require_local()` on all nine of these
        // (routes/extensions_api/routes.py). Admin scope alone is not enough:
        // each one either installs or authors executable code on the box.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let s = || State(Arc::clone(&state));
        let name = || AxumPath("thing".to_string());
        let q = || {
            Query(AuthorReadQuery {
                file_type: "entrypoint".to_string(),
                filename: "main".to_string(),
            })
        };

        let responses = vec![
            ("install", install(s(), None, remote(), Bytes::new()).await),
            ("update", update_git(s(), None, remote(), name()).await),
            ("update-all", update_all_git(s(), None, remote()).await),
            (
                "uninstall",
                uninstall_ext(s(), None, remote(), name()).await,
            ),
            (
                "author/create",
                author_create(s(), None, remote(), Bytes::new()).await,
            ),
            (
                "author/files",
                author_files(s(), None, remote(), name()).await,
            ),
            (
                "author/read",
                author_read(s(), None, remote(), name(), q()).await,
            ),
            (
                "author/write",
                author_write(s(), None, remote(), name(), Bytes::new()).await,
            ),
            (
                "author/validate",
                author_validate(s(), None, remote()).await,
            ),
        ];
        assert_eq!(responses.len(), 9);
        for (label, resp) in responses {
            assert_eq!(
                resp.status(),
                StatusCode::FORBIDDEN,
                "{label} must refuse a remote caller"
            );
            let body = json_body(resp).await;
            assert_eq!(body["ok"], false, "{label}");
            assert!(
                body["error"]
                    .as_str()
                    .unwrap_or_default()
                    .ends_with("is only available from localhost"),
                "{label} returned {:?}",
                body["error"]
            );
        }
    }

    #[tokio::test]
    async fn a_missing_peer_address_is_not_treated_as_local() {
        // `is_local` maps an absent ConnectInfo to false. If that ever flips
        // to true, an unidentifiable caller would gain authoring rights.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let resp = author_create(State(Arc::clone(&state)), None, None, Bytes::new()).await;
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    }

    // ── authoring: create / write / read / files ────────────────────────────

    #[tokio::test]
    async fn create_scaffolds_the_manifest_and_entrypoint() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let resp = author_create(
            State(Arc::clone(&state)),
            None,
            loopback(),
            Bytes::from(r#"{"name": "my-ext", "description": "hi"}"#),
        )
        .await;
        let body = json_body(resp).await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["name"], "custom-my-ext");

        let base = temp.path().join("extensions").join("custom-my-ext");
        let manifest: Value =
            serde_json::from_str(&std::fs::read_to_string(base.join("extension.json")).unwrap())
                .unwrap();
        assert_eq!(manifest["name"], "custom-my-ext");
        assert_eq!(manifest["entry"], "my_ext_ext.py");
        assert_eq!(manifest["trust_level"], "untrusted");
        assert_eq!(manifest["blueprint_prefix"], "/ext/custom-my-ext");
        assert_eq!(manifest["description"], "hi");
        assert!(base.join("my_ext_ext.py").is_file());
        assert!(base.join("templates").join("my_ext").is_dir());
        assert!(base.join("static").is_dir());
    }

    #[tokio::test]
    async fn create_defaults_the_description_and_refuses_a_second_run() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = Bytes::from(r#"{"name": "dup"}"#);

        let first = author_create(State(Arc::clone(&state)), None, loopback(), body.clone()).await;
        assert_eq!(json_body(first).await["ok"], true);

        let manifest: Value = serde_json::from_str(
            &std::fs::read_to_string(
                temp.path()
                    .join("extensions")
                    .join("custom-dup")
                    .join("extension.json"),
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(manifest["description"], "Custom extension: dup");

        let second = author_create(State(Arc::clone(&state)), None, loopback(), body).await;
        let body = json_body(second).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Extension 'custom-dup' already exists");
    }

    #[tokio::test]
    async fn write_then_read_round_trips_and_lists() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        author_create(
            State(Arc::clone(&state)),
            None,
            loopback(),
            Bytes::from(r#"{"name": "rt"}"#),
        )
        .await;

        let wrote = author_write(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("rt".to_string()),
            Bytes::from(r#"{"file_type": "template", "filename": "page", "content": "<b>hi</b>"}"#),
        )
        .await;
        let body = json_body(wrote).await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["file"], "templates/rt/page.html");
        assert_eq!(body["size"], 9);

        let read = author_read(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("rt".to_string()),
            Query(AuthorReadQuery {
                file_type: "template".to_string(),
                filename: "page".to_string(),
            }),
        )
        .await;
        let body = json_body(read).await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["content"], "<b>hi</b>");
        assert_eq!(body["file"], "templates/rt/page.html");

        let listed = author_files(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("rt".to_string()),
        )
        .await;
        let body = json_body(listed).await;
        assert_eq!(body["ok"], true, "{body}");
        let paths: Vec<&str> = body["files"]
            .as_array()
            .unwrap()
            .iter()
            .map(|f| f["path"].as_str().unwrap())
            .collect();
        // Sorted, slash-separated, and relative to the extension root.
        assert_eq!(
            paths,
            vec!["extension.json", "rt_ext.py", "templates/rt/page.html"]
        );
        assert!(body["total_size"].as_u64().unwrap() > 0);
    }

    #[tokio::test]
    async fn write_enforces_the_per_type_size_cap() {
        // `config` caps at 10240 while `entrypoint` caps at 51200; a single
        // shared cap would let an over-long config through.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        author_create(
            State(Arc::clone(&state)),
            None,
            loopback(),
            Bytes::from(r#"{"name": "cap"}"#),
        )
        .await;

        let big = "x".repeat(10241);
        let payload = json!({"file_type": "config", "filename": "extension", "content": big});
        let resp = author_write(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("cap".to_string()),
            Bytes::from(serde_json::to_vec(&payload).unwrap()),
        )
        .await;
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Content too large (10241 bytes, max 10240)");

        // The same length is fine for a type with the larger cap.
        let payload =
            json!({"file_type": "entrypoint", "filename": "main", "content": "y".repeat(10241)});
        let resp = author_write(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("cap".to_string()),
            Bytes::from(serde_json::to_vec(&payload).unwrap()),
        )
        .await;
        assert_eq!(json_body(resp).await["ok"], true);
    }

    #[tokio::test]
    async fn write_measures_the_cap_in_bytes_not_characters() {
        // Python compares `len(content.encode("utf-8"))`. Counting characters
        // would let a multibyte payload exceed the cap by up to 3x.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        author_create(
            State(Arc::clone(&state)),
            None,
            loopback(),
            Bytes::from(r#"{"name": "mb"}"#),
        )
        .await;

        // 3418 chars * 3 bytes = 10254 bytes, over the 10240 config cap.
        let payload =
            json!({"file_type": "config", "filename": "extension", "content": "あ".repeat(3418)});
        let resp = author_write(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("mb".to_string()),
            Bytes::from(serde_json::to_vec(&payload).unwrap()),
        )
        .await;
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false, "{body}");
        assert_eq!(body["error"], "Content too large (10254 bytes, max 10240)");
    }

    #[tokio::test]
    async fn write_rejects_a_nul_byte() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        author_create(
            State(Arc::clone(&state)),
            None,
            loopback(),
            Bytes::from(r#"{"name": "nul"}"#),
        )
        .await;

        let payload = json!({"file_type": "entrypoint", "filename": "main", "content": "a\u{0}b"});
        let resp = author_write(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("nul".to_string()),
            Bytes::from(serde_json::to_vec(&payload).unwrap()),
        )
        .await;
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Binary content is not allowed");
    }

    #[tokio::test]
    async fn write_and_read_refuse_an_extension_that_was_never_created() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;

        let resp = author_write(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("ghost".to_string()),
            Bytes::from(r#"{"file_type": "entrypoint", "filename": "main", "content": ""}"#),
        )
        .await;
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false);
        assert_eq!(
            body["error"],
            "Extension 'custom-ghost' does not exist. Create it first."
        );

        let resp = author_files(
            State(Arc::clone(&state)),
            None,
            loopback(),
            AxumPath("ghost".to_string()),
        )
        .await;
        assert_eq!(
            json_body(resp).await["error"],
            "Extension 'custom-ghost' does not exist"
        );
    }

    #[tokio::test]
    async fn read_reports_missing_and_non_utf8_files_as_business_errors() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        author_create(
            State(Arc::clone(&state)),
            None,
            loopback(),
            Bytes::from(r#"{"name": "bin"}"#),
        )
        .await;
        let read = |ft: &str, fname: &str| {
            let state = Arc::clone(&state);
            let (ft, fname) = (ft.to_string(), fname.to_string());
            async move {
                author_read(
                    State(state),
                    None,
                    loopback(),
                    AxumPath("bin".to_string()),
                    Query(AuthorReadQuery {
                        file_type: ft,
                        filename: fname,
                    }),
                )
                .await
            }
        };

        let body = json_body(read("static_js", "absent").await).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "File not found: absent.js");

        let base = temp.path().join("extensions").join("custom-bin");
        std::fs::create_dir_all(base.join("static")).unwrap();
        std::fs::write(base.join("static").join("raw.js"), [0xff, 0xfe, 0x00]).unwrap();
        let body = json_body(read("static_js", "raw").await).await;
        assert_eq!(body["ok"], false);
        assert_eq!(
            body["error"],
            "File contains binary data and cannot be read as text"
        );
    }

    #[tokio::test]
    async fn a_malformed_create_body_is_an_empty_object_not_a_400() {
        // Python: `get_json(force=True, silent=True) or {}`, so a broken body
        // falls through to the name validator.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let resp = author_create(
            State(Arc::clone(&state)),
            None,
            loopback(),
            Bytes::from("not json at all"),
        )
        .await;
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Extension name must not be empty");
    }

    #[tokio::test]
    async fn validate_is_still_unimplemented() {
        // Guards against someone "finishing" the route with manifest checks
        // only: Python's verdict also runs CodeVerifier, and a partial answer
        // in the same response shape would read as approval.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let resp = author_validate(State(Arc::clone(&state)), None, loopback()).await;
        assert_eq!(resp.status(), StatusCode::NOT_IMPLEMENTED);
    }

    // ── permissions ─────────────────────────────────────────────────────────

    fn perms_state_dir(temp: &TempDir, ext_dir_name: &str, manifest: &str) -> PathBuf {
        write_extension(temp.path(), ext_dir_name, manifest);
        temp.path().to_path_buf()
    }

    #[tokio::test]
    async fn permissions_get_404_when_the_extension_is_absent() {
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let resp = extension_permissions_get(
            State(Arc::clone(&state)),
            None,
            AxumPath("nope".to_string()),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
        let body = json_body(resp).await;
        assert_eq!(body["ok"], false);
        assert_eq!(body["error"], "Extension 'nope' not found");
    }

    #[tokio::test]
    async fn permissions_get_reports_declarations_and_no_grant_on_file() {
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(
            &temp,
            "sample",
            r#"{"name": "sample", "permissions": {
                 "required": [{"name": "db:read", "reason": "needs tags"}],
                 "optional": [{"name": "network:internet"}]}}"#,
        );
        let state = test_state(root, "{}").await;

        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["approved"], false);
        assert_eq!(body["granted"], Value::Null);
        assert_eq!(body["permissions"]["required"][0]["name"], "db:read");
        assert_eq!(body["permissions"]["required"][0]["reason"], "needs tags");
        // A declaration without a reason still appears, with an empty reason.
        assert_eq!(
            body["permissions"]["optional"][0]["name"],
            "network:internet"
        );
        assert_eq!(body["permissions"]["optional"][0]["reason"], "");
    }

    #[tokio::test]
    async fn trust_level_is_computed_not_read_from_the_manifest() {
        // The manifest declares itself trusted; Python ignores that field and
        // derives the level from the name and directory instead. Trusting the
        // file would let any extension promote itself.
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(
            &temp,
            "sample",
            r#"{"name": "sample", "trust_level": "trusted"}"#,
        );
        let state = test_state(root, "{}").await;
        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["trust_level"], "untrusted");
    }

    #[tokio::test]
    async fn only_a_bundled_builtin_directory_earns_trusted() {
        // `builtin-x` is trusted only from the directory `builtin_x` under the
        // extensions root. The same manifest in a differently-named directory
        // is untrusted, which is what stops a copied builtin from inheriting
        // the trust of the real one.
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "builtin_x", r#"{"name": "builtin-x"}"#);
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("builtin-x".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["trust_level"], "trusted", "{body}");

        let other = TempDir::new().unwrap();
        write_extension(other.path(), "somewhere_else", r#"{"name": "builtin-x"}"#);
        let state = test_state(other.path().to_path_buf(), "{}").await;
        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("builtin-x".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["trust_level"], "untrusted", "{body}");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn a_symlink_to_the_bundled_directory_does_not_inherit_its_trust() {
        // This fixture exists to isolate the directory-basename check. The
        // canonicalize comparison cannot reject it: the link's target *is* the
        // bundled directory, so both sides resolve to the same path. Only the
        // basename check says "aaa_copy" is not "builtin_x".
        //
        // The name sorts before "builtin_x" so `find_extension_manifest`,
        // which scans in sorted order, reaches the link first.
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "builtin_x", r#"{"name": "builtin-x"}"#);
        let exts = temp.path().join("extensions");
        std::os::unix::fs::symlink(exts.join("builtin_x"), exts.join("aaa_copy")).unwrap();

        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("builtin-x".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["trust_level"], "untrusted", "{body}");
    }

    #[tokio::test]
    async fn approve_writes_the_full_record_and_get_reads_it_back() {
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(root, "{}").await;

        let body = json_body(
            extension_permissions_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                Bytes::from(r#"{"granted": ["db:read"], "denied": ["network:internet"]}"#),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["action"], "approved");
        assert_eq!(body["granted"][0], "db:read");

        // The record lands in the top-level extension_permissions section,
        // not under `extensions`, and carries every key Python writes.
        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        let rec = &config["extension_permissions"]["sample"];
        assert_eq!(rec["granted"][0], "db:read");
        assert_eq!(rec["denied"][0], "network:internet");
        assert_eq!(rec["trust_level"], "untrusted");
        assert_eq!(rec["auto_approved"], false);
        assert!(
            rec["granted_at"].as_str().unwrap().len() >= 20,
            "granted_at must be a timestamp, got {:?}",
            rec["granted_at"]
        );
        assert!(
            config.get("extensions").is_none(),
            "must not touch extensions"
        );

        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["approved"], true);
        assert_eq!(body["granted"]["granted"][0], "db:read");
        assert_eq!(body["granted"]["denied"][0], "network:internet");
    }

    #[tokio::test]
    async fn approve_defaults_both_lists_to_empty() {
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(root, "{}").await;
        let body = json_body(
            extension_permissions_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                Bytes::from("{}"),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["granted"], json!([]));
        assert_eq!(body["denied"], json!([]));
    }

    #[tokio::test]
    async fn approve_400s_when_a_list_field_is_not_a_list() {
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(root, "{}").await;
        for (payload, message) in [
            (r#"{"granted": "db:read"}"#, "granted must be a list"),
            (r#"{"denied": {"a": 1}}"#, "denied must be a list"),
        ] {
            let resp = extension_permissions_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                Bytes::from(payload),
            )
            .await;
            assert_eq!(resp.status(), StatusCode::BAD_REQUEST, "{payload}");
            assert_eq!(json_body(resp).await["error"], message);
        }
        // Nothing was persisted by the rejected requests.
        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert!(config.get("extension_permissions").is_none(), "{config}");
    }

    #[tokio::test]
    async fn revoke_removes_only_the_named_extension() {
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        write_extension(temp.path(), "other", r#"{"name": "other"}"#);
        let state = test_state(
            root,
            r#"{"extension_permissions": {
                 "sample": {"granted": ["db:read"]},
                 "other": {"granted": ["db:write"]}}}"#,
        )
        .await;

        let body = json_body(
            extension_permissions_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                Bytes::from(r#"{"action": "revoke"}"#),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["action"], "revoked");

        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert!(config["extension_permissions"].get("sample").is_none());
        assert_eq!(
            config["extension_permissions"]["other"]["granted"][0],
            "db:write"
        );
    }

    #[tokio::test]
    async fn revoke_is_idempotent() {
        // Python's `revoke_permissions` returns False for an absent entry and
        // the route still answers 200 "revoked".
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(root, "{}").await;
        let body = json_body(
            extension_permissions_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                Bytes::from(r#"{"action": "revoke"}"#),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["action"], "revoked");
    }

    #[tokio::test]
    async fn an_unknown_action_is_rejected_before_anything_is_written() {
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(
            root,
            r#"{"extension_permissions": {"sample": {"granted": ["db:read"]}}}"#,
        )
        .await;
        let resp = extension_permissions_post(
            State(Arc::clone(&state)),
            None,
            AxumPath("sample".to_string()),
            Bytes::from(r#"{"action": "delete"}"#),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(resp).await["error"], "invalid action: 'delete'");

        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert_eq!(
            config["extension_permissions"]["sample"]["granted"][0],
            "db:read"
        );
    }

    #[tokio::test]
    async fn a_malformed_permission_record_reads_as_no_approval() {
        // Python's loader skips non-dict entries, so a scalar under an
        // extension's key must not be reported as a grant.
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(root, r#"{"extension_permissions": {"sample": "yes"}}"#).await;
        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["approved"], false, "{body}");
        assert_eq!(body["granted"], Value::Null);
    }

    #[tokio::test]
    async fn permissions_post_requires_a_json_object_body() {
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(root, "{}").await;
        for (payload, code) in [("[]", "invalid_json_object"), ("nonsense", "invalid_json")] {
            let resp = extension_permissions_post(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
                Bytes::from(payload),
            )
            .await;
            assert_eq!(resp.status(), StatusCode::BAD_REQUEST, "{payload}");
            assert_eq!(json_body(resp).await["code"], code);
        }
    }

    #[tokio::test]
    async fn section_write_preserves_unrelated_config_keys() {
        // `save_section_entry` rewrites the whole file; anything it drops is
        // silent data loss for the user's settings.
        let temp = TempDir::new().unwrap();
        let root = perms_state_dir(&temp, "sample", r#"{"name": "sample"}"#);
        let state = test_state(
            root,
            r#"{"scan_roots": ["/data"], "extensions": {"sample": {"enabled": false}}}"#,
        )
        .await;
        extension_permissions_post(
            State(Arc::clone(&state)),
            None,
            AxumPath("sample".to_string()),
            Bytes::from(r#"{"granted": ["db:read"]}"#),
        )
        .await;
        let config = crate::ext_config::read_config(&state.config.config_path).unwrap();
        assert_eq!(config["scan_roots"][0], "/data");
        assert_eq!(config["extensions"]["sample"]["enabled"], false);
        assert_eq!(
            config["extension_permissions"]["sample"]["granted"][0],
            "db:read"
        );
    }

    // ── manifest review / runtime reporting ─────────────────────────────────

    #[tokio::test]
    async fn a_bare_string_is_a_valid_permission_declaration() {
        // Python's `parse_permissions` accepts `["db:read"]` as well as
        // `[{"name": "db:read"}]`. Handling only the object form silently
        // under-reports what an extension asked for — which is what the
        // operator approves against.
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "permissions": {
                 "required": ["db:read", {"name": "db:write", "reason": "why"}],
                 "optional": ["event_bus"]}}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = json_body(
            extension_permissions_get(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        let required = body["permissions"]["required"].as_array().unwrap();
        assert_eq!(required.len(), 2, "{body}");
        assert_eq!(required[0]["name"], "db:read");
        assert_eq!(required[0]["reason"], "");
        assert_eq!(required[1]["name"], "db:write");
        assert_eq!(required[1]["reason"], "why");
        assert_eq!(body["permissions"]["optional"][0]["name"], "event_bus");
    }

    #[test]
    fn an_empty_permissions_object_is_absent_not_empty() {
        // Python: `if not raw` catches `{}`, so `{"permissions": {}}` means
        // "undeclared" and blocks, while an explicit empty required/optional
        // pair is a real (empty) declaration that passes.
        assert!(parse_permissions(&json!({"permissions": {}})).is_none());
        assert!(parse_permissions(&json!({})).is_none());
        assert!(parse_permissions(&json!({"permissions": []})).is_none());
        assert!(parse_permissions(&json!({"permissions": {"required": []}})).is_some());
    }

    #[test]
    fn review_blocks_when_permissions_are_undeclared() {
        let (approved, issues) = review_manifest("untrusted", &json!({"name": "x"}));
        assert!(!approved);
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0]["severity"], "block");
        assert!(issues[0]["message"]
            .as_str()
            .unwrap()
            .contains("permissions フィールドが未定義"));
    }

    #[test]
    fn review_blocks_an_unknown_permission_name() {
        let (approved, issues) = review_manifest(
            "untrusted",
            &json!({"permissions": {"required": ["db:read", "moon:harvest"]}}),
        );
        assert!(!approved);
        assert_eq!(issues.len(), 1, "{issues:?}");
        let msg = issues[0]["message"].as_str().unwrap();
        assert!(msg.contains("未知の権限 'moon:harvest'"), "{msg}");
        // The valid list is enumerated for the operator, sorted.
        assert!(
            msg.contains("blueprint:api, blueprint:page, config:read"),
            "{msg}"
        );
    }

    #[test]
    fn review_warns_on_each_dangerous_combination() {
        let cases = [
            (
                vec!["network:internet", "fs:write:any"],
                "fs:write:any, network:internet",
            ),
            (
                vec!["subprocess", "network:internet"],
                "network:internet, subprocess",
            ),
            (
                vec!["subprocess", "fs:write:any"],
                "fs:write:any, subprocess",
            ),
            (
                vec!["db:write", "network:internet"],
                "db:write, network:internet",
            ),
        ];
        for (perms, rendered) in cases {
            let (approved, issues) =
                review_manifest("untrusted", &json!({"permissions": {"required": perms}}));
            // A dangerous combination warns; it does not block.
            assert!(approved, "{perms:?} must not block");
            let warns: Vec<&str> = issues
                .iter()
                .filter(|i| i["severity"] == "warn")
                .map(|i| i["message"].as_str().unwrap())
                .collect();
            assert!(
                warns.iter().any(|m| m.contains(rendered)),
                "{perms:?} -> {warns:?}"
            );
        }
    }

    #[test]
    fn review_counts_required_and_optional_together_for_combinations() {
        // Python unions both lists before testing combinations, so splitting a
        // dangerous pair across required/optional does not evade the warning.
        let (_, issues) = review_manifest(
            "untrusted",
            &json!({"permissions": {
                "required": ["subprocess"],
                "optional": ["network:internet"]}}),
        );
        assert!(
            issues.iter().any(|i| i["message"]
                .as_str()
                .unwrap()
                .contains("リモートコード実行リスク")),
            "{issues:?}"
        );
    }

    #[test]
    fn review_warns_about_hooks_and_blueprints_without_their_permission() {
        let (_, issues) = review_manifest(
            "untrusted",
            &json!({"hooks": ["on_scan"], "has_blueprint": true,
                    "permissions": {"required": ["db:read"]}}),
        );
        let msgs: Vec<&str> = issues
            .iter()
            .map(|i| i["message"].as_str().unwrap())
            .collect();
        assert!(msgs.iter().any(|m| m.contains("event_bus")), "{msgs:?}");
        assert!(msgs.iter().any(|m| m.contains("blueprint:api")), "{msgs:?}");

        // Declaring them silences both, and an empty hooks list never warns.
        let (_, issues) = review_manifest(
            "untrusted",
            &json!({"hooks": [], "has_blueprint": true,
                    "permissions": {"required": ["blueprint:page"]}}),
        );
        assert!(issues.is_empty(), "{issues:?}");
    }

    #[test]
    fn a_trusted_builtin_bypasses_the_whole_review() {
        // Python returns the default verdict immediately for L0, so even an
        // undeclared permissions field is approved.
        let (approved, issues) = review_manifest("trusted", &json!({"name": "builtin-x"}));
        assert!(approved);
        assert!(issues.is_empty());
    }

    #[tokio::test]
    async fn scan_results_reports_the_review_and_leaves_code_scan_null() {
        // `code_scan: null` is the honest value: no Python AST parser ran.
        // Emitting an empty-but-approved code_scan would assert that code
        // nobody read is clean, and the UI renders that as "No issues found".
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "permissions": {"required": ["subprocess", "network:internet"]}}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = json_body(
            extension_scan_results(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["name"], "sample");
        assert_eq!(body["trust_level"], "untrusted");
        assert_eq!(body["manifest_review"]["approved"], true);
        assert_eq!(body["manifest_review"]["issues"][0]["severity"], "warn");
        assert_eq!(
            body["code_scan"],
            Value::Null,
            "code_scan must stay null while no scanner runs"
        );
    }

    #[tokio::test]
    async fn rescan_answers_exactly_as_scan_results_does() {
        // Python's `rescan_extension` is a straight delegation; if the two
        // ever diverge, one of the two surfaces is lying about the same data.
        let temp = TempDir::new().unwrap();
        write_extension(
            temp.path(),
            "sample",
            r#"{"name": "sample", "permissions": {"required": ["moon:harvest"]}}"#,
        );
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let scanned = json_body(
            extension_scan_results(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        let rescanned = json_body(
            extension_rescan(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(scanned, rescanned);
        assert_eq!(scanned["manifest_review"]["approved"], false, "{scanned}");
    }

    #[tokio::test]
    async fn integrity_reports_nothing_monitored_rather_than_a_clean_bill() {
        // `monitored: false` is what the UI keys on to render no panel at
        // all. Flipping it to true with `tampered: false` would paint a green
        // "Integrity: OK" over files no monitor ever hashed.
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "sample", r#"{"name": "sample"}"#);
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = json_body(
            extension_integrity(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["integrity"]["monitored"], false);
        assert_eq!(body["integrity"]["file_count"], 0);
        assert_eq!(body["integrity"]["tampered"], false);
        assert_eq!(body["integrity"]["tampered_files"], json!([]));
        assert_eq!(body["revocation"]["denial_count"], 0);
        assert_eq!(body["revocation"]["last_access"], Value::Null);
        assert_eq!(body["import_guard"]["import_denial_count"], 0);
    }

    #[tokio::test]
    async fn tokens_reports_an_empty_summary() {
        let temp = TempDir::new().unwrap();
        write_extension(temp.path(), "sample", r#"{"name": "sample"}"#);
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = json_body(
            extension_tokens(
                State(Arc::clone(&state)),
                None,
                AxumPath("sample".to_string()),
            )
            .await,
        )
        .await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["token_count"], 0);
        assert_eq!(body["tokens"], json!([]));
    }

    #[tokio::test]
    async fn every_runtime_route_404s_for_an_unknown_extension() {
        // Python looks the manifest up first and 404s; answering 200 with
        // zeros for a name that does not exist would invent an extension.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let s = || State(Arc::clone(&state));
        let n = || AxumPath("ghost".to_string());
        let responses = vec![
            ("scan-results", extension_scan_results(s(), None, n()).await),
            ("rescan", extension_rescan(s(), None, n()).await),
            ("tokens", extension_tokens(s(), None, n()).await),
            ("integrity", extension_integrity(s(), None, n()).await),
        ];
        assert_eq!(responses.len(), 4);
        for (label, resp) in responses {
            assert_eq!(resp.status(), StatusCode::NOT_FOUND, "{label}");
            let body = json_body(resp).await;
            assert_eq!(body["ok"], false, "{label}");
            assert_eq!(body["error"], "Extension 'ghost' not found", "{label}");
        }
    }

    // ── marketplace refresh ─────────────────────────────────────────────────

    /// Serve one fixed JSON body on `/index.json` and return its URL.
    async fn index_server(body: &'static str) -> (String, tokio::task::JoinHandle<()>) {
        use axum::{routing::get, Router};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let router = Router::new().route(
            "/index.json",
            get(move || async move {
                (
                    [(axum::http::header::CONTENT_TYPE, "application/json")],
                    body,
                )
            }),
        );
        let handle = tokio::spawn(async move {
            let _ = axum::serve(listener, router).await;
        });
        (format!("http://127.0.0.1:{port}/index.json"), handle)
    }

    #[tokio::test]
    async fn refresh_without_an_index_url_reports_zero() {
        // The default config has no `extension_index_url`, and Python's
        // `fetch_index` returns [] for it.
        //
        // This asserts the answer, not the absence of a request: the empty-URL
        // early return in `fetch_marketplace_index` is unobservable from here,
        // because a request to "" fails before reaching the network and lands
        // on the same empty list. Removing that branch does not fail this
        // test, and no test here claims otherwise.
        let temp = TempDir::new().unwrap();
        let state = test_state(temp.path().to_path_buf(), "{}").await;
        let body = json_body(marketplace_refresh(State(Arc::clone(&state)), None).await).await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["refreshed"], true);
        assert_eq!(body["total"], 0);
    }

    #[tokio::test]
    async fn refresh_counts_the_whole_index_not_a_filtered_view() {
        // Python takes `len(extensions)` straight from `fetch_index`, before
        // `search_index`'s query filter or the `installed` annotation. Reusing
        // the filtered list here would under-report the index size.
        let (url, server) =
            index_server(r#"[{"name":"alpha"},{"name":"beta"},{"name":"gamma"}]"#).await;
        let temp = TempDir::new().unwrap();
        // An extension is installed locally and a query would match only one
        // entry; neither may affect the count.
        write_extension(temp.path(), "alpha", r#"{"name": "alpha"}"#);
        let state = test_state(
            temp.path().to_path_buf(),
            &format!(r#"{{"extension_index_url": "{url}"}}"#),
        )
        .await;

        let body = json_body(marketplace_refresh(State(Arc::clone(&state)), None).await).await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["total"], 3, "{body}");

        // The GET surface still filters, so the two answers legitimately differ.
        let listed = json_body(
            marketplace(
                State(Arc::clone(&state)),
                None,
                Query(MarketplaceQuery {
                    q: "alpha".to_string(),
                }),
            )
            .await,
        )
        .await;
        assert_eq!(listed["total"], 1, "{listed}");
        server.abort();
    }

    #[tokio::test]
    async fn refresh_unwraps_an_object_index_by_its_extensions_key() {
        // `fetch_index` accepts both a bare array and `{"extensions": [...]}`.
        let (url, server) =
            index_server(r#"{"extensions":[{"name":"a"},{"name":"b"}],"version":2}"#).await;
        let temp = TempDir::new().unwrap();
        let state = test_state(
            temp.path().to_path_buf(),
            &format!(r#"{{"extension_index_url": "{url}"}}"#),
        )
        .await;
        let body = json_body(marketplace_refresh(State(Arc::clone(&state)), None).await).await;
        assert_eq!(body["total"], 2, "{body}");
        server.abort();
    }

    #[tokio::test]
    async fn refresh_degrades_to_zero_when_the_index_is_unreachable_or_junk() {
        // Python logs a warning and returns []; the route still answers 200
        // with refreshed:true rather than surfacing the fetch error.
        let temp = TempDir::new().unwrap();

        // Nothing listening on this port.
        let dead = {
            let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let p = l.local_addr().unwrap().port();
            drop(l);
            format!("http://127.0.0.1:{p}/index.json")
        };
        let state = test_state(
            temp.path().to_path_buf(),
            &format!(r#"{{"extension_index_url": "{dead}"}}"#),
        )
        .await;
        let body = json_body(marketplace_refresh(State(Arc::clone(&state)), None).await).await;
        assert_eq!(body["ok"], true, "{body}");
        assert_eq!(body["total"], 0);

        // A JSON scalar is neither an array nor an object with `extensions`.
        let (url, server) = index_server("42").await;
        let temp2 = TempDir::new().unwrap();
        let state = test_state(
            temp2.path().to_path_buf(),
            &format!(r#"{{"extension_index_url": "{url}"}}"#),
        )
        .await;
        let body = json_body(marketplace_refresh(State(Arc::clone(&state)), None).await).await;
        assert_eq!(body["total"], 0, "{body}");
        server.abort();
    }
}

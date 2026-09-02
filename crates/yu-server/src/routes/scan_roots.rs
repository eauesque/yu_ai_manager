use std::{
    collections::{BTreeMap, HashMap},
    path::{Path, PathBuf},
};

use axum::{
    extract::{Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

#[derive(Deserialize)]
pub struct AddScanRootBody {
    pub path: Option<String>,
    pub recursive: Option<bool>,
    pub comment: Option<String>,
}

#[derive(Deserialize)]
pub struct BatchToggleBody {
    pub enabled: Option<bool>,
}

#[derive(Deserialize)]
pub struct ReorderBody {
    pub roots: Option<Vec<Value>>,
    pub order: Option<Vec<usize>>,
}

#[derive(Deserialize)]
pub struct EditScanRootBody {
    pub path: Option<String>,
    pub recursive: Option<bool>,
    pub comment: Option<String>,
}

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

fn api_error(msg: &str, code: &str, status: StatusCode) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": msg, "code": code})),
    )
        .into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": "internal_server_error"})),
    )
        .into_response()
}

fn roots_summary_error(error: impl std::fmt::Debug) -> Response {
    tracing::error!(?error, "Roots summary failed");
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({
            "ok": false,
            "error": "Failed to compute roots summary",
            "code": "roots_summary_failed",
        })),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn read_config(config_path: &Path) -> Result<Value, std::io::Error> {
    let text = std::fs::read_to_string(config_path)?;
    crate::config_io::parse_strict(config_path, &text)
}

#[allow(dead_code)]
fn get_roots_mut(config: &mut Value) -> &mut Vec<Value> {
    config
        .get_mut("scan_roots")
        .and_then(Value::as_array_mut)
        .expect("scan_roots is array")
}

fn ensure_roots_mut(config: &mut Value) -> &mut Vec<Value> {
    if config.get("scan_roots").is_none() {
        config["scan_roots"] = json!([]);
    }
    config["scan_roots"].as_array_mut().unwrap()
}

fn validate_index(roots: &[Value], index: i64) -> Result<usize, ()> {
    // `try_from` rejects the negative half, so the bound below is the only
    // remaining condition -- the two can no longer drift apart.
    usize::try_from(index)
        .ok()
        .filter(|index| *index < roots.len())
        .ok_or(())
}

fn notify_scan_roots_changed(state: &SharedState) {
    if !state.config.python_url.is_empty() {
        let url = format!(
            "{}/_internal/scan-roots-changed",
            state.config.python_url.trim_end_matches('/')
        );
        let client = state.python_client.clone();
        tokio::spawn(async move {
            let _ = client.post(&url).send().await;
        });
    }

    if let Some(infer_client) = state.infer_client.clone() {
        let config_path = state.config.config_path.clone();
        let fallback = state.config.app_config.clone();
        let notify_lock = state.infer_notify_lock.clone();
        // Captured synchronously, in write order (notify_scan_roots_changed
        // runs right after each config.json write, itself serialized by
        // settings_lock) -- so this reflects true mutation order even though
        // the read+send below happens later, out on a spawned task.
        let generation = state
            .scan_roots_generation
            .fetch_add(1, std::sync::atomic::Ordering::SeqCst)
            + 1;
        tokio::spawn(async move {
            // Hold the lock across read+send: each notify re-reads config.json
            // fresh, so unserialized concurrent sends can arrive at yu-infer
            // out of order over HTTP and let an older read clobber a newer
            // one. Reading while holding the lock guarantees every send we
            // START is at least as fresh as the one before it.
            // The send itself is capped with a timeout -- InferClient's
            // reqwest::Client has none of its own, so a hung yu-infer would
            // otherwise hold this lock forever and wedge every notify after
            // it. A timed-out send is not a cancelled one, though: its bytes
            // may already be sitting with yu-infer, which could still apply
            // them after a later, faster send we already let through -- the
            // lock only orders sends we ourselves start. `generation` carries
            // the true order, and the pinned yu-infer enforces it by dropping
            // anything not strictly newer than what it already applied.
            let _guard = notify_lock.lock().await;
            let config = read_config(&config_path).unwrap_or(fallback);
            let scan_roots: Vec<String> = config
                .get("scan_roots")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|root| root.get("path").and_then(|path| path.as_str()))
                        .map(ToString::to_string)
                        .collect()
                })
                .unwrap_or_default();
            let _ = tokio::time::timeout(
                std::time::Duration::from_secs(5),
                infer_client.scan_roots_changed(&scan_roots, generation),
            )
            .await;
        });
    }
}

async fn purge_files_under(db: &SqlitePool, root_path: &str) -> Result<u64, sqlx::Error> {
    let norm = root_path
        .replace('\\', "/")
        .trim_end_matches('/')
        .to_string();
    let fwd = format!("{norm}/%");
    let bwd = format!("{}\\%", norm.replace('/', "\\"));
    let result = sqlx::query("DELETE FROM files WHERE path LIKE ? OR path LIKE ?")
        .bind(fwd)
        .bind(bwd)
        .execute(db)
        .await?;
    Ok(result.rows_affected())
}

/// Drop the quotes Windows Explorer's "Copy as path" wraps around a path.
///
/// Pasting `"C:\Users\me\Pictures"` into the scan-root field stored the quotes
/// verbatim; every root added that way then failed `canonicalize` with
/// ERROR_INVALID_NAME (os error 123) and the scanner silently had no roots at
/// all. Applied both when a root is entered and when one is read back, so an
/// install that already has quoted roots recovers without the user re-typing
/// them.
///
/// Strips only a MATCHED pair: a quote on one side alone is part of the name,
/// since POSIX filenames may legitimately contain `"` and `'`.
pub fn unquote_path(raw: &str) -> String {
    let s = raw.trim();
    if s.len() >= 2 {
        for quote in ['"', '\''] {
            if s.starts_with(quote) && s.ends_with(quote) {
                return s[1..s.len() - 1].trim().to_string();
            }
        }
    }
    s.to_string()
}

fn sanitize_path(raw: &str) -> String {
    let owned = unquote_path(raw);
    let s = owned.as_str();

    if let Some(rest) = s.strip_prefix('~') {
        if let Some(home) = std::env::var_os("HOME") {
            return format!("{}{}", home.to_string_lossy(), rest);
        }
    }
    s.to_string()
}

pub async fn checkpoints(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_checkpoints(&state.db_read, &state.checkpoints_cache).await {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "failed to list checkpoints"),
    }
}

pub async fn scan_roots(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_scan_roots(&state).await {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "failed to list scan roots"),
    }
}

pub async fn scanned_roots(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_scanned_roots(&state).await {
        Ok(value) => api_result(value),
        Err(error) => roots_summary_error(error),
    }
}

pub async fn get_scan_root(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(index): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    let roots = config_scan_roots(&config);
    let idx = match validate_index(&roots, index) {
        Ok(i) => i,
        Err(()) => return api_error("Invalid index", "invalid_index", StatusCode::NOT_FOUND),
    };
    api_result(json!({"root": roots[idx].clone()}))
}

pub async fn add_scan_root(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<AddScanRootBody>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let raw_path = match body.path.as_deref().filter(|path| !path.is_empty()) {
        Some(path) => path.to_string(),
        None => return api_error("path is required", "path_required", StatusCode::BAD_REQUEST),
    };
    let path = sanitize_path(&raw_path);

    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    let roots = ensure_roots_mut(&mut config);
    if roots
        .iter()
        .any(|root| root.get("path").and_then(Value::as_str) == Some(&path))
    {
        return api_error(
            "Path already exists",
            "duplicate_path",
            StatusCode::CONFLICT,
        );
    }

    roots.push(json!({
        "path": path,
        "enabled": true,
        "recursive": body.recursive.unwrap_or(true),
        "comment": body.comment.unwrap_or_default(),
    }));
    let index = roots.len() - 1;
    let roots_snapshot = json!(roots.clone());

    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write config");
    }
    notify_scan_roots_changed(&state);
    api_result(json!({"roots": roots_snapshot, "index": index}))
}

pub async fn remove_scan_root(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(index): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    let roots = ensure_roots_mut(&mut config);
    let idx = match validate_index(roots, index) {
        Ok(index) => index,
        Err(()) => return api_error("Invalid index", "invalid_index", StatusCode::BAD_REQUEST),
    };
    let mut removed_root = roots.remove(idx);
    let removed_path = removed_root
        .get("path")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write config");
    }

    // The read-modify-write is complete; release the global config lock before
    // the purge, which can delete a large number of rows and would otherwise
    // block every other config.json writer for its duration.
    drop(_guard);

    let purged: u64 = if !removed_path.is_empty() {
        match purge_files_under(&state.db, &removed_path).await {
            Ok(n) => n,
            Err(error) => {
                tracing::error!(?error, "purge_files_under failed for {removed_path}");
                0
            }
        }
    } else {
        0
    };
    removed_root["purged"] = json!(purged);

    notify_scan_roots_changed(&state);
    api_result(json!({"removed": removed_root}))
}

pub async fn toggle_scan_root(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(index): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    let roots = ensure_roots_mut(&mut config);
    let idx = match validate_index(roots, index) {
        Ok(index) => index,
        Err(()) => return api_error("Invalid index", "invalid_index", StatusCode::BAD_REQUEST),
    };
    let new_enabled = !roots[idx]
        .get("enabled")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    roots[idx]["enabled"] = json!(new_enabled);
    let roots_snapshot = json!(roots.clone());

    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write config");
    }
    notify_scan_roots_changed(&state);
    api_result(json!({"roots": roots_snapshot, "enabled": new_enabled}))
}

pub async fn batch_toggle_scan_roots(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<BatchToggleBody>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let enable = body.enabled.unwrap_or(true);
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    let roots = ensure_roots_mut(&mut config);
    for root in roots.iter_mut() {
        root["enabled"] = json!(enable);
    }
    let roots_snapshot = json!(roots.clone());

    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write config");
    }
    notify_scan_roots_changed(&state);
    api_result(json!({"roots": roots_snapshot}))
}

pub async fn reorder_scan_roots(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<ReorderBody>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };

    if let Some(new_roots) = body.roots {
        config["scan_roots"] = json!(new_roots);
    } else if let Some(order) = body.order {
        let roots = ensure_roots_mut(&mut config);
        let len = roots.len();
        let mut seen = vec![false; len];
        for &idx in &order {
            if idx >= len || seen[idx] {
                return api_error(
                    "Invalid order array",
                    "invalid_order",
                    StatusCode::BAD_REQUEST,
                );
            }
            seen[idx] = true;
        }
        if order.len() != len {
            return api_error(
                "Invalid order array",
                "invalid_order",
                StatusCode::BAD_REQUEST,
            );
        }
        let old_roots = roots.clone();
        for (new_idx, old_idx) in order.into_iter().enumerate() {
            roots[new_idx] = old_roots[old_idx].clone();
        }
    } else {
        return api_error(
            "roots or order required",
            "missing_body",
            StatusCode::BAD_REQUEST,
        );
    }

    let roots_snapshot = config
        .get("scan_roots")
        .cloned()
        .unwrap_or_else(|| json!([]));
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write config");
    }
    notify_scan_roots_changed(&state);
    api_result(json!({"roots": roots_snapshot}))
}

pub async fn edit_scan_root(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(index): AxumPath<i64>,
    Json(body): Json<EditScanRootBody>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read config"),
    };
    let roots = ensure_roots_mut(&mut config);
    let idx = match validate_index(roots, index) {
        Ok(index) => index,
        Err(()) => return api_error("Invalid index", "invalid_index", StatusCode::BAD_REQUEST),
    };

    if let Some(raw_path) = body.path.as_deref().filter(|path| !path.is_empty()) {
        let path = sanitize_path(raw_path);
        let conflict = roots
            .iter()
            .enumerate()
            .any(|(i, root)| i != idx && root.get("path").and_then(Value::as_str) == Some(&path));
        if conflict {
            return api_error(
                "Path already exists",
                "duplicate_path",
                StatusCode::CONFLICT,
            );
        }
        roots[idx]["path"] = json!(path);
    }
    if let Some(recursive) = body.recursive {
        roots[idx]["recursive"] = json!(recursive);
    }
    if let Some(comment) = body.comment {
        roots[idx]["comment"] = json!(comment);
    }
    let updated_root = roots[idx].clone();

    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write config");
    }
    notify_scan_roots_changed(&state);
    api_result(json!({"success": true, "root": updated_root}))
}

async fn table_exists(db: &SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

async fn build_checkpoints(
    pool: &SqlitePool,
    cache: &crate::state::TtlCache<Value>,
) -> Result<Value, sqlx::Error> {
    cache
        .get_or_try_insert_with(|| build_checkpoints_uncached(pool))
        .await
}

async fn build_checkpoints_uncached(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "templates").await? {
        return Ok(json!({"checkpoints": []}));
    }
    let rows = sqlx::query(
        "SELECT model_name, model_hash, COUNT(*) as count
         FROM templates
         WHERE model_name IS NOT NULL AND model_name != ''
         GROUP BY model_name, model_hash
         ORDER BY count DESC
         LIMIT 100",
    )
    .fetch_all(pool)
    .await?;
    if !rows.is_empty() {
        return Ok(json!({
            "checkpoints": rows.into_iter().map(|row| json!({
                "name": row.get::<String, _>(0),
                "hash": row.try_get::<Option<String>, _>(1).ok().flatten(),
                "count": row.get::<i64, _>(2),
            })).collect::<Vec<_>>()
        }));
    }

    let rows = sqlx::query(
        "SELECT raw_prompt FROM templates WHERE raw_prompt LIKE '%Model:%' LIMIT 50000",
    )
    .fetch_all(pool)
    .await?;
    let mut counts = BTreeMap::<String, i64>::new();
    for row in rows {
        let raw = row.try_get::<Option<String>, _>(0)?.unwrap_or_default();
        if let Some(name) = extract_model_name(&raw) {
            *counts.entry(name).or_insert(0) += 1;
        }
    }
    let mut ranked = counts.into_iter().collect::<Vec<_>>();
    ranked.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    ranked.truncate(100);
    Ok(json!({
        "checkpoints": ranked.into_iter().map(|(name, count)| json!({
            "name": name,
            "hash": Value::Null,
            "count": count,
        })).collect::<Vec<_>>()
    }))
}

fn extract_model_name(raw: &str) -> Option<String> {
    let after = raw.split_once("Model:")?.1;
    let end = after
        .char_indices()
        .find_map(|(idx, ch)| (ch == ',' || ch == '\n').then_some(idx))
        .unwrap_or(after.len());
    let name = after[..end].trim();
    (!name.is_empty()).then(|| name.to_string())
}

fn config_scan_roots(config: &Value) -> Vec<Value> {
    config
        .get("scan_roots")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
}

fn root_path(root: &Value) -> Option<&str> {
    root.get("path")
        .and_then(Value::as_str)
        .filter(|path| !path.is_empty())
}

fn path_bounds(path: &str) -> (String, String, String, String) {
    let norm = path.replace('\\', "/").trim_end_matches('/').to_string();
    let fwd_lo = format!("{norm}/");
    let fwd_hi = format!("{norm}0");
    let bck = norm.replace('/', "\\");
    let bck_lo = format!("{bck}\\");
    let bck_hi = format!("{bck}]");
    (fwd_lo, fwd_hi, bck_lo, bck_hi)
}

async fn count_files_under(pool: &SqlitePool, path: &str) -> Result<i64, sqlx::Error> {
    let (fwd_lo, fwd_hi, bck_lo, bck_hi) = path_bounds(path);
    sqlx::query_scalar(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND (
         (path >= ? AND path < ?) OR (path >= ? AND path < ?))",
    )
    .bind(fwd_lo)
    .bind(fwd_hi)
    .bind(bck_lo)
    .bind(bck_hi)
    .fetch_one(pool)
    .await
}

async fn build_scan_roots(state: &SharedState) -> Result<Value, sqlx::Error> {
    // ponytail: state.config.app_config is a one-time startup snapshot; CRUD
    // handlers write straight to disk, so reads must go back to disk too or
    // additions/removals never show up for the life of the process.
    let config =
        read_config(&state.config.config_path).unwrap_or_else(|_| state.config.app_config.clone());
    let mut roots = Vec::new();
    for root in config_scan_roots(&config) {
        let mut root = root;
        if let Some(path) = root_path(&root).map(str::to_string) {
            let exists = Path::new(&path).exists();
            root["exists"] = Value::Bool(exists);
            root["file_count"] = json!(count_files_under(&state.db_read, &path).await?);
            if !exists && root.get("enabled").and_then(Value::as_bool).unwrap_or(true) {
                root["warning"] = json!("Path not found");
            }
        }
        roots.push(root);
    }
    Ok(json!({"roots": roots}))
}

fn extract_root_dir(path: &str) -> String {
    let sep = if path.contains('\\') { '\\' } else { '/' };
    if path.starts_with("\\\\") || path.starts_with("//") {
        let prefix = path.chars().take(2).collect::<String>();
        let rest = path.chars().skip(2).collect::<String>();
        let parts = rest.split(sep).collect::<Vec<_>>();
        return format!(
            "{}{}",
            prefix,
            parts
                .into_iter()
                .take(3)
                .collect::<Vec<_>>()
                .join(&sep.to_string())
        );
    }
    if path.len() >= 3 && path.as_bytes().get(1) == Some(&b':') && path.chars().nth(2) == Some(sep)
    {
        let prefix = path.chars().take(3).collect::<String>();
        let rest = path.chars().skip(3).collect::<String>();
        let parts = rest.split(sep).collect::<Vec<_>>();
        return if parts.first().is_some_and(|part| !part.is_empty()) {
            format!("{}{}", prefix, parts[0])
        } else {
            prefix
        };
    }
    if let Some(rest) = path.strip_prefix('/') {
        return format!("/{}", rest.split('/').take(2).collect::<Vec<_>>().join("/"));
    }
    path.to_string()
}

/// True when `child` is `parent` itself or nested under it. The boundary
/// separator is inferred from `parent`: `\` only when `parent` itself
/// contains a backslash (i.e. looks like a Windows-style path), `/`
/// otherwise. Paths in `files.path` are not guaranteed to use the
/// platform's native separator (they may be forward-slash even on Windows,
/// or synced in from a different OS via LAN Cowork), so
/// `std::path::MAIN_SEPARATOR` alone is not reliable here — but always
/// accepting `\` unconditionally would falsely treat it as a separator in a
/// POSIX filename that legitimately contains one.
fn is_path_prefix(child: &str, parent: &str) -> bool {
    if child == parent {
        return true;
    }
    let Some(rest) = child.strip_prefix(parent) else {
        return false;
    };
    let sep = if parent.contains('\\') { '\\' } else { '/' };
    rest.starts_with(sep)
}

async fn build_scanned_roots(state: &SharedState) -> Result<Value, sqlx::Error> {
    let config =
        read_config(&state.config.config_path).unwrap_or_else(|_| state.config.app_config.clone());
    let mut registered = config_scan_roots(&config)
        .into_iter()
        .filter_map(|root| root_path(&root).map(resolve_real_path))
        .collect::<Vec<_>>();
    registered.sort_by_key(|root| std::cmp::Reverse(root.len()));
    let mut roots = Vec::<(String, i64)>::new();
    for root in &registered {
        let like_pattern = format!("{}/%", root.trim_end_matches(['/', '\\']));
        let count: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM files WHERE is_deleted = 0 AND path LIKE ?")
                .bind(like_pattern)
                .fetch_one(&state.db_read)
                .await?;
        if count > 0 {
            roots.push((root.clone(), count));
        }
    }
    let mut query = "SELECT path FROM files WHERE is_deleted = 0".to_string();
    let exclude_patterns = registered
        .iter()
        .map(|root| format!("{}/%", root.trim_end_matches(['/', '\\'])))
        .collect::<Vec<_>>();
    if !exclude_patterns.is_empty() {
        query.push_str(&" AND path NOT LIKE ?".repeat(exclude_patterns.len()));
    }
    let mut sql = sqlx::query(&query);
    for pattern in &exclude_patterns {
        sql = sql.bind(pattern);
    }
    let rows = sql.fetch_all(&state.db_read).await?;
    let mut unmatched = Vec::<(String, i64, usize)>::new();
    for row in rows {
        let path = row.get::<String, _>(0);
        let root = extract_root_dir(&path);
        if !root.is_empty() {
            if let Some((_, count, _)) = unmatched.iter_mut().find(|(path, _, _)| path == &root) {
                *count += 1;
            } else {
                let first_idx = unmatched.len();
                unmatched.push((root, 1, first_idx));
            }
        }
    }
    unmatched.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.2.cmp(&b.2)));
    unmatched.truncate(200);
    let mut resolve_cache = HashMap::<String, String>::new();
    for (rd, count, _) in unmatched {
        let norm_rd = cached_resolve(&mut resolve_cache, &rd);
        let mut merged = false;
        let mut index = 0;
        while index < roots.len() {
            let existing = roots[index].0.clone();
            let norm_ex = cached_resolve(&mut resolve_cache, &existing);
            if is_path_prefix(&norm_rd, &norm_ex) {
                roots[index].1 += count;
                merged = true;
                break;
            }
            if is_path_prefix(&norm_ex, &norm_rd) {
                let (_, old_count) = roots.remove(index);
                roots.push((rd.clone(), old_count + count));
                merged = true;
                break;
            }
            index += 1;
        }
        if !merged {
            roots.push((rd, count));
        }
    }
    let mut result = roots;
    result.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    result.truncate(50);
    Ok(json!({
        "roots": result.into_iter().map(|(path, count)| json!({"path": path, "count": count})).collect::<Vec<_>>()
    }))
}

fn resolve_real_path(path: &str) -> String {
    if path.starts_with("\\\\") || path.starts_with("//") {
        return normalize_path_string(path);
    }
    std::fs::canonicalize(path)
        .unwrap_or_else(|_| PathBuf::from(path))
        .to_string_lossy()
        .into_owned()
}

fn normalize_path_string(path: &str) -> String {
    Path::new(path)
        .components()
        .as_path()
        .to_string_lossy()
        .into_owned()
}

fn cached_resolve(cache: &mut HashMap<String, String>, path: &str) -> String {
    if let Some(resolved) = cache.get(path) {
        return resolved.clone();
    }
    let resolved = resolve_real_path(path);
    cache.insert(path.to_string(), resolved.clone());
    resolved
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        collections::HashSet,
        fs,
        path::PathBuf,
        str::FromStr,
        sync::{
            atomic::{AtomicU64, Ordering},
            Arc,
        },
        time::{SystemTime, UNIX_EPOCH},
    };

    use axum::body::to_bytes;
    use axum::extract::Path as AxumPath;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    struct TestRoot {
        path: PathBuf,
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn test_root() -> TestRoot {
        // ponytail: nanos alone can collide between tests running in the same
        // thread-pool tick on Windows (coarse clock), which now matters because
        // build_scan_roots reads config.json from this dir off disk — a
        // collision made one test silently read another test's leftover file.
        static COUNTER: AtomicU64 = AtomicU64::new(0);
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
        let path =
            std::env::temp_dir().join(format!("yu-server-scan-roots-test-{suffix}-{unique}"));
        fs::create_dir_all(&path).unwrap();
        TestRoot { path }
    }

    async fn test_state(root: &TestRoot, app_config: Value) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );
             CREATE TABLE templates (
               file_id INTEGER,
               model_name TEXT,
               model_hash TEXT,
               raw_prompt TEXT
             );
             INSERT INTO files(id, path, is_deleted) VALUES
               (1, '/home/pi/a.png', 0),
               (2, '/home/pi/nested/b.png', 0),
               (3, '/home/pi/deleted.png', 1),
               (4, '/other/c.png', 0);
             INSERT INTO templates(file_id, model_name, model_hash, raw_prompt) VALUES
               (1, 'Model B', 'hash-b', NULL),
               (2, 'Model A', 'hash-a', NULL),
               (3, 'Model B', 'hash-b', NULL);",
        )
        .execute(&pool)
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
                    config_path: root.path.join("config.json"),
                    project_root: root.path.clone(),
                    app_config,
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

    async fn test_state_with_config_file(root: &TestRoot, config: Value) -> SharedState {
        fs::write(
            root.path.join("config.json"),
            serde_json::to_string_pretty(&config).unwrap(),
        )
        .unwrap();
        test_state(root, config).await
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn checkpoints_returns_model_counts_by_popularity() {
        let root = test_root();
        let response = checkpoints(State(test_state(&root, json!({})).await), None).await;
        let value = json_body(response).await;
        assert_eq!(
            value["checkpoints"][0],
            json!({"name": "Model B", "hash": "hash-b", "count": 2})
        );
        assert_eq!(
            value["checkpoints"][1],
            json!({"name": "Model A", "hash": "hash-a", "count": 1})
        );
    }

    #[tokio::test]
    async fn scan_roots_returns_config_roots_with_exists_and_file_count() {
        // `exists` is a real filesystem check, so the scan root must be a
        // directory this test owns. The shared seed's `/home/pi` rows only ever
        // existed on the Raspberry Pi this was originally written on, which made
        // the assertion unsatisfiable everywhere else.
        let root = test_root();
        let scan_dir = root.path.join("scan-root");
        fs::create_dir_all(scan_dir.join("nested")).unwrap();
        let scan_path = scan_dir.to_string_lossy().to_string();

        let config = json!({"scan_roots": [{"path": scan_path.clone(), "enabled": true}]});
        let state = test_state(&root, config).await;
        sqlx::query(
            "INSERT INTO files(id, path, is_deleted) VALUES (10, ?, 0), (11, ?, 0), (12, ?, 1)",
        )
        .bind(scan_dir.join("a.png").to_string_lossy().to_string())
        .bind(
            scan_dir
                .join("nested")
                .join("b.png")
                .to_string_lossy()
                .to_string(),
        )
        .bind(scan_dir.join("deleted.png").to_string_lossy().to_string())
        .execute(&state.db)
        .await
        .unwrap();

        let response = scan_roots(State(Arc::clone(&state)), None).await;
        let value = json_body(response).await;
        assert_eq!(value["roots"][0]["exists"], true);
        // Nested counts, deleted does not.
        assert_eq!(value["roots"][0]["file_count"], 2);
        assert!(value["roots"][0]["warning"].is_null());
    }

    #[tokio::test]
    async fn scanned_roots_summarizes_registered_and_unmatched_roots() {
        let root = test_root();
        let response = scanned_roots(State(test_state(&root, json!({})).await), None).await;
        let value = json_body(response).await;
        assert_eq!(value["roots"][0], json!({"path": "/home/pi", "count": 2}));
        assert_eq!(
            value["roots"][1],
            json!({"path": "/other/c.png", "count": 1})
        );
    }

    #[tokio::test]
    async fn scanned_roots_merges_parent_children_and_sorts_path_ties() {
        // Use paths that are certain not to exist on the host: `build_scanned_roots`
        // canonicalizes root paths to detect nesting, and canonicalize() only
        // resolves paths that actually exist. A fixed literal like "/home/pi"
        // may coincidentally exist on some machines (observed on a Windows
        // dev box, from an unrelated artifact), which made the nested-vs-parent
        // comparison asymmetric and non-deterministic. A per-run unique
        // suffix keeps this test deterministic everywhere.
        let unique = std::time::SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let parent = format!("/home/pi-{unique}");
        let nested = format!("{parent}/nested");
        let tie_a = format!("/aaa/tie-{unique}.png");
        let tie_b = format!("/zzz/tie-{unique}.png");

        let root = test_root();
        let state = test_state(
            &root,
            json!({"scan_roots": [{"path": nested.clone(), "enabled": true}]}),
        )
        .await;
        sqlx::query(
            "INSERT INTO files(id, path, is_deleted) VALUES(20, ?, 0), (21, ?, 0), (22, ?, 0), (23, ?, 0)",
        )
        .bind(format!("{parent}/a.png"))
        .bind(format!("{nested}/b.png"))
        .bind(tie_a.clone())
        .bind(tie_b.clone())
        .execute(&state.db)
        .await
        .unwrap();

        let value = json_body(scanned_roots(State(state), None).await).await;
        let roots = value["roots"].as_array().unwrap();
        assert!(
            roots
                .iter()
                .any(|r| r["path"] == json!(parent) && r["count"] == json!(2)),
            "nested root should merge into its parent: {roots:?}"
        );
        assert!(
            !roots.iter().any(|r| r["path"] == json!(nested)),
            "nested child must not survive as a separate entry once merged into the parent"
        );
        // Equal-count entries must sort alphabetically by path (tie-break).
        let index_of = |path: &str| {
            roots
                .iter()
                .position(|r| r["path"] == json!(path))
                .unwrap_or_else(|| panic!("{path} missing from roots: {roots:?}"))
        };
        assert_eq!(roots[index_of(&tie_a)]["count"], json!(1));
        assert_eq!(roots[index_of(&tie_b)]["count"], json!(1));
        assert!(
            index_of(&tie_a) < index_of("/other/c.png"),
            "\"{tie_a}\" should sort before \"/other/c.png\" among equal counts"
        );
        assert!(
            index_of("/other/c.png") < index_of(&tie_b),
            "\"/other/c.png\" should sort before \"{tie_b}\" among equal counts"
        );
    }

    #[tokio::test]
    async fn add_scan_root_appends_and_returns_index() {
        let root = test_root();
        let state = test_state_with_config_file(&root, json!({"scan_roots": []})).await;
        let value = json_body(
            add_scan_root(
                State(state),
                None,
                Json(AddScanRootBody {
                    path: Some("/new/root".to_string()),
                    recursive: Some(false),
                    comment: Some("added".to_string()),
                }),
            )
            .await,
        )
        .await;

        assert_eq!(value["index"], json!(0));
        assert_eq!(value["roots"].as_array().unwrap().len(), 1);
        assert_eq!(value["roots"][0]["path"], json!("/new/root"));
    }

    #[tokio::test]
    async fn add_scan_root_rejects_duplicate() {
        let root = test_root();
        let state = test_state_with_config_file(
            &root,
            json!({"scan_roots": [{"path": "/dupe", "enabled": true}]}),
        )
        .await;
        let response = add_scan_root(
            State(state),
            None,
            Json(AddScanRootBody {
                path: Some("/dupe".to_string()),
                recursive: None,
                comment: None,
            }),
        )
        .await;

        assert_eq!(response.status(), StatusCode::CONFLICT);
        assert_eq!(json_body(response).await["code"], json!("duplicate_path"));
    }

    #[tokio::test]
    async fn add_scan_root_rejects_empty_path() {
        let root = test_root();
        let state = test_state_with_config_file(&root, json!({"scan_roots": []})).await;
        let response = add_scan_root(
            State(state),
            None,
            Json(AddScanRootBody {
                path: Some(String::new()),
                recursive: None,
                comment: None,
            }),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(response).await["code"], json!("path_required"));
    }

    #[tokio::test]
    async fn remove_scan_root_removes_entry() {
        let root = test_root();
        let state = test_state_with_config_file(
            &root,
            json!({"scan_roots": [{"path": "/first"}, {"path": "/second"}]}),
        )
        .await;
        let value = json_body(remove_scan_root(State(state), None, AxumPath(0)).await).await;

        assert_eq!(value["removed"]["path"], json!("/first"));
        assert_eq!(value["removed"]["purged"], json!(0));
    }

    #[tokio::test]
    async fn remove_scan_root_rejects_out_of_bounds() {
        let root = test_root();
        let state = test_state_with_config_file(&root, json!({"scan_roots": []})).await;
        let response = remove_scan_root(State(state), None, AxumPath(99)).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(response).await["code"], json!("invalid_index"));
    }

    #[tokio::test]
    async fn toggle_scan_root_flips_enabled() {
        let root = test_root();
        let state = test_state_with_config_file(
            &root,
            json!({"scan_roots": [{"path": "/root", "enabled": true}]}),
        )
        .await;
        let value = json_body(toggle_scan_root(State(state), None, AxumPath(0)).await).await;

        assert_eq!(value["enabled"], json!(false));
        assert_eq!(value["roots"][0]["enabled"], json!(false));
    }

    #[tokio::test]
    async fn batch_toggle_disables_all() {
        let root = test_root();
        let state = test_state_with_config_file(
            &root,
            json!({"scan_roots": [{"path": "/a", "enabled": true}, {"path": "/b", "enabled": true}]}),
        )
        .await;
        let value = json_body(
            batch_toggle_scan_roots(
                State(state),
                None,
                Json(BatchToggleBody {
                    enabled: Some(false),
                }),
            )
            .await,
        )
        .await;

        assert!(value["roots"]
            .as_array()
            .unwrap()
            .iter()
            .all(|root| root["enabled"] == json!(false)));
    }

    #[tokio::test]
    async fn reorder_by_order_array() {
        let root = test_root();
        let state = test_state_with_config_file(
            &root,
            json!({"scan_roots": [{"path": "/a"}, {"path": "/b"}]}),
        )
        .await;
        let value = json_body(
            reorder_scan_roots(
                State(state),
                None,
                Json(ReorderBody {
                    roots: None,
                    order: Some(vec![1, 0]),
                }),
            )
            .await,
        )
        .await;

        assert_eq!(value["roots"][0]["path"], json!("/b"));
        assert_eq!(value["roots"][1]["path"], json!("/a"));
    }

    #[tokio::test]
    async fn reorder_rejects_invalid_order() {
        let root = test_root();
        let state = test_state_with_config_file(
            &root,
            json!({"scan_roots": [{"path": "/a"}, {"path": "/b"}]}),
        )
        .await;
        let response = reorder_scan_roots(
            State(state),
            None,
            Json(ReorderBody {
                roots: None,
                order: Some(vec![0, 0]),
            }),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(json_body(response).await["code"], json!("invalid_order"));
    }

    #[tokio::test]
    async fn edit_scan_root_updates_path() {
        let root = test_root();
        let state = test_state_with_config_file(
            &root,
            json!({"scan_roots": [{"path": "/old", "recursive": true}]}),
        )
        .await;
        let value = json_body(
            edit_scan_root(
                State(state),
                None,
                AxumPath(0),
                Json(EditScanRootBody {
                    path: Some("/new".to_string()),
                    recursive: None,
                    comment: None,
                }),
            )
            .await,
        )
        .await;

        assert_eq!(value["success"], json!(true));
        assert_eq!(value["root"]["path"], json!("/new"));
    }
}

// --- One-time scan_roots recovery -----------------------------------------
//
// Port of `core/scan_roots_api/ops_recovery.py`. Detects and offers to
// restore scan roots lost to the stale-read / reorder-overwrite bug fixed in
// v4.681.6 (a write action could overwrite config.json's `scan_roots` with a
// stale, possibly empty, in-memory snapshot). The marker this reads is
// planted by `core/schema_core/schema_migrate_steps_88.py`; the UI side is
// `src/ts/tools-page/roots/recovery.ts`.

const RECOVERY_MARKER_NAME: &str = "scan_roots_recovery_pending.json";

/// Directory names that must never be auto-registered as a scan root when
/// they appear one level below a drive letter -- e.g. "C:\Users" (every
/// profile on the machine, not just the library owner's) or "C:\Windows".
/// The orphan-root reconstruction in `build_scanned_roots` deliberately falls
/// back to a coarse 1-2-segment bucket when it cannot merge a path into
/// something more specific (see `extract_root_dir`), which is fine for the
/// informational summary a human reads, but not for a path this feature can
/// register with one click.
const DANGEROUS_ROOT_NAMES: &[&str] = &[
    "users",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "system volume information",
    "$recycle.bin",
    "appdata",
    "boot",
    "recovery",
    "perflogs",
];

/// Special administrative UNC shares with no ordinary-data-folder meaning of
/// their own -- ADMIN$ *is* the Windows install directory, IPC$ is a named
/// pipe (not a filesystem path at all), and NETLOGON/SYSVOL/PRINT$ are
/// domain-controller/print-spooler shares.
const DANGEROUS_UNC_SHARE_NAMES: &[&str] = &["admin$", "ipc$", "print$", "netlogon", "sysvol"];

#[derive(Deserialize, Default)]
pub struct RecoveryApplyBody {
    pub paths: Option<Vec<String>>,
}

/// Undo Windows' "verbatim"/device-namespace path prefixes.
///
/// `\\?\C:\Users`, `\\?\UNC\host\share`, `\\.\C:\Users` and
/// `\\.\UNC\host\share` are all the same locations as `C:\Users` and
/// `\\host\share` -- just spelled so the length limit and `.`/`..`
/// normalization are skipped (`\\?\...`, what `std::fs::canonicalize` emits
/// on Windows) or so the path resolves through the Win32 device namespace
/// (`\\.\...`); both namespaces alias UNC the same way, via a `UNC\`
/// sub-prefix rather than a drive letter. Segment-counting any of these
/// spellings directly undercounts by the prefix's own segment(s) and lets a
/// disguised `C:\Users` (or bare UNC share) slip past the broad-root check.
fn strip_verbatim_prefix(path: &str) -> String {
    for prefix in ["\\\\?\\", "\\\\.\\"] {
        let Some(rest) = path.strip_prefix(prefix) else {
            continue;
        };
        if rest.len() >= 4 && rest[..4].eq_ignore_ascii_case("UNC\\") {
            return format!("\\\\{}", &rest[4..]);
        }
        return rest.to_string();
    }
    path.to_string()
}

/// Would registering `path` as a recursive scan root be reckless?
///
/// Rejects bare drive roots ("C:", "C:\") and well-known shallow system
/// directories ("C:\Users", "C:\Windows", ...) regardless of drive letter. A
/// bare UNC share ("\\host\share", no subpath) is rejected the same way a
/// bare drive letter is: for UNC, host+share together are the volume, so a
/// subpath is one segment deeper than for a local drive.
///
/// Windows administrative shares alias exactly these same dangerous locations
/// and are unwound before the depth check ever sees them:
/// `\\host\C$\...` *is* `C:\...` on that host, and
/// `\\host\ADMIN$`/`IPC$`/`PRINT$`/`NETLOGON`/`SYSVOL` name Windows-internal
/// shares with no ordinary-data-folder meaning at all.
fn is_dangerously_broad(path: &str) -> bool {
    let raw = strip_verbatim_prefix(path.trim());
    let p = raw.trim_end_matches(['\\', '/']);
    if p.is_empty() {
        return true;
    }
    // Python: `_DRIVE_ROOT_RE.fullmatch(p + ("\\" if not p.endswith(":") else ""))`
    // -- with trailing separators already stripped, that matches exactly the
    // two-char "<letter>:" form.
    let bytes = p.as_bytes();
    if bytes.len() == 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':' {
        return true;
    }
    let is_unc = raw.starts_with("\\\\") || raw.starts_with("//");
    let parts: Vec<&str> = p.split(['\\', '/']).filter(|s| !s.is_empty()).collect();
    if is_unc && parts.len() >= 2 {
        let share = parts[1].trim();
        if DANGEROUS_UNC_SHARE_NAMES.contains(&share.to_ascii_lowercase().as_str()) {
            return true;
        }
        let share_bytes = share.as_bytes();
        if share_bytes.len() == 2 && share_bytes[0].is_ascii_alphabetic() && share_bytes[1] == b'$'
        {
            // "\\host\C$\rest..." aliases "C:\rest...": re-run the local-path
            // rule against the drive it actually points at.
            let rest = parts[2..].join("\\");
            return is_dangerously_broad(&format!("{}:\\{}", &share[..1], rest));
        }
    }
    let min_depth = if is_unc { 3 } else { 2 };
    if parts.len() < min_depth {
        return true;
    }
    if !is_unc && parts.len() == 2 {
        return DANGEROUS_ROOT_NAMES.contains(&parts[1].trim().to_ascii_lowercase().as_str());
    }
    false
}

fn filter_recovery_candidates(payload: &Value) -> Vec<Value> {
    payload
        .get("roots")
        .and_then(Value::as_array)
        .map(|roots| {
            roots
                .iter()
                .filter(
                    |candidate| match candidate.get("path").and_then(Value::as_str) {
                        Some(path) if !is_dangerously_broad(path) => true,
                        Some(path) => {
                            tracing::warn!(
                            "scan_roots recovery: refusing dangerously broad candidate {path:?}"
                        );
                            false
                        }
                        None => false,
                    },
                )
                .cloned()
                .collect()
        })
        .unwrap_or_default()
}

fn recovery_marker_path(state: &SharedState) -> PathBuf {
    crate::secret_store::data_dir(&state.config.project_root).join(RECOVERY_MARKER_NAME)
}

fn read_recovery_marker(path: &Path) -> Value {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .unwrap_or_else(|| json!({}))
}

fn write_recovery_marker(path: &Path, pending: bool) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Err(error) = std::fs::write(path, json!({"pending": pending}).to_string()) {
        tracing::warn!(?error, "Failed to write scan_roots recovery marker");
    }
}

/// GET /api/scan-roots/recovery-check
///
/// The heavy candidate computation (a full `files` table scan, via
/// `build_scanned_roots`) only runs when the marker is present and
/// `scan_roots` is still empty -- unaffected installs never pay for it.
pub async fn recovery_check(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let marker = recovery_marker_path(&state);
    if !marker.exists() {
        return api_result(json!({"pending": false}));
    }
    if !read_recovery_marker(&marker)
        .get("pending")
        .and_then(Value::as_bool)
        .unwrap_or(true)
    {
        return api_result(json!({"pending": false}));
    }

    let config =
        read_config(&state.config.config_path).unwrap_or_else(|_| state.config.app_config.clone());
    if !config_scan_roots(&config).is_empty() {
        // Resolved by other means (manual add, an earlier apply) -- stop asking.
        write_recovery_marker(&marker, false);
        return api_result(json!({"pending": false}));
    }

    let payload = match build_scanned_roots(&state).await {
        Ok(payload) => payload,
        Err(error) => {
            tracing::warn!(?error, "scan_roots recovery: roots summary failed");
            return api_result(json!({"pending": false}));
        }
    };
    let candidates = filter_recovery_candidates(&payload);
    if candidates.is_empty() {
        write_recovery_marker(&marker, false);
        return api_result(json!({"pending": false}));
    }
    api_result(json!({"pending": true, "candidates": candidates}))
}

/// POST /api/scan-roots/recovery-apply
///
/// Candidates are recomputed server-side and used as an allowlist --
/// `paths` (if given) only narrows that set, it never injects an arbitrary
/// path the scan did not itself surface.
pub async fn recovery_apply(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<RecoveryApplyBody>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let requested = body.and_then(|Json(body)| body.paths);

    let payload = match build_scanned_roots(&state).await {
        Ok(payload) => payload,
        Err(error) => {
            tracing::error!(?error, "scan_roots recovery: failed to compute candidates");
            return api_error(
                "Failed to compute recovery candidates",
                "recovery_unavailable",
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    };
    let candidate_paths: Vec<String> = filter_recovery_candidates(&payload)
        .iter()
        .filter_map(|candidate| {
            candidate
                .get("path")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        })
        .collect();

    let selected: Vec<String> = match requested {
        Some(requested) => requested
            .into_iter()
            .filter(|path| candidate_paths.contains(path))
            .collect(),
        None => {
            let mut all = candidate_paths.clone();
            all.sort();
            all.dedup();
            all
        }
    };

    let mut added = Vec::<Value>::new();
    let mut skipped = Vec::<String>::new();
    let mut changed = false;
    {
        let _guard = state.settings_lock.lock().await;
        let mut config = match read_config(&state.config.config_path) {
            Ok(config) => config,
            Err(error) => return internal_error(error, "failed to read config"),
        };
        for raw_path in selected {
            let path = sanitize_path(&raw_path);
            if path.is_empty() {
                skipped.push(raw_path);
                continue;
            }
            let roots = ensure_roots_mut(&mut config);
            let duplicate = roots.iter().any(|root| {
                root.get("path")
                    .and_then(Value::as_str)
                    .is_some_and(|existing| {
                        normalize_for_compare(existing) == normalize_for_compare(&path)
                    })
            });
            if duplicate {
                skipped.push(path);
                continue;
            }
            let new_root = json!({
                "path": path,
                "enabled": true,
                "recursive": true,
                "comment": "auto-recovered (v4.681.6)",
            });
            roots.push(new_root.clone());
            added.push(new_root);
            changed = true;
        }
        if changed {
            if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
                return internal_error(error, "failed to write config");
            }
        }
    }
    if changed {
        notify_scan_roots_changed(&state);
    }

    write_recovery_marker(&recovery_marker_path(&state), false);
    api_result(json!({"added": added, "skipped": skipped}))
}

/// POST /api/scan-roots/recovery-dismiss
pub async fn recovery_dismiss(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    write_recovery_marker(&recovery_marker_path(&state), false);
    api_result(json!({"ok": true}))
}

/// Case- and separator-insensitive comparison key, mirroring Python's
/// `os.path.normcase(path.replace("/", os.sep).replace("\\", os.sep))` in
/// `core/scan_roots_api/ops_write.py::add_scan_root`.
pub(crate) fn normalize_for_compare(path: &str) -> String {
    let unified = path.replace('\\', "/");
    if cfg!(windows) {
        unified.to_lowercase()
    } else {
        unified
    }
}

#[cfg(test)]
mod recovery_tests {
    use super::{is_dangerously_broad, sanitize_path, strip_verbatim_prefix, unquote_path};

    #[test]
    fn rejects_bare_drive_roots() {
        for path in ["C:", "C:\\", "c:/", "  D:\\  ", ""] {
            assert!(is_dangerously_broad(path), "{path:?} must be rejected");
        }
    }

    #[test]
    fn rejects_shallow_system_dirs_on_any_drive() {
        for path in [
            "C:\\Users",
            "c:\\users\\",
            "D:\\Windows",
            "C:/Program Files (x86)",
            "E:\\$Recycle.Bin",
        ] {
            assert!(is_dangerously_broad(path), "{path:?} must be rejected");
        }
    }

    #[test]
    fn accepts_ordinary_library_paths() {
        for path in [
            "C:\\Users\\me\\Pictures",
            "D:\\Photos",
            "/home/me/pictures",
            "\\\\host\\share\\photos",
        ] {
            assert!(!is_dangerously_broad(path), "{path:?} must be accepted");
        }
    }

    #[test]
    fn rejects_bare_unc_share_and_admin_shares() {
        for path in [
            "\\\\host\\share",
            "\\\\host\\IPC$",
            "\\\\host\\admin$\\anything",
            "\\\\host\\C$",
            "\\\\host\\C$\\Users",
        ] {
            assert!(is_dangerously_broad(path), "{path:?} must be rejected");
        }
        // A drive share with a real subpath below the dangerous names is fine.
        assert!(!is_dangerously_broad("\\\\host\\C$\\Photos\\2026"));
    }

    #[test]
    fn verbatim_prefixes_do_not_hide_dangerous_paths() {
        assert_eq!(strip_verbatim_prefix("\\\\?\\C:\\Users"), "C:\\Users");
        assert_eq!(
            strip_verbatim_prefix("\\\\?\\UNC\\host\\share"),
            "\\\\host\\share"
        );
        for path in [
            "\\\\?\\C:\\Users",
            "\\\\.\\C:\\Windows",
            "\\\\?\\UNC\\host\\share",
            "\\\\?\\C:\\",
        ] {
            assert!(is_dangerously_broad(path), "{path:?} must be rejected");
        }
        assert!(!is_dangerously_broad("\\\\?\\C:\\Photos\\2026"));
    }

    /// Windows Explorer's "Copy as path" wraps the path in quotes, and pasting
    /// that stored them verbatim: every root added that way then failed
    /// `canonicalize` with ERROR_INVALID_NAME and the scanner had no roots at
    /// all, silently.
    ///
    /// Python has stripped these since `sanitize_user_path`
    /// (`helpers_text_path.py`); this closes the asymmetry rather than adding
    /// a new rule.
    #[test]
    fn quoted_paths_from_copy_as_path_are_unwrapped() {
        for (raw, want) in [
            (r#""C:\Users\me\Pictures""#, r"C:\Users\me\Pictures"),
            (r#"  "H:\dwhelper"  "#, r"H:\dwhelper"),
            ("'/home/me/pictures'", "/home/me/pictures"),
            // Already clean input is untouched.
            (r"C:\Users\me\Pictures", r"C:\Users\me\Pictures"),
            ("/home/me/pictures", "/home/me/pictures"),
        ] {
            assert_eq!(unquote_path(raw), want, "input {raw:?}");
        }
    }

    /// Only a matched pair is stripped: a quote on one side is part of the
    /// name, and POSIX filenames may contain `"` and `'`.
    #[test]
    fn an_unmatched_quote_is_part_of_the_name() {
        for raw in [
            "/home/me/say \"hi\"",
            "/home/me/\"quoted-start",
            "/home/me/trailing\"",
            "\"",
        ] {
            assert_eq!(unquote_path(raw), raw.trim(), "input {raw:?}");
        }
    }

    #[test]
    fn sanitize_path_unquotes_before_expanding_a_tilde() {
        // The two must compose: a quoted `~/pictures` has to reach the tilde
        // expansion, not stay a literal `~` because the quotes hid it from the
        // prefix check.
        //
        // Asserted against whatever HOME already is rather than setting it:
        // `set_var` is process-wide, and mutating it here made an unrelated
        // test in another module fail when the suite ran together.
        let expected = std::env::var_os("HOME")
            .map(|home| format!("{}/pictures", home.to_string_lossy()))
            .unwrap_or_else(|| "~/pictures".to_string());
        assert_eq!(sanitize_path("\"~/pictures\""), expected);
    }
}

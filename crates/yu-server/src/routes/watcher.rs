use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use serde_json::json;

use crate::ext_config::{read_config, scan_root_configs, ScanRootCfg};
use crate::state::{AppState, SharedState};

/// config.json key for this extension's settings, matching Python's
/// `EXTENSIONS["builtin-auto-scan-watcher"]`.
pub(crate) const WATCHER_EXT_NAME: &str = "builtin-auto-scan-watcher";

/// `enabled` resolved with the same precedence as every other extension
/// (config.json > `extension.json` `config.enabled` > true). A missing
/// manifest -- a source checkout without `extensions/`, or a packaged build
/// that ships the Rust route only -- must not disable the watcher, so it
/// falls back to the config.json value alone.
fn extension_is_enabled(s: &AppState, config: &serde_json::Value) -> bool {
    match crate::routes::extensions_admin::find_extension_manifest(s, WATCHER_EXT_NAME) {
        Some((_, manifest)) => {
            crate::ext_config::resolve_extension_enabled(config, WATCHER_EXT_NAME, &manifest)
        }
        None => crate::ext_config::extension_value(config, WATCHER_EXT_NAME, "enabled")
            .and_then(|v| v.as_bool())
            .unwrap_or(true),
    }
}

/// Enabled scan roots, re-read from config.json rather than taken from the
/// process-wide startup snapshot: scan-root CRUD writes config.json directly
/// without refreshing `config.app_config`, so the snapshot goes stale on the
/// first add/remove/toggle. Python re-reads for the same reason
/// (`_get_roots_and_paths`). The snapshot is the fallback whenever the file
/// cannot be read or carries no `scan_roots` key at all -- an absent key is
/// "nothing on disk to read", not "the user removed every root", and the
/// on-disk file may legitimately not exist yet.
pub fn watcher_roots(s: &AppState) -> Vec<ScanRootCfg> {
    let config = read_config(&s.config.config_path)
        .ok()
        .filter(|c| c.get("scan_roots").is_some())
        .unwrap_or_else(|| s.config.app_config.clone());
    scan_root_configs(&config)
}

pub fn watcher_info_body(s: &AppState) -> serde_json::Value {
    let (running, watched_roots, stats) = s.watcher.info();
    json!({
        "running": running,
        "watched_roots": watched_roots,
        "stats": stats,
    })
}

pub async fn watcher_info(State(s): State<SharedState>) -> impl IntoResponse {
    Json(watcher_info_body(&s))
}

/// Core `auto_scan_start` logic shared by the REST route and the MCP
/// `auto_scan_start` tool. The HTTP status is meaningful only to the REST
/// caller; the MCP tool returns the JSON body as-is regardless of status,
/// matching the Python reference (which surfaces the relayed response body
/// as tool content independent of the underlying HTTP status).
pub fn watcher_start_result(s: &AppState) -> (StatusCode, serde_json::Value) {
    if s.config.safe_mode {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            json!({"ok": false, "error": "safe mode active"}),
        );
    }

    let roots = watcher_roots(s);

    if roots.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            json!({"ok": false, "error": "No scan_roots configured"}),
        );
    }

    match s.watcher.start(
        roots,
        s.db.clone(),
        s.job_manager.clone(),
        s.config.config_path.clone(),
    ) {
        Ok(watched) => (
            StatusCode::OK,
            json!({"ok": true, "watched_roots": watched}),
        ),
        Err(e) if e == "Already running" => {
            (StatusCode::CONFLICT, json!({"ok": false, "error": e}))
        }
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            json!({"ok": false, "error": e}),
        ),
    }
}

pub async fn watcher_start(State(s): State<SharedState>) -> impl IntoResponse {
    let (status, body) = watcher_start_result(&s);
    (status, Json(body)).into_response()
}

/// Boot-time auto-start, mirroring Python's `_on_register`
/// (`extensions/builtin_auto_scan_watcher/auto_scan_watcher.py`), where
/// `auto_start` defaults to true. Failures are logged, never fatal: the
/// watcher is an accelerator for scanning, not a prerequisite for serving.
pub fn auto_start_if_configured(s: &AppState) {
    if s.config.safe_mode {
        return;
    }
    let config = read_config(&s.config.config_path).unwrap_or_else(|_| s.config.app_config.clone());
    // A disabled extension never gets its blueprint registered in Python, so
    // `_on_register` -- and with it the auto-start -- never runs. Honour the
    // same switch here; without it, turning the extension off left the Rust
    // watcher running anyway.
    if !extension_is_enabled(s, &config) {
        tracing::info!("Watcher auto-start skipped: extension disabled");
        return;
    }
    let enabled = crate::ext_config::extension_value(&config, WATCHER_EXT_NAME, "auto_start")
        .and_then(|v| v.as_bool())
        .unwrap_or(true);
    if !enabled {
        return;
    }
    let roots = watcher_roots(s);
    if roots.is_empty() {
        tracing::info!("Watcher auto-start skipped: no enabled scan_roots");
        return;
    }
    match s.watcher.start(
        roots,
        s.db.clone(),
        s.job_manager.clone(),
        s.config.config_path.clone(),
    ) {
        Ok(watched) => tracing::info!("Watcher auto-started: {} roots", watched.len()),
        Err(e) => tracing::warn!("Watcher auto-start failed: {e}"),
    }
}

/// Re-point a running watcher at the current scan_roots. Called after every
/// scan-root mutation, matching Python's SCAN_ROOTS_CHANGED subscriber: a
/// stopped watcher stays stopped, and a running one stops outright once the
/// last enabled root is gone.
pub fn restart_on_roots_changed(s: &AppState) {
    let (running, _, _) = s.watcher.info();
    if !running {
        return;
    }
    let roots = watcher_roots(s);
    if roots.is_empty() {
        s.watcher.stop();
        tracing::info!("Watcher stopped: no enabled scan_roots remain");
        return;
    }
    if let Err(e) = s.watcher.restart(
        roots,
        s.db.clone(),
        s.job_manager.clone(),
        s.config.config_path.clone(),
    ) {
        tracing::warn!("Watcher restart on scan_roots change failed: {e}");
    }
}

pub async fn watcher_stop(State(s): State<SharedState>) -> impl IntoResponse {
    if s.watcher.stop() {
        Json(json!({"ok": true})).into_response()
    } else {
        (
            StatusCode::CONFLICT,
            Json(json!({"ok": false, "error": "Not running"})),
        )
            .into_response()
    }
}

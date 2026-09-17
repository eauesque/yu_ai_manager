//! Scan control endpoints.
//!
//! status/start/cancel/resume/scan-all/dismiss use Rust ScanManager.
//! queue endpoints remain Python forwarders.

use axum::{
    body::Bytes,
    extract::{Extension, Path, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};

use serde::Deserialize;
use serde_json::{json, Map, Value};

use crate::{
    auth::{scope::require_scope, AuthContext},
    routes::scan_api::{api_error, error_body},
    scan_manager::{ScanCmd, ScanError},
    state::SharedState,
};

fn gate(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0), "scan")
}

/// Mirrors Python `api_success`: payload keys remain top-level and `data` is
/// null unless the payload supplies it.
fn success_body(payload: Value) -> Value {
    let data = payload.get("data").cloned().unwrap_or(Value::Null);
    let mut body = Map::from_iter([
        ("ok".to_string(), Value::Bool(true)),
        ("error".to_string(), Value::Null),
        ("data".to_string(), data),
    ]);
    if let Value::Object(payload) = payload {
        body.extend(payload);
    }
    Value::Object(body)
}

fn api_success(payload: Value, status: StatusCode) -> Response {
    (status, Json(success_body(payload))).into_response()
}

/// Mirrors Werkzeug/Quart's `Request.is_json`, which Python's
/// `require_json_dict` gates on: the mimetype (Content-Type before any
/// `;` parameter) must be exactly `application/json` or match
/// `application/*+json`. A missing header and a present-but-wrong header
/// are both `false` -- there is no special case for "absent".
fn is_json_content_type(headers: &HeaderMap) -> bool {
    headers
        .get(axum::http::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .map(|ct| {
            let mimetype = ct
                .split(';')
                .next()
                .unwrap_or("")
                .trim()
                .to_ascii_lowercase();
            mimetype == "application/json"
                || (mimetype.starts_with("application/") && mimetype.ends_with("+json"))
        })
        .unwrap_or(false)
}

/// Mirrors Python's `require_json_dict` (core/infra_core/api_request.py):
/// Content-Type check, then JSON parse, then object-shape check, each with
/// its own `code`. Shared by `/api/scan/start` and `/api/scan-all` so the
/// two endpoints cannot drift into two different error styles.
fn require_json_dict(headers: &HeaderMap, body: &Bytes) -> Result<Map<String, Value>, Response> {
    if !is_json_content_type(headers) {
        return Err(api_error(
            "JSON body is required",
            StatusCode::BAD_REQUEST,
            json!({"code": "invalid_content_type"}),
        ));
    }
    match serde_json::from_slice::<Value>(body) {
        Ok(Value::Object(data)) => Ok(data),
        Ok(_) => Err(api_error(
            "JSON object body is required",
            StatusCode::BAD_REQUEST,
            json!({"code": "invalid_json_object"}),
        )),
        Err(_) => Err(api_error(
            "Invalid JSON body",
            StatusCode::BAD_REQUEST,
            json!({"code": "invalid_json"}),
        )),
    }
}

async fn fwd_get(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "scan_unavailable"})),
        )
            .into_response();
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
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "scan_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .post(&url)
        .header("X-Remote-User", "yu-proxy-auth")
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

async fn fwd_delete(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "scan_unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .delete(&url)
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

/// GET /api/scan/status
pub async fn scan_status(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return api_error("not implemented", StatusCode::NOT_IMPLEMENTED, json!({}));
    };
    api_success(json!(sm.status()), StatusCode::OK)
}

struct StartBody {
    root: String,
    recursive: bool,
    force: bool,
    scan_zips: bool,
}

fn default_true() -> bool {
    true
}

/// Park a request that arrived while a scan was running, mirroring Python's
/// `scan_start_payload` / `run_scan_all_roots`: 202 with the queue position on
/// success, 409 when the same root is already queued or the queue is full.
fn queue_response(s: &SharedState, item: QueueArgs<'_>) -> Response {
    match s.scan_queue.enqueue(
        item.root,
        item.recursive,
        item.force,
        item.scan_zips,
        item.label,
        item.source,
    ) {
        Ok(queued) => {
            let mut payload = json!({
                "status": "queued",
                "queue_id": queued.queue_id,
                "position": s.scan_queue.size(),
            });
            if item.source == "scan-all" {
                payload["success"] = Value::Bool(true);
            }
            api_success(payload, StatusCode::ACCEPTED)
        }
        Err(_) => api_error(
            if item.source == "scan-all" {
                "Scan-all request could not be queued"
            } else {
                "Scan request could not be queued"
            },
            StatusCode::CONFLICT,
            if item.source == "scan-all" {
                json!({})
            } else {
                json!({"code": "queue_error"})
            },
        ),
    }
}

struct QueueArgs<'a> {
    root: &'a str,
    recursive: bool,
    force: bool,
    scan_zips: bool,
    label: &'a str,
    source: &'a str,
}

/// POST /api/scan/start
pub async fn scan_start(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return api_error("not implemented", StatusCode::NOT_IMPLEMENTED, json!({}));
    };
    let data = match require_json_dict(&headers, &body) {
        Ok(data) => data,
        Err(r) => return r,
    };
    let Some(root) = data.get("root").and_then(Value::as_str) else {
        return api_error(
            "root path required",
            StatusCode::BAD_REQUEST,
            json!({"code": "root_required"}),
        );
    };
    let parsed = StartBody {
        root: root.to_string(),
        recursive: data
            .get("recursive")
            .and_then(Value::as_bool)
            .unwrap_or_else(default_true),
        force: data.get("force").and_then(Value::as_bool).unwrap_or(false),
        scan_zips: data
            .get("scan_zips")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    };
    let label = format!("フォルダスキャン: {}", parsed.root);
    scan_core::ipc::clear_scan_state(&s.config.project_root);
    match sm.spawn_worker(
        ScanCmd::Start {
            root: parsed.root.clone(),
            recursive: parsed.recursive,
            force: parsed.force,
            scan_zips: parsed.scan_zips,
            resume: false,
            db_path: s.config.db_path.clone(),
        },
        s.clone(),
    ) {
        Ok(_) => api_success(json!({"status": "started"}), StatusCode::OK),
        Err(ScanError::AlreadyRunning) => queue_response(
            &s,
            QueueArgs {
                root: &parsed.root,
                recursive: parsed.recursive,
                force: parsed.force,
                scan_zips: parsed.scan_zips,
                label: &label,
                source: "api",
            },
        ),
        Err(e) => api_error(&e.to_string(), StatusCode::INTERNAL_SERVER_ERROR, json!({})),
    }
}

/// POST /api/scan/cancel
pub async fn scan_cancel(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return api_error("not implemented", StatusCode::NOT_IMPLEMENTED, json!({}));
    };
    if sm.stop() {
        api_success(
            json!({
                "status": "cancelling",
                "message": cancel_message(sm.is_scan_all()),
            }),
            StatusCode::OK,
        )
    } else {
        api_error(
            "no running scan to cancel",
            StatusCode::NOT_FOUND,
            json!({"code": "scan_not_running"}),
        )
    }
}

/// Selects the exact cancel message Python returns, mirroring
/// `cancel_scan_payload` in `core/scan_api/ops_payloads.py`: a scan-all
/// sweep gets its own Japanese string, a single-root scan gets another.
fn cancel_message(is_scan_all: bool) -> &'static str {
    if is_scan_all {
        "一括スキャン停止を要求しました"
    } else {
        "スキャン停止を要求しました"
    }
}

/// POST /api/scan/resume
pub async fn scan_resume(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    _body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return api_error("not implemented", StatusCode::NOT_IMPLEMENTED, json!({}));
    };
    let state_path = s.config.project_root.join("core").join("scan_state.json");
    let state = match std::fs::read_to_string(state_path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
    {
        Some(Value::Object(state)) if state.contains_key("root") && state.contains_key("total") => {
            state
        }
        _ => {
            return api_error(
                "no interrupted scan",
                StatusCode::NOT_FOUND,
                json!({"code": "no_interrupted_scan"}),
            )
        }
    };
    let root = state
        .get("root")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let recursive = state
        .get("recursive")
        .and_then(Value::as_bool)
        .unwrap_or_else(default_true);
    let scan_zips = state
        .get("scan_zips")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    match sm.spawn_worker(
        ScanCmd::Start {
            root: root.clone(),
            recursive,
            force: false,
            scan_zips,
            resume: true,
            db_path: s.config.db_path.clone(),
        },
        s.clone(),
    ) {
        Ok(_) => api_success(json!({"status": "resumed", "root": root}), StatusCode::OK),
        Err(ScanError::AlreadyRunning) => api_error(
            "scan already running",
            StatusCode::CONFLICT,
            json!({"code": "scan_already_running"}),
        ),
        Err(e) => api_error(&e.to_string(), StatusCode::INTERNAL_SERVER_ERROR, json!({})),
    }
}

/// GET /api/scan/queue
pub async fn scan_queue_list(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    api_success(
        json!({"items": s.scan_queue.list(), "count": s.scan_queue.size()}),
        StatusCode::OK,
    )
}

struct ScanAllBody {
    force: bool,
}

/// POST /api/scan-all
pub async fn scan_all(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return api_error("not implemented", StatusCode::NOT_IMPLEMENTED, json!({}));
    };
    let data = match require_json_dict(&headers, &body) {
        Ok(data) => data,
        Err(r) => return r,
    };
    let parsed = ScanAllBody {
        force: data.get("force").and_then(Value::as_bool).unwrap_or(false),
    };
    scan_core::ipc::clear_scan_state(&s.config.project_root);
    match sm.spawn_worker(
        ScanCmd::ScanAll {
            force: parsed.force,
            db_path: s.config.db_path.clone(),
        },
        s.clone(),
    ) {
        Ok(_) => api_success(
            json!({"success": true, "message": format!("Scanning {} root(s)", crate::scan_native::enabled_roots(&s).len())}),
            StatusCode::OK,
        ),
        Err(ScanError::AlreadyRunning) => queue_response(
            &s,
            QueueArgs {
                root: crate::scan_queue::SCAN_ALL_ROOT,
                recursive: true,
                force: parsed.force,
                scan_zips: true,
                label: "全フォルダスキャン",
                source: "scan-all",
            },
        ),
        Err(ScanError::NoRoots) => {
            api_error("No enabled scan roots", StatusCode::BAD_REQUEST, json!({}))
        }
    }
}

/// POST /api/scan/dismiss
pub async fn scan_dismiss(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let Some(sm) = s.scan_manager.get() else {
        return api_error("not implemented", StatusCode::NOT_IMPLEMENTED, json!({}));
    };
    let _ = sm.dismiss();
    api_success(json!({"status": "dismissed"}), StatusCode::OK)
}

/// POST /api/scan/queue/clear
pub async fn scan_queue_clear(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    _body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let cleared = s.scan_queue.clear();
    api_success(
        json!({"status": "cleared", "cleared": cleared}),
        StatusCode::OK,
    )
}

/// DELETE /api/scan/queue/:queue_id
pub async fn scan_queue_remove(
    State(s): State<SharedState>,
    Path(queue_id): Path<String>,
) -> Response {
    if s.scan_queue.remove(&queue_id) {
        api_success(json!({"status": "removed"}), StatusCode::OK)
    } else {
        api_error(
            "item not found",
            StatusCode::NOT_FOUND,
            json!({"code": "not_found"}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// What this checks and what it does NOT: this only verifies that
    /// `success_body` wraps an arbitrary payload in the `{ok, error, data}`
    /// envelope correctly. It builds `expected` from the same `payload` it
    /// feeds `success_body`, so it cannot fail on the payload's *content* --
    /// a fixture like `"スキャン停止を要求しました"` here is exercising the
    /// envelope, not pinning that string. The literal Japanese messages are
    /// pinned separately, against Python, by
    /// `scan_cancel_message_matches_python` below.
    #[test]
    fn scan_success_shapes_match_python_api_result() {
        for payload in [
            json!({"status": "started"}),
            json!({"status": "cancelling", "message": "スキャン停止を要求しました"}),
            json!({"status": "cancelling", "message": "一括スキャン停止を要求しました"}),
            json!({"status": "resumed", "root": "/tmp/root"}),
            json!({"items": [], "count": 0}),
            json!({"success": true, "message": "Scanning 1 root(s)"}),
            json!({"status": "dismissed"}),
            json!({"status": "cleared", "cleared": 0}),
            json!({"status": "removed"}),
        ] {
            let mut expected = payload.clone();
            expected["ok"] = Value::Bool(true);
            expected["error"] = Value::Null;
            expected["data"] = Value::Null;
            assert_eq!(success_body(payload), expected);
        }
    }

    #[test]
    fn scan_error_shapes_match_python_api_result() {
        assert_eq!(
            error_body("root path required", json!({"code": "root_required"})),
            json!({"ok": false, "error": "root path required", "code": "root_required"}),
        );
        assert_eq!(
            error_body(
                "no running scan to cancel",
                json!({"code": "scan_not_running"})
            ),
            json!({"ok": false, "error": "no running scan to cancel", "code": "scan_not_running"}),
        );
        assert_eq!(
            error_body(
                "no interrupted scan",
                json!({"code": "no_interrupted_scan"})
            ),
            json!({"ok": false, "error": "no interrupted scan", "code": "no_interrupted_scan"}),
        );
        assert_eq!(
            error_body(
                "scan already running",
                json!({"code": "scan_already_running"})
            ),
            json!({"ok": false, "error": "scan already running", "code": "scan_already_running"}),
        );
        assert_eq!(
            error_body("item not found", json!({"code": "not_found"})),
            json!({"ok": false, "error": "item not found", "code": "not_found"}),
        );
        assert_eq!(
            error_body("not implemented", json!({})),
            json!({"ok": false, "error": "not implemented"}),
        );
    }

    /// Gap 1(a): pins the exact Japanese strings `scan_cancel` selects,
    /// copied byte-for-byte from `cancel_scan_payload` in
    /// `core/scan_api/ops_payloads.py` (NOT from the Rust source under
    /// test) so this cannot pin the bug instead of the behaviour.
    #[test]
    fn scan_cancel_message_matches_python() {
        assert_eq!(cancel_message(false), "スキャン停止を要求しました");
        assert_eq!(cancel_message(true), "一括スキャン停止を要求しました");
    }

    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::scan_manager::ScanManager;
    use crate::state::{AppState, Config};

    async fn raw_test_state() -> SharedState {
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
                    rate_limit_trusted_proxies: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("nonexistent-config.json"),
                    project_root: PathBuf::from("."),
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
                    wd_tagger_root: std::path::PathBuf::from("."),
                    clip_model_dir: std::path::PathBuf::from("."),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    /// A `SharedState` with `scan_manager` initialised, for handlers that
    /// short-circuit on `scan_manager.get()` being `None`.
    async fn test_state() -> SharedState {
        let state = raw_test_state().await;
        state
            .scan_manager
            .set(Arc::new(ScanManager::new(
                state.config.project_root.clone(),
            )))
            .ok();
        state
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    fn json_headers() -> HeaderMap {
        let mut h = HeaderMap::new();
        h.insert(
            axum::http::header::CONTENT_TYPE,
            "application/json".parse().unwrap(),
        );
        h
    }

    #[tokio::test]
    async fn scan_cancel_returns_message_for_running_scan_kind() {
        for (is_scan_all, message) in [
            (false, "スキャン停止を要求しました"),
            (true, "一括スキャン停止を要求しました"),
        ] {
            let state = raw_test_state().await;
            let manager = Arc::new(ScanManager::new(state.config.project_root.clone()));
            manager.set_test_running(is_scan_all);
            state.scan_manager.set(manager).ok();

            let response = scan_cancel(State(state), None, Bytes::new()).await;
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(json_body(response).await["message"], json!(message));
        }
    }

    /// Gap 3: an absent Content-Type must be rejected exactly like Python's
    /// `require_json_dict` (`request.is_json` is false with no header).
    #[tokio::test]
    async fn scan_start_rejects_missing_content_type() {
        let response = scan_start(
            State(test_state().await),
            None,
            HeaderMap::new(),
            Bytes::from_static(br#"{"root": "/tmp/x"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "JSON body is required", "code": "invalid_content_type"})
        );
    }

    /// Gap 3: a wrong (non-JSON) Content-Type is rejected the same way as a
    /// missing one -- Python's `is_json` has no special case for "absent".
    #[tokio::test]
    async fn scan_start_rejects_wrong_content_type() {
        let mut headers = HeaderMap::new();
        headers.insert(
            axum::http::header::CONTENT_TYPE,
            "text/plain".parse().unwrap(),
        );
        let response = scan_start(
            State(test_state().await),
            None,
            headers,
            Bytes::from_static(br#"{"root": "/tmp/x"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "JSON body is required", "code": "invalid_content_type"})
        );
    }

    /// Gap 3: malformed JSON with the right Content-Type gets Python's
    /// `invalid_json` code, not `invalid_content_type`.
    #[tokio::test]
    async fn scan_start_rejects_malformed_json() {
        let response = scan_start(
            State(test_state().await),
            None,
            json_headers(),
            Bytes::from_static(b"{not json"),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "Invalid JSON body", "code": "invalid_json"})
        );
    }

    /// Gap 2/3: a well-formed but non-object JSON body is rejected, matching
    /// Python's `invalid_json_object` code.
    #[tokio::test]
    async fn scan_start_rejects_non_object_json() {
        let response = scan_start(
            State(test_state().await),
            None,
            json_headers(),
            Bytes::from_static(b"[]"),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "JSON object body is required", "code": "invalid_json_object"})
        );
    }

    /// Gap 2: `/api/scan-all` used to `unwrap_or` a default on any
    /// unparsable body, silently starting a scan with `force=false`. It must
    /// now 400 like Python instead.
    #[tokio::test]
    async fn scan_all_rejects_malformed_body() {
        let response = scan_all(
            State(test_state().await),
            None,
            json_headers(),
            Bytes::from_static(b"not json at all"),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "Invalid JSON body", "code": "invalid_json"})
        );
    }

    /// Gap 3: `/api/scan-all` never inspected Content-Type at all before.
    #[tokio::test]
    async fn scan_all_rejects_missing_content_type() {
        let response = scan_all(
            State(test_state().await),
            None,
            HeaderMap::new(),
            Bytes::from_static(b"{}"),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "JSON body is required", "code": "invalid_content_type"})
        );
    }

    /// Gap 4: the "scan_manager not initialised" 501 fallback must go
    /// through `error_body()` like every other error response.
    #[tokio::test]
    async fn scan_status_not_implemented_uses_error_body_shape() {
        // scan_manager left unset -- the "not implemented" branch.
        let bare = raw_test_state().await;
        let response = scan_status(State(bare), None).await;
        assert_eq!(response.status(), StatusCode::NOT_IMPLEMENTED);
        let body = json_body(response).await;
        assert_eq!(body, json!({"ok": false, "error": "not implemented"}));
    }

    /// A `SharedState` with `pin_auth_enabled: true` (and `scan_manager`
    /// initialised), for the scope-gate tests below -- `test_state()` /
    /// `raw_test_state()` hardcode `pin_auth_enabled: false`, under which
    /// `gate()` always passes regardless of scope.
    async fn gated_test_state() -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
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
                    rate_limit_trusted_proxies: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: true,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("nonexistent-config.json"),
                    project_root: PathBuf::from("."),
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
                    wd_tagger_root: std::path::PathBuf::from("."),
                    clip_model_dir: std::path::PathBuf::from("."),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        );
        state
            .scan_manager
            .set(Arc::new(ScanManager::new(
                state.config.project_root.clone(),
            )))
            .ok();
        state
    }

    fn non_admin_auth() -> Option<Extension<AuthContext>> {
        Some(Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["read".to_string()]),
        }))
    }

    fn admin_auth() -> Option<Extension<AuthContext>> {
        Some(Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["admin".to_string()]),
        }))
    }

    /// Gap: `scan_dismiss` skipped `gate()` entirely, so a non-admin API key
    /// could clear interrupted-scan state. This must now 403 with the exact
    /// same body shape every sibling handler in this file returns.
    #[tokio::test]
    async fn scan_dismiss_rejects_non_admin_scope() {
        let response = scan_dismiss(
            State(gated_test_state().await),
            non_admin_auth(),
            Bytes::new(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "Insufficient scope: requires 'scan'"})
        );
    }

    #[tokio::test]
    async fn scan_dismiss_allows_admin_scope() {
        let response =
            scan_dismiss(State(gated_test_state().await), admin_auth(), Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": true, "error": null, "data": null, "status": "dismissed"})
        );
    }

    /// PIN-authenticated browser sessions carry an `AuthContext` whose
    /// `reason` is not `"api_key"` (e.g. `"session"`/`"cookie"`), matching
    /// Python's `require_admin_scope()` passing requests through when
    /// `request.api_key_info` is absent -- see
    /// `require_admin_scope_allows_pin_session_context` in `auth/scope.rs`
    /// for the same convention.
    #[tokio::test]
    async fn scan_dismiss_allows_pin_session_with_no_auth_context() {
        let pin_session = Some(Extension(AuthContext {
            reason: "session".to_string(),
            scopes: None,
        }));
        let response =
            scan_dismiss(State(gated_test_state().await), pin_session, Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
    }

    /// Gap: `scan_queue_clear` skipped `gate()` entirely, so a non-admin API
    /// key could empty the scan queue.
    #[tokio::test]
    async fn scan_queue_clear_rejects_non_admin_scope() {
        let response = scan_queue_clear(
            State(gated_test_state().await),
            non_admin_auth(),
            Bytes::new(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "Insufficient scope: requires 'scan'"})
        );
    }

    #[tokio::test]
    async fn scan_queue_clear_allows_admin_scope() {
        let response =
            scan_queue_clear(State(gated_test_state().await), admin_auth(), Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": true, "error": null, "data": null, "status": "cleared", "cleared": 0})
        );
    }

    /// Gap: `scan_all` skipped `gate()` entirely, so a non-admin API key
    /// could kick off a scan across every root.
    #[tokio::test]
    async fn scan_all_rejects_non_admin_scope() {
        let response = scan_all(
            State(gated_test_state().await),
            non_admin_auth(),
            json_headers(),
            Bytes::from_static(b"{}"),
        )
        .await;
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({"ok": false, "error": "Insufficient scope: requires 'scan'"})
        );
    }

    #[tokio::test]
    async fn scan_all_allows_admin_scope() {
        let response = scan_all(
            State(gated_test_state().await),
            admin_auth(),
            json_headers(),
            Bytes::from_static(b"{}"),
        )
        .await;
        // No enabled roots in the bare test state, so the handler reaches
        // past the gate and returns its own 400 -- proof the gate did not
        // swallow the request.
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body, json!({"ok": false, "error": "No enabled scan roots"}));
    }
}

#[derive(Deserialize)]
struct PurgeBody {
    root: String,
}

/// POST /api/scanned-roots/purge
pub async fn scanned_roots_purge(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let root: String = match serde_json::from_slice::<PurgeBody>(&body) {
        Ok(b) => b.root,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"ok": false, "error": "missing root"})),
            )
                .into_response();
        }
    };
    if root.trim().is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "empty root"})),
        )
            .into_response();
    }
    // Escape LIKE metacharacters ('%' and '_') so user input cannot widen the pattern.
    fn escape_like(s: &str) -> String {
        s.replace('%', "\\%").replace('_', "\\_")
    }
    let fwd = escape_like(&root.replace('\\', "/"));
    let bwd = escape_like(&root.replace('/', "\\"));
    let like_fwd = format!("{}/%", fwd.trim_end_matches('/'));
    let like_bwd = format!("{}\\%", bwd.trim_end_matches('\\'));

    let res = sqlx::query(
        "UPDATE files SET extracted_to_file_id = NULL \
         WHERE extracted_to_file_id IN \
           (SELECT id FROM files WHERE path LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\')",
    )
    .bind(&like_fwd)
    .bind(&like_bwd)
    .execute(&s.db)
    .await;
    if let Err(e) = res {
        tracing::error!("scanned_roots_purge UPDATE: {e}");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "db_error"})),
        )
            .into_response();
    }

    match sqlx::query("DELETE FROM files WHERE path LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\'")
        .bind(&like_fwd)
        .bind(&like_bwd)
        .execute(&s.db)
        .await
    {
        Ok(r) => {
            Json(json!({"ok": true, "purged": r.rows_affected(), "pruned_tags": 0})).into_response()
        }
        Err(e) => {
            tracing::error!("scanned_roots_purge DELETE: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

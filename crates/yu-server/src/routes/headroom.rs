use axum::extract::Query;
use axum::http::StatusCode;
use axum::{extract::State, response::IntoResponse, Extension, Json};
use serde_json::json;
use std::collections::HashMap;
use std::time::Duration;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::config_io::{load as load_config_json, validate_base_url, write as write_config_json};
use crate::state::SharedState;

const DEFAULT_BASE_URL: &str = "http://127.0.0.1:8787";
const TIMEOUT_SECS: u64 = 5;

fn upstream_base(state: &SharedState) -> String {
    state
        .config
        .app_config
        .pointer("/gateway/backends/headroom/base_url")
        .and_then(|v| v.as_str())
        .unwrap_or(DEFAULT_BASE_URL)
        .trim_end_matches('/')
        .to_string()
}

async fn fetch(base: &str, path: &str) -> impl IntoResponse {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .build()
        .expect("failed to build headroom client");
    let url = format!("{base}{path}");
    match client.get(&url).send().await {
        Ok(resp) => {
            let status =
                StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            let body: serde_json::Value = resp.json().await.unwrap_or(json!({}));
            (status, Json(body)).into_response()
        }
        Err(e) if e.is_connect() => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error": format!("headroom not reachable at {base}"), "code": "offline"})),
        )
            .into_response(),
        Err(e) if e.is_timeout() => (
            StatusCode::GATEWAY_TIMEOUT,
            Json(json!({"error": "headroom timed out", "code": "timeout"})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({"error": e.to_string(), "code": "error"})),
        )
            .into_response(),
    }
}

/// GET /api/headroom/livez
pub async fn headroom_livez(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    fetch(&upstream_base(&state), "/livez")
        .await
        .into_response()
}

/// GET /api/headroom/readyz
pub async fn headroom_readyz(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    fetch(&upstream_base(&state), "/readyz")
        .await
        .into_response()
}

/// GET /api/headroom/health
pub async fn headroom_health(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    fetch(&upstream_base(&state), "/health")
        .await
        .into_response()
}

/// GET /api/headroom/stats
pub async fn headroom_stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    fetch(&upstream_base(&state), "/stats")
        .await
        .into_response()
}

/// GET /api/headroom/stats-history
pub async fn headroom_stats_history(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    let base = upstream_base(&state);
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .build()
        .expect("failed to build headroom client");
    let url = format!("{base}/stats-history");
    match client.get(&url).query(&params).send().await {
        Ok(resp) => {
            let status =
                StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            let body: serde_json::Value = resp.json().await.unwrap_or(json!({}));
            (status, Json(body)).into_response()
        }
        Err(e) if e.is_connect() => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error": format!("headroom not reachable at {base}"), "code": "offline"})),
        )
            .into_response(),
        Err(e) if e.is_timeout() => (
            StatusCode::GATEWAY_TIMEOUT,
            Json(json!({"error": "headroom timed out", "code": "timeout"})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({"error": e.to_string(), "code": "error"})),
        )
            .into_response(),
    }
}

/// GET /api/headroom/metrics
pub async fn headroom_metrics(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    fetch(&upstream_base(&state), "/metrics")
        .await
        .into_response()
}

/// GET /api/gateway/headroom/config
pub async fn headroom_config(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }

    let cfg = load_config_json(&state.config.config_path);
    let hr = &cfg["gateway"]["backends"]["headroom"];
    // Python defaults a MISSING base_url to the default URL and only then validates
    // (`hr_cfg.get("base_url", _DEFAULT_BASE_URL)`), so an absent key is valid, not
    // invalid. Reading it as "" called an unconfigured backend broken.
    let stored_url = hr["base_url"].as_str().unwrap_or(DEFAULT_BASE_URL);

    // Python reports only WHETHER a key is configured, never the key itself
    // (routes/headroom_api.py). Returning the stored secret here handed it to every
    // caller that cleared the admin scope check.
    let auth_key_configured = hr["auth_key"]
        .as_str()
        .map(|key| !key.is_empty())
        .unwrap_or(false);

    // Python validates the stored URL and falls back to the default with
    // `config_status: "invalid"` rather than echoing an unusable value. The rule lives
    // in `config_io::validate_base_url` -- which the PUT already uses, and which this
    // file already imports. A second copy here is how two checks drift apart.
    let valid = validate_base_url(stored_url).is_ok();
    if valid {
        Json(json!({
            "base_url": stored_url,
            "auth_key_configured": auth_key_configured,
        }))
        .into_response()
    } else {
        Json(json!({
            "base_url": DEFAULT_BASE_URL,
            "auth_key_configured": auth_key_configured,
            "config_status": "invalid",
        }))
        .into_response()
    }
}

/// PUT /api/gateway/headroom/config
pub async fn gateway_headroom_config_put(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<serde_json::Value>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    let body = body.map(|Json(v)| v).unwrap_or_default();
    let base_url_raw = body["base_url"].as_str().unwrap_or("").to_string();
    let auth_key = body["auth_key"].as_str().unwrap_or("").trim().to_string();

    let base_url = match validate_base_url(&base_url_raw) {
        Ok(u) => u,
        Err(msg) => return (StatusCode::BAD_REQUEST, Json(json!({"error": msg}))).into_response(),
    };

    let mut config = load_config_json(&state.config.config_path);
    config["gateway"]["backends"]["headroom"]["base_url"] = json!(base_url);
    config["gateway"]["backends"]["headroom"]["auth_key"] = json!(auth_key);
    if let Err(e) = write_config_json(&state.config.config_path, &config) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response();
    }

    // Python echoes only whether a key is now configured, never the key itself
    // (routes/headroom_api.py). Returning it on write is the same leak as the GET.
    Json(json!({
        "base_url": base_url,
        "auth_key_configured": !auth_key.is_empty(),
    }))
    .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use axum::response::IntoResponse;
    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::collections::HashSet;
    use std::path::PathBuf;
    use std::str::FromStr;
    use std::sync::Arc;

    use crate::state::{AppState, Config};

    async fn test_state_with_config_path(
        app_config: serde_json::Value,
        config_path: std::path::PathBuf,
    ) -> SharedState {
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
                    quick_lock_enabled: false,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path,
                    project_root: PathBuf::from("."),
                    app_config,
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                    mcp_native: false,
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

    async fn json_body(response: axum::response::Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    /// Python answers `auth_key_configured` -- whether a key is set -- and never the
    /// key itself (routes/headroom_api.py). This test used to assert the opposite,
    /// pinning the leak in place: the suite stayed green precisely because the
    /// assertion encoded the wrong contract.
    #[tokio::test]
    async fn headroom_config_reports_whether_a_key_is_set_never_the_key() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        std::fs::write(
            &config_path,
            serde_json::to_string(&json!({
                "gateway": {
                    "backends": {
                        "headroom": {
                            "base_url": "http://headroom.example.test",
                            "auth_key": "secret-key"
                        }
                    }
                }
            }))
            .unwrap(),
        )
        .unwrap();

        let state = test_state_with_config_path(json!({}), config_path).await;
        let response = headroom_config(State(state), None).await.into_response();

        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(
            body,
            json!({
                "base_url": "http://headroom.example.test",
                "auth_key_configured": true,
            })
        );
        // Belt and braces: the stored value must not appear anywhere in the body.
        assert!(
            !serde_json::to_string(&body).unwrap().contains("secret-key"),
            "the stored auth key leaked into the response: {body}"
        );
    }

    /// An unset key reports false rather than an empty string, and an unusable stored
    /// URL falls back to the default with `config_status: "invalid"` -- both are
    /// Python's behaviour.
    #[tokio::test]
    async fn headroom_config_marks_an_unusable_base_url_invalid() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        std::fs::write(
            &config_path,
            serde_json::to_string(&json!({
                "gateway": {"backends": {"headroom": {"base_url": "not a url"}}}
            }))
            .unwrap(),
        )
        .unwrap();

        let state = test_state_with_config_path(json!({}), config_path).await;
        let body = json_body(headroom_config(State(state), None).await.into_response()).await;
        assert_eq!(body["base_url"], DEFAULT_BASE_URL, "body: {body}");
        assert_eq!(body["auth_key_configured"], false);
        assert_eq!(body["config_status"], "invalid");
    }

    #[tokio::test]
    async fn headroom_config_returns_defaults_when_config_has_no_headroom_section() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        let state = test_state_with_config_path(json!({}), config_path).await;
        let response = headroom_config(State(state), None).await.into_response();

        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["base_url"], DEFAULT_BASE_URL);
        // No key set reports false, not an empty string -- and never the value.
        assert_eq!(body["auth_key_configured"], false);
        assert!(body.get("auth_key").is_none(), "body: {body}");
    }

    #[tokio::test]
    async fn headroom_config_put_validates_empty_base_url() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        let state = test_state_with_config_path(json!({}), config_path).await;
        let response = gateway_headroom_config_put(
            State(state),
            None,
            Some(Json(json!({"base_url": "", "auth_key": "key"}))),
        )
        .await
        .into_response();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn headroom_config_put_validates_invalid_scheme() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        let state = test_state_with_config_path(json!({}), config_path).await;
        let response = gateway_headroom_config_put(
            State(state),
            None,
            Some(Json(
                json!({"base_url": "ftp://example.com", "auth_key": ""}),
            )),
        )
        .await
        .into_response();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn headroom_config_put_writes_and_get_reads_back() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        let state = test_state_with_config_path(json!({}), config_path.clone()).await;

        let put_resp = gateway_headroom_config_put(
            State(state.clone()),
            None,
            Some(Json(
                json!({"base_url": "http://127.0.0.1:8788", "auth_key": "my-key"}),
            )),
        )
        .await
        .into_response();
        assert_eq!(put_resp.status(), StatusCode::OK);
        let put_body = json_body(put_resp).await;
        assert_eq!(put_body["base_url"], "http://127.0.0.1:8788");
        // Python echoes `auth_key_configured` on write too, never the key. This
        // assertion used to require the key -- the fourth test in this file that was
        // holding the leak in place.
        assert_eq!(put_body["auth_key_configured"], true);
        assert!(
            !serde_json::to_string(&put_body).unwrap().contains("my-key"),
            "the auth key was echoed back on write: {put_body}"
        );

        let get_resp = headroom_config(State(state), None).await.into_response();
        assert_eq!(get_resp.status(), StatusCode::OK);
        let get_body = json_body(get_resp).await;
        assert_eq!(get_body["base_url"], "http://127.0.0.1:8788");
        // The GET reports that a key is configured; it must not hand it back.
        assert_eq!(get_body["auth_key_configured"], true);
        assert!(
            !serde_json::to_string(&get_body).unwrap().contains("my-key"),
            "the stored auth key leaked into the GET response: {get_body}"
        );
    }
}

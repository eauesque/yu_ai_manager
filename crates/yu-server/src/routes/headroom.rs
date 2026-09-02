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
    let base_url = hr["base_url"]
        .as_str()
        .unwrap_or(DEFAULT_BASE_URL)
        .to_string();
    let auth_key = hr["auth_key"].as_str().unwrap_or("").to_string();
    Json(json!({"base_url": base_url, "auth_key": auth_key})).into_response()
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

    Json(json!({"base_url": base_url, "auth_key": auth_key})).into_response()
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

    #[tokio::test]
    async fn headroom_config_reads_base_url_and_auth_key_from_disk() {
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
        assert_eq!(
            json_body(response).await,
            json!({"base_url": "http://headroom.example.test", "auth_key": "secret-key"})
        );
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
        assert_eq!(body["auth_key"], "");
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
        assert_eq!(put_body["auth_key"], "my-key");

        let get_resp = headroom_config(State(state), None).await.into_response();
        assert_eq!(get_resp.status(), StatusCode::OK);
        let get_body = json_body(get_resp).await;
        assert_eq!(get_body["base_url"], "http://127.0.0.1:8788");
        assert_eq!(get_body["auth_key"], "my-key");
    }
}

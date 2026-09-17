use axum::{
    body::Bytes, extract::State, http::StatusCode, response::IntoResponse, Extension, Json,
};
use serde_json::json;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::state::SharedState;

/// GET /api/svg/info
pub async fn svg_info(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    if state.config.python_url.is_empty() {
        return Json(json!({"available": false, "backend": null})).into_response();
    }
    let url = format!(
        "{}/api/svg/info",
        state.config.python_url.trim_end_matches('/')
    );
    match state
        .python_client
        .get(&url)
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
        .send()
        .await
    {
        Ok(response) => {
            let status = response.status();
            response.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |body| (status, body).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

/// POST /api/svg/rasterize — admin scope required
pub async fn svg_rasterize(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> axum::response::Response {
    if let Some(r) = require_admin_scope(state.config.pin_auth_enabled, auth.as_ref().map(|c| &c.0))
    {
        return r;
    }
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "unavailable"})),
        )
            .into_response();
    }
    let url = format!(
        "{}/api/svg/rasterize",
        state.config.python_url.trim_end_matches('/')
    );
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

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use axum::extract::State;
    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::collections::HashSet;
    use std::path::PathBuf;
    use std::str::FromStr;
    use std::sync::Arc;

    use crate::state::{AppState, Config, SharedState};

    async fn test_state(python_url: String) -> SharedState {
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
                    python_url,
                    config_path: PathBuf::from("config.json"),
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

    async fn json_body(response: axum::response::Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn svg_info_returns_unavailable_without_backend() {
        let response = svg_info(State(test_state(String::new()).await), None)
            .await
            .into_response();
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        assert_eq!(
            json_body(response).await,
            json!({"available": false, "backend": null})
        );
    }

    #[tokio::test]
    async fn svg_info_forwards_python_availability() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};

        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = [0; 1024];
            let size = stream.read(&mut request).await.unwrap();
            assert!(std::str::from_utf8(&request[..size])
                .unwrap()
                .starts_with("GET /api/svg/info HTTP/1.1"));
            stream
                .write_all(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 36\r\nConnection: close\r\n\r\n{\"available\":true,\"backend\":\"resvg\"}",
                )
                .await
                .unwrap();
        });

        let response = svg_info(State(test_state(format!("http://{address}")).await), None)
            .await
            .into_response();
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        assert_eq!(
            json_body(response).await,
            json!({"available": true, "backend": "resvg"})
        );
    }
}

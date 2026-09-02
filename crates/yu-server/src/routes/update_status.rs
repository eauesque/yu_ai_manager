use axum::{extract::State, response::IntoResponse, Extension, Json};
use serde_json::{json, Value};
use std::path::Path;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::state::SharedState;

fn api_success(payload: Value) -> axum::response::Response {
    let mut body = json!({"ok": true, "error": null, "data": null});
    if let (Some(dst), Some(src)) = (body.as_object_mut(), payload.as_object()) {
        for (key, value) in src {
            dst.insert(key.clone(), value.clone());
        }
    }
    Json(body).into_response()
}

fn detect_install_type_with_env(
    project_root: &Path,
    tauri_pin_set: bool,
    docker_container_set: bool,
    docker_env_exists: bool,
) -> &'static str {
    if tauri_pin_set {
        return "tauri";
    }
    if docker_env_exists || docker_container_set {
        return "docker";
    }
    if project_root.join(".git").exists() {
        return "git";
    }
    if project_root.join("python").join("python.exe").exists() {
        return "portable";
    }
    "unknown"
}

pub(crate) fn detect_install_type(project_root: &Path) -> &'static str {
    detect_install_type_with_env(
        project_root,
        std::env::var("YU_TAURI_PIN").is_ok(),
        std::env::var("DOCKER_CONTAINER").is_ok(),
        Path::new("/.dockerenv").exists(),
    )
}

/// GET /api/system/update/status
pub async fn update_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }

    let version = std::fs::read_to_string(state.config.project_root.join("VERSION"))
        .unwrap_or_default()
        .trim()
        .to_string();
    api_success(json!({
        "install_type": detect_install_type(&state.config.project_root),
        "update_in_progress": false,
        "version": version,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use axum::extract::State;
    use axum::response::IntoResponse;
    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::collections::HashSet;
    use std::path::{Path, PathBuf};
    use std::str::FromStr;
    use std::sync::Arc;
    use tempfile::TempDir;

    use crate::state::{AppState, Config, SharedState};

    async fn test_state(project_root: PathBuf) -> SharedState {
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
                    config_path: PathBuf::from("config.json"),
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

    async fn json_body(response: axum::response::Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    fn temp_project(version: &str) -> TempDir {
        let root = tempfile::tempdir().unwrap();
        std::fs::write(root.path().join("VERSION"), version).unwrap();
        root
    }

    #[tokio::test]
    async fn update_status_returns_python_success_shape() {
        let root = temp_project("9.8.7\n");
        let expected_install_type = detect_install_type(root.path());
        let response = update_status(State(test_state(root.path().to_path_buf()).await), None)
            .await
            .into_response();
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        assert_eq!(
            json_body(response).await,
            json!({
                "ok": true,
                "error": null,
                "data": null,
                "install_type": expected_install_type,
                "update_in_progress": false,
                "version": "9.8.7"
            })
        );
    }

    #[test]
    fn detect_install_type_prefers_tauri_then_docker_then_git_then_portable() {
        let root = tempfile::tempdir().unwrap();
        std::fs::create_dir(root.path().join(".git")).unwrap();
        std::fs::create_dir(root.path().join("python")).unwrap();
        std::fs::write(root.path().join("python").join("python.exe"), "").unwrap();
        assert_eq!(
            detect_install_type_with_env(root.path(), true, true, true),
            "tauri"
        );
        assert_eq!(
            detect_install_type_with_env(root.path(), false, true, false),
            "docker"
        );
        assert_eq!(
            detect_install_type_with_env(root.path(), false, false, true),
            "docker"
        );
        assert_eq!(
            detect_install_type_with_env(root.path(), false, false, false),
            "git"
        );
    }

    #[test]
    fn detect_install_type_falls_back_to_portable() {
        let root = tempfile::tempdir().unwrap();
        std::fs::create_dir(root.path().join("python")).unwrap();
        std::fs::write(root.path().join("python").join("python.exe"), "").unwrap();
        assert_eq!(
            detect_install_type_with_env(Path::new(root.path()), false, false, false),
            "portable"
        );
    }
}

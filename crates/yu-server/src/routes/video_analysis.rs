use std::{
    env, fs,
    path::{Path, PathBuf},
};

use axum::{
    extract::{Extension, State},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Map, Value};
use sqlx::SqlitePool;

use crate::config_io::load as load_config_json;
use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

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

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn default_video_config() -> Map<String, Value> {
    Map::from_iter([
        ("enabled".to_string(), json!(true)),
        ("keyframe_count".to_string(), json!(4)),
        ("strategy".to_string(), json!("uniform")),
        ("scene_threshold".to_string(), json!(0.4)),
        ("store_per_keyframe".to_string(), json!(false)),
    ])
}

pub(crate) fn merged_video_config(config: &Value) -> Value {
    let mut merged = default_video_config();
    if let Some(user) = config.get("video_analysis").and_then(Value::as_object) {
        for (key, value) in user {
            merged.insert(key.clone(), value.clone());
        }
    }
    Value::Object(merged)
}

pub(crate) fn check_ffmpeg() -> bool {
    let Some(path) = env::var_os("PATH") else {
        return false;
    };
    env::split_paths(&path).any(|dir| {
        let candidate = dir.join("ffmpeg");
        candidate.is_file()
    })
}

async fn video_status(pool: &SqlitePool) -> Value {
    let video_files = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0
         AND file_ext IN ('.mp4','.webm','.avi','.mov','.mkv','.m4v','.ogv')",
    )
    .fetch_one(pool)
    .await
    .unwrap_or(0);
    let files_with_keyframes =
        sqlx::query_scalar::<_, i64>("SELECT COUNT(DISTINCT file_id) FROM file_keyframes")
            .fetch_one(pool)
            .await
            .unwrap_or(0);
    json!({
        "ffmpeg": check_ffmpeg(),
        "video_files": video_files,
        "files_with_keyframes": files_with_keyframes,
    })
}

pub async fn config(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    api_result(json!({"config": merged_video_config(&load_config_json(&state.config.config_path))}))
}

pub async fn status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    api_result(video_status(&state.db_read).await)
}

pub async fn config_save(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(data) = body.as_object() else {
        return (
            axum::http::StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "JSON object required", "code": "invalid_json"})),
        )
            .into_response();
    };

    let allowed = [
        "enabled",
        "keyframe_count",
        "strategy",
        "scene_threshold",
        "store_per_keyframe",
    ];
    let mut filtered: serde_json::Map<String, serde_json::Value> = serde_json::Map::new();
    for key in &allowed {
        if let Some(v) = data.get(*key) {
            filtered.insert(key.to_string(), v.clone());
        }
    }

    // Validate booleans
    for key in &["enabled", "store_per_keyframe"] {
        if let Some(v) = filtered.get(*key) {
            if !v.is_boolean() {
                return (
                    axum::http::StatusCode::BAD_REQUEST,
                    Json(json!({"ok": false, "error": format!("{key} must be a boolean"), "code": "invalid_value"})),
                ).into_response();
            }
        }
    }
    // Validate keyframe_count
    if let Some(v) = filtered.get("keyframe_count") {
        let n = v.as_i64().unwrap_or(-1);
        if !(1..=16).contains(&n) {
            return (
                axum::http::StatusCode::BAD_REQUEST,
                Json(json!({"ok": false, "error": "keyframe_count must be an integer between 1 and 16", "code": "invalid_value"})),
            ).into_response();
        }
    }
    // Validate strategy
    if let Some(v) = filtered.get("strategy") {
        let s = v.as_str().unwrap_or("");
        if !matches!(s, "uniform" | "scene" | "single") {
            return (
                axum::http::StatusCode::BAD_REQUEST,
                Json(json!({"ok": false, "error": "strategy must be one of: uniform, scene, single", "code": "invalid_value"})),
            ).into_response();
        }
    }
    // Validate scene_threshold
    if let Some(v) = filtered.get("scene_threshold") {
        let f = v.as_f64().unwrap_or(-1.0);
        if !(0.0..=1.0).contains(&f) {
            return (
                axum::http::StatusCode::BAD_REQUEST,
                Json(json!({"ok": false, "error": "scene_threshold must be a number between 0.0 and 1.0", "code": "invalid_value"})),
            ).into_response();
        }
        let rounded = (f * 100.0).round() / 100.0;
        filtered.insert("scene_threshold".to_string(), json!(rounded));
    }

    // Load, merge, save config.json
    let config_path = &state.config.config_path;
    let _guard = state.settings_lock.lock().await;
    let mut cfg = load_config_json(config_path);
    let va_section = cfg
        .as_object_mut()
        .and_then(|m| m.get_mut("video_analysis"))
        .and_then(|v| v.as_object_mut());
    if let Some(section) = va_section {
        for (k, v) in &filtered {
            section.insert(k.clone(), v.clone());
        }
    } else {
        let existing = cfg
            .as_object()
            .and_then(|m| m.get("video_analysis"))
            .and_then(|v| v.as_object())
            .cloned()
            .unwrap_or_default();
        let mut merged_section = existing;
        for (k, v) in &filtered {
            merged_section.insert(k.clone(), v.clone());
        }
        if let Some(map) = cfg.as_object_mut() {
            map.insert(
                "video_analysis".to_string(),
                serde_json::Value::Object(merged_section),
            );
        }
    }
    // Route the write through config_io so this shares the atomic tmp+rename
    // and 0600 permissions with every other config.json writer. A serialization
    // failure surfaces as an io::Error from the same call.
    if let Err(e) = crate::config_io::write(config_path, &cfg) {
        tracing::error!(?e, "video config write failed");
        return (
            axum::http::StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "internal_server_error"})),
        )
            .into_response();
    }

    // Reload and return merged config (same as get)
    let saved = load_config_json(config_path);
    api_result(json!({"config": merged_video_config(&saved)}))
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::{collections::HashSet, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    struct TestRoot {
        path: PathBuf,
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn test_root() -> TestRoot {
        let path = std::env::temp_dir().join(format!(
            "yu-server-video-test-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&path).unwrap();
        TestRoot { path }
    }

    async fn test_state(root: &TestRoot, schema: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        if !schema.is_empty() {
            sqlx::raw_sql(schema).execute(&pool).await.unwrap();
        }
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

    #[tokio::test]
    async fn video_config_merges_defaults_user_overrides_and_extra_keys() {
        let root = test_root();
        fs::write(
            root.path.join("config.json"),
            json!({"video_analysis": {"enabled": false, "keyframe_count": 8, "extra": "kept"}})
                .to_string(),
        )
        .unwrap();

        let value = json_body(config(State(test_state(&root, "").await), None).await).await;

        assert_eq!(value["config"]["enabled"], false);
        assert_eq!(value["config"]["keyframe_count"], 8);
        assert_eq!(value["config"]["strategy"], "uniform");
        assert_eq!(value["config"]["scene_threshold"], 0.4);
        assert_eq!(value["config"]["store_per_keyframe"], false);
        assert_eq!(value["config"]["extra"], "kept");
    }

    #[tokio::test]
    async fn video_status_counts_videos_and_missing_keyframe_table_as_zero() {
        let root = test_root();
        let state = test_state(
            &root,
            "CREATE TABLE files(id INTEGER PRIMARY KEY, is_deleted INTEGER NOT NULL, file_ext TEXT);
             INSERT INTO files(id, is_deleted, file_ext) VALUES
               (1, 0, '.mp4'), (2, 0, '.png'), (3, 1, '.webm'), (4, 0, '.mkv');",
        )
        .await;

        let value = json_body(status(State(state), None).await).await;

        assert!(value["ffmpeg"].is_boolean());
        assert_eq!(value["video_files"], 2);
        assert_eq!(value["files_with_keyframes"], 0);
    }
}

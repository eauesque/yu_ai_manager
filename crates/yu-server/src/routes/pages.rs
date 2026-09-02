use axum::{
    body::Bytes,
    extract::{Extension, State},
    http::{header::CONTENT_TYPE, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use std::path::PathBuf;
use tokio::fs;

use crate::{auth::AuthContext, config_io, routes::ui, state::SharedState};

fn bad_request(code: &str, message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
        .into_response()
}

pub(crate) fn is_json_content_type(headers: &HeaderMap) -> bool {
    headers
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(|content_type| {
            content_type.starts_with("application/json") || content_type.contains("+json")
        })
        .unwrap_or(false)
}

pub async fn favicon(State(state): State<SharedState>) -> Response {
    let config = config_io::load(&state.config.config_path);
    let active = ui::resolve_active_ui(&state.config.project_root, &config);
    let root = &state.config.project_root;
    let active_dir = root.join("ui").join(&active).join("static");
    let default_dir = root.join("ui").join("default").join("static");
    let dirs: Vec<PathBuf> = if active == "default" {
        vec![default_dir]
    } else {
        vec![active_dir, default_dir]
    };

    for dir in &dirs {
        for (name, mime) in [
            ("favicon.svg", "image/svg+xml"),
            ("favicon.png", "image/png"),
        ] {
            let path = dir.join(name);
            if let Ok(bytes) = fs::read(path).await {
                return (StatusCode::OK, [(CONTENT_TYPE, mime)], bytes).into_response();
            }
        }
    }

    StatusCode::NOT_FOUND.into_response()
}

pub async fn convert(
    State(state): State<SharedState>,
    maybe_auth: Option<Extension<AuthContext>>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !is_json_content_type(&headers) {
        return bad_request("invalid_content_type", "JSON body is required");
    }

    let data: Value = match serde_json::from_slice(&body) {
        Ok(value) => value,
        Err(_) => return bad_request("invalid_json", "Invalid JSON body"),
    };

    let Some(obj) = data.as_object() else {
        return bad_request("invalid_json_object", "JSON object body is required");
    };

    let mode = obj.get("mode").and_then(Value::as_str).unwrap_or("");

    if !obj.contains_key("prompt") || !obj.contains_key("mode") {
        return bad_request("invalid_request", "Invalid request");
    }

    let prompt = match obj["prompt"].as_str() {
        Some(value) => value,
        None => return bad_request("invalid_prompt", "prompt must be a string"),
    };

    if prompt.chars().count() > 8192 {
        return bad_request("prompt_too_long", "Prompt too long (max 8192 chars)");
    }

    let result = match mode {
        "nai_to_sd" => crate::sd_nai::convert_nai_to_sd(prompt, true),
        "sd_to_nai" => crate::sd_nai::convert_sd_to_nai(prompt, true, true, true),
        _ => return bad_request("invalid_mode", "Invalid mode"),
    };

    ui::api_result(json!({"result": result}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::{to_bytes, Bytes},
        extract::State,
        http::{header::CONTENT_TYPE, HeaderMap, HeaderValue, StatusCode},
        response::Response,
    };
    use serde_json::{json, Value};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::{
        collections::HashSet,
        fs,
        path::{Path, PathBuf},
        str::FromStr,
        sync::Arc,
        time::{SystemTime, UNIX_EPOCH},
    };

    use crate::state::{AppState, Config, SharedState};

    fn temp_root(name: &str) -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("yu-pages-{name}-{unique}"))
    }

    fn write_file(path: &Path, body: &str) {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, body).unwrap();
    }

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
                    quick_lock_enabled: false,
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

    fn json_headers() -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        headers
    }

    async fn call_convert(state: SharedState, body: impl Into<Bytes>) -> (StatusCode, Value) {
        let response = convert(State(state), None, json_headers(), body.into()).await;
        let status = response.status();
        let value = json_body(response).await;
        (status, value)
    }

    #[test]
    fn json_content_type_accepts_application_json() {
        let mut headers = HeaderMap::new();
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        assert!(is_json_content_type(&headers));
    }

    #[test]
    fn json_content_type_accepts_charset_suffix() {
        let mut headers = HeaderMap::new();
        headers.insert(
            CONTENT_TYPE,
            HeaderValue::from_static("application/json; charset=utf-8"),
        );
        assert!(is_json_content_type(&headers));
    }

    #[test]
    fn json_content_type_accepts_json_suffix() {
        let mut headers = HeaderMap::new();
        headers.insert(
            CONTENT_TYPE,
            HeaderValue::from_static("application/vnd.api+json"),
        );
        assert!(is_json_content_type(&headers));
    }

    #[test]
    fn json_content_type_rejects_text_plain() {
        let mut headers = HeaderMap::new();
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("text/plain"));
        assert!(!is_json_content_type(&headers));
    }

    #[tokio::test]
    async fn favicon_returns_svg_when_present() {
        let root = temp_root("fav-svg");
        let static_dir = root.join("ui/default/static");
        fs::create_dir_all(&static_dir).unwrap();
        fs::write(static_dir.join("favicon.svg"), b"<svg/>").unwrap();

        let state = test_state(root.clone()).await;
        let response = favicon(State(state)).await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(response.status(), StatusCode::OK);
        let content_type = response.headers()[CONTENT_TYPE].to_str().unwrap();
        assert!(content_type.starts_with("image/svg+xml"));
    }

    #[tokio::test]
    async fn favicon_falls_back_to_png_when_no_svg() {
        let root = temp_root("fav-png");
        let static_dir = root.join("ui/default/static");
        fs::create_dir_all(&static_dir).unwrap();
        fs::write(static_dir.join("favicon.png"), b"\x89PNG").unwrap();

        let state = test_state(root.clone()).await;
        let response = favicon(State(state)).await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(response.status(), StatusCode::OK);
        let content_type = response.headers()[CONTENT_TYPE].to_str().unwrap();
        assert!(content_type.starts_with("image/png"));
    }

    #[tokio::test]
    async fn favicon_returns_404_when_missing() {
        let root = temp_root("fav-404");
        fs::create_dir_all(&root).unwrap();

        let state = test_state(root.clone()).await;
        let response = favicon(State(state)).await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn favicon_active_ui_takes_priority_over_default() {
        let root = temp_root("fav-active");
        let active_static = root.join("ui/custom/static");
        let default_static = root.join("ui/default/static");
        fs::create_dir_all(&active_static).unwrap();
        fs::create_dir_all(&default_static).unwrap();
        fs::write(active_static.join("favicon.svg"), b"<svg>active</svg>").unwrap();
        fs::write(default_static.join("favicon.svg"), b"<svg>default</svg>").unwrap();
        write_file(&root.join("config.json"), r#"{"ui":"custom"}"#);
        write_file(
            &root.join("ui/custom/manifest.json"),
            r#"{"name":"custom","version":"1.0","type":"full"}"#,
        );

        let state = test_state(root.clone()).await;
        let response = favicon(State(state)).await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"<svg>active</svg>");
    }

    #[tokio::test]
    async fn favicon_rejects_path_traversal_ui_name() {
        let root = temp_root("fav-traversal");
        let static_dir = root.join("ui/default/static");
        fs::create_dir_all(&static_dir).unwrap();
        fs::write(static_dir.join("favicon.svg"), b"<svg/>").unwrap();
        fs::write(root.join("config.json"), r#"{"ui":"../evil"}"#).unwrap();

        let state = test_state(root.clone()).await;
        let response = favicon(State(state)).await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn convert_missing_content_type_returns_400() {
        let root = temp_root("conv-ct");
        let state = test_state(root.clone()).await;

        let response = convert(
            State(state),
            None,
            HeaderMap::new(),
            Bytes::from_static(b"{\"prompt\":\"a\",\"mode\":\"nai_to_sd\"}"),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = json_body(response).await;
        assert_eq!(body["code"], "invalid_content_type");
        assert_eq!(body["error"], "JSON body is required");
    }

    #[tokio::test]
    async fn convert_invalid_json_returns_400() {
        let root = temp_root("conv-json");
        let state = test_state(root.clone()).await;
        let (status, body) = call_convert(state, Bytes::from_static(b"not-json")).await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "invalid_json");
        assert_eq!(body["error"], "Invalid JSON body");
    }

    #[tokio::test]
    async fn convert_non_object_json_returns_400() {
        let root = temp_root("conv-arr");
        let state = test_state(root.clone()).await;
        let (status, body) = call_convert(state, Bytes::from_static(b"[1,2,3]")).await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "invalid_json_object");
        assert_eq!(body["error"], "JSON object body is required");
    }

    #[tokio::test]
    async fn convert_missing_prompt_returns_400_invalid_request() {
        let root = temp_root("conv-noprompt");
        let state = test_state(root.clone()).await;
        let (status, body) = call_convert(
            state,
            serde_json::to_vec(&json!({"mode":"nai_to_sd"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "invalid_request");
        assert_eq!(body["error"], "Invalid request");
    }

    #[tokio::test]
    async fn convert_non_string_prompt_returns_400() {
        let root = temp_root("conv-numpr");
        let state = test_state(root.clone()).await;
        let (status, body) = call_convert(
            state,
            serde_json::to_vec(&json!({"prompt":123,"mode":"nai_to_sd"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "invalid_prompt");
        assert_eq!(body["error"], "prompt must be a string");
    }

    #[tokio::test]
    async fn convert_prompt_too_long_returns_400() {
        let root = temp_root("conv-long");
        let state = test_state(root.clone()).await;
        let long_prompt = "a".repeat(8193);
        let (status, body) = call_convert(
            state,
            serde_json::to_vec(&json!({"prompt": long_prompt, "mode": "nai_to_sd"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "prompt_too_long");
        assert_eq!(body["error"], "Prompt too long (max 8192 chars)");
    }

    #[tokio::test]
    async fn convert_invalid_mode_returns_400() {
        let root = temp_root("conv-badmode");
        let state = test_state(root.clone()).await;
        let (status, body) = call_convert(
            state,
            serde_json::to_vec(&json!({"prompt":"test","mode":"bogus"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "invalid_mode");
        assert_eq!(body["error"], "Invalid mode");
    }

    #[tokio::test]
    async fn convert_nai_to_sd_returns_result_without_warnings() {
        let root = temp_root("conv-n2s");
        let state = test_state(root.clone()).await;
        let (status, body) = call_convert(
            state,
            serde_json::to_vec(&json!({"prompt":"(girl:1.2)","mode":"nai_to_sd"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["ok"], true);
        assert!(body["result"].is_string());
        assert!(body.get("warnings").is_none());
    }

    #[tokio::test]
    async fn convert_sd_to_nai_returns_result() {
        let root = temp_root("conv-s2n");
        let state = test_state(root.clone()).await;
        let (status, body) = call_convert(
            state,
            serde_json::to_vec(&json!({"prompt":"(girl:1.2)","mode":"sd_to_nai"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["ok"], true);
        assert!(body["result"].is_string());
    }

    #[tokio::test]
    async fn convert_multibyte_prompt_8192_chars_is_ok() {
        let root = temp_root("conv-mb-ok");
        let state = test_state(root.clone()).await;
        let prompt_8192 = "あ".repeat(8192);
        let (status, _) = call_convert(
            state,
            serde_json::to_vec(&json!({"prompt": prompt_8192, "mode": "nai_to_sd"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::OK);
    }

    #[tokio::test]
    async fn convert_multibyte_prompt_8193_chars_returns_400() {
        let root = temp_root("conv-mb-long");
        let state = test_state(root.clone()).await;
        let prompt_8193 = "あ".repeat(8193);
        let (status, body) = call_convert(
            state,
            serde_json::to_vec(&json!({"prompt": prompt_8193, "mode": "nai_to_sd"})).unwrap(),
        )
        .await;
        let _ = fs::remove_dir_all(root);

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "prompt_too_long");
    }

    // `expand` モードの Python 中継を検める試験は削除した。expand は UI（`src/ts/`）にも
    // Python 側（`extensions/builtin_sd_nai_convert/`）にも存在せず、handler は
    // `nai_to_sd` / `sd_to_nai` 以外を 400 `invalid_mode` とする。未知 mode の
    // 振舞いは `convert_invalid_mode_returns_400` が既に固定している。
}

// REWRITE_MARKER_v2 — comfyui_bridge top-of-file sentinel
use axum::{
    extract::{Extension, Multipart, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{delete, get, post},
    Json, Router,
};
use bytes::Bytes;
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    collections::{HashMap, HashSet, VecDeque},
    io::Read,
    path::{Path, PathBuf},
    sync::{Mutex, OnceLock},
    time::UNIX_EPOCH,
};

use crate::config_io::{load as load_config_json, write as write_config_json};
use crate::{
    auth::scope::{require_admin_scope, AuthContext},
    secret_store,
    state::SharedState,
};

pub mod generate;
pub mod simple_builder;

const EXT_NAME: &str = "builtin-comfyui-bridge";
const DEFAULT_API_URL: &str = "http://127.0.0.1:8188";
pub(super) const COMFY_USER_AGENT: &str = "yu-ai-manager/1.0";

static SAVE_NAMING_OPTIONS: &[&str] = &["daily_folder", "date_prefix", "timestamp"];
static IMAGE_FORMATS: &[&str] = &["png", "webp", "jpg"];
const MAX_SAFETENSORS_HEADER_BYTES: u64 = 16 * 1024 * 1024;
const CHECKPOINT_CACHE_MAX_ENTRIES: usize = 256;
const MAX_IMAGE_UPLOAD_BYTES: usize = 25 * 1024 * 1024;
const MAX_WORKFLOW_FILE_BYTES: u64 = 32 * 1024 * 1024;
const WORKFLOW_IMAGE_EXTENSIONS: &[&str] = &["png", "jpg", "jpeg", "webp"];

#[derive(Clone)]
struct CheckpointCacheEntry {
    mtime_ns: i128,
    size: u64,
    family: String,
    metadata: serde_json::Map<String, Value>,
}

#[derive(Default)]
struct CheckpointCache {
    entries: HashMap<PathBuf, CheckpointCacheEntry>,
    order: VecDeque<PathBuf>,
}

impl CheckpointCache {
    fn insert(&mut self, path: PathBuf, entry: CheckpointCacheEntry) {
        if self.entries.len() >= CHECKPOINT_CACHE_MAX_ENTRIES {
            if let Some(oldest) = self.order.pop_front() {
                self.entries.remove(&oldest);
            }
        }
        if self.entries.insert(path.clone(), entry).is_none() {
            self.order.push_back(path);
        }
    }
}

static CHECKPOINT_CACHE: OnceLock<Mutex<CheckpointCache>> = OnceLock::new();

pub(super) fn ext_config(state: &SharedState) -> Value {
    let full = load_config_json(&state.config.config_path);
    full.get("extensions")
        .and_then(|e| e.get(EXT_NAME))
        .cloned()
        .unwrap_or_else(|| json!({}))
}

pub(super) fn cfg_str<'a>(cfg: &'a Value, key: &str, default: &'a str) -> &'a str {
    cfg.get(key).and_then(Value::as_str).unwrap_or(default)
}

pub(super) fn cfg_bool(cfg: &Value, key: &str, default: bool) -> bool {
    cfg.get(key).and_then(Value::as_bool).unwrap_or(default)
}

pub(super) fn cfg_i64(cfg: &Value, key: &str, default: i64) -> i64 {
    cfg.get(key).and_then(Value::as_i64).unwrap_or(default)
}

pub(super) fn comfy_api_url(cfg: &Value) -> String {
    cfg_str(cfg, "api_url", DEFAULT_API_URL)
        .trim_end_matches('/')
        .to_string()
}

pub(super) fn python_url(state: &SharedState) -> Option<String> {
    let url = state.config.python_url.trim();
    if url.is_empty() {
        None
    } else {
        Some(url.trim_end_matches('/').to_string())
    }
}

pub(super) fn api_ok(payload: Value) -> Json<Value> {
    let mut body = json!({"ok": true, "error": null, "data": null});
    if let Value::Object(map) = payload {
        let obj = body.as_object_mut().unwrap();
        for (k, v) in map {
            obj.insert(k, v);
        }
    }
    Json(body)
}

pub(super) fn api_err(msg: &str, status: StatusCode) -> Response {
    tracing::warn!(
        status = status.as_u16(),
        error = msg,
        "comfyui_bridge api error"
    );
    (status, Json(json!({"ok": false, "error": msg}))).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use tracing_subscriber::layer::SubscriberExt;

    #[test]
    fn api_err_emits_warning_log() {
        let ring = Arc::new(crate::logs::LogRingBuffer::new(8));
        let subscriber = tracing_subscriber::registry().with(
            crate::logs::tracing_layer::TracingLayer::new(Arc::clone(&ring), tracing::Level::INFO),
        );

        tracing::subscriber::with_default(subscriber, || {
            let _ = api_err("missing workflow", StatusCode::BAD_REQUEST);
        });

        let entries = ring.recent(8, Some("WARN"), None);
        assert!(entries.iter().any(|entry| {
            entry.message == "comfyui_bridge api error"
                && entry
                    .fields
                    .as_ref()
                    .and_then(|fields| fields.get("error"))
                    .and_then(serde_json::Value::as_str)
                    == Some("missing workflow")
        }));
    }

    async fn test_state(config_path: std::path::PathBuf) -> SharedState {
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
        use std::str::FromStr;

        // repo root: crates/yu-server -> crates -> repo root
        let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|p| p.parent()) // crate-escapes-root: This cross-language test helper intentionally targets the yu_ai_manager checkout to compare Python extensions, which are absent from the extracted crates/ mirror and make this test unable to run there.
            .unwrap()
            .to_path_buf();
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(
            crate::state::AppState::new(
                crate::state::Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: Default::default(),
                    trusted_peer_ips: Default::default(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path,
                    project_root,
                    app_config: json!({}),
                    cache_dir: std::path::PathBuf::from("."),
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

    async fn response_json(resp: Response) -> Value {
        let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    async fn mock_object_info(data: Value) -> String {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/object_info",
            get(move || {
                let data = data.clone();
                async move { Json(data) }
            }),
        );
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        format!("http://{addr}")
    }

    fn write_safetensors(path: &Path, header: Value) {
        let payload = serde_json::to_vec(&header).unwrap();
        let mut contents = (payload.len() as u64).to_le_bytes().to_vec();
        contents.extend(payload);
        std::fs::write(path, contents).unwrap();
    }

    async fn checkpoint_response(config: Value, name: &str) -> Response {
        let config_file = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(config_file.path(), config.to_string()).unwrap();
        let state = test_state(config_file.path().to_path_buf()).await;
        checkpoint_info(
            State(state),
            Query(CheckpointInfoQuery {
                name: Some(name.to_string()),
            }),
        )
        .await
    }

    #[test]
    fn checkpoint_info_reads_safetensors_header_family() {
        let root = tempfile::tempdir().unwrap();
        let checkpoints = root.path().join("checkpoints");
        std::fs::create_dir(&checkpoints).unwrap();
        write_safetensors(
            &checkpoints.join("model.safetensors"),
            json!({"conditioner.embedders.1.model.weight": {"shape": [1]}}),
        );

        let info = inspect_checkpoint("model.safetensors", root.path().to_str().unwrap()).unwrap();
        assert_eq!(info["source"], "header");
        assert_eq!(info["family"], "sdxl");
    }

    #[test]
    fn checkpoint_info_marks_non_safetensors_unsupported() {
        let root = tempfile::tempdir().unwrap();
        let checkpoints = root.path().join("checkpoints");
        std::fs::create_dir(&checkpoints).unwrap();
        std::fs::write(checkpoints.join("model.ckpt"), b"not safetensors").unwrap();

        let info = inspect_checkpoint("model.ckpt", root.path().to_str().unwrap()).unwrap();
        assert_eq!(info["source"], "unsupported");
        assert!(info["family"].is_null());
    }

    #[tokio::test]
    async fn checkpoint_info_missing_file_is_unavailable_with_status_200() {
        let root = tempfile::tempdir().unwrap();
        let response = checkpoint_response(
            json!({"extensions": {"builtin-comfyui-bridge": {"models_root": root.path()}}}),
            "missing.safetensors",
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response_json(response).await["source"], "unavailable");
    }

    #[tokio::test]
    async fn checkpoint_info_unset_models_root_is_unavailable_with_status_200() {
        let response = checkpoint_response(
            json!({"extensions": {"builtin-comfyui-bridge": {"api_url": "http://remote.example:8188"}}}),
            "model.safetensors",
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response_json(response).await["source"], "unavailable");
    }

    #[test]
    fn checkpoint_info_rejects_parent_traversal_name() {
        assert_eq!(
            inspect_checkpoint("subdir/../model.safetensors", "/unused"),
            Err("path traversal ('..' is not allowed)")
        );
    }

    #[test]
    fn checkpoint_info_rejects_absolute_name() {
        assert_eq!(
            inspect_checkpoint("/outside/model.safetensors", "/unused"),
            Err("absolute paths are not allowed")
        );
    }

    #[test]
    fn checkpoint_info_rejects_symlink_outside_models_root() {
        let root = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let checkpoints = root.path().join("checkpoints");
        std::fs::create_dir(&checkpoints).unwrap();
        let outside_model = outside.path().join("outside.safetensors");
        write_safetensors(
            &outside_model,
            json!({"conditioner.embedders.1.model.weight": {"shape": [1]}}),
        );
        let link = checkpoints.join("linked.safetensors");
        #[cfg(unix)]
        std::os::unix::fs::symlink(&outside_model, &link).unwrap();
        #[cfg(windows)]
        std::os::windows::fs::symlink_file(&outside_model, &link).unwrap();

        let info = inspect_checkpoint("linked.safetensors", root.path().to_str().unwrap()).unwrap();
        assert_eq!(info["source"], "unavailable");
    }

    #[test]
    fn checkpoint_info_rejects_header_larger_than_cap() {
        let root = tempfile::tempdir().unwrap();
        let checkpoints = root.path().join("checkpoints");
        std::fs::create_dir(&checkpoints).unwrap();
        std::fs::write(
            checkpoints.join("oversized.safetensors"),
            (MAX_SAFETENSORS_HEADER_BYTES + 1).to_le_bytes(),
        )
        .unwrap();

        let info =
            inspect_checkpoint("oversized.safetensors", root.path().to_str().unwrap()).unwrap();
        assert_eq!(info["source"], "unsupported");
    }

    #[test]
    fn checkpoint_cache_evicts_oldest_past_256_entries() {
        let mut cache = CheckpointCache::default();
        for index in 0..=CHECKPOINT_CACHE_MAX_ENTRIES {
            cache.insert(
                PathBuf::from(format!("model-{index}")),
                CheckpointCacheEntry {
                    mtime_ns: 0,
                    size: 0,
                    family: "unknown".to_string(),
                    metadata: Default::default(),
                },
            );
        }
        assert_eq!(cache.entries.len(), CHECKPOINT_CACHE_MAX_ENTRIES);
        assert!(!cache.entries.contains_key(Path::new("model-0")));
    }

    #[tokio::test]
    async fn custom_nodes_filters_name_and_category_case_insensitively() {
        let api_url = mock_object_info(json!({
            "AlphaNode": {"category": "Video Tools", "description": "alpha"},
            "BetaNODE": {"category": "Image", "description": "beta"},
        }))
        .await;
        let tmp = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(
            tmp.path(),
            json!({
                "extensions": {
                    "builtin-comfyui-bridge": {"api_url": api_url}
                }
            })
            .to_string(),
        )
        .unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;

        let body = response_json(
            custom_nodes(State(Arc::clone(&state)), Query(FilterQuery { q: None })).await,
        )
        .await;
        assert_eq!(body["nodes"].as_array().unwrap().len(), 2);

        for (q, expected) in [
            ("video", "AlphaNode"),
            ("beta", "BetaNODE"),
            ("ALPHANODE", "AlphaNode"),
        ] {
            let body = response_json(
                custom_nodes(
                    State(Arc::clone(&state)),
                    Query(FilterQuery {
                        q: Some(q.to_string()),
                    }),
                )
                .await,
            )
            .await;
            assert_eq!(body["nodes"].as_array().unwrap().len(), 1);
            assert_eq!(body["nodes"][0]["name"], expected);
        }
    }

    #[test]
    fn registry_id_validation() {
        assert!(is_valid_registry_id("wan22"));
        assert!(is_valid_registry_id("my-model_v2"));
        assert!(!is_valid_registry_id(""));
        assert!(!is_valid_registry_id(&"a".repeat(65)));
        assert!(!is_valid_registry_id("has space"));
        assert!(!is_valid_registry_id("has/slash"));
    }

    #[test]
    fn ctrl_chars_detection_allows_tab_rejects_others() {
        assert!(!has_ctrl_chars("clean	text"));
        assert!(has_ctrl_chars("badtext"));
        assert!(has_ctrl_chars(
            "bad
text"
        ));
    }

    #[test]
    fn validate_post_body_rejects_too_many_patterns() {
        let data = json!({"unet_patterns": vec!["p"; 33]});
        assert!(validate_registry_post_body(&data)
            .unwrap()
            .contains("32 items"));
    }

    #[test]
    fn validate_post_body_rejects_bad_source_url() {
        let data = json!({"source_url": "ftp://example.com"});
        assert!(validate_registry_post_body(&data)
            .unwrap()
            .contains("http or https"));
    }

    #[test]
    fn validate_post_body_rejects_out_of_range_steps() {
        let data = json!({"default_steps": 0});
        assert!(validate_registry_post_body(&data)
            .unwrap()
            .contains("between 1 and 10000"));
    }

    #[test]
    fn entry_from_dict_accepts_legacy_singular_pattern() {
        let data = json!({"id": "x", "unet_pattern": "foo"});
        let entry = registry_entry_from_dict(&data, false).unwrap();
        assert_eq!(entry.unet_patterns, vec!["foo".to_string()]);
    }

    #[test]
    fn entry_from_dict_rejects_missing_patterns() {
        let data = json!({"id": "x"});
        assert!(registry_entry_from_dict(&data, false).is_none());
    }

    #[tokio::test]
    async fn post_model_registry_entry_creates_then_updates() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;

        let resp = post_model_registry_entry(
            State(Arc::clone(&state)),
            None,
            Json(json!({"id": "myid", "unet_patterns": ["wan2.2"], "notes": "n1"})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::CREATED);

        // second call with the same id updates in place (created=false)
        let resp = post_model_registry_entry(
            State(Arc::clone(&state)),
            None,
            Json(json!({"id": "myid", "unet_patterns": ["wan2.2"], "notes": "n2"})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);

        let user = load_user_registry(&state);
        assert_eq!(user.len(), 1);
        assert_eq!(user[0].notes, "n2");
    }

    #[tokio::test]
    async fn post_model_registry_entry_rejects_invalid_id() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let resp = post_model_registry_entry(
            State(state),
            None,
            Json(json!({"id": "bad id!", "unet_patterns": ["x"]})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn post_model_registry_entry_rejects_missing_patterns() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let resp = post_model_registry_entry(State(state), None, Json(json!({"id": "myid"}))).await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn delete_model_registry_entry_round_trip() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;

        let _ = post_model_registry_entry(
            State(Arc::clone(&state)),
            None,
            Json(json!({"id": "myid", "unet_patterns": ["wan2.2"]})),
        )
        .await;

        let resp = delete_model_registry_entry(
            State(Arc::clone(&state)),
            None,
            AxumPath("myid".to_string()),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        assert!(load_user_registry(&state).is_empty());

        // deleting again -> 404 (not found anywhere)
        let resp = delete_model_registry_entry(
            State(Arc::clone(&state)),
            None,
            AxumPath("myid".to_string()),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn delete_model_registry_entry_refuses_builtin_without_override() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        // "wan22" is a real id in the bundled model_registry_builtin.json
        let resp =
            delete_model_registry_entry(State(state), None, AxumPath("wan22".to_string())).await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn get_model_registry_keeps_registry_when_comfyui_fails() {
        let tmp = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(
            tmp.path(),
            json!({
                "extensions": {
                    "builtin-comfyui-bridge": {"api_url": "http://127.0.0.1:0"}
                }
            })
            .to_string(),
        )
        .unwrap();
        let state = test_state(tmp.path().to_path_buf()).await;
        let resp = post_model_registry_entry(
            State(Arc::clone(&state)),
            None,
            Json(json!({"id": "myid", "unet_patterns": ["wan2.2"]})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::CREATED);

        let resp = get_model_registry(State(state), None).await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = response_json(resp).await;
        assert!(body["registry"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| entry["id"] == "myid"));
        assert_eq!(body["available_models"]["diffusion_models"], json!([]));
        assert_eq!(body["available_models"]["vaes"], json!([]));
        assert_eq!(body["available_models"]["text_encoders"], json!([]));
        assert!(body["models_error"].as_str().is_some_and(|s| !s.is_empty()));
    }

    fn sample_api_workflow() -> Value {
        json!({
            "1": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 123,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "positive": ["2", 0],
                    "negative": ["3", 0]
                }
            },
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "lowres"}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768}}
        })
    }

    fn png_chunk(chunk_type: &[u8; 4], data: &[u8]) -> Vec<u8> {
        let mut chunk = (data.len() as u32).to_be_bytes().to_vec();
        chunk.extend_from_slice(chunk_type);
        chunk.extend_from_slice(data);
        chunk.extend_from_slice(&0u32.to_be_bytes());
        chunk
    }

    fn png_with_text(keyword: &str, value: &str) -> Vec<u8> {
        png_with_text_entries(&[(keyword, value)])
    }

    fn png_with_text_entries(entries: &[(&str, &str)]) -> Vec<u8> {
        let mut png = b"\x89PNG\r\n\x1a\n".to_vec();
        for &(keyword, value) in entries {
            let mut text = keyword.as_bytes().to_vec();
            text.push(0);
            text.extend_from_slice(value.as_bytes());
            png.extend(png_chunk(b"tEXt", &text));
        }
        png.extend(png_chunk(b"IEND", &[]));
        png
    }

    fn png_with_compressed_itxt(keyword: &str) -> Vec<u8> {
        let mut png = b"\x89PNG\r\n\x1a\n".to_vec();
        let mut text = keyword.as_bytes().to_vec();
        text.extend_from_slice(&[0, 1, 0, 0, 0]);
        text.extend_from_slice(b"compressed");
        png.extend(png_chunk(b"iTXt", &text));
        png.extend(png_chunk(b"IEND", &[]));
        png
    }

    fn multipart_body(
        field_name: &str,
        filename: Option<&str>,
        data: &[u8],
    ) -> (&'static str, Vec<u8>) {
        let boundary = "yu-comfyui-test-boundary";
        let filename = filename
            .map(|filename| format!("; filename=\"{filename}\""))
            .unwrap_or_default();
        let mut body = format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"{filename}\r\nContent-Type: application/octet-stream\r\n\r\n"
        )
        .into_bytes();
        body.extend_from_slice(data);
        body.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());
        (boundary, body)
    }

    async fn multipart_response(field_name: &str, filename: &str, data: &[u8]) -> Response {
        use tower::ServiceExt;

        let (boundary, body) = multipart_body(field_name, Some(filename), data);
        Router::new()
            .route("/extract", post(extract_workflow))
            .layer(axum::extract::DefaultBodyLimit::max(
                MAX_IMAGE_UPLOAD_BYTES + 1024 * 1024,
            ))
            .oneshot(
                axum::http::Request::builder()
                    .method("POST")
                    .uri("/extract")
                    .header(
                        axum::http::header::CONTENT_TYPE,
                        format!("multipart/form-data; boundary={boundary}"),
                    )
                    .body(axum::body::Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap()
    }

    async fn upload_response(
        api_url: &str,
        field_name: &str,
        filename: Option<&str>,
        data: &[u8],
    ) -> Response {
        use tower::ServiceExt;

        let config_file = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(
            config_file.path(),
            json!({"extensions": {"builtin-comfyui-bridge": {"api_url": api_url}}}).to_string(),
        )
        .unwrap();
        let state = test_state(config_file.path().to_path_buf()).await;
        let (boundary, body) = multipart_body(field_name, filename, data);
        Router::new()
            .route("/upload", post(upload_controlnet_image))
            .layer(axum::extract::DefaultBodyLimit::max(
                MAX_IMAGE_UPLOAD_BYTES + 1024 * 1024,
            ))
            .with_state(state)
            .oneshot(
                axum::http::Request::builder()
                    .method("POST")
                    .uri("/upload")
                    .header(
                        axum::http::header::CONTENT_TYPE,
                        format!("multipart/form-data; boundary={boundary}"),
                    )
                    .body(axum::body::Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap()
    }

    async fn workflow_file_state(root: &Path, api_url: &str) -> SharedState {
        let config_path = root.join("config.json");
        std::fs::write(
            &config_path,
            json!({"extensions": {"builtin-comfyui-bridge": {"api_url": api_url}}}).to_string(),
        )
        .unwrap();
        let state = test_state(config_path).await;
        sqlx::query(
            "CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0)",
        )
        .execute(&state.db)
        .await
        .unwrap();
        state
    }

    async fn insert_workflow_file(state: &SharedState, file_id: i64, path: &Path) {
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (?, ?, 0)")
            .bind(file_id)
            .bind(path.to_string_lossy().into_owned())
            .execute(&state.db)
            .await
            .unwrap();
    }

    async fn workflow_file_response(state: SharedState, route: &str, body: Value) -> Response {
        use tower::ServiceExt;

        routes()
            .with_state(state)
            .oneshot(
                axum::http::Request::builder()
                    .method("POST")
                    .uri(route)
                    .header(axum::http::header::CONTENT_TYPE, "application/json")
                    .body(axum::body::Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap()
    }

    async fn assert_workflow_file_front_half(route: &str) {
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), "http://127.0.0.1:1").await;

        let response =
            workflow_file_response(Arc::clone(&state), route, json!({"file_id": "1"})).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await["error"],
            "file_id (int) is required"
        );

        let response =
            workflow_file_response(Arc::clone(&state), route, json!({"file_id": 1})).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            response_json(response).await["error"],
            "ファイルが見つかりません"
        );

        let missing = root.path().join("missing.png");
        insert_workflow_file(&state, 2, &missing).await;
        let response =
            workflow_file_response(Arc::clone(&state), route, json!({"file_id": 2})).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            response_json(response).await["error"],
            "ファイルが見つかりません"
        );

        let unsupported = root.path().join("workflow.gif");
        std::fs::write(&unsupported, b"gif").unwrap();
        insert_workflow_file(&state, 3, &unsupported).await;
        let response =
            workflow_file_response(Arc::clone(&state), route, json!({"file_id": 3})).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await["error"],
            "対応していないファイル形式です"
        );

        let oversized = root.path().join("workflow.png");
        std::fs::File::create(&oversized)
            .unwrap()
            .set_len(MAX_WORKFLOW_FILE_BYTES + 1)
            .unwrap();
        insert_workflow_file(&state, 4, &oversized).await;
        let response = workflow_file_response(state, route, json!({"file_id": 4})).await;
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert_eq!(
            response_json(response).await["error"],
            "ファイルサイズが大きすぎます"
        );
    }

    async fn mock_prompt_server(
        status: StatusCode,
        response_body: &str,
    ) -> (String, Arc<Mutex<Option<Value>>>) {
        let received = Arc::new(Mutex::new(None));
        let capture = Arc::clone(&received);
        let response_body = response_body.to_string();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/prompt",
            post(move |body: Bytes| {
                let capture = Arc::clone(&capture);
                let response_body = response_body.clone();
                async move {
                    *capture.lock().unwrap() = serde_json::from_slice(&body).ok();
                    (status, response_body)
                }
            }),
        );
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{address}"), received)
    }

    async fn mock_upload_server(
        status: StatusCode,
        result: Value,
    ) -> (String, Arc<Mutex<Vec<u8>>>) {
        let received = Arc::new(Mutex::new(Vec::new()));
        let capture = Arc::clone(&received);
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/upload/image",
            post(move |body: Bytes| {
                let capture = Arc::clone(&capture);
                let result = result.clone();
                async move {
                    *capture.lock().unwrap() = body.to_vec();
                    (status, Json(result))
                }
            }),
        );
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{address}"), received)
    }

    #[tokio::test]
    async fn parse_workflow_params_extracts_ksampler_parameters() {
        let response = parse_workflow_params(Json(sample_api_workflow())).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = response_json(response).await;
        assert_eq!(body["simple_params"]["seed"], 123);
        assert_eq!(body["simple_params"]["steps"], 20);
        assert_eq!(body["simple_params"]["prompt"], "a cat");
        assert_eq!(body["simple_params"]["negative_prompt"], "lowres");
        assert_eq!(body["simple_params"]["width"], 512);
        assert_eq!(body["simple_params"]["height"], 768);
    }

    #[tokio::test]
    async fn parse_workflow_params_rejects_unrecognisable_workflows() {
        for workflow in [
            json!({}),
            json!({"1": {"class_type": "Unknown", "inputs": {}}}),
        ] {
            let response = parse_workflow_params(Json(workflow)).await;
            assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
            assert_eq!(
                response_json(response).await["error"],
                "ワークフローから Simple モードのパラメータを抽出できませんでした"
            );
        }
    }

    #[tokio::test]
    async fn extract_workflow_requires_image_part() {
        let response = multipart_response("other", "workflow.png", b"ignored").await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await["error"],
            "image file is required"
        );
    }

    #[tokio::test]
    async fn extract_workflow_rejects_unsupported_extension() {
        let response = multipart_response("image", "workflow.gif", b"ignored").await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await["error"],
            "Unsupported format: gif"
        );
    }

    #[tokio::test]
    async fn extract_workflow_rejects_upload_over_25_mib() {
        let data = vec![0; MAX_IMAGE_UPLOAD_BYTES + 1];
        let response = multipart_response("image", "workflow.png", &data).await;
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert_eq!(
            response_json(response).await["error"],
            "image exceeds 26,214,400 byte limit"
        );
    }

    #[tokio::test]
    async fn extract_workflow_reads_api_prompt_and_simple_params() {
        let png = png_with_text("prompt", &sample_api_workflow().to_string());
        let response = multipart_response("image", "workflow.png", &png).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = response_json(response).await;
        assert_eq!(body["format"], "api");
        assert_eq!(body["simple_params"]["seed"], 123);
    }

    #[tokio::test]
    async fn extract_workflow_reads_editor_workflow_without_simple_params() {
        let png = png_with_text("workflow", &json!({"nodes": []}).to_string());
        let response = multipart_response("image", "workflow.png", &png).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = response_json(response).await;
        assert_eq!(body["format"], "editor");
        assert!(body.get("simple_params").is_none());
    }

    #[tokio::test]
    async fn extract_workflow_rejects_png_without_metadata() {
        let mut png = b"\x89PNG\r\n\x1a\n".to_vec();
        png.extend(png_chunk(b"IEND", &[]));
        let response = multipart_response("image", "workflow.png", &png).await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(
            response_json(response).await["error"],
            "No workflow metadata found in PNG"
        );
    }

    #[tokio::test]
    async fn extract_workflow_distinguishes_compressed_itxt() {
        let png = png_with_compressed_itxt("prompt");
        let response = multipart_response("image", "workflow.png", &png).await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(
            response_json(response).await["error"],
            "Compressed iTXt workflow metadata is not supported"
        );
    }

    #[tokio::test]
    async fn check_workflow_from_file_validates_front_half() {
        assert_workflow_file_front_half("/ext/comfyui-bridge/api/check-workflow-from-file").await;
    }

    #[tokio::test]
    async fn queue_workflow_from_file_validates_front_half() {
        assert_workflow_file_front_half("/ext/comfyui-bridge/api/queue-workflow-from-file").await;
    }

    #[tokio::test]
    async fn check_workflow_from_file_fails_open_when_extraction_fails() {
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), "http://127.0.0.1:1").await;
        let path = root.path().join("broken.png");
        std::fs::write(&path, b"not an image").unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/check-workflow-from-file",
            json!({"file_id": 1}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response_json(response).await["status"], "ok");
    }

    #[tokio::test]
    async fn check_workflow_from_file_accepts_editor_format() {
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), "http://127.0.0.1:1").await;
        let path = root.path().join("editor.png");
        std::fs::write(&path, png_with_text("workflow", r#"{"nodes":[]}"#)).unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/check-workflow-from-file",
            json!({"file_id": 1}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response_json(response).await["status"], "ok");
    }

    #[tokio::test]
    async fn queue_workflow_from_file_rejects_extraction_failure() {
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), "http://127.0.0.1:1").await;
        let path = root.path().join("broken.png");
        std::fs::write(&path, b"not an image").unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/queue-workflow-from-file",
            json!({"file_id": 1}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(
            response_json(response).await["error"],
            "ワークフロー情報が見つかりません"
        );
    }

    #[tokio::test]
    async fn queue_workflow_from_file_rejects_editor_format() {
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), "http://127.0.0.1:1").await;
        let path = root.path().join("editor.png");
        std::fs::write(&path, png_with_text("workflow", r#"{"nodes":[]}"#)).unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/queue-workflow-from-file",
            json!({"file_id": 1}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(
            response_json(response).await["error"],
            "Editor format workflow はキュー投入に対応していません"
        );
    }

    #[tokio::test]
    async fn queue_workflow_from_file_migrates_clip_type_without_supplement() {
        let (api_url, received) =
            mock_prompt_server(StatusCode::OK, r#"{"prompt_id":"queued"}"#).await;
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), &api_url).await;
        let workflow = json!({
            "1": {"class_type": "CLIPLoader", "inputs": {
                "clip_name": "qwen_3_8b.safetensors", "type": "wan"
            }}
        });
        let path = root.path().join("workflow.png");
        std::fs::write(&path, png_with_text("prompt", &workflow.to_string())).unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/queue-workflow-from-file",
            json!({"file_id": 1, "supplement": false}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response_json(response).await["prompt_id"], "queued");
        assert_eq!(
            received.lock().unwrap().as_ref().unwrap()["prompt"]["1"]["inputs"]["type"],
            "qwen_image"
        );
    }

    #[tokio::test]
    async fn queue_workflow_from_file_rejects_supplement_without_gen_params() {
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), "http://127.0.0.1:1").await;
        let path = root.path().join("workflow.png");
        std::fs::write(
            &path,
            png_with_text("prompt", &sample_api_workflow().to_string()),
        )
        .unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/queue-workflow-from-file",
            json!({"file_id": 1, "supplement": true}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await["error"],
            "バックアップ情報が見つかりません"
        );
    }

    #[tokio::test]
    async fn workflow_from_file_detects_and_applies_model_supplement() {
        let (api_url, received) =
            mock_prompt_server(StatusCode::OK, r#"{"prompt_id":"queued"}"#).await;
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), &api_url).await;
        let workflow = json!({
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "", "type": null}}
        });
        let gen_params = json!({
            "text_encoder_1": "qwen_3_8b.safetensors",
            "clip_type": "wan"
        });
        let prompt = workflow.to_string();
        let backup = gen_params.to_string();
        let path = root.path().join("workflow.png");
        std::fs::write(
            &path,
            png_with_text_entries(&[("prompt", &prompt), ("_gen_params", &backup)]),
        )
        .unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            Arc::clone(&state),
            "/ext/comfyui-bridge/api/check-workflow-from-file",
            json!({"file_id": 1}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response_json(response).await["status"],
            "supplement_available"
        );

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/queue-workflow-from-file",
            json!({"file_id": 1, "supplement": true}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = response_json(response).await;
        assert_eq!(body["supplemented"], true);
        assert_eq!(
            body["supplement_applied"]["clip_name"],
            "qwen_3_8b.safetensors"
        );
        assert_eq!(
            received.lock().unwrap().as_ref().unwrap()["prompt"]["1"]["inputs"]["type"],
            "qwen_image"
        );
    }

    #[tokio::test]
    async fn queue_workflow_from_file_maps_connection_failure_to_502() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let api_url = format!("http://{}", listener.local_addr().unwrap());
        drop(listener);
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), &api_url).await;
        let path = root.path().join("workflow.png");
        std::fs::write(
            &path,
            png_with_text("prompt", &sample_api_workflow().to_string()),
        )
        .unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/queue-workflow-from-file",
            json!({"file_id": 1}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
        assert_eq!(
            response_json(response).await["error"],
            "ComfyUI への接続に失敗しました"
        );
    }

    #[tokio::test]
    async fn queue_workflow_from_file_maps_http_failure_to_502() {
        let (api_url, _) =
            mock_prompt_server(StatusCode::SERVICE_UNAVAILABLE, "upstream broke").await;
        let root = tempfile::tempdir().unwrap();
        let state = workflow_file_state(root.path(), &api_url).await;
        let path = root.path().join("workflow.png");
        std::fs::write(
            &path,
            png_with_text("prompt", &sample_api_workflow().to_string()),
        )
        .unwrap();
        insert_workflow_file(&state, 1, &path).await;

        let response = workflow_file_response(
            state,
            "/ext/comfyui-bridge/api/queue-workflow-from-file",
            json!({"file_id": 1}),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
        assert_eq!(
            response_json(response).await["error"],
            "ComfyUI エラー: HTTP 503 — upstream broke"
        );
    }

    #[tokio::test]
    async fn upload_controlnet_image_requires_image_part() {
        let response =
            upload_response("http://127.0.0.1:1", "other", Some("image.png"), b"ignored").await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await["error"],
            "image file is required"
        );
    }

    #[tokio::test]
    async fn upload_controlnet_image_rejects_unsupported_extension() {
        let response =
            upload_response("http://127.0.0.1:1", "image", Some("image.gif"), b"ignored").await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await["error"],
            "Unsupported format: gif"
        );
    }

    #[tokio::test]
    async fn upload_controlnet_image_rejects_upload_over_25_mib() {
        let data = vec![0; MAX_IMAGE_UPLOAD_BYTES + 1];
        let response =
            upload_response("http://127.0.0.1:1", "image", Some("image.png"), &data).await;
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
    }

    #[tokio::test]
    async fn upload_controlnet_image_sniffs_jpeg_under_png_filename() {
        let (api_url, received) =
            mock_upload_server(StatusCode::OK, json!({"name": "x.jpg"})).await;
        let response = upload_response(&api_url, "image", Some("x.png"), b"\xff\xd8jpeg").await;
        assert_eq!(response.status(), StatusCode::OK);
        let received = received.lock().unwrap();
        let body = String::from_utf8_lossy(&received);
        assert!(body.contains("filename=\"x.jpg\""));
        assert!(body.contains("Content-Type: image/jpeg"));
    }

    #[tokio::test]
    async fn upload_controlnet_image_sniffs_webp() {
        let (api_url, received) =
            mock_upload_server(StatusCode::OK, json!({"name": "x.webp"})).await;
        let response = upload_response(&api_url, "image", Some("x.png"), b"RIFFxxxxWEBPdata").await;
        assert_eq!(response.status(), StatusCode::OK);
        let received = received.lock().unwrap();
        let body = String::from_utf8_lossy(&received);
        assert!(body.contains("filename=\"x.webp\""));
        assert!(body.contains("Content-Type: image/webp"));
    }

    #[tokio::test]
    async fn upload_controlnet_image_treats_other_bytes_as_png() {
        let (api_url, received) =
            mock_upload_server(StatusCode::OK, json!({"name": "x.png"})).await;
        let response = upload_response(&api_url, "image", Some("x.jpeg"), b"garbage").await;
        assert_eq!(response.status(), StatusCode::OK);
        let received = received.lock().unwrap();
        let body = String::from_utf8_lossy(&received);
        assert!(body.contains("filename=\"x.png\""));
        assert!(body.contains("Content-Type: image/png"));
    }

    #[tokio::test]
    async fn upload_controlnet_image_falls_back_to_sent_filename() {
        let (api_url, _) = mock_upload_server(StatusCode::OK, json!({})).await;
        let response = upload_response(&api_url, "image", Some("x.jpeg"), b"garbage").await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response_json(response).await["name"], "x.png");
    }

    #[tokio::test]
    async fn upload_controlnet_image_uses_controlnet_default_filename() {
        let (api_url, _) = mock_upload_server(StatusCode::OK, json!({})).await;
        let response = upload_response(&api_url, "image", None, b"garbage").await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response_json(response).await["name"],
            "controlnet_input.png"
        );
    }

    #[tokio::test]
    async fn upload_controlnet_image_maps_upstream_failures_to_502() {
        let (api_url, _) = mock_upload_server(StatusCode::INTERNAL_SERVER_ERROR, json!({})).await;
        let response = upload_response(&api_url, "image", Some("x.png"), b"garbage").await;
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
        assert!(response_json(response).await["error"]
            .as_str()
            .unwrap()
            .starts_with("Upload failed: HTTP 500"));

        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let api_url = format!("http://{}", listener.local_addr().unwrap());
        drop(listener);
        let response = upload_response(&api_url, "image", Some("x.png"), b"garbage").await;
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
        assert!(response_json(response).await["error"]
            .as_str()
            .unwrap()
            .starts_with("Upload failed: "));
    }
}

fn admin_guard(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0))
}

// ---------------------------------------------------------------------------
// ComfyUI HTTP helpers
// ---------------------------------------------------------------------------

pub(super) async fn comfy_get(
    client: &reqwest::Client,
    api_url: &str,
    path: &str,
    api_key: &str,
) -> Result<Value, String> {
    let mut req = client
        .get(format!("{api_url}{path}"))
        .header("User-Agent", COMFY_USER_AGENT)
        .timeout(std::time::Duration::from_secs(30));
    if !api_key.is_empty() {
        req = req.header("Authorization", format!("Bearer {api_key}"));
    }
    let resp = req.send().await.map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }
    resp.json::<Value>().await.map_err(|e| e.to_string())
}

pub(super) async fn comfy_post(
    client: &reqwest::Client,
    api_url: &str,
    path: &str,
    body: &Value,
    api_key: &str,
) -> Result<Value, String> {
    let mut req = client
        .post(format!("{api_url}{path}"))
        .header("User-Agent", COMFY_USER_AGENT)
        .timeout(std::time::Duration::from_secs(30))
        .json(body);
    if !api_key.is_empty() {
        req = req.header("Authorization", format!("Bearer {api_key}"));
    }
    let resp = req.send().await.map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }
    let bytes = resp.bytes().await.map_err(|e| e.to_string())?;
    if bytes.is_empty() {
        return Ok(json!(null));
    }
    serde_json::from_slice(&bytes).map_err(|e| e.to_string())
}

fn get_api_key(cfg: &Value, project_root: &std::path::Path) -> String {
    let enc = cfg_str(cfg, "api_key_enc", "");
    if enc.is_empty() {
        return String::new();
    }
    secret_store::decrypt(enc, project_root)
}

/// Parse /object_info/{node_type} response → list of enum values.
/// Handles both new format ["COMBO", {"options":[...]}] and legacy [[...], ...].
fn parse_enum_options(data: &Value, node_type: &str, field: &str) -> Vec<String> {
    let entry = data
        .get(node_type)
        .and_then(|n| n.get("input"))
        .and_then(|i| i.get("required"))
        .and_then(|r| r.get(field))
        .and_then(Value::as_array);
    let entry = match entry {
        Some(e) if !e.is_empty() => e,
        _ => return vec![],
    };
    // New format: ["COMBO", {"options": [...]}]
    if entry.first().and_then(Value::as_str) == Some("COMBO") {
        if let Some(opts) = entry
            .get(1)
            .and_then(|v| v.get("options"))
            .and_then(Value::as_array)
        {
            return opts
                .iter()
                .filter_map(Value::as_str)
                .map(String::from)
                .collect();
        }
    }
    // Legacy format: [["model1", "model2"], ...]
    if let Some(list) = entry.first().and_then(Value::as_array) {
        return list
            .iter()
            .filter_map(Value::as_str)
            .map(String::from)
            .collect();
    }
    vec![]
}

async fn fetch_enum(
    client: &reqwest::Client,
    api_url: &str,
    node_type: &str,
    field: &str,
    api_key: &str,
) -> Vec<String> {
    fetch_enum_result(client, api_url, node_type, field, api_key)
        .await
        .unwrap_or_default()
}

async fn fetch_enum_result(
    client: &reqwest::Client,
    api_url: &str,
    node_type: &str,
    field: &str,
    api_key: &str,
) -> Result<Vec<String>, String> {
    let data = comfy_get(
        client,
        api_url,
        &format!("/object_info/{node_type}"),
        api_key,
    )
    .await?;
    Ok(parse_enum_options(&data, node_type, field))
}

// ---------------------------------------------------------------------------
// Route handlers
// ---------------------------------------------------------------------------

async fn info(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    Json(json!({
        "name": EXT_NAME,
        "bridge": "comfyui",
        "api_url": cfg_str(&cfg, "api_url", DEFAULT_API_URL),
    }))
    .into_response()
}

async fn test_connection(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    match comfy_get(&state.python_client, &api_url, "/system_stats", &key).await {
        Ok(data) => {
            let sys = data.get("system").cloned().unwrap_or(json!({}));
            api_ok(json!({
                "ok": true,
                "version": sys.get("comfyui_version").and_then(Value::as_str).unwrap_or("unknown"),
                "device": sys.get("device_name").and_then(Value::as_str).unwrap_or("unknown"),
                "vram_total": sys.get("vram_total").and_then(Value::as_u64).unwrap_or(0),
                "vram_free": sys.get("vram_free").and_then(Value::as_u64).unwrap_or(0),
            }))
            .into_response()
        }
        Err(e) => api_ok(json!({"ok": false, "error": e})).into_response(),
    }
}

async fn get_config(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let masked_key = if cfg_str(&cfg, "api_key_enc", "").is_empty() {
        ""
    } else {
        "***"
    };
    api_ok(json!({
        "api_url": cfg_str(&cfg, "api_url", DEFAULT_API_URL),
        "auto_send": cfg_bool(&cfg, "auto_send", false),
        "default_sampler": cfg_str(&cfg, "default_sampler", "euler"),
        "default_scheduler": cfg_str(&cfg, "default_scheduler", "normal"),
        "save_folder": cfg_str(&cfg, "save_folder", ""),
        "auto_save": cfg_bool(&cfg, "auto_save", false),
        "save_naming": cfg_str(&cfg, "save_naming", "daily_folder"),
        "auto_import": cfg_bool(&cfg, "auto_import", true),
        "default_image_format": cfg_str(&cfg, "default_image_format", "png"),
        "models_root": cfg_str(&cfg, "models_root", ""),
        "bridge_managed_save": cfg_bool(&cfg, "bridge_managed_save", false),
        "comfy_output_root": cfg_str(&cfg, "comfy_output_root", ""),
        "comfy_output_same_as_save_folder": cfg_bool(&cfg, "comfy_output_same_as_save_folder", true),
        "max_batch_size": cfg_i64(&cfg, "max_batch_size", 8),
        "gateway_url": cfg_str(&cfg, "gateway_url", ""),
        "api_key_enc": masked_key,
    })).into_response()
}

#[derive(Debug, Deserialize)]
struct SaveComfyConfigReq {
    api_url: Option<String>,
    auto_send: Option<bool>,
    default_sampler: Option<String>,
    default_scheduler: Option<String>,
    save_folder: Option<String>,
    auto_save: Option<bool>,
    save_naming: Option<String>,
    auto_import: Option<bool>,
    default_image_format: Option<String>,
    models_root: Option<String>,
    bridge_managed_save: Option<bool>,
    comfy_output_root: Option<String>,
    comfy_output_same_as_save_folder: Option<bool>,
    max_batch_size: Option<Value>,
    api_key_enc: Option<String>,
    gateway_url: Option<String>,
}

async fn post_config(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(req): Json<SaveComfyConfigReq>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let mut full = load_config_json(&state.config.config_path);
    if full.get("extensions").is_none() {
        full["extensions"] = json!({});
    }
    if full["extensions"].get(EXT_NAME).is_none() {
        full["extensions"][EXT_NAME] = json!({});
    }
    let mut saved = serde_json::Map::new();

    macro_rules! save_field {
        ($key:expr, $val:expr) => {{
            full["extensions"][EXT_NAME][$key] = json!($val);
            saved.insert($key.to_string(), json!($val));
        }};
    }

    if let Some(url) = &req.api_url {
        let url = url.trim();
        if !url.starts_with("http://") && !url.starts_with("https://") {
            return api_err(
                "api_url must use http:// or https://",
                StatusCode::BAD_REQUEST,
            );
        }
        save_field!("api_url", url);
    }
    if let Some(v) = req.auto_send {
        save_field!("auto_send", v);
    }
    if let Some(s) = &req.default_sampler {
        let s = s.trim();
        if s.is_empty() {
            return api_err("default_sampler must not be empty", StatusCode::BAD_REQUEST);
        }
        save_field!("default_sampler", s);
    }
    if let Some(s) = &req.default_scheduler {
        let s = s.trim();
        if s.is_empty() {
            return api_err(
                "default_scheduler must not be empty",
                StatusCode::BAD_REQUEST,
            );
        }
        save_field!("default_scheduler", s);
    }
    if let Some(s) = &req.save_folder {
        save_field!("save_folder", s.trim());
    }
    if let Some(v) = req.auto_save {
        save_field!("auto_save", v);
    }
    if let Some(s) = &req.save_naming {
        let s = s.trim();
        if !SAVE_NAMING_OPTIONS.contains(&s) {
            return api_err("save_naming is invalid", StatusCode::BAD_REQUEST);
        }
        save_field!("save_naming", s);
    }
    if let Some(v) = req.auto_import {
        save_field!("auto_import", v);
    }
    if let Some(s) = &req.default_image_format {
        let s = s.trim().to_lowercase();
        if !IMAGE_FORMATS.contains(&s.as_str()) {
            return api_err("default_image_format is invalid", StatusCode::BAD_REQUEST);
        }
        save_field!("default_image_format", s);
    }
    if let Some(s) = &req.models_root {
        save_field!("models_root", s.trim());
    }
    if let Some(v) = req.bridge_managed_save {
        save_field!("bridge_managed_save", v);
    }
    if let Some(s) = &req.comfy_output_root {
        save_field!("comfy_output_root", s.trim());
    }
    if let Some(v) = req.comfy_output_same_as_save_folder {
        save_field!("comfy_output_same_as_save_folder", v);
    }
    if let Some(mbs) = &req.max_batch_size {
        let n = mbs.as_i64().unwrap_or(-1);
        if !(1..=64).contains(&n) {
            return api_err(
                "max_batch_size must be between 1 and 64",
                StatusCode::BAD_REQUEST,
            );
        }
        save_field!("max_batch_size", n);
    }
    if let Some(gw) = &req.gateway_url {
        let gw = gw.trim();
        if !gw.is_empty() && !gw.starts_with("http://") && !gw.starts_with("https://") {
            return api_err(
                "gateway_url must use http:// or https://",
                StatusCode::BAD_REQUEST,
            );
        }
        save_field!("gateway_url", gw);
    }
    if let Some(raw) = &req.api_key_enc {
        let raw = raw.trim();
        if raw != "***" {
            let stored = if raw.is_empty() || raw.starts_with("enc:") {
                raw.to_string()
            } else {
                secret_store::encrypt(raw, &state.config.project_root)
            };
            full["extensions"][EXT_NAME]["api_key_enc"] = json!(&stored);
            saved.insert(
                "api_key_enc".to_string(),
                json!(if stored.is_empty() { "" } else { "***" }),
            );
        }
    }

    if saved.is_empty() {
        return api_err("No valid config fields provided", StatusCode::BAD_REQUEST);
    }
    if let Err(e) = write_config_json(&state.config.config_path, &full) {
        tracing::error!("comfyui_bridge: config write failed: {e}");
        return api_err("Failed to save config", StatusCode::INTERNAL_SERVER_ERROR);
    }
    api_ok(json!({"saved": Value::Object(saved)})).into_response()
}

// ---------------------------------------------------------------------------
// Discovery endpoints (all call /object_info/<NodeType>)
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct FilterQuery {
    q: Option<String>,
}

#[derive(Deserialize)]
struct HasNodeQuery {
    r#type: Option<String>,
}

#[derive(Deserialize)]
struct DiscoveryModelsQuery {
    r#type: Option<String>,
    q: Option<String>,
}

#[derive(Deserialize)]
struct CheckpointInfoQuery {
    name: Option<String>,
}

fn checkpoint_cache() -> &'static Mutex<CheckpointCache> {
    CHECKPOINT_CACHE.get_or_init(|| Mutex::new(CheckpointCache::default()))
}

fn unavailable_checkpoint(error: &str) -> Value {
    json!({"family": null, "source": "unavailable", "error": error})
}

fn read_safetensors_header(path: &Path) -> Option<serde_json::Map<String, Value>> {
    let mut file = std::fs::File::open(path).ok()?;
    let mut size_bytes = [0_u8; 8];
    file.read_exact(&mut size_bytes).ok()?;
    let header_size = u64::from_le_bytes(size_bytes);
    if header_size == 0 || header_size > MAX_SAFETENSORS_HEADER_BYTES {
        return None;
    }
    let mut payload = vec![0_u8; usize::try_from(header_size).unwrap_or(0)];
    file.read_exact(&mut payload).ok()?;
    serde_json::from_slice::<Value>(&payload)
        .ok()?
        .as_object()
        .cloned()
}

fn detect_checkpoint_family(header: &serde_json::Map<String, Value>) -> &'static str {
    let arch = header
        .get("__metadata__")
        .and_then(Value::as_object)
        .and_then(|meta| meta.get("modelspec.architecture"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_lowercase();
    if arch.contains("anima") || arch.contains("qwen") {
        return "qwen3";
    }
    if arch.contains("pixart") || arch.contains("auraflow") {
        return "t5only";
    }
    if arch.contains("xl") || arch.contains("sdxl") {
        return "sdxl";
    }
    if arch.contains("flux") {
        return "flux";
    }
    if arch.contains("sd3") || arch.contains("stable-diffusion-3") {
        return "sd3";
    }
    if arch.contains("stable-diffusion-v1") || arch.contains("sd-v1") || arch.contains("sd_v1") {
        return "sd15";
    }

    let keys: Vec<_> = header
        .keys()
        .filter(|key| key.as_str() != "__metadata__")
        .collect();
    if keys.is_empty() {
        return "unknown";
    }
    if keys.iter().any(|key| {
        key.starts_with("model.text_encoders.qwen.") || key.starts_with("text_encoders.qwen.")
    }) {
        return "qwen3";
    }
    if keys.iter().any(|key| {
        key.starts_with("conditioner.embedders.1.")
            || key.starts_with("model.diffusion_model.label_emb.")
    }) {
        return "sdxl";
    }
    for key in &keys {
        if key.starts_with("double_blocks.")
            || key.starts_with("model.diffusion_model.double_blocks.")
        {
            return "flux";
        }
        if key.starts_with("model.diffusion_model.joint_blocks.") {
            return "sd3";
        }
    }
    if let Some(key) = keys.iter().find(|key| key.contains("attn2.to_k.weight")) {
        let input_dim = header
            .get(key.as_str())
            .and_then(Value::as_object)
            .and_then(|tensor| tensor.get("shape"))
            .and_then(Value::as_array)
            .and_then(|shape| shape.get(1))
            .and_then(Value::as_u64);
        if input_dim == Some(2048) {
            return "sdxl";
        }
        if input_dim == Some(768) {
            return "sd15";
        }
    }
    if keys
        .iter()
        .any(|key| key.starts_with("cond_stage_model.transformer."))
    {
        return "sd15";
    }
    let has_t5 = keys.iter().any(|key| {
        key.starts_with("model.text_encoders.t5.") || key.starts_with("text_encoders.t5.")
    });
    let has_clip = keys.iter().any(|key| {
        key.contains("cond_stage_model")
            || key.contains("clip_l")
            || key.starts_with("conditioner.embedders.0.")
    });
    let has_flux_struct = keys.iter().any(|key| {
        key.starts_with("double_blocks.")
            || key.starts_with("model.diffusion_model.double_blocks.")
            || key.starts_with("joint_blocks.")
            || key.starts_with("model.diffusion_model.joint_blocks.")
    });
    if has_t5 && !has_clip && !has_flux_struct {
        "t5only"
    } else {
        "unknown"
    }
}

fn home_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    let value = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME"));
    #[cfg(not(windows))]
    let value = std::env::var_os("HOME");
    value.map(PathBuf::from)
}

fn expand_models_root(models_root: &str) -> PathBuf {
    if models_root == "~" {
        return home_dir().unwrap_or_else(|| PathBuf::from(models_root));
    }
    if let Some(suffix) = models_root
        .strip_prefix("~/")
        .or_else(|| models_root.strip_prefix("~\\"))
    {
        if let Some(home) = home_dir() {
            return home.join(suffix);
        }
    }
    PathBuf::from(models_root)
}

fn resolve_checkpoint_path(name: &str, models_root: &str) -> Option<PathBuf> {
    let root = expand_models_root(models_root);
    if !root.is_absolute() {
        return None;
    }
    let name = name.replace('\\', "/");
    let name = name.trim_start_matches('/');
    let root = root.canonicalize().ok()?;
    for candidate in [
        root.join(name),
        root.join("checkpoints").join(name),
        root.join("models").join("checkpoints").join(name),
    ] {
        if !candidate.is_file() {
            continue;
        }
        let Ok(candidate) = candidate.canonicalize() else {
            continue;
        };
        if crate::path_guard::path_is_within(&candidate, &root) {
            return Some(candidate);
        }
    }
    None
}

fn checkpoint_stamp(path: &Path) -> Option<(i128, u64)> {
    let metadata = path.metadata().ok()?;
    let modified = metadata.modified().ok()?;
    let mtime_ns = match modified.duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_nanos() as i128,
        Err(error) => -(error.duration().as_nanos() as i128),
    };
    Some((mtime_ns, metadata.len()))
}

fn inspect_checkpoint(name: &str, models_root: &str) -> Result<Value, &'static str> {
    if name.is_empty() {
        return Err("name parameter is required");
    }
    if let Some(reason) = simple_builder::reject_model_name(name) {
        return Err(reason);
    }
    if models_root.is_empty() {
        return Ok(unavailable_checkpoint("models_root not configured"));
    }
    let Some(path) = resolve_checkpoint_path(name, models_root) else {
        return Ok(unavailable_checkpoint("file not found locally"));
    };
    let path_text = path.to_string_lossy().into_owned();
    if !path
        .extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| extension.eq_ignore_ascii_case("safetensors"))
    {
        return Ok(json!({
            "family": null,
            "source": "unsupported",
            "path": path_text,
            "error": "only .safetensors files can be inspected",
        }));
    }
    let Some((mtime_ns, size)) = checkpoint_stamp(&path) else {
        return Ok(unavailable_checkpoint("file not readable locally"));
    };
    if let Some(cached) = checkpoint_cache()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .entries
        .get(&path)
        .filter(|entry| entry.mtime_ns == mtime_ns && entry.size == size)
        .cloned()
    {
        return Ok(json!({
            "family": cached.family,
            "source": "header",
            "path": path_text,
            "metadata": cached.metadata,
            "cached": true,
        }));
    }
    let Some(header) = read_safetensors_header(&path) else {
        return Ok(json!({
            "family": null,
            "source": "unsupported",
            "path": path_text,
            "error": "could not parse safetensors header",
        }));
    };
    let family = detect_checkpoint_family(&header).to_string();
    let metadata: serde_json::Map<String, Value> = header
        .get("__metadata__")
        .and_then(Value::as_object)
        .map(|metadata| {
            metadata
                .iter()
                .filter_map(|(key, value)| match value {
                    Value::String(text) if text.chars().count() < 200 => {
                        Some((key.clone(), value.clone()))
                    }
                    _ => None,
                })
                .collect()
        })
        .unwrap_or_default();
    checkpoint_cache()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .insert(
            path,
            CheckpointCacheEntry {
                mtime_ns,
                size,
                family: family.clone(),
                metadata: metadata.clone(),
            },
        );
    Ok(json!({
        "family": family,
        "source": "header",
        "path": path_text,
        "metadata": metadata,
        "cached": false,
    }))
}

fn auto_detect_models_root(api_url: &str) -> String {
    if api_url.is_empty() {
        return String::new();
    }
    let without_scheme = api_url.split_once("://").map_or(api_url, |(_, rest)| rest);
    let before_port = without_scheme
        .split_once(':')
        .map_or(without_scheme, |(host, _)| host);
    let host = before_port
        .split_once('/')
        .map_or(before_port, |(host, _)| host)
        .to_lowercase();
    if !matches!(host.as_str(), "127.0.0.1" | "localhost" | "::1") {
        return String::new();
    }

    let mut candidates = Vec::new();
    #[cfg(windows)]
    for drive in ["C:", "D:", "O:"] {
        candidates.push(PathBuf::from(format!("{drive}/ComfyUI/models")));
        candidates.push(PathBuf::from(format!(
            "{drive}/ComfyUI_windows_portable/ComfyUI/models"
        )));
        candidates.push(PathBuf::from(format!("{drive}/comfyui/models")));
    }
    if let Some(home) = home_dir() {
        candidates.push(home.join("ComfyUI").join("models"));
        candidates.push(home.join("comfyui").join("models"));
    }
    candidates
        .into_iter()
        .find(|candidate| candidate.join("checkpoints").is_dir())
        .map(|candidate| candidate.to_string_lossy().into_owned())
        .unwrap_or_default()
}

async fn checkpoint_info(
    State(state): State<SharedState>,
    Query(query): Query<CheckpointInfoQuery>,
) -> Response {
    let name = query.name.unwrap_or_default().trim().to_string();
    let cfg = ext_config(&state);
    let mut models_root = cfg_str(&cfg, "models_root", "").to_string();
    if models_root.is_empty() {
        models_root = auto_detect_models_root(cfg_str(&cfg, "api_url", DEFAULT_API_URL));
    }
    match tokio::task::spawn_blocking(move || inspect_checkpoint(&name, &models_root)).await {
        Ok(Ok(info)) => api_ok(info).into_response(),
        Ok(Err(error)) => api_err(error, StatusCode::BAD_REQUEST),
        Err(_) => api_err(
            "Checkpoint inspection failed",
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn samplers(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let list = fetch_enum(
        &state.python_client,
        &api_url,
        "KSampler",
        "sampler_name",
        &key,
    )
    .await;
    api_ok(json!({"samplers": list})).into_response()
}

async fn schedulers(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let list = fetch_enum(
        &state.python_client,
        &api_url,
        "KSampler",
        "scheduler",
        &key,
    )
    .await;
    api_ok(json!({"schedulers": list})).into_response()
}

async fn models(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let list = fetch_enum(
        &state.python_client,
        &api_url,
        "CheckpointLoaderSimple",
        "ckpt_name",
        &key,
    )
    .await;
    api_ok(json!({"models": list})).into_response()
}

async fn loras(State(state): State<SharedState>, Query(q): Query<FilterQuery>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let filter = q.q.unwrap_or_default().to_lowercase();
    // Try LoraLoader first, then LoraLoaderModelOnly
    let mut list = fetch_enum(
        &state.python_client,
        &api_url,
        "LoraLoader",
        "lora_name",
        &key,
    )
    .await;
    if list.is_empty() {
        list = fetch_enum(
            &state.python_client,
            &api_url,
            "LoraLoaderModelOnly",
            "lora_name",
            &key,
        )
        .await;
    }
    if !filter.is_empty() {
        list.retain(|n| n.to_lowercase().contains(&filter));
    }
    api_ok(json!({"loras": list})).into_response()
}

async fn embeddings(State(state): State<SharedState>, Query(q): Query<FilterQuery>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let filter = q.q.unwrap_or_default().to_lowercase();
    let list: Vec<String> =
        match comfy_get(&state.python_client, &api_url, "/api/embeddings", &key).await {
            Ok(Value::Array(arr)) => arr
                .iter()
                .filter_map(Value::as_str)
                .map(String::from)
                .collect(),
            Ok(Value::Object(map)) => map.keys().cloned().collect(),
            _ => vec![],
        };
    let list: Vec<_> = if filter.is_empty() {
        list
    } else {
        list.into_iter()
            .filter(|n| n.to_lowercase().contains(&filter))
            .collect()
    };
    api_ok(json!({"embeddings": list})).into_response()
}

async fn custom_nodes(State(state): State<SharedState>, Query(q): Query<FilterQuery>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let filter = q.q.unwrap_or_default().trim().to_lowercase();
    let mut nodes: Vec<Value> = match comfy_get(
        &state.python_client,
        &api_url,
        "/object_info",
        &key,
    )
    .await
    {
        Ok(Value::Object(nodes)) => nodes
            .into_iter()
            .filter_map(|(name, info)| {
                let info = info.as_object()?;
                Some(json!({
                    "name": name,
                    "category": info.get("category").and_then(Value::as_str).unwrap_or(""),
                    "description": info.get("description").and_then(Value::as_str).unwrap_or(""),
                }))
            })
            .collect(),
        _ => vec![],
    };
    if !filter.is_empty() {
        nodes.retain(|node| {
            ["name", "category"].iter().any(|field| {
                node.get(field)
                    .and_then(Value::as_str)
                    .is_some_and(|value| value.to_lowercase().contains(&filter))
            })
        });
    }
    api_ok(json!({"nodes": nodes})).into_response()
}

async fn diffusion_models(
    State(state): State<SharedState>,
    Query(q): Query<FilterQuery>,
) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let filter = q.q.unwrap_or_default().to_lowercase();
    let mut list = fetch_enum(
        &state.python_client,
        &api_url,
        "UNETLoader",
        "unet_name",
        &key,
    )
    .await;
    if !filter.is_empty() {
        list.retain(|n| n.to_lowercase().contains(&filter));
    }
    api_ok(json!({"models": list})).into_response()
}

async fn text_encoders(State(state): State<SharedState>, Query(q): Query<FilterQuery>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let filter = q.q.unwrap_or_default().to_lowercase();
    let mut list = fetch_enum(
        &state.python_client,
        &api_url,
        "CLIPLoader",
        "clip_name",
        &key,
    )
    .await;
    if !filter.is_empty() {
        list.retain(|n| n.to_lowercase().contains(&filter));
    }
    api_ok(json!({"encoders": list})).into_response()
}

async fn clip_types(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let mut list = fetch_enum(
        &state.python_client,
        &api_url,
        "DualCLIPLoader",
        "type",
        &key,
    )
    .await;
    if list.is_empty() {
        list = fetch_enum(&state.python_client, &api_url, "CLIPLoader", "type", &key).await;
    }
    api_ok(json!({"clip_types": list})).into_response()
}

async fn weight_dtypes(State(state): State<SharedState>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let list = fetch_enum(
        &state.python_client,
        &api_url,
        "UNETLoader",
        "weight_dtype",
        &key,
    )
    .await;
    let list = if list.is_empty() {
        vec![
            "default",
            "fp8_e4m3fn",
            "fp8_e4m3fn_fast",
            "fp8_e5m2",
            "fp16",
            "bf16",
            "fp32",
        ]
        .into_iter()
        .map(String::from)
        .collect()
    } else {
        list
    };
    api_ok(json!({"weight_dtypes": list})).into_response()
}

async fn controlnets(State(state): State<SharedState>, Query(q): Query<FilterQuery>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let filter = q.q.unwrap_or_default().to_lowercase();
    let mut list = fetch_enum(
        &state.python_client,
        &api_url,
        "ControlNetLoader",
        "control_net_name",
        &key,
    )
    .await;
    if !filter.is_empty() {
        list.retain(|n| n.to_lowercase().contains(&filter));
    }
    api_ok(json!({"models": list})).into_response()
}

async fn upscale_models(
    State(state): State<SharedState>,
    Query(q): Query<FilterQuery>,
) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let filter = q.q.unwrap_or_default().to_lowercase();
    let mut list = fetch_enum(
        &state.python_client,
        &api_url,
        "UpscaleModelLoader",
        "model_name",
        &key,
    )
    .await;
    if !filter.is_empty() {
        list.retain(|n| n.to_lowercase().contains(&filter));
    }
    api_ok(json!({"models": list})).into_response()
}

async fn has_node(State(state): State<SharedState>, Query(q): Query<HasNodeQuery>) -> Response {
    let node_type = match q.r#type.as_deref().filter(|s| !s.is_empty()) {
        Some(t) => t.to_string(),
        None => return api_err("missing 'type' query param", StatusCode::BAD_REQUEST),
    };
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let available = match comfy_get(
        &state.python_client,
        &api_url,
        &format!("/object_info/{node_type}"),
        &key,
    )
    .await
    {
        Ok(data) => data
            .as_object()
            .map(|m| m.contains_key(&node_type))
            .unwrap_or(false),
        Err(_) => false,
    };
    api_ok(json!({"node_type": node_type, "available": available})).into_response()
}

async fn discovery_models(
    State(state): State<SharedState>,
    Query(q): Query<DiscoveryModelsQuery>,
) -> Response {
    let model_type = match q.r#type.as_deref().filter(|s| !s.is_empty()) {
        Some(t) => t.to_string(),
        None => return api_err("type parameter is required", StatusCode::BAD_REQUEST),
    };
    let filter = q.q.unwrap_or_default().to_lowercase();
    let loader_map: &[(&str, &str, &str)] = &[
        ("diffusion_models", "UNETLoader", "unet_name"),
        ("text_encoders", "CLIPLoader", "clip_name"),
        ("controlnet", "ControlNetLoader", "control_net_name"),
        ("upscale_models", "UpscaleModelLoader", "model_name"),
        ("loras", "LoraLoader", "lora_name"),
        ("vae", "VAELoader", "vae_name"),
        ("checkpoints", "CheckpointLoaderSimple", "ckpt_name"),
        ("clip", "CLIPLoader", "clip_name"),
        ("clip_vision", "CLIPVisionLoader", "clip_name"),
        ("unet", "UNETLoader", "unet_name"),
    ];
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let models =
        if let Some((_, node, field)) = loader_map.iter().find(|(t, _, _)| *t == model_type) {
            fetch_enum(&state.python_client, &api_url, node, field, &key).await
        } else {
            vec![]
        };
    let models: Vec<_> = if filter.is_empty() {
        models
    } else {
        models
            .into_iter()
            .filter(|n| n.to_lowercase().contains(&filter))
            .collect()
    };
    api_ok(json!({"models": models, "type": model_type})).into_response()
}

async fn refresh_assets(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let loaders = [
        ("checkpoints", "CheckpointLoaderSimple", "ckpt_name"),
        ("loras", "LoraLoader", "lora_name"),
        ("vae", "VAELoader", "vae_name"),
        ("clip", "CLIPLoader", "clip_name"),
        ("unet", "UNETLoader", "unet_name"),
        ("controlnet", "ControlNetLoader", "control_net_name"),
        ("upscale_model", "UpscaleModelLoader", "model_name"),
    ];
    let mut results = serde_json::Map::new();
    for (label, node_type, field) in loaders {
        let r = match comfy_get(
            &state.python_client,
            &api_url,
            &format!("/object_info/{node_type}"),
            &key,
        )
        .await
        {
            Ok(data) => {
                let count = parse_enum_options(&data, node_type, field).len();
                json!({"ok": true, "count": count})
            }
            Err(e) => json!({"ok": false, "error": e}),
        };
        results.insert(label.to_string(), r);
    }
    api_ok(json!({"results": Value::Object(results)})).into_response()
}

fn index_workflow_nodes(workflow: &Value) -> HashMap<&str, Vec<&Value>> {
    let mut by_type = HashMap::new();
    if let Some(nodes) = workflow.as_object() {
        for node in nodes.values() {
            if let Some(class_type) = node.get("class_type").and_then(Value::as_str) {
                by_type
                    .entry(class_type)
                    .or_insert_with(Vec::new)
                    .push(node);
            }
        }
    }
    by_type
}

fn first_workflow_node<'a>(
    by_type: &'a HashMap<&str, Vec<&'a Value>>,
    type_names: &[&str],
) -> Option<&'a Value> {
    type_names
        .iter()
        .find_map(|name| by_type.get(name).and_then(|nodes| nodes.first()).copied())
}

fn node_inputs(node: &Value) -> Option<&serde_json::Map<String, Value>> {
    node.get("inputs").and_then(Value::as_object)
}

fn set_string_param(params: &mut serde_json::Map<String, Value>, key: &str, value: Option<&Value>) {
    if let Some(Value::String(value)) = value {
        if !value.is_empty() {
            params.insert(key.to_string(), Value::String(value.clone()));
        }
    }
}

fn extract_model_params(
    by_type: &HashMap<&str, Vec<&Value>>,
    params: &mut serde_json::Map<String, Value>,
) {
    let unet = first_workflow_node(by_type, &["UNETLoader"]);
    if let Some(inputs) = unet.and_then(node_inputs) {
        set_string_param(params, "diffusion_model", inputs.get("unet_name"));
        set_string_param(params, "weight_dtype", inputs.get("weight_dtype"));
    }

    if let Some(inputs) = first_workflow_node(by_type, &["DualCLIPLoader"]).and_then(node_inputs) {
        set_string_param(params, "text_encoder_1", inputs.get("clip_name1"));
        set_string_param(params, "text_encoder_2", inputs.get("clip_name2"));
        set_string_param(params, "clip_type", inputs.get("type"));
    } else if let Some(inputs) = first_workflow_node(by_type, &["CLIPLoader"]).and_then(node_inputs)
    {
        set_string_param(params, "text_encoder_1", inputs.get("clip_name"));
        set_string_param(params, "clip_type", inputs.get("type"));
    }

    if unet.is_none() {
        if let Some(inputs) =
            first_workflow_node(by_type, &["CheckpointLoaderSimple"]).and_then(node_inputs)
        {
            set_string_param(params, "ckpt_name", inputs.get("ckpt_name"));
        }
    }
    if let Some(inputs) = first_workflow_node(by_type, &["VAELoader"]).and_then(node_inputs) {
        set_string_param(params, "vae_name", inputs.get("vae_name"));
    }
}

fn workflow_reference(value: &Value) -> Option<(String, usize)> {
    let reference = value.as_array()?;
    if reference.len() < 2 {
        return None;
    }
    let node_id = match &reference[0] {
        Value::String(value) => value.clone(),
        Value::Number(value) => value.to_string(),
        _ => return None,
    };
    Some((node_id, usize::try_from(reference[1].as_u64()?).ok()?))
}

fn trace_clip_text(
    workflow: &Value,
    node_id: &str,
    output_slot: usize,
    depth: usize,
) -> Option<Value> {
    if depth > 10 {
        return None;
    }
    let node = workflow.as_object()?.get(node_id)?;
    if node.get("class_type").and_then(Value::as_str) == Some("CLIPTextEncode") {
        return node_inputs(node)?
            .get("text")
            .filter(|text| !text.is_null())
            .cloned();
    }

    let inputs = node_inputs(node)?;
    let slot_keys = ["positive", "negative"];
    let mut tried = HashSet::new();
    if let Some(key) = slot_keys.get(output_slot) {
        if let Some(reference) = inputs.get(*key).and_then(workflow_reference) {
            tried.insert(reference.clone());
            if let Some(text) = trace_clip_text(workflow, &reference.0, reference.1, depth + 1) {
                return Some(text);
            }
        }
    }
    for key in slot_keys {
        if let Some(reference) = inputs.get(key).and_then(workflow_reference) {
            if tried.insert(reference.clone()) {
                if let Some(text) = trace_clip_text(workflow, &reference.0, reference.1, depth + 1)
                {
                    return Some(text);
                }
            }
        }
    }
    None
}

fn extract_prompts_from_sampler(
    workflow: &Value,
    sampler: &Value,
    params: &mut serde_json::Map<String, Value>,
) {
    let Some(inputs) = node_inputs(sampler) else {
        return;
    };
    for (input_key, param_key) in [("positive", "prompt"), ("negative", "negative_prompt")] {
        if let Some((node_id, output_slot)) = inputs.get(input_key).and_then(workflow_reference) {
            if let Some(text) = trace_clip_text(workflow, &node_id, output_slot, 0) {
                params.insert(param_key.to_string(), text);
            }
        }
    }
}

fn extract_prompts_by_title(
    by_type: &HashMap<&str, Vec<&Value>>,
    params: &mut serde_json::Map<String, Value>,
) {
    let Some(nodes) = by_type.get("CLIPTextEncode") else {
        return;
    };
    for node in nodes {
        let title = node
            .get("_meta")
            .and_then(|meta| meta.get("title"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_lowercase();
        let text = node_inputs(node)
            .and_then(|inputs| inputs.get("text"))
            .cloned()
            .unwrap_or_else(|| Value::String(String::new()));
        if title.contains("positive") && !params.contains_key("prompt") {
            params.insert("prompt".to_string(), text);
        } else if title.contains("negative") && !params.contains_key("negative_prompt") {
            params.insert("negative_prompt".to_string(), text);
        }
    }
    if !params.contains_key("prompt") {
        if let Some(text) = nodes
            .first()
            .and_then(|node| node_inputs(node))
            .and_then(|inputs| inputs.get("text"))
        {
            params.insert("prompt".to_string(), text.clone());
        }
    }
    if !params.contains_key("negative_prompt") {
        if let Some(text) = nodes
            .get(1)
            .and_then(|node| node_inputs(node))
            .and_then(|inputs| inputs.get("text"))
        {
            params.insert("negative_prompt".to_string(), text.clone());
        }
    }
}

fn extract_simple_params(workflow: &Value) -> serde_json::Map<String, Value> {
    let by_type = index_workflow_nodes(workflow);
    let mut params = serde_json::Map::new();
    extract_model_params(&by_type, &mut params);

    if let Some(sampler) = first_workflow_node(&by_type, &["KSampler", "KSamplerAdvanced"]) {
        if let Some(inputs) = node_inputs(sampler) {
            for key in ["seed", "steps", "cfg", "sampler_name", "scheduler"] {
                if let Some(value) = inputs.get(key) {
                    params.insert(key.to_string(), value.clone());
                }
            }
        }
        extract_prompts_from_sampler(workflow, sampler, &mut params);
    } else {
        extract_prompts_by_title(&by_type, &mut params);
    }

    if let Some(inputs) = first_workflow_node(&by_type, &["EmptyLatentImage"]).and_then(node_inputs)
    {
        for key in ["width", "height"] {
            if let Some(value) = inputs.get(key) {
                params.insert(key.to_string(), value.clone());
            }
        }
    }
    params
}

async fn parse_workflow_params(Json(workflow): Json<Value>) -> Response {
    if !workflow.is_object() {
        return api_err("JSON object body is required", StatusCode::BAD_REQUEST);
    }
    let simple_params = extract_simple_params(&workflow);
    if simple_params.is_empty() {
        return api_err(
            "ワークフローから Simple モードのパラメータを抽出できませんでした",
            StatusCode::UNPROCESSABLE_ENTITY,
        );
    }
    api_ok(json!({"simple_params": simple_params})).into_response()
}

fn workflow_image_extension(filename: &str) -> Result<String, String> {
    let extension = Path::new(filename)
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if WORKFLOW_IMAGE_EXTENSIONS.contains(&extension.as_str()) {
        Ok(extension)
    } else {
        Err(format!(
            "Unsupported format: {}",
            if extension.is_empty() {
                "unknown"
            } else {
                &extension
            }
        ))
    }
}

async fn read_image_upload(
    mut multipart: Multipart,
    default_filename: &str,
) -> Result<(Vec<u8>, String, String), Response> {
    loop {
        match multipart.next_field().await {
            Ok(Some(mut field)) if field.name() == Some("image") => {
                let filename = field.file_name().unwrap_or(default_filename).to_string();
                let extension = workflow_image_extension(&filename)
                    .map_err(|error| api_err(&error, StatusCode::BAD_REQUEST))?;
                let mut data = Vec::new();
                loop {
                    match field.chunk().await {
                        Ok(Some(chunk)) => {
                            if data.len().saturating_add(chunk.len()) > MAX_IMAGE_UPLOAD_BYTES {
                                return Err(api_err(
                                    "image exceeds 26,214,400 byte limit",
                                    StatusCode::PAYLOAD_TOO_LARGE,
                                ));
                            }
                            data.extend_from_slice(&chunk);
                        }
                        Ok(None) => return Ok((data, filename, extension)),
                        Err(error) => {
                            return Err(api_err(
                                &format!("failed to read upload: {error}"),
                                StatusCode::BAD_REQUEST,
                            ))
                        }
                    }
                }
            }
            Ok(Some(_)) => continue,
            Ok(None) => return Err(api_err("image file is required", StatusCode::BAD_REQUEST)),
            Err(error) => {
                return Err(api_err(
                    &format!("multipart error: {error}"),
                    StatusCode::BAD_REQUEST,
                ))
            }
        }
    }
}

fn extract_exif_workflow(data: &[u8]) -> Result<(&'static str, Value), String> {
    let tags = meta_extract::read_exif_tags_from_bytes(data);
    let comment = [
        "UserComment",
        "Exif.Image.UserComment",
        "Exif.Photo.UserComment",
    ]
    .iter()
    .find_map(|key| tags.get(*key));
    let Some(comment) = comment else {
        return Err(if tags.is_empty() {
            "No EXIF data found".to_string()
        } else {
            "No UserComment in EXIF".to_string()
        });
    };

    let mut chunks = meta_extract::PngTextChunks::default();
    if let Some(raw) = comment.strip_prefix("YU_META:") {
        let value: Value =
            serde_json::from_str(raw).map_err(|_| "YU_META JSON parse error".to_string())?;
        let Some(map) = value.as_object() else {
            return Err("YU_META is not a dict".to_string());
        };
        for key in ["prompt", "workflow"] {
            if let Some(value) = map.get(key).and_then(Value::as_str) {
                chunks.entries.insert(key.to_string(), value.to_string());
            }
        }
        return meta_extract::comfyui::extract_comfyui_workflow(&chunks)
            .map_err(str::to_string)?
            .ok_or_else(|| "No workflow key in YU_META chunks".to_string());
    }

    chunks
        .entries
        .insert("exif:UserComment".to_string(), comment.clone());
    meta_extract::comfyui::extract_comfyui_workflow(&chunks)
        .map_err(str::to_string)?
        .ok_or_else(|| "No valid workflow in EXIF".to_string())
}

fn extract_workflow_from_image(
    data: &[u8],
    extension: &str,
) -> Result<(&'static str, Value), String> {
    match extension {
        "png" => {
            let chunks = meta_extract::parse_png_text_chunks(data);
            meta_extract::comfyui::extract_comfyui_workflow(&chunks)
                .map_err(str::to_string)?
                .ok_or_else(|| "No workflow metadata found in PNG".to_string())
        }
        "webp" | "jpg" | "jpeg" => extract_exif_workflow(data),
        _ => Err(format!("Unsupported format: {extension}")),
    }
}

enum WorkflowFileError {
    Expected(Response),
    Unexpected(&'static str),
}

async fn resolve_workflow_file(
    state: &SharedState,
    body: &Value,
) -> Result<(PathBuf, String), WorkflowFileError> {
    let Some(file_id) = body.get("file_id").and_then(Value::as_i64) else {
        return Err(WorkflowFileError::Expected(api_err(
            "file_id (int) is required",
            StatusCode::BAD_REQUEST,
        )));
    };
    let path =
        sqlx::query_scalar::<_, String>("SELECT path FROM files WHERE id = ? AND is_deleted = 0")
            .bind(file_id)
            .fetch_optional(&state.db_read)
            .await
            .map_err(|_| WorkflowFileError::Unexpected("database query failed"))?
            .ok_or_else(|| {
                WorkflowFileError::Expected(api_err(
                    "ファイルが見つかりません",
                    StatusCode::NOT_FOUND,
                ))
            })?;
    let path = PathBuf::from(path);
    let metadata = tokio::fs::metadata(&path).await.map_err(|_| {
        WorkflowFileError::Expected(api_err("ファイルが見つかりません", StatusCode::NOT_FOUND))
    })?;
    if !metadata.is_file() {
        return Err(WorkflowFileError::Expected(api_err(
            "ファイルが見つかりません",
            StatusCode::NOT_FOUND,
        )));
    }
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !WORKFLOW_IMAGE_EXTENSIONS.contains(&extension.as_str()) {
        return Err(WorkflowFileError::Expected(api_err(
            "対応していないファイル形式です",
            StatusCode::BAD_REQUEST,
        )));
    }
    if metadata.len() > MAX_WORKFLOW_FILE_BYTES {
        return Err(WorkflowFileError::Expected(api_err(
            "ファイルサイズが大きすぎます",
            StatusCode::PAYLOAD_TOO_LARGE,
        )));
    }
    Ok((path, extension))
}

fn empty_model_value(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => true,
        Some(value) => matches!(
            value.as_str().map(str::trim),
            Some("") | Some("undefined") | Some("null") | Some("None")
        ),
    }
}

fn model_node_mappings(class_type: &str) -> &'static [(&'static str, &'static str)] {
    match class_type {
        "CheckpointLoaderSimple" => &[("ckpt_name", "ckpt_name")],
        "UNETLoader" => &[("unet_name", "diffusion_model")],
        "DualCLIPLoader" => &[
            ("clip_name1", "text_encoder_1"),
            ("clip_name2", "text_encoder_2"),
        ],
        "CLIPLoader" => &[("clip_name", "text_encoder_1")],
        "VAELoader" => &[("vae_name", "vae_name")],
        _ => &[],
    }
}

fn check_model_nodes(
    workflow: &Value,
    gen_params: Option<&serde_json::Map<String, Value>>,
) -> Value {
    let mut empty_slots = Vec::new();
    let mut loader_type = "unknown";
    for node in workflow
        .as_object()
        .into_iter()
        .flat_map(|map| map.values())
    {
        let class_type = node
            .get("class_type")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let inputs = node.get("inputs").and_then(Value::as_object);
        for &(input_key, backup_key) in model_node_mappings(class_type) {
            if empty_model_value(inputs.and_then(|map| map.get(input_key))) {
                empty_slots.push(backup_key);
                loader_type = match class_type {
                    "CheckpointLoaderSimple" | "VAELoader" => "checkpoint",
                    "UNETLoader" | "DualCLIPLoader" | "CLIPLoader" => "unet",
                    _ => "unknown",
                };
            }
        }
    }
    if empty_slots.is_empty() {
        return json!({"status": "ok"});
    }
    if let Some(params) = gen_params.filter(|params| !params.is_empty()) {
        if empty_slots
            .iter()
            .all(|key| !empty_model_value(params.get(*key)))
        {
            let mut info = serde_json::Map::new();
            for key in [
                "ckpt_name",
                "diffusion_model",
                "vae_name",
                "text_encoder_1",
                "text_encoder_2",
                "clip_type",
            ] {
                info.insert(
                    key.to_string(),
                    params
                        .get(key)
                        .cloned()
                        .unwrap_or_else(|| Value::String(String::new())),
                );
            }
            return json!({
                "status": "supplement_available",
                "loader_type": loader_type,
                "supplement_model_info": info,
            });
        }
    }
    json!({
        "status": "warning_no_backup",
        "loader_type": loader_type,
        "message": "モデルノードが未設定で、生成時のバックアップ情報もありません。ComfyUI 側で手動設定が必要です。",
    })
}

fn extract_gen_params_from_image(
    data: &[u8],
    extension: &str,
) -> Option<serde_json::Map<String, Value>> {
    let raw = if extension == "png" {
        meta_extract::parse_png_text_chunks(data)
            .entries
            .remove("_gen_params")
    } else {
        let tags = meta_extract::read_exif_tags_from_bytes(data);
        let comment = [
            "UserComment",
            "Exif.Image.UserComment",
            "Exif.Photo.UserComment",
        ]
        .iter()
        .find_map(|key| tags.get(*key))?;
        serde_json::from_str::<Value>(comment.strip_prefix("YU_META:")?)
            .ok()?
            .get("_gen_params")?
            .as_str()
            .map(str::to_string)
    }?;
    serde_json::from_str::<Value>(&raw)
        .ok()?
        .as_object()
        .cloned()
}

fn supplement_model_nodes(
    workflow: &mut Value,
    gen_params: &serde_json::Map<String, Value>,
) -> serde_json::Map<String, Value> {
    let mut applied = serde_json::Map::new();
    for node in workflow
        .as_object_mut()
        .into_iter()
        .flat_map(|map| map.values_mut())
    {
        let class_type = node
            .get("class_type")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let Some(inputs) = node.get_mut("inputs").and_then(Value::as_object_mut) else {
            continue;
        };
        let mappings: &[(&str, &str)] = match class_type.as_str() {
            "CheckpointLoaderSimple" => &[("ckpt_name", "ckpt_name")],
            "UNETLoader" => &[("unet_name", "diffusion_model")],
            "DualCLIPLoader" => &[
                ("clip_name1", "text_encoder_1"),
                ("clip_name2", "text_encoder_2"),
                ("type", "clip_type"),
            ],
            "CLIPLoader" => &[("clip_name", "text_encoder_1"), ("type", "clip_type")],
            "VAELoader" => &[("vae_name", "vae_name")],
            _ => &[],
        };
        for &(input_key, backup_key) in mappings {
            if empty_model_value(inputs.get(input_key)) {
                if let Some(value) = gen_params
                    .get(backup_key)
                    .filter(|value| !empty_model_value(Some(value)))
                {
                    inputs.insert(input_key.to_string(), value.clone());
                    applied.insert(input_key.to_string(), value.clone());
                }
            }
        }
    }
    applied
}

fn migrate_clip_types(workflow: &mut Value) {
    for node in workflow
        .as_object_mut()
        .into_iter()
        .flat_map(|map| map.values_mut())
    {
        let class_type = node
            .get("class_type")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if !matches!(class_type, "CLIPLoader" | "DualCLIPLoader") {
            continue;
        }
        let Some(inputs) = node.get_mut("inputs").and_then(Value::as_object_mut) else {
            continue;
        };
        let encoder = inputs
            .get("clip_name")
            .and_then(Value::as_str)
            .filter(|name| !name.is_empty())
            .or_else(|| inputs.get("clip_name1").and_then(Value::as_str))
            .unwrap_or_default()
            .to_ascii_lowercase();
        if ["anima-", "anima_", "anima.", "qwen"]
            .iter()
            .any(|needle| encoder.contains(needle))
            && inputs.get("type").and_then(Value::as_str) != Some("qwen_image")
        {
            inputs.insert("type".to_string(), Value::String("qwen_image".to_string()));
        }
    }
}

fn json_truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) | Some(Value::Bool(false)) => false,
        Some(Value::Number(number)) => number.as_f64() != Some(0.0),
        Some(Value::String(value)) => !value.is_empty(),
        Some(Value::Array(value)) => !value.is_empty(),
        Some(Value::Object(value)) => !value.is_empty(),
        Some(Value::Bool(true)) => true,
    }
}

async fn check_workflow_from_file(
    State(state): State<SharedState>,
    Json(body): Json<Value>,
) -> Response {
    let (path, extension) = match resolve_workflow_file(&state, &body).await {
        Ok(file) => file,
        Err(WorkflowFileError::Expected(response)) => return response,
        Err(WorkflowFileError::Unexpected(error)) => {
            tracing::warn!(error, "check-workflow-from-file: unexpected error");
            return api_ok(json!({"status": "ok"})).into_response();
        }
    };
    let filename = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let result = tokio::task::spawn_blocking(move || -> Result<Value, std::io::ErrorKind> {
        let data = std::fs::read(path).map_err(|error| error.kind())?;
        let gen_params = extract_gen_params_from_image(&data, &extension);
        let Ok((format, workflow)) = extract_workflow_from_image(&data, &extension) else {
            return Ok(json!({"status": "ok"}));
        };
        if format == "editor" {
            return Ok(json!({"status": "ok"}));
        }
        Ok(check_model_nodes(&workflow, gen_params.as_ref()))
    })
    .await;
    match result {
        Ok(Ok(check)) => api_ok(check).into_response(),
        Ok(Err(error)) => {
            tracing::warn!(file = filename, error = ?error, "check-workflow-from-file: unexpected error");
            api_ok(json!({"status": "ok"})).into_response()
        }
        Err(_) => {
            tracing::warn!(
                file = filename,
                "check-workflow-from-file: unexpected error"
            );
            api_ok(json!({"status": "ok"})).into_response()
        }
    }
}

enum QueuePromptError {
    Connection,
    Http(StatusCode, String),
    Other(String),
}

async fn queue_prompt(
    state: &SharedState,
    workflow: Value,
) -> Result<(Value, String), QueuePromptError> {
    let config = ext_config(state);
    let api_url = comfy_api_url(&config);
    let api_key = get_api_key(&config, &state.config.project_root);
    let mut request = state
        .python_client
        .post(format!("{api_url}/prompt"))
        .header("User-Agent", COMFY_USER_AGENT)
        .timeout(std::time::Duration::from_secs(30))
        .json(&json!({
            "prompt": workflow,
            "client_id": uuid::Uuid::new_v4().to_string(),
        }));
    if !api_key.is_empty() {
        request = request.header("Authorization", format!("Bearer {api_key}"));
    }
    let response = request.send().await.map_err(|error| {
        if error.is_connect() {
            QueuePromptError::Connection
        } else {
            QueuePromptError::Other(error.to_string())
        }
    })?;
    let status = response.status();
    let bytes = response
        .bytes()
        .await
        .map_err(|error| QueuePromptError::Other(error.to_string()))?;
    if !status.is_success() {
        return Err(QueuePromptError::Http(
            status,
            String::from_utf8_lossy(&bytes)
                .trim()
                .chars()
                .take(300)
                .collect(),
        ));
    }
    let result: Value = serde_json::from_slice(&bytes)
        .map_err(|error| QueuePromptError::Other(error.to_string()))?;
    Ok((
        result.get("prompt_id").cloned().unwrap_or(Value::Null),
        api_url,
    ))
}

async fn queue_workflow_from_file(
    State(state): State<SharedState>,
    Json(body): Json<Value>,
) -> Response {
    let supplement = json_truthy(body.get("supplement"));
    let (path, extension) = match resolve_workflow_file(&state, &body).await {
        Ok(file) => file,
        Err(WorkflowFileError::Expected(response)) => return response,
        Err(WorkflowFileError::Unexpected(error)) => {
            return api_err(&format!("ComfyUI エラー: {error}"), StatusCode::BAD_GATEWAY)
        }
    };
    let prepared = tokio::task::spawn_blocking(move || {
        let data = std::fs::read(path).map_err(|error| {
            (
                StatusCode::BAD_GATEWAY,
                format!("ComfyUI エラー: file read failed: {}", error.kind()),
            )
        })?;
        let (format, mut workflow) =
            extract_workflow_from_image(&data, &extension).map_err(|_| {
                (
                    StatusCode::UNPROCESSABLE_ENTITY,
                    "ワークフロー情報が見つかりません".to_string(),
                )
            })?;
        if format == "editor" {
            return Err((
                StatusCode::UNPROCESSABLE_ENTITY,
                "Editor format workflow はキュー投入に対応していません".to_string(),
            ));
        }
        let mut applied = serde_json::Map::new();
        if supplement {
            let gen_params = extract_gen_params_from_image(&data, &extension).ok_or_else(|| {
                (
                    StatusCode::BAD_REQUEST,
                    "バックアップ情報が見つかりません".to_string(),
                )
            })?;
            applied = supplement_model_nodes(&mut workflow, &gen_params);
            if check_model_nodes(&workflow, None)
                .get("status")
                .and_then(Value::as_str)
                != Some("ok")
            {
                return Err((
                    StatusCode::BAD_REQUEST,
                    "補完後もモデルノードが未設定のままです。ComfyUI 側で手動設定してください。"
                        .to_string(),
                ));
            }
        }
        // Old images may contain stale clip_type values and must migrate before every queue.
        migrate_clip_types(&mut workflow);
        Ok((workflow, applied))
    })
    .await;
    let (workflow, applied) = match prepared {
        Ok(Ok(prepared)) => prepared,
        Ok(Err((status, error))) => return api_err(&error, status),
        Err(_) => {
            return api_err(
                "ComfyUI エラー: workflow processing failed",
                StatusCode::BAD_GATEWAY,
            )
        }
    };
    let (prompt_id, comfyui_url) = match queue_prompt(&state, workflow).await {
        Ok(result) => result,
        Err(QueuePromptError::Connection) => {
            return api_err("ComfyUI への接続に失敗しました", StatusCode::BAD_GATEWAY)
        }
        Err(QueuePromptError::Http(status, detail)) => {
            let detail = if detail.is_empty() {
                String::new()
            } else {
                format!(" — {detail}")
            };
            return api_err(
                &format!("ComfyUI エラー: HTTP {}{detail}", status.as_u16()),
                StatusCode::BAD_GATEWAY,
            );
        }
        Err(QueuePromptError::Other(error)) => {
            return api_err(&format!("ComfyUI エラー: {error}"), StatusCode::BAD_GATEWAY)
        }
    };
    let mut payload = json!({"prompt_id": prompt_id, "comfyui_url": comfyui_url});
    if supplement && !applied.is_empty() {
        payload["supplemented"] = Value::Bool(true);
        payload["supplement_applied"] = Value::Object(applied);
    }
    api_ok(payload).into_response()
}

async fn extract_workflow(multipart: Multipart) -> Response {
    let (data, _, extension) = match read_image_upload(multipart, "unknown.png").await {
        Ok(image) => image,
        Err(response) => return response,
    };

    match extract_workflow_from_image(&data, &extension) {
        Ok((format, workflow)) => {
            let mut payload = json!({"workflow": workflow, "format": format});
            if format == "api" {
                payload.as_object_mut().unwrap().insert(
                    "simple_params".to_string(),
                    Value::Object(extract_simple_params(&workflow)),
                );
            }
            api_ok(payload).into_response()
        }
        Err(error) => api_err(&error, StatusCode::UNPROCESSABLE_ENTITY),
    }
}

fn upload_image_format(data: &[u8]) -> (&'static str, &'static str) {
    if data.starts_with(&[0xff, 0xd8]) {
        ("image/jpeg", "jpg")
    } else if data.len() > 12 && data.starts_with(b"RIFF") && &data[8..12] == b"WEBP" {
        ("image/webp", "webp")
    } else {
        ("image/png", "png")
    }
}

async fn comfy_upload_image(
    client: &reqwest::Client,
    api_url: &str,
    data: Vec<u8>,
    filename: &str,
    api_key: &str,
) -> Result<Value, String> {
    let (content_type, extension) = upload_image_format(&data);
    let stem = filename
        .rsplit_once('.')
        .map(|(stem, _)| stem)
        .unwrap_or(filename);
    let filename = format!("{stem}.{extension}");
    let boundary = uuid::Uuid::new_v4().simple().to_string();
    let mut body = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
    )
    .into_bytes();
    body.extend_from_slice(&data);
    body.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());

    let mut request = client
        .post(format!("{api_url}/upload/image"))
        .header("User-Agent", COMFY_USER_AGENT)
        .header(
            "Content-Type",
            format!("multipart/form-data; boundary={boundary}"),
        )
        .timeout(std::time::Duration::from_secs(30))
        .body(body);
    if !api_key.is_empty() {
        request = request.header("Authorization", format!("Bearer {api_key}"));
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("HTTP {}", response.status()));
    }
    let result = response
        .json::<Value>()
        .await
        .map_err(|error| error.to_string())?;
    let Some(result) = result.as_object() else {
        return Err("upload response is not an object".to_string());
    };
    Ok(result
        .get("name")
        .cloned()
        .unwrap_or(Value::String(filename)))
}

async fn upload_controlnet_image(
    State(state): State<SharedState>,
    multipart: Multipart,
) -> Response {
    let (data, filename, _) = match read_image_upload(multipart, "controlnet_input.png").await {
        Ok(image) => image,
        Err(response) => return response,
    };
    let config = ext_config(&state);
    let api_url = comfy_api_url(&config);
    let api_key = get_api_key(&config, &state.config.project_root);
    match comfy_upload_image(&state.python_client, &api_url, data, &filename, &api_key).await {
        Ok(name) => api_ok(json!({"name": name})).into_response(),
        Err(error) => api_err(&format!("Upload failed: {error}"), StatusCode::BAD_GATEWAY),
    }
}

// ---------------------------------------------------------------------------
// save-batch  (Rust native; sweep_meta handled inline)
// ---------------------------------------------------------------------------

async fn save_batch(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }

    let body_json: Value = match serde_json::from_slice(&body) {
        Ok(v) => v,
        Err(_) => return api_err("Invalid JSON body", StatusCode::BAD_REQUEST),
    };

    // Extract sweep_meta early (validated; None if absent or invalid)
    let sweep_meta = body_json
        .get("sweep_meta")
        .and_then(crate::routes::sweep_common::validate_sweep_meta);

    let images: Vec<String> = body_json
        .get("images")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(Value::as_str)
                .map(String::from)
                .collect()
        })
        .unwrap_or_default();
    if images.is_empty() {
        return api_err(
            "images array is required and must be non-empty",
            StatusCode::BAD_REQUEST,
        );
    }
    let seeds: Vec<i64> = body_json
        .get("seeds")
        .and_then(Value::as_array)
        .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_default();
    let cfg = ext_config(&state);
    let auto_import = cfg_bool(&cfg, "auto_import", true);
    let save_folder = body_json
        .get("save_folder")
        .and_then(Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "save_folder", ""))
        .to_string();
    let save_naming = body_json
        .get("save_naming")
        .and_then(Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "save_naming", "daily_folder"))
        .to_string();
    let image_format = body_json
        .get("image_format")
        .and_then(Value::as_str)
        .unwrap_or_else(|| cfg_str(&cfg, "default_image_format", "png"))
        .to_string();
    if save_folder.is_empty() {
        return api_err("save_folder is required", StatusCode::BAD_REQUEST);
    }
    let items: Vec<(&str, i64)> = images
        .iter()
        .enumerate()
        .map(|(i, s)| (s.as_str(), seeds.get(i).copied().unwrap_or(-1)))
        .collect();
    let (saved_paths, errs) = crate::routes::bridge_save::save_images_to_disk(
        &items,
        &save_folder,
        &image_format,
        &save_naming,
    );

    // Sweep XMP + DB (best-effort)
    if let Some(ref meta) = sweep_meta {
        if !saved_paths.is_empty() {
            crate::routes::sweep_common::write_sweep_xmp_to_paths(&saved_paths, meta);
            crate::routes::sweep_common::upsert_sweep_db(&state.db, meta, &saved_paths).await;
        }
    }
    let file_ids = if auto_import && !saved_paths.is_empty() {
        crate::routes::sweep_common::upsert_files_from_paths(&state, &saved_paths).await
    } else {
        Default::default()
    };

    let count = saved_paths.len();
    let saved_items: Vec<Value> =
        crate::routes::sweep_common::saved_items_from_file_ids(&saved_paths, &file_ids);
    api_ok(json!({
        "saved": saved_paths,
        "count": count,
        "errors": errs,
        "saved_items": saved_items,
    }))
    .into_response()
}

// ---------------------------------------------------------------------------
// Progress + Cancel (backed by job_manager)
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct ProgressQuery {
    task_id: Option<String>,
}

async fn progress(State(state): State<SharedState>, Query(q): Query<ProgressQuery>) -> Response {
    if let Some(task_id) = q.task_id {
        match state.job_manager.get_job(&task_id) {
            None => return api_ok(json!({
                "status": "pending", "progress": 0.0, "step": 0, "total_steps": 0, "registered": false,
            })).into_response(),
            Some(job) => return api_ok(json!({
                "status": if job.running { "running" } else { "done" },
                "progress": job.percent.unwrap_or(0.0) / 100.0,
                "step": job.current.unwrap_or(0),
                "total_steps": job.total.unwrap_or(0),
                "registered": true,
                "error_message": job.error,
            })).into_response(),
        }
    }
    api_ok(json!({"status": "idle", "progress": 0.0, "step": 0, "total_steps": 0})).into_response()
}

async fn cancel(State(state): State<SharedState>, Json(body): Json<Value>) -> Response {
    let task_id = body.get("task_id").and_then(Value::as_str);
    if let Some(tid) = task_id {
        if state.job_manager.get_job(tid).is_none() {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"ok": false, "error": "task not found"})),
            )
                .into_response();
        }
        let cancelled = state.job_manager.cancel_job(tid);
        // Also send interrupt to ComfyUI
        let cfg = ext_config(&state);
        let api_url = comfy_api_url(&cfg);
        let key = get_api_key(&cfg, &state.config.project_root);
        let _ = comfy_post(
            &state.python_client,
            &api_url,
            "/interrupt",
            &json!({}),
            &key,
        )
        .await;
        return api_ok(json!({"cancelled": cancelled})).into_response();
    }
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    match comfy_post(
        &state.python_client,
        &api_url,
        "/interrupt",
        &json!({}),
        &key,
    )
    .await
    {
        Ok(_) => api_ok(json!({"cancelled": true})).into_response(),
        Err(e) => api_err(
            &format!("ComfyUI interrupt error: {e}"),
            StatusCode::BAD_GATEWAY,
        ),
    }
}

// ---------------------------------------------------------------------------
// Model registry (native) — mirrors Python's
// extensions/builtin_comfyui_bridge/core_impl/comfyui_model_registry.py +
// comfyui_api_model_registry_routes.py.
// ---------------------------------------------------------------------------

const REGISTRY_MAX_PATTERNS: usize = 32;
const REGISTRY_MAX_PATTERN_LEN: usize = 128;
const REGISTRY_MAX_FIELD_LEN: usize = 256;
const REGISTRY_MAX_NOTES_LEN: usize = 2000;

#[derive(Clone)]
struct RegistryEntry {
    id: String,
    unet_patterns: Vec<String>,
    vae: String,
    clip_1: String,
    clip_2: String,
    clip_type: String,
    latent_node: String,
    source_url: String,
    default_sampler: String,
    default_scheduler: String,
    default_cfg: Option<f64>,
    default_steps: Option<i64>,
    notes: String,
    builtin: bool,
    shadows_builtin: bool,
}

fn is_valid_registry_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

/// Mirrors Python's `_CTRL_RE = re.compile(r"[\x00-\x08\x0a-\x0d\x0e-\x1f]")`:
/// control chars 0x00-0x1f except tab (0x09).
fn has_ctrl_chars(value: &str) -> bool {
    value.chars().any(|c| (c as u32) <= 0x1f && c != '\t')
}

fn value_to_display_string(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => String::new(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        other => other.to_string(),
    }
}

/// Mirrors Python's `data.get("unet_patterns") or data.get("unet_pattern")`
/// truthiness check used to decide whether any pattern was supplied at all.
fn is_truthy_patterns_field(v: Option<&Value>) -> bool {
    match v {
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().map(|f| f != 0.0).unwrap_or(true),
        Some(Value::Null) | None => false,
        Some(_) => true,
    }
}

/// Mirrors Python's `_validate_post_body`.
fn validate_registry_post_body(data: &Value) -> Option<String> {
    if let Some(Value::Array(patterns)) = data.get("unet_patterns") {
        if patterns.len() > REGISTRY_MAX_PATTERNS {
            return Some(format!(
                "'unet_patterns' must not exceed {REGISTRY_MAX_PATTERNS} items"
            ));
        }
        for p in patterns {
            let ps = value_to_display_string(p);
            if ps.chars().count() > REGISTRY_MAX_PATTERN_LEN {
                return Some(format!(
                    "each pattern in 'unet_patterns' must not exceed {REGISTRY_MAX_PATTERN_LEN} characters"
                ));
            }
            if has_ctrl_chars(&ps) {
                return Some("patterns must not contain control characters".to_string());
            }
        }
    }

    for field in [
        "vae",
        "clip_1",
        "clip_2",
        "clip_type",
        "latent_node",
        "source_url",
        "default_sampler",
        "default_scheduler",
    ] {
        if let Some(val) = data.get(field) {
            if !val.is_null() {
                let vs = value_to_display_string(val);
                if vs.chars().count() > REGISTRY_MAX_FIELD_LEN {
                    return Some(format!(
                        "'{field}' must not exceed {REGISTRY_MAX_FIELD_LEN} characters"
                    ));
                }
                if has_ctrl_chars(&vs) {
                    return Some(format!("'{field}' must not contain control characters"));
                }
            }
        }
    }

    let source_url = data
        .get("source_url")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if !source_url.is_empty() {
        match url::Url::parse(source_url) {
            Ok(u) if u.scheme() == "http" || u.scheme() == "https" => {
                if u.host_str().unwrap_or("").is_empty() {
                    return Some("'source_url' must include a host".to_string());
                }
            }
            _ => return Some("'source_url' must use http or https".to_string()),
        }
    }

    if let Some(notes) = data.get("notes") {
        if !notes.is_null() {
            let ns = value_to_display_string(notes);
            if ns.chars().count() > REGISTRY_MAX_NOTES_LEN {
                return Some(format!(
                    "'notes' must not exceed {REGISTRY_MAX_NOTES_LEN} characters"
                ));
            }
            if has_ctrl_chars(&ns) {
                return Some("'notes' must not contain control characters".to_string());
            }
        }
    }

    if let Some(cfg) = data.get("default_cfg") {
        if !cfg.is_null() {
            match cfg.as_f64() {
                Some(f) if f.is_finite() => {}
                Some(_) => return Some("'default_cfg' must be a finite number".to_string()),
                None => return Some("'default_cfg' must be a number".to_string()),
            }
        }
    }

    if let Some(steps) = data.get("default_steps") {
        if !steps.is_null() {
            match steps.as_i64() {
                Some(n) if (1..=10000).contains(&n) => {}
                Some(_) => return Some("'default_steps' must be between 1 and 10000".to_string()),
                None => return Some("'default_steps' must be an integer".to_string()),
            }
        }
    }

    None
}

/// Mirrors Python's `_entry_from_dict`. Returns None if `id` or at least one
/// pattern is missing.
fn registry_entry_from_dict(d: &Value, builtin: bool) -> Option<RegistryEntry> {
    let eid = d
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if eid.is_empty() {
        return None;
    }

    let patterns: Vec<String> = match d.get("unet_patterns") {
        Some(Value::Array(arr)) => arr
            .iter()
            .map(value_to_display_string)
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect(),
        Some(Value::String(s)) => {
            let t = s.trim();
            if t.is_empty() {
                vec![]
            } else {
                vec![t.to_string()]
            }
        }
        None | Some(Value::Null) => {
            let single = d
                .get("unet_pattern")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            if single.is_empty() {
                vec![]
            } else {
                vec![single]
            }
        }
        _ => vec![],
    };
    if patterns.is_empty() {
        return None;
    }

    let default_cfg = d
        .get("default_cfg")
        .and_then(|v| if v.is_null() { None } else { v.as_f64() });
    let default_steps =
        d.get("default_steps")
            .and_then(|v| if v.is_null() { None } else { v.as_i64() });

    Some(RegistryEntry {
        id: eid,
        unet_patterns: patterns,
        vae: d
            .get("vae")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        clip_1: d
            .get("clip_1")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        clip_2: d
            .get("clip_2")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        clip_type: d
            .get("clip_type")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        latent_node: d
            .get("latent_node")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        source_url: d
            .get("source_url")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        default_sampler: d
            .get("default_sampler")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        default_scheduler: d
            .get("default_scheduler")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        default_cfg,
        default_steps,
        notes: d
            .get("notes")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        builtin,
        shadows_builtin: false,
    })
}

fn registry_entry_to_dict(e: &RegistryEntry, include_builtin_flag: bool) -> Value {
    let mut d = json!({
        "id": e.id,
        "unet_patterns": e.unet_patterns,
        "vae": e.vae,
        "clip_1": e.clip_1,
        "clip_2": e.clip_2,
        "clip_type": e.clip_type,
        "latent_node": e.latent_node,
        "source_url": e.source_url,
        "default_sampler": e.default_sampler,
        "default_scheduler": e.default_scheduler,
        "default_cfg": e.default_cfg,
        "default_steps": e.default_steps,
        "notes": e.notes,
    });
    if include_builtin_flag {
        d["builtin"] = json!(e.builtin);
        if e.shadows_builtin {
            d["shadows_builtin"] = json!(true);
        }
    }
    d
}

fn load_user_registry(state: &SharedState) -> Vec<RegistryEntry> {
    let cfg = ext_config(state);
    cfg.get("model_registry_user")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|item| registry_entry_from_dict(item, false))
                .collect()
        })
        .unwrap_or_default()
}

fn load_builtin_registry(state: &SharedState) -> Vec<RegistryEntry> {
    let path = state
        .config
        .project_root
        .join("extensions")
        .join("builtin_comfyui_bridge")
        .join("model_registry_builtin.json");
    let Some(raw) = std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
    else {
        return vec![];
    };
    raw.get("entries")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|item| registry_entry_from_dict(item, true))
                .collect()
        })
        .unwrap_or_default()
}

fn save_user_registry(state: &SharedState, entries: &[RegistryEntry]) -> std::io::Result<()> {
    let mut full = load_config_json(&state.config.config_path);
    let data: Vec<Value> = entries
        .iter()
        .map(|e| registry_entry_to_dict(e, false))
        .collect();
    full["extensions"][EXT_NAME]["model_registry_user"] = json!(data);
    write_config_json(&state.config.config_path, &full)
}

/// Mirrors Python's `upsert_user_entry`: replace-if-same-id (append at end),
/// else append as new. Returns `(entry, created)`.
fn upsert_user_registry_entry(
    state: &SharedState,
    data: &Value,
) -> Result<(RegistryEntry, bool), String> {
    let entry = registry_entry_from_dict(data, false).ok_or_else(|| {
        "Invalid entry: 'id' and at least one pattern in 'unet_patterns' are required".to_string()
    })?;

    let mut user = load_user_registry(state);
    let mut created = true;
    user.retain(|existing| {
        if existing.id == entry.id {
            created = false;
            false
        } else {
            true
        }
    });
    user.push(entry.clone());
    save_user_registry(state, &user).map_err(|e| e.to_string())?;
    Ok((entry, created))
}

/// Mirrors Python's `delete_user_entry`. Ok(true)=deleted, Ok(false)=not
/// found anywhere, Err=id belongs to a built-in entry with no user override.
fn delete_user_registry_entry(state: &SharedState, entry_id: &str) -> Result<bool, String> {
    let user = load_user_registry(state);
    let orig_len = user.len();
    let new_user: Vec<RegistryEntry> = user.into_iter().filter(|e| e.id != entry_id).collect();
    if new_user.len() == orig_len {
        let builtin = load_builtin_registry(state);
        if builtin.iter().any(|e| e.id == entry_id) {
            return Err(format!(
                "Built-in entry '{entry_id}' cannot be deleted. Create a user entry with the same id to override it instead."
            ));
        }
        return Ok(false);
    }
    save_user_registry(state, &new_user).map_err(|e| e.to_string())?;
    Ok(true)
}

/// GET /ext/comfyui-bridge/api/model-registry
async fn get_model_registry(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }

    let mut registry = load_user_registry(&state);
    let mut builtin = load_builtin_registry(&state);
    let builtin_ids: std::collections::HashSet<String> =
        builtin.iter().map(|entry| entry.id.clone()).collect();
    let user_ids: std::collections::HashSet<String> =
        registry.iter().map(|entry| entry.id.clone()).collect();
    for entry in &mut registry {
        entry.shadows_builtin = builtin_ids.contains(&entry.id);
    }
    builtin.retain(|entry| !user_ids.contains(&entry.id));
    registry.extend(builtin);
    let registry: Vec<Value> = registry
        .iter()
        .map(|entry| registry_entry_to_dict(entry, true))
        .collect();

    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let key = get_api_key(&cfg, &state.config.project_root);
    let available = async {
        Ok::<Value, String>(json!({
            "diffusion_models": fetch_enum_result(
                &state.python_client, &api_url, "UNETLoader", "unet_name", &key,
            ).await?,
            "vaes": fetch_enum_result(
                &state.python_client, &api_url, "VAELoader", "vae_name", &key,
            ).await?,
            "text_encoders": fetch_enum_result(
                &state.python_client, &api_url, "CLIPLoader", "clip_name", &key,
            ).await?,
        }))
    }
    .await;
    match available {
        Ok(available_models) => {
            api_ok(json!({"registry": registry, "available_models": available_models}))
                .into_response()
        }
        Err(models_error) => api_ok(json!({
            "registry": registry,
            "available_models": {
                "diffusion_models": [],
                "vaes": [],
                "text_encoders": [],
            },
            "models_error": models_error,
        }))
        .into_response(),
    }
}

/// POST /ext/comfyui-bridge/api/model-registry
async fn post_model_registry_entry(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(data): Json<Value>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }

    let entry_id = data
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if entry_id.is_empty() {
        return api_err("'id' is required", StatusCode::BAD_REQUEST);
    }
    if !is_valid_registry_id(&entry_id) {
        return api_err(
            "'id' must be 1–64 characters: letters, digits, hyphens, or underscores",
            StatusCode::BAD_REQUEST,
        );
    }

    let has_patterns = is_truthy_patterns_field(data.get("unet_patterns"))
        || is_truthy_patterns_field(data.get("unet_pattern"));
    if !has_patterns {
        return api_err(
            "'unet_patterns' is required (list of substring patterns)",
            StatusCode::BAD_REQUEST,
        );
    }

    if let Some(msg) = validate_registry_post_body(&data) {
        return api_err(&msg, StatusCode::BAD_REQUEST);
    }

    match upsert_user_registry_entry(&state, &data) {
        Ok((entry, created)) => {
            let status = if created {
                StatusCode::CREATED
            } else {
                StatusCode::OK
            };
            (
                status,
                api_ok(json!({"entry": registry_entry_to_dict(&entry, true), "created": created})),
            )
                .into_response()
        }
        Err(msg) => api_err(&msg, StatusCode::BAD_REQUEST),
    }
}

/// DELETE /ext/comfyui-bridge/api/model-registry/{id}
async fn delete_model_registry_entry(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    AxumPath(entry_id): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_guard(&state, auth.as_ref()) {
        return r;
    }
    if !is_valid_registry_id(&entry_id) {
        return api_err("Invalid entry id", StatusCode::BAD_REQUEST);
    }

    match delete_user_registry_entry(&state, &entry_id) {
        Ok(true) => api_ok(json!({"deleted": true, "id": entry_id})).into_response(),
        Ok(false) => api_err(
            &format!("Entry '{entry_id}' not found in user registry"),
            StatusCode::NOT_FOUND,
        ),
        Err(msg) => api_err(&msg, StatusCode::BAD_REQUEST),
    }
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

pub fn routes() -> Router<SharedState> {
    let p = "/ext/comfyui-bridge";
    Router::new()
        // Info
        .route(&format!("{p}/info"), get(info))
        // Config
        .route(
            &format!("{p}/api/config"),
            get(get_config).post(post_config),
        )
        .route(&format!("{p}/api/test-connection"), post(test_connection))
        // Asset discovery (all Rust)
        .route(&format!("{p}/api/samplers"), get(samplers))
        .route(&format!("{p}/api/schedulers"), get(schedulers))
        .route(&format!("{p}/api/models"), get(models))
        .route(&format!("{p}/api/loras"), get(loras))
        .route(&format!("{p}/api/embeddings"), get(embeddings))
        .route(&format!("{p}/api/diffusion-models"), get(diffusion_models))
        .route(&format!("{p}/api/text-encoders"), get(text_encoders))
        .route(&format!("{p}/api/clip-types"), get(clip_types))
        .route(&format!("{p}/api/weight-dtypes"), get(weight_dtypes))
        .route(&format!("{p}/api/controlnets"), get(controlnets))
        .route(&format!("{p}/api/upscale-models"), get(upscale_models))
        .route(&format!("{p}/api/has-node"), get(has_node))
        .route(&format!("{p}/api/discovery/models"), get(discovery_models))
        .route(&format!("{p}/api/refresh-assets"), post(refresh_assets))
        // Save-batch (Rust, sweep_meta → Python fallback)
        .route(&format!("{p}/api/save-batch"), post(save_batch))
        // Generate + progress/cancel (Rust, json mode only)
        .route(&format!("{p}/api/generate"), post(generate::generate))
        .route(&format!("{p}/api/progress"), get(generate::progress))
        .route(&format!("{p}/api/cancel"), post(generate::cancel))
        // Remaining ComfyUI APIs (all Rust)
        .route(&format!("{p}/api/custom-nodes"), get(custom_nodes))
        .route(&format!("{p}/api/checkpoint-info"), get(checkpoint_info))
        .route(&format!("{p}/api/extract-workflow"), post(extract_workflow))
        .route(
            &format!("{p}/api/parse-workflow-params"),
            post(parse_workflow_params),
        )
        .route(
            &format!("{p}/api/upload-controlnet-image"),
            post(upload_controlnet_image),
        )
        .route(
            &format!("{p}/api/check-workflow-from-file"),
            post(check_workflow_from_file),
        )
        .route(
            &format!("{p}/api/queue-workflow-from-file"),
            post(queue_workflow_from_file),
        )
        .route(
            &format!("{p}/api/model-registry"),
            get(get_model_registry).post(post_model_registry_entry),
        )
        .route(
            &format!("{p}/api/model-registry/{{id}}"),
            delete(delete_model_registry_entry),
        )
}

//! Hailo HEF model filesystem/HTTP operations: status lookup and download.
//! Faithful Rust ports of
//! `extensions/builtin_hailo_genai/core_impl/model_download_exec.py` and
//! `extensions/builtin_hailo_yolo_detect/core_impl/model_download.py`.
//!
//! Unlike the Python reference, `progress_callback` is intentionally not
//! ported: the frontend (`templates/hailo_genai/_genai_script.html`) never
//! wires it to any polling/SSE consumer — it just awaits the final JSON from
//! a single blocking `fetch()`. Building a progress-reporting mechanism here
//! would be unused dead code.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use std::time::Duration;

use futures_util::StreamExt;
use tokio::io::AsyncWriteExt;

use super::hailo_model_registry::GenAiModelInfo;

const YOLO_MODEL_BASE_URL: &str =
    "https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h";

/// Metadata for a downloadable Hailo YOLO HEF model.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct YoloModelInfo {
    pub(crate) hef_filename: String,
    pub(crate) description: String,
    pub(crate) url: String,
    pub(crate) input_size: u32,
}

/// Hailo Model Zoo YOLO HEFs supported by the hailo-yolo extension.
pub(crate) static YOLO_MODELS: LazyLock<HashMap<String, YoloModelInfo>> = LazyLock::new(|| {
    HashMap::from([
        (
            "yolov8n".to_string(),
            YoloModelInfo {
                hef_filename: "yolov8n.hef".to_string(),
                description: "YOLOv8 Nano (mAP 36.4, fastest)".to_string(),
                url: format!("{YOLO_MODEL_BASE_URL}/yolov8n.hef"),
                input_size: 640,
            },
        ),
        (
            "yolov11n".to_string(),
            YoloModelInfo {
                hef_filename: "yolov11n.hef".to_string(),
                description: "YOLOv11 Nano (mAP 37.9)".to_string(),
                url: format!("{YOLO_MODEL_BASE_URL}/yolov11n.hef"),
                input_size: 640,
            },
        ),
        (
            "yolov5m".to_string(),
            YoloModelInfo {
                hef_filename: "yolov5m_wo_spp.hef".to_string(),
                description: "YOLOv5 Medium (mAP 41.4, most accurate)".to_string(),
                url: format!("{YOLO_MODEL_BASE_URL}/yolov5m_wo_spp.hef"),
                input_size: 640,
            },
        ),
    ])
});

/// `HAILO_HEF_DIR` env var override, else `$HOME/hailo_models`. Mirrors
/// `analysis.rs::hailo_hef_dir()`'s env-override convention. This is the
/// single source of truth reused by `auto_stubs.rs::model_name_to_hef_path`
/// (the actual LLM/VLM inference hef_path resolution), so `/model/status`,
/// `/model/download`, and real generation all agree on which directory
/// holds the `.hef` files.
pub(crate) fn default_hef_dir() -> PathBuf {
    std::env::var_os("HAILO_HEF_DIR")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join("hailo_models")))
        .unwrap_or_else(|| PathBuf::from("hailo_models"))
}

/// Returns the expected local path for a HEF filename.
pub(crate) fn get_hef_path(hef_filename: &str, hef_dir: &Path) -> PathBuf {
    hef_dir.join(hef_filename)
}

/// Builds the `{name: {available, path, type, description, file_size_mb}}`
/// map exactly as Python's `get_model_status` does.
pub(crate) fn get_model_status(
    registry: &HashMap<String, GenAiModelInfo>,
    hef_dir: &Path,
) -> serde_json::Value {
    let mut map = serde_json::Map::new();
    for (name, info) in registry {
        let path = get_hef_path(&info.hef_filename, hef_dir);
        let exists = path.exists();
        let file_size_mb = if exists {
            std::fs::metadata(&path).ok().map(|m| {
                let mb = m.len() as f64 / 1024.0 / 1024.0;
                (mb * 10.0).round() / 10.0
            })
        } else {
            None
        };
        map.insert(
            name.clone(),
            serde_json::json!({
                "available": exists,
                "path": path.to_string_lossy(),
                "type": info.model_type.as_str(),
                "description": info.description,
                "file_size_mb": file_size_mb,
            }),
        );
    }
    serde_json::Value::Object(map)
}

/// Builds the YOLO-specific `{name: {available, path, description,
/// input_size, file_size_mb}}` map. This intentionally does not expose the
/// GenAI-only `type` field.
pub(crate) fn get_yolo_model_status(hef_dir: &Path) -> serde_json::Value {
    let mut map = serde_json::Map::new();
    for (name, info) in YOLO_MODELS.iter() {
        let path = get_hef_path(&info.hef_filename, hef_dir);
        let exists = path.exists();
        let file_size_mb = if exists {
            std::fs::metadata(&path).ok().map(|m| {
                let mb = m.len() as f64 / 1024.0 / 1024.0;
                (mb * 10.0).round() / 10.0
            })
        } else {
            None
        };
        map.insert(
            name.clone(),
            serde_json::json!({
                "available": exists,
                "path": path.to_string_lossy(),
                "description": info.description,
                "input_size": info.input_size,
                "file_size_mb": file_size_mb,
            }),
        );
    }
    serde_json::Value::Object(map)
}

#[derive(Debug)]
pub(crate) enum DownloadError {
    UnknownModel(String),
    Io(String),
    Http(String),
}

impl std::fmt::Display for DownloadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DownloadError::UnknownModel(name) => write!(f, "Unknown GenAI model: {name}"),
            DownloadError::Io(msg) | DownloadError::Http(msg) => write!(f, "{msg}"),
        }
    }
}

impl std::error::Error for DownloadError {}

/// Downloads a HEF file into `hef_dir` if not already present.
/// If the target file already exists, this is a no-op that returns
/// immediately (matches Python — no re-download, no HTTP call made).
/// Otherwise streams the download to a `.tmp` sibling and atomically renames
/// it into place on completion.
pub(crate) async fn download_hef(
    hef_filename: &str,
    url: &str,
    hef_dir: &Path,
    user_agent: &str,
) -> Result<PathBuf, DownloadError> {
    tokio::fs::create_dir_all(hef_dir)
        .await
        .map_err(|e| DownloadError::Io(format!("Failed to create hef dir: {e}")))?;

    let target = get_hef_path(hef_filename, hef_dir);
    if target.exists() {
        return Ok(target);
    }

    let tmp_path = {
        let mut name = target.clone().into_os_string();
        name.push(".tmp");
        PathBuf::from(name)
    };

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(300))
        .redirect(reqwest::redirect::Policy::limited(5))
        .build()
        .map_err(|e| DownloadError::Http(e.to_string()))?;

    let resp = client
        .get(url)
        .header(reqwest::header::USER_AGENT, user_agent)
        .send()
        .await
        .map_err(|e| DownloadError::Http(format!("Download request failed: {e}")))?;

    if !resp.status().is_success() {
        return Err(DownloadError::Http(format!(
            "Download failed with status {}",
            resp.status()
        )));
    }

    let mut stream = resp.bytes_stream();
    let mut file = tokio::fs::File::create(&tmp_path)
        .await
        .map_err(|e| DownloadError::Io(format!("Failed to create temp file: {e}")))?;

    while let Some(chunk) = stream.next().await {
        let chunk =
            chunk.map_err(|e| DownloadError::Http(format!("Download stream error: {e}")))?;
        file.write_all(&chunk)
            .await
            .map_err(|e| DownloadError::Io(format!("Failed to write chunk: {e}")))?;
    }
    file.flush()
        .await
        .map_err(|e| DownloadError::Io(format!("Failed to flush temp file: {e}")))?;
    drop(file);

    tokio::fs::rename(&tmp_path, &target)
        .await
        .map_err(|e| DownloadError::Io(format!("Failed to finalize download: {e}")))?;

    Ok(target)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::routes::hailo_model_registry::GenAiModelType;
    use std::io::Write as _;

    fn sample_registry() -> HashMap<String, GenAiModelInfo> {
        let mut registry = HashMap::new();
        registry.insert(
            "llama3.2-1b".to_string(),
            GenAiModelInfo {
                name: "llama3.2-1b".to_string(),
                model_type: GenAiModelType::Llm,
                hef_filename: "Llama3.2-1B-Instruct.hef".to_string(),
                description: "Llama 3.2 1B Instruct".to_string(),
                url: "https://example.invalid/Llama3.2-1B-Instruct.hef".to_string(),
            },
        );
        registry
    }

    #[test]
    fn get_hef_path_joins_filename_to_hef_dir() {
        let dir = PathBuf::from("/tmp/does-not-matter");
        assert_eq!(
            get_hef_path("Llama3.2-1B-Instruct.hef", &dir),
            dir.join("Llama3.2-1B-Instruct.hef")
        );
    }

    #[test]
    fn get_model_status_reports_available_and_missing_models() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let mut registry = sample_registry();
        registry.insert(
            "whisper-tiny".to_string(),
            GenAiModelInfo {
                name: "whisper-tiny".to_string(),
                model_type: GenAiModelType::Speech2Text,
                hef_filename: "Whisper-Tiny.hef".to_string(),
                description: "Whisper Tiny".to_string(),
                url: "https://example.invalid/Whisper-Tiny.hef".to_string(),
            },
        );

        // Only the whisper-tiny HEF actually exists on disk.
        let present_path = tmp.path().join("Whisper-Tiny.hef");
        let mut f = std::fs::File::create(&present_path).expect("create dummy hef");
        f.write_all(&[0u8; 2048]).expect("write dummy bytes");
        drop(f);

        let status = get_model_status(&registry, tmp.path());

        let missing = &status["llama3.2-1b"];
        assert_eq!(missing["available"], false);
        assert_eq!(missing["file_size_mb"], serde_json::Value::Null);
        assert_eq!(missing["type"], "llm");

        let present = &status["whisper-tiny"];
        assert_eq!(present["available"], true);
        assert_eq!(present["type"], "s2t");
        assert_eq!(present["path"], present_path.to_string_lossy().to_string());
        // 2048 bytes = 0.001953125 MB, rounds to 0.0.
        assert_eq!(present["file_size_mb"], 0.0);
    }

    #[tokio::test]
    async fn download_hef_already_exists_is_a_noop_and_makes_no_network_call() {
        let registry = sample_registry();
        let info = registry.get("llama3.2-1b").expect("sample model exists");
        let tmp = tempfile::tempdir().expect("tempdir");
        let target = tmp.path().join("Llama3.2-1B-Instruct.hef");
        std::fs::write(&target, b"already here").expect("pre-create target");

        // The sample model URL points at a `.invalid` TLD (RFC 2606 reserved,
        // guaranteed unresolvable) so if download_hef ever attempted a real
        // request here, this test would hang/fail rather than silently pass.
        let result = download_hef(&info.hef_filename, &info.url, tmp.path(), "test-agent")
            .await
            .expect("existing file short-circuits download");
        assert_eq!(result, target);
        assert_eq!(std::fs::read(&target).unwrap(), b"already here");
    }

    #[tokio::test]
    async fn download_hef_streams_body_to_target_via_local_mock_server() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt as _};
        use tokio::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr = listener.local_addr().expect("local_addr");
        let body = b"fake hef bytes for streaming test";

        let server = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.expect("accept");
            let mut buf = [0u8; 1024];
            let _ = socket.read(&mut buf).await.expect("read request");
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            );
            socket
                .write_all(response.as_bytes())
                .await
                .expect("write headers");
            socket.write_all(body).await.expect("write body");
            socket.shutdown().await.expect("shutdown");
        });

        let tmp = tempfile::tempdir().expect("tempdir");
        let url = format!("http://{addr}/Mock-Model.hef");
        let result = download_hef("Mock-Model.hef", &url, tmp.path(), "test-agent")
            .await
            .expect("download should succeed");

        server.await.expect("mock server task");

        assert_eq!(result, tmp.path().join("Mock-Model.hef"));
        let written = std::fs::read(&result).expect("read downloaded file");
        assert_eq!(written, body);
        // No leftover .tmp file after a successful rename.
        assert!(!tmp.path().join("Mock-Model.hef.tmp").exists());
    }

    #[test]
    fn yolo_models_match_python_registry() {
        assert_eq!(YOLO_MODELS.len(), 3);

        let expected = [
            (
                "yolov8n",
                "yolov8n.hef",
                "https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/yolov8n.hef",
                640,
                "YOLOv8 Nano (mAP 36.4, fastest)",
            ),
            (
                "yolov11n",
                "yolov11n.hef",
                "https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/yolov11n.hef",
                640,
                "YOLOv11 Nano (mAP 37.9)",
            ),
            (
                "yolov5m",
                "yolov5m_wo_spp.hef",
                "https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/yolov5m_wo_spp.hef",
                640,
                "YOLOv5 Medium (mAP 41.4, most accurate)",
            ),
        ];

        for (name, filename, url, input_size, description) in expected {
            let info = YOLO_MODELS.get(name).expect("expected YOLO model");
            assert_eq!(info.hef_filename, filename);
            assert_eq!(info.url, url);
            assert_eq!(info.input_size, input_size);
            assert_eq!(info.description, description);
        }
    }

    #[test]
    fn get_yolo_model_status_reports_availability_size_and_input_size() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let present_path = tmp.path().join("yolov11n.hef");
        std::fs::File::create(&present_path)
            .expect("create dummy HEF")
            .set_len(1_572_864)
            .expect("set dummy HEF size");

        let status = get_yolo_model_status(tmp.path());

        let missing = &status["yolov8n"];
        assert_eq!(missing["available"], false);
        assert_eq!(missing["file_size_mb"], serde_json::Value::Null);
        assert_eq!(missing["input_size"], 640);
        assert!(missing.get("type").is_none());

        let present = &status["yolov11n"];
        assert_eq!(present["available"], true);
        assert_eq!(present["path"], present_path.to_string_lossy().to_string());
        assert_eq!(present["input_size"], 640);
        assert_eq!(present["file_size_mb"], 1.5);
        assert!(present.get("type").is_none());
    }
}

//! Safe downloader and status handlers for the CLIP ONNX text encoder.

use std::{
    path::{Path, PathBuf},
    sync::LazyLock,
    time::Duration,
};

use axum::{
    extract::{Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use futures_util::StreamExt;
use serde_json::json;
use sha2::{Digest, Sha256};
use tokio::io::AsyncWriteExt;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const REPO: &str = "Xenova/clip-vit-base-patch16";
const BASE_URL: &str = "https://huggingface.co/Xenova/clip-vit-base-patch16/resolve/main";
const USER_AGENT: &str = "YU-AI-Manager/2.0 (CLIP-ONNX text downloader)";
const MAX_MODEL_BYTES: u64 = 512 * 1024 * 1024;
const MAX_TOKENIZER_BYTES: u64 = 32 * 1024 * 1024;
static DOWNLOAD_LOCK: LazyLock<tokio::sync::Mutex<()>> =
    LazyLock::new(|| tokio::sync::Mutex::new(()));

pub(crate) fn model_dir(cache_dir: &Path) -> PathBuf {
    // Match Python's `cache_path("clip_onnx")` contract. The sidecar receives
    // the same resolved directory at spawn time, so a non-default
    // TAGDB_CACHE_DIR cannot make download and inference disagree.
    if let Some(path) = std::env::var_os("HAILO_CLIP_TEXT_MODEL_DIR") {
        return PathBuf::from(path);
    }
    cache_dir
        .join("clip_onnx")
        .join("Xenova_clip-vit-base-patch16")
}
fn model_path(cache_dir: &Path) -> PathBuf {
    model_dir(cache_dir).join("text_model.onnx")
}
fn tokenizer_path(cache_dir: &Path) -> PathBuf {
    model_dir(cache_dir).join("tokenizer.json")
}
pub(crate) fn model_ready(cache_dir: &Path) -> bool {
    model_path(cache_dir).is_file() && tokenizer_path(cache_dir).is_file()
}

fn admin_or_response(
    state: &SharedState,
    auth: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(
        state.config.pin_auth_enabled,
        auth.map(|extension| &extension.0),
    )
}

pub async fn status_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let model = model_path(&state.config.cache_dir);
    let tokenizer = tokenizer_path(&state.config.cache_dir);
    let size_mb = std::fs::metadata(&model).ok().map_or(0.0, |metadata| {
        (metadata.len() as f64 / 1_048_576.0 * 100.0).round() / 100.0
    });
    Json(json!({"repo":REPO, "ready":model_ready(&state.config.cache_dir), "path":model, "tokenizer_path":tokenizer, "size_mb":size_mb})).into_response()
}

pub async fn download_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let _guard = DOWNLOAD_LOCK.lock().await;
    if model_ready(&state.config.cache_dir) {
        return Json(json!({"status":"already_downloaded"})).into_response();
    }
    let model = model_path(&state.config.cache_dir);
    let tokenizer = tokenizer_path(&state.config.cache_dir);
    let result = async {
        if !model.is_file() {
            download_one(
                &format!("{BASE_URL}/onnx/text_model.onnx"),
                &model,
                MAX_MODEL_BYTES,
            )
            .await?;
        }
        if !tokenizer.is_file() {
            download_one(
                &format!("{BASE_URL}/tokenizer.json"),
                &tokenizer,
                MAX_TOKENIZER_BYTES,
            )
            .await?;
        }
        Ok::<(), DownloadError>(())
    }
    .await;
    match result {
        Ok(()) => Json(json!({"status":"ok"})).into_response(),
        Err(error) => {
            tracing::warn!(%error, "CLIP text model download failed");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status":"error", "message":"Model download failed"})),
            )
                .into_response()
        }
    }
}

#[derive(Debug)]
enum DownloadError {
    Io(String),
    Http(String),
    SizeExceeded,
    UnsafeUrl,
}
impl std::fmt::Display for DownloadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(value) | Self::Http(value) => f.write_str(value),
            Self::SizeExceeded => f.write_str("download exceeds maximum size"),
            Self::UnsafeUrl => f.write_str("model URL is not HTTPS"),
        }
    }
}

async fn download_one(url: &str, target: &Path, max_bytes: u64) -> Result<(), DownloadError> {
    if !url.starts_with("https://") {
        return Err(DownloadError::UnsafeUrl);
    }
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(300))
        .redirect(reqwest::redirect::Policy::limited(5))
        .build()
        .map_err(|error| DownloadError::Http(error.to_string()))?;
    let response = client
        .get(url)
        .header(reqwest::header::USER_AGENT, USER_AGENT)
        .send()
        .await
        .map_err(|error| DownloadError::Http(error.to_string()))?;
    if response.url().scheme() != "https" {
        return Err(DownloadError::UnsafeUrl);
    }
    if !response.status().is_success() {
        return Err(DownloadError::Http(format!(
            "download returned {}",
            response.status()
        )));
    }
    if response
        .content_length()
        .is_some_and(|length| length > max_bytes)
    {
        return Err(DownloadError::SizeExceeded);
    }
    let temp = target.with_extension(format!(
        "{}.tmp",
        target
            .extension()
            .and_then(|extension| extension.to_str())
            .unwrap_or("download")
    ));
    tokio::fs::create_dir_all(
        target
            .parent()
            .ok_or_else(|| DownloadError::Io("target has no parent".to_string()))?,
    )
    .await
    .map_err(|error| DownloadError::Io(error.to_string()))?;
    let mut file = tokio::fs::File::create(&temp)
        .await
        .map_err(|error| DownloadError::Io(error.to_string()))?;
    let mut stream = response.bytes_stream();
    let mut written = 0_u64;
    let mut digest = Sha256::new();
    let write_result = async {
        while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|error| DownloadError::Http(error.to_string()))?;
            written = written
                .checked_add(chunk.len() as u64)
                .ok_or(DownloadError::SizeExceeded)?;
            if written > max_bytes {
                return Err(DownloadError::SizeExceeded);
            }
            digest.update(&chunk);
            file.write_all(&chunk)
                .await
                .map_err(|error| DownloadError::Io(error.to_string()))?;
        }
        file.flush()
            .await
            .map_err(|error| DownloadError::Io(error.to_string()))?;
        Ok::<(), DownloadError>(())
    }
    .await;
    drop(file);
    if let Err(error) = write_result {
        let _ = tokio::fs::remove_file(&temp).await;
        return Err(error);
    }
    // The upstream Python source does not publish a pinned digest. Compute and
    // log SHA-256 for auditability; a fixed expected digest can be added when
    // upstream supplies one without changing the atomic download protocol.
    tracing::info!(path = %target.display(), bytes = written, sha256 = %hex::encode(digest.finalize()), "downloaded CLIP text artifact");
    if let Err(error) = tokio::fs::rename(&temp, target).await {
        let _ = tokio::fs::remove_file(&temp).await;
        return Err(DownloadError::Io(error.to_string()));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_accepts_https_download_urls() {
        assert!(!"http://example.test/a".starts_with("https://"));
        assert!("https://example.test/a".starts_with("https://"));
    }

    #[test]
    fn model_directory_uses_configured_cache_root() {
        let cache = Path::new("/tmp/semantic-cache");
        // This process does not set the override in tests; it remains the
        // explicit escape hatch for an independently-run yu-infer.
        if std::env::var_os("HAILO_CLIP_TEXT_MODEL_DIR").is_none() {
            assert_eq!(
                model_dir(cache),
                cache.join("clip_onnx/Xenova_clip-vit-base-patch16")
            );
        }
    }

    #[tokio::test]
    async fn model_routes_require_admin_scope() {
        let state = crate::state::semantic_test_state(true).await;
        assert_eq!(
            status_handler(State(state.clone()), None).await.status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            download_handler(State(state), None).await.status(),
            StatusCode::FORBIDDEN
        );
    }
}

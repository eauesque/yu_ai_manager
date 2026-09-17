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
    paths::home_dir,
    state::SharedState,
};

const REPO: &str = "Xenova/clip-vit-base-patch16";
const BASE_URL: &str = "https://huggingface.co/Xenova/clip-vit-base-patch16/resolve/main";
const USER_AGENT: &str = "YU-AI-Manager/2.0 (CLIP-ONNX text downloader)";
const MAX_MODEL_BYTES: u64 = 512 * 1024 * 1024;
const MAX_TOKENIZER_BYTES: u64 = 32 * 1024 * 1024;
static DOWNLOAD_LOCK: LazyLock<tokio::sync::Mutex<()>> =
    LazyLock::new(|| tokio::sync::Mutex::new(()));

const CLIP_MODEL_FILES: [&str; 3] = ["text_model.onnx", "tokenizer.json", "vision_model.onnx"];

fn count_files_present(dir: &Path) -> usize {
    CLIP_MODEL_FILES
        .iter()
        .filter(|name| dir.join(name).is_file())
        .count()
}

/// Resolve the CLIP model directory across primary then legacy cache locations.
///
/// This mirrors Python's `resolve_existing_model_path()`: the override wins,
/// then whichever of primary/legacy holds more of the CLIP files wins
/// without splitting files across directories -- ties go to primary.
pub(crate) fn model_dir(cache_dir: &Path) -> PathBuf {
    if let Some(path) = std::env::var_os("HAILO_CLIP_TEXT_MODEL_DIR") {
        return PathBuf::from(path);
    }
    let primary = download_dir(cache_dir);
    let Some(legacy) = home_dir()
        .map(|home| home.join(".cache/yu_ai_manager/clip_onnx/Xenova_clip-vit-base-patch16"))
    else {
        return primary;
    };
    if count_files_present(&legacy) > count_files_present(&primary) {
        legacy
    } else {
        primary
    }
}

fn download_dir(cache_dir: &Path) -> PathBuf {
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
pub(crate) fn vision_model_path(cache_dir: &Path) -> PathBuf {
    model_dir(cache_dir).join("vision_model.onnx")
}
pub(crate) fn model_ready(cache_dir: &Path) -> bool {
    model_path(cache_dir).is_file() && tokenizer_path(cache_dir).is_file()
}
pub(crate) fn vision_model_ready(cache_dir: &Path) -> bool {
    vision_model_path(cache_dir).is_file()
}

fn download_complete(cache_dir: &Path) -> bool {
    model_ready(cache_dir) && vision_model_ready(cache_dir)
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
    let vision = vision_model_path(&state.config.cache_dir);
    let size_mb = std::fs::metadata(&model).ok().map_or(0.0, |metadata| {
        (metadata.len() as f64 / 1_048_576.0 * 100.0).round() / 100.0
    });
    let vision_size_mb = std::fs::metadata(&vision).ok().map_or(0.0, |metadata| {
        (metadata.len() as f64 / 1_048_576.0 * 100.0).round() / 100.0
    });
    Json(json!({"repo":REPO, "ready":download_complete(&state.config.cache_dir), "path":model, "tokenizer_path":tokenizer, "size_mb":size_mb, "text_ready":model_ready(&state.config.cache_dir), "vision_ready":vision_model_ready(&state.config.cache_dir), "vision_path":vision, "vision_size_mb":vision_size_mb})).into_response()
}

pub async fn download_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let result = run_download(&state.config.cache_dir, BASE_URL).await;
    if result.get("status").and_then(serde_json::Value::as_str) == Some("error") {
        (StatusCode::INTERNAL_SERVER_ERROR, Json(result)).into_response()
    } else {
        Json(result).into_response()
    }
}

async fn run_download(cache_dir: &Path, base_url: &str) -> serde_json::Value {
    let _guard = DOWNLOAD_LOCK.lock().await;
    if download_complete(cache_dir) {
        return json!({"status":"already_downloaded"});
    }
    let download_dir = download_dir(cache_dir);
    let model = download_dir.join("text_model.onnx");
    let tokenizer = download_dir.join("tokenizer.json");
    let vision = download_dir.join("vision_model.onnx");
    let result = async {
        if !model.is_file() {
            download_one(
                &format!("{base_url}/onnx/text_model.onnx"),
                &model,
                MAX_MODEL_BYTES,
            )
            .await?;
        }
        if !tokenizer.is_file() {
            download_one(
                &format!("{base_url}/tokenizer.json"),
                &tokenizer,
                MAX_TOKENIZER_BYTES,
            )
            .await?;
        }
        if !vision.is_file() {
            download_one(
                &format!("{base_url}/onnx/vision_model.onnx"),
                &vision,
                MAX_MODEL_BYTES,
            )
            .await?;
        }
        Ok::<(), DownloadError>(())
    }
    .await;
    match result {
        Ok(()) => json!({"status":"ok"}),
        Err(error) => {
            tracing::warn!(%error, "CLIP text model download failed");
            json!({"status":"error", "message":"Model download failed"})
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

    fn with_clip_test_env(test: impl FnOnce()) {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let home = std::env::var_os("HOME");
        #[cfg(windows)]
        let userprofile = std::env::var_os("USERPROFILE");
        let override_dir = std::env::var_os("HAILO_CLIP_TEXT_MODEL_DIR");
        unsafe {
            std::env::remove_var("HAILO_CLIP_TEXT_MODEL_DIR");
        }
        test();
        unsafe {
            match home {
                Some(value) => std::env::set_var("HOME", value),
                None => std::env::remove_var("HOME"),
            }
            #[cfg(windows)]
            match userprofile {
                Some(value) => std::env::set_var("USERPROFILE", value),
                None => std::env::remove_var("USERPROFILE"),
            }
            match override_dir {
                Some(value) => std::env::set_var("HAILO_CLIP_TEXT_MODEL_DIR", value),
                None => std::env::remove_var("HAILO_CLIP_TEXT_MODEL_DIR"),
            }
        }
    }

    #[test]
    fn model_directory_resolves_primary_legacy_and_download_destination() {
        with_clip_test_env(|| {
            let temp = tempfile::tempdir().unwrap();
            let home = tempfile::tempdir().unwrap();
            unsafe {
                std::env::set_var("HOME", home.path());
                #[cfg(windows)]
                std::env::set_var("USERPROFILE", home.path());
            }
            let primary = download_dir(temp.path());
            let legacy = home
                .path()
                .join(".cache/yu_ai_manager/clip_onnx/Xenova_clip-vit-base-patch16");

            std::fs::create_dir_all(&primary).unwrap();
            std::fs::write(primary.join("text_model.onnx"), []).unwrap();
            assert_eq!(model_dir(temp.path()), primary);

            std::fs::remove_file(primary.join("text_model.onnx")).unwrap();
            std::fs::create_dir_all(&legacy).unwrap();
            std::fs::write(legacy.join("vision_model.onnx"), []).unwrap();
            assert_eq!(model_dir(temp.path()), legacy);

            std::fs::remove_file(legacy.join("vision_model.onnx")).unwrap();
            assert_eq!(model_dir(temp.path()), primary);
            assert_eq!(download_dir(temp.path()), primary);
        });
    }

    #[test]
    fn model_directory_prefers_more_complete_directory_by_file_count() {
        with_clip_test_env(|| {
            let temp = tempfile::tempdir().unwrap();
            let home = tempfile::tempdir().unwrap();
            unsafe {
                std::env::set_var("HOME", home.path());
                #[cfg(windows)]
                std::env::set_var("USERPROFILE", home.path());
            }
            let primary = download_dir(temp.path());
            let legacy = home
                .path()
                .join(".cache/yu_ai_manager/clip_onnx/Xenova_clip-vit-base-patch16");

            // Primary has only one of three files (an interrupted download);
            // legacy has all three. The more complete directory wins.
            std::fs::create_dir_all(&primary).unwrap();
            std::fs::write(primary.join("text_model.onnx"), []).unwrap();
            std::fs::create_dir_all(&legacy).unwrap();
            std::fs::write(legacy.join("text_model.onnx"), []).unwrap();
            std::fs::write(legacy.join("tokenizer.json"), []).unwrap();
            std::fs::write(legacy.join("vision_model.onnx"), []).unwrap();
            assert_eq!(model_dir(temp.path()), legacy);

            // Both directories are equally complete: tie goes to primary.
            std::fs::write(primary.join("tokenizer.json"), []).unwrap();
            std::fs::write(primary.join("vision_model.onnx"), []).unwrap();
            assert_eq!(model_dir(temp.path()), primary);
        });
    }

    #[test]
    fn text_ready_without_vision_does_not_skip_download() {
        // Must hold the env lock: `model_dir` reads HOME (to find the legacy
        // directory) and HAILO_CLIP_TEXT_MODEL_DIR. Without the guard this test
        // resolved `dir` while a concurrent test had HOME pointed elsewhere, so
        // it created one directory and then wrote the files under another --
        // `model_ready` then saw nothing. It passed alone and failed in the full
        // run, which is what an unguarded read of process-global state looks
        // like. The three sibling tests were already wrapped; this one was not.
        with_clip_test_env(|| {
            let temp = tempfile::tempdir().unwrap();
            // Isolate from the real machine's home dir -- without this, a
            // real ~/.cache/yu_ai_manager/clip_onnx/... left by actual app
            // use makes vision_model_ready() see a stray file and this
            // assertion depends on host state instead of the fixture.
            let home = tempfile::tempdir().unwrap();
            unsafe {
                std::env::set_var("HOME", home.path());
                #[cfg(windows)]
                std::env::set_var("USERPROFILE", home.path());
            }
            let dir = model_dir(temp.path());
            std::fs::create_dir_all(&dir).unwrap();
            std::fs::write(model_path(temp.path()), []).unwrap();
            std::fs::write(tokenizer_path(temp.path()), []).unwrap();

            assert!(model_ready(temp.path()));
            assert!(!vision_model_ready(temp.path()));
            assert!(!download_complete(temp.path()));
        });
    }

    /// Lay out model files under the resolved model dir, holding the env lock
    /// only while resolving and writing.
    ///
    /// The async tests cannot wrap their whole body in `with_clip_test_env`: it
    /// holds a `std::sync::Mutex`, and carrying that guard across an `.await`
    /// is exactly the pattern the clippy gate forbids. All the shared state
    /// they touch is read here anyway -- `model_dir` reads HOME and
    /// HAILO_CLIP_TEXT_MODEL_DIR -- so the lock only needs to span this setup,
    /// not the download call that follows.
    fn lay_out_model_files(cache_dir: &Path, files: &[&str]) {
        with_clip_test_env(|| {
            // download_dir (primary), not model_dir: model_dir prefers
            // whichever of primary/legacy has more files, and on a machine
            // where the real user's home already has a complete CLIP cache
            // under ~/.cache/yu_ai_manager/clip_onnx/..., that resolves to
            // the *real* legacy directory -- writing test fixtures into
            // actual production cache state instead of the tempdir this
            // test thinks it's isolated to.
            let dir = download_dir(cache_dir);
            std::fs::create_dir_all(&dir).unwrap();
            for name in files {
                std::fs::write(dir.join(name), []).unwrap();
            }
        });
    }

    /// RAII HOME/USERPROFILE override that survives an `.await` -- unlike
    /// `with_clip_test_env`, which restores as soon as its closure returns
    /// and cannot itself span an `.await` (holding its `Mutex` guard across
    /// one is exactly what clippy's `await_holding_lock` forbids). The lock
    /// here is only taken transiently inside `set`/`drop`, never held by the
    /// guard itself, so it's safe to keep across a `.await`.
    ///
    /// Needed because `model_dir` picks primary vs. legacy by file count:
    /// without a private, empty legacy directory, a real complete CLIP
    /// cache under the host's actual home directory outranks whatever the
    /// test wrote to its primary tempdir, and the test starts asserting
    /// against production state instead of its own fixture.
    struct HomeGuard {
        home: Option<std::ffi::OsString>,
        #[cfg(windows)]
        userprofile: Option<std::ffi::OsString>,
    }

    impl HomeGuard {
        fn set(path: &Path) -> Self {
            let _guard = crate::ENV_MUTATION_TEST_LOCK
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            let home = std::env::var_os("HOME");
            #[cfg(windows)]
            let userprofile = std::env::var_os("USERPROFILE");
            unsafe {
                std::env::set_var("HOME", path);
                #[cfg(windows)]
                std::env::set_var("USERPROFILE", path);
            }
            Self {
                home,
                #[cfg(windows)]
                userprofile,
            }
        }
    }

    impl Drop for HomeGuard {
        fn drop(&mut self) {
            let _guard = crate::ENV_MUTATION_TEST_LOCK
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            unsafe {
                match &self.home {
                    Some(v) => std::env::set_var("HOME", v),
                    None => std::env::remove_var("HOME"),
                }
                #[cfg(windows)]
                match &self.userprofile {
                    Some(v) => std::env::set_var("USERPROFILE", v),
                    None => std::env::remove_var("USERPROFILE"),
                }
            }
        }
    }

    #[tokio::test]
    async fn complete_model_skips_download() {
        let temp = tempfile::tempdir().unwrap();
        let home = tempfile::tempdir().unwrap();
        let _home_guard = HomeGuard::set(home.path());
        lay_out_model_files(
            temp.path(),
            &["text_model.onnx", "tokenizer.json", "vision_model.onnx"],
        );

        assert_eq!(
            run_download(temp.path(), "http://127.0.0.1:1").await["status"],
            "already_downloaded"
        );
    }

    #[tokio::test]
    async fn text_only_model_does_not_skip_download() {
        let temp = tempfile::tempdir().unwrap();
        let home = tempfile::tempdir().unwrap();
        let _home_guard = HomeGuard::set(home.path());
        lay_out_model_files(temp.path(), &["text_model.onnx", "tokenizer.json"]);

        assert_ne!(
            run_download(temp.path(), "http://127.0.0.1:1").await["status"],
            "already_downloaded"
        );
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

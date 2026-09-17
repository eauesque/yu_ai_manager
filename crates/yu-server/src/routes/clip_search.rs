//! Native read-side handlers for the Hailo semantic-search extension.

use std::{
    collections::HashSet,
    path::Path,
    sync::LazyLock,
    time::{Duration, Instant},
};

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    infer_client::{InferClient, InferClientError},
    state::SharedState,
};

use super::vector_store::{self, DEFAULT_MODEL};

const MAX_QUERY_CHARS: usize = 500;
const DEFAULT_LIMIT: usize = 50;
const MAX_LIMIT: usize = 200;
const DEFAULT_THRESHOLD: f32 = 0.2;
const IMAGE_EXTENSIONS: &[&str] = &[
    "png", "jpg", "jpeg", "webp", "gif", "avif", "bmp", "tiff", "tif", "heif", "heic", "jxl", "svg",
];
const VIDEO_EXTENSIONS: &[&str] = &["webm", "mp4", "avi", "mov", "mkv", "m4v", "ogv"];

#[derive(Debug, Deserialize)]
pub struct SearchQuery {
    pub q: Option<String>,
    pub limit: Option<String>,
    pub threshold: Option<String>,
    #[serde(rename = "format")]
    pub format: Option<String>,
    pub format_exts: Option<String>,
    pub from: Option<String>,
    pub to: Option<String>,
    pub model_filter: Option<String>,
    pub min_width: Option<String>,
    pub max_width: Option<String>,
    pub min_height: Option<String>,
    pub max_height: Option<String>,
    pub in_path: Option<String>,
    pub fav_only: Option<String>,
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

/// Text inference is sidecar-only in v1. This intentionally does not fall
/// back to a local ONNX encoder: standalone means no Python process, not no
/// `yu-infer` process.
pub(crate) async fn call_clip_text(
    state: &SharedState,
    text: String,
) -> Result<Vec<f32>, ClipCallError> {
    let client = state
        .infer_client
        .as_ref()
        .ok_or(ClipCallError::Unavailable)?;
    let value = client
        .infer_clip_text(text)
        .await
        .map_err(ClipCallError::Infer)?;
    parse_vector(value)
}

/// Canonicalizes and fail-closed validates a file against configured scan
/// roots before sending its bytes to the Hailo image sidecar.
pub(crate) async fn call_clip_image(
    state: &SharedState,
    path: &Path,
    preferred: ImageBackend,
) -> Result<Vec<f32>, ClipCallError> {
    let client = state
        .infer_client
        .as_ref()
        .ok_or(ClipCallError::Unavailable)?;
    let (hailo_available, onnx_available) = match preferred {
        ImageBackend::Auto => {
            let hailo_available = probe_hailo_image_backend(state).await;
            let onnx_available = !hailo_available && probe_onnx_image_backend(state).await;
            (hailo_available, onnx_available)
        }
        ImageBackend::Hailo => (probe_hailo_image_backend(state).await, false),
        ImageBackend::Onnx => (false, probe_onnx_image_backend(state).await),
    };
    let image_base64 = read_image_as_base64(state, path).await?;
    let value = match select_image_backend(preferred, hailo_available, onnx_available) {
        Some(ImageBackend::Hailo) => client.infer_clip_image(image_base64).await,
        Some(ImageBackend::Onnx) => client.infer_clip_image_onnx(image_base64).await,
        Some(ImageBackend::Auto) | None => return Err(ClipCallError::Unavailable),
    }
    .map_err(ClipCallError::Infer)?;
    parse_vector(value)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ImageBackend {
    Auto,
    Hailo,
    Onnx,
}

pub(crate) fn select_image_backend(
    preferred: ImageBackend,
    hailo_available: bool,
    onnx_available: bool,
) -> Option<ImageBackend> {
    let hailo = hailo_available.then_some(ImageBackend::Hailo);
    let onnx = onnx_available.then_some(ImageBackend::Onnx);
    match preferred {
        ImageBackend::Auto => hailo.or(onnx),
        ImageBackend::Hailo => hailo,
        ImageBackend::Onnx => onnx,
    }
}

pub(crate) async fn read_image_as_base64(
    state: &SharedState,
    path: &Path,
) -> Result<String, ClipCallError> {
    let path = validate_scan_path(state, path).ok_or(ClipCallError::PathRejected)?;
    let data = tokio::fs::read(path)
        .await
        .map_err(|error| ClipCallError::Io(error.to_string()))?;
    // yu-infer independently enforces the decoded/base64 budgets. This bound
    // avoids allocating an unbounded request before that second boundary.
    if data.len() > 16 * 1024 * 1024 {
        return Err(ClipCallError::Io(
            "image exceeds 16 MiB local read limit".to_string(),
        ));
    }
    use base64::Engine as _;
    Ok(base64::engine::general_purpose::STANDARD.encode(data))
}

fn validate_scan_path(state: &SharedState, path: &Path) -> Option<std::path::PathBuf> {
    let real_path = std::fs::canonicalize(path).ok()?;
    let roots: Vec<std::path::PathBuf> = state
        .config
        .app_config
        .get("scan_roots")
        .and_then(Value::as_array)?
        .iter()
        .filter_map(|entry| entry.get("path").and_then(Value::as_str))
        .filter_map(|entry| std::fs::canonicalize(entry).ok())
        .collect();
    (!roots.is_empty() && roots.iter().any(|root| real_path.starts_with(root))).then_some(real_path)
}

#[derive(Debug)]
pub(crate) enum ClipCallError {
    Unavailable,
    PathRejected,
    Io(String),
    Infer(InferClientError),
    InvalidResponse,
}

fn parse_vector(value: Value) -> Result<Vec<f32>, ClipCallError> {
    let vector = value
        .get("data")
        .and_then(|data| data.get("vector"))
        .and_then(Value::as_array)
        .ok_or(ClipCallError::InvalidResponse)?
        .iter()
        .map(|entry| {
            entry
                .as_f64()
                .map(crate::num::narrow_f32)
                .filter(|value| value.is_finite())
        })
        .collect::<Option<Vec<_>>>()
        .ok_or(ClipCallError::InvalidResponse)?;
    (vector.len() == 512)
        .then_some(vector)
        .ok_or(ClipCallError::InvalidResponse)
}

pub async fn search_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Query(query): Query<SearchQuery>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let query_text = query.q.as_deref().unwrap_or_default().trim().to_string();
    if query_text.is_empty() {
        return bad_request("Query parameter 'q' is required");
    }
    if query_text.chars().count() > MAX_QUERY_CHARS {
        return bad_request("Query too long (max 500 chars)");
    }
    let limit = match parse_limit(query.limit.as_deref()) {
        Ok(value) => value,
        Err(message) => return bad_request(message),
    };
    let threshold = match parse_threshold(query.threshold.as_deref()) {
        Ok(value) => value,
        Err(message) => return bad_request(message),
    };

    let started = Instant::now();
    let vector = match call_clip_text(&state, query_text.clone()).await {
        Ok(vector) => vector,
        Err(ClipCallError::Unavailable)
        | Err(ClipCallError::Infer(InferClientError::BadStatus { status: 503, .. })) => {
            return service_unavailable("CLIP text encoder is unavailable")
        }
        Err(error) => {
            tracing::error!(?error, "CLIP text inference failed");
            return internal_error("Search failed");
        }
    };

    let allowed = match build_filter_ids(&state, &query).await {
        Ok(ids) => ids,
        Err(error) => {
            tracing::error!(%error, "CLIP filter query failed");
            return internal_error("Search filter failed");
        }
    };
    if let Err(error) = ensure_current_index(&state).await {
        tracing::error!(%error, "CLIP index load/rebuild failed");
        return internal_error("Search index unavailable");
    }
    // Match the Python FAISS path: request additional nearest candidates
    // before applying a SQL-derived allow-list, then cap the final response.
    let matches = match state.clip_index.search(
        &vector,
        candidate_limit(limit, allowed.is_some()),
        threshold,
    ) {
        Ok(matches) => matches,
        Err(error) => {
            tracing::error!(%error, "CLIP index search failed");
            return internal_error("Search failed");
        }
    };
    // Apply the allow-list only here -- NOT `.take(limit)` yet. A soft-deleted
    // file is only discovered once `get_file_paths_by_ids` excludes it below,
    // so truncating to `limit` before that point can drop it from a set that
    // already had fewer than `limit` matches, permanently losing valid
    // lower-ranked candidates that `candidate_limit`'s over-fetch existed to
    // cover. `limit` is applied to `results` instead, after path resolution.
    let matches: Vec<_> = matches
        .into_iter()
        .filter(|(file_id, _)| allowed.as_ref().is_none_or(|ids| ids.contains(file_id)))
        .collect();
    let paths = match vector_store::get_file_paths_by_ids(
        &state.db_read,
        &matches.iter().map(|(id, _)| *id).collect::<Vec<_>>(),
    )
    .await
    {
        Ok(paths) => paths,
        Err(error) => {
            tracing::error!(%error, "CLIP result path lookup failed");
            return internal_error("Search failed");
        }
    };
    let mut results = build_search_results(matches, &paths);
    results.truncate(limit);
    let indexed_count = state
        .clip_index
        .active_meta()
        .map_or(0, |meta| meta.vector_count);
    let status = if results.is_empty() { "empty" } else { "ok" };
    Json(json!({
        "status": status,
        "total": results.len(),
        "results": results,
        "query": query_text,
        "indexed_count": indexed_count,
        "threshold": threshold,
        "timing": {"total_ms": started.elapsed().as_millis(), "backend": "usearch"},
    }))
    .into_response()
}

pub async fn runtime_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    let counts = state
        .clip_runtime_cache
        .get_or_try_insert_with(|| async {
            let indexed =
                vector_store::count_indexed(&state.vectors_db_read, DEFAULT_MODEL).await?;
            let unindexed = vector_store::count_unindexed(
                &state.db_read,
                &state.vectors_db_read,
                DEFAULT_MODEL,
            )
            .await?;
            Ok::<_, vector_store::VectorStoreError>((indexed, unindexed))
        })
        .await;
    match counts {
        Ok((indexed_count, unindexed_count)) => {
            let backends = backends_payload(&state).await;
            Json(json!({
                "status": "ok", "indexed_count": indexed_count, "unindexed_count": unindexed_count,
                "backends": backends["backends"].clone(),
                "auto_index_on_scan": false, "preferred_backend": "auto",
            }))
            .into_response()
        }
        Err(error) => {
            tracing::error!(%error, "CLIP runtime counts failed");
            internal_error("Runtime status unavailable")
        }
    }
}

pub async fn backends_handler(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_or_response(&state, auth.as_ref()) {
        return response;
    }
    Json(backends_payload(&state).await).into_response()
}

/// 1x1-pixel-shaped probe payload. HailoRT loads and validates the CLIP HEF
/// *before* touching image bytes, so any failure past that point (invalid
/// image) already proves the device call got further than a stub build can.
const HAILO_PROBE_IMAGE_BASE64: &str = "AA==";
const HAILO_PROBE_TTL: Duration = Duration::from_secs(30);
/// Bounds the probe round-trip itself. Without this, a wedged sidecar
/// (device hung, or the single-threaded HailoRT device queue backed up
/// behind a stuck real request) would leave `infer_clip_image`'s awaited
/// call -- and therefore `backends_payload`, and therefore both
/// `runtime_handler` and `backends_handler` -- hanging indefinitely for
/// every caller, since `reqwest::Client::new()` sets no request timeout.
const HAILO_PROBE_TIMEOUT: Duration = Duration::from_secs(10);
/// `error` codes `clip_image` (yu-hailo-infer's `router.rs`) can only return
/// once HailoRT metadata load for the HEF has already succeeded -- proof the
/// call reached real device work, not a stub. Keep in sync with the sidecar;
/// an unrecognized code is deliberately treated as "not proven", not "ok".
const HAILO_POST_METADATA_ERROR_CODES: &[&str] = &[
    "hailort_clip_image_invalid_metadata",
    "clip_image_invalid_image",
    "media_preprocessing_busy",
    "media_preprocessing_failed",
    "hailort_clip_image_failed",
];
static HAILO_PROBE_CACHE: LazyLock<tokio::sync::RwLock<Option<(Instant, bool)>>> =
    LazyLock::new(|| tokio::sync::RwLock::new(None));
static ONNX_IMAGE_PROBE_CACHE: LazyLock<tokio::sync::RwLock<Option<(Instant, bool)>>> =
    LazyLock::new(|| tokio::sync::RwLock::new(None));

/// `state.infer_client.is_some()` only proves the sidecar process started
/// and answered `/healthz` -- a build without HailoRT headers (the shipped
/// binary, unless it was cross-compiled with the SDK present) still starts
/// and answers healthy on real Hailo hardware, and its HailoRT calls fail
/// per-request instead. Nor does `/dev/hailo0` existing prove *this* binary
/// can use it. Only an actual round-trip distinguishes the two, so probe the
/// real endpoint and cache the (rate-limited, device-serialized) result.
async fn probe_hailo_image_backend(state: &SharedState) -> bool {
    let Some(client) = state.infer_client.as_ref() else {
        return false;
    };
    if !super::analysis::is_hailo_device_available() {
        return false;
    }
    if let Some((checked_at, available)) = *HAILO_PROBE_CACHE.read().await {
        if checked_at.elapsed() < HAILO_PROBE_TTL {
            return available;
        }
    }
    let available = hailo_image_backend_reachable(client).await;
    *HAILO_PROBE_CACHE.write().await = Some((Instant::now(), available));
    available
}

/// `hailo_stub` from yu-hailo-infer's `/healthz` (0.4.0 onwards): the sidecar
/// itself reporting that it was built without HailoRT headers, so it links
/// the stub shim and can never reach the device however its per-request
/// errors happen to be shaped. `None` means the sidecar did not say -- it
/// predates the field -- and the caller must fall through to the round-trip
/// probe rather than assume either answer.
fn healthz_hailo_stub(body: &Value) -> Option<bool> {
    body.get("hailo_stub")?.as_bool()
}

fn healthz_clip_image_onnx(body: &Value) -> Option<bool> {
    body.get("clip_image_onnx")?.as_bool()
}

async fn probe_onnx_image_backend(state: &SharedState) -> bool {
    let Some(client) = state.infer_client.as_ref() else {
        return false;
    };
    if let Some((checked_at, available)) = *ONNX_IMAGE_PROBE_CACHE.read().await {
        if checked_at.elapsed() < HAILO_PROBE_TTL {
            return available;
        }
    }
    let available = onnx_image_backend_reachable(client).await;
    *ONNX_IMAGE_PROBE_CACHE.write().await = Some((Instant::now(), available));
    available
}

async fn onnx_image_backend_reachable(client: &InferClient) -> bool {
    matches!(
        tokio::time::timeout(HAILO_PROBE_TIMEOUT, client.healthz()).await,
        Ok(Ok(body)) if healthz_clip_image_onnx(&body) == Some(true)
    )
}

/// The uncached decision: ask the sidecar what it is, then -- only if that
/// leaves the question open -- make it prove it by reaching the device.
async fn hailo_image_backend_reachable(client: &InferClient) -> bool {
    // A stub build is authoritative and cheap: no device round-trip, and no
    // dependency on `HAILO_POST_METADATA_ERROR_CODES` staying in sync. An
    // unreachable or older `/healthz` says nothing either way, so fall
    // through instead of failing closed on it.
    if let Ok(Ok(body)) = tokio::time::timeout(HAILO_PROBE_TIMEOUT, client.healthz()).await {
        if healthz_hailo_stub(&body) == Some(true) {
            return false;
        }
    }
    // A non-stub build still only proves this binary *links* HailoRT: the HEF
    // can be missing and the device busy or wedged, so the round-trip stays.
    match tokio::time::timeout(
        HAILO_PROBE_TIMEOUT,
        client.infer_clip_image(HAILO_PROBE_IMAGE_BASE64.to_string()),
    )
    .await
    {
        Ok(Ok(_)) => true,
        // Fail closed: only count a response as evidence of a real device if
        // its `error` code is one we know the sidecar can only reach *after*
        // HailoRT metadata load succeeds (our garbage payload is chosen to
        // fail decode there, on real hardware). Any other code -- including
        // "hailort_clip_image_metadata_failed" (the signature a stub build
        // always returns, regardless of hef_path or image content), an auth
        // or size-limit rejection, or an error shape we don't recognize --
        // is treated as "not proven available", not "assume available".
        Ok(Err(InferClientError::BadStatus { body, .. })) => serde_json::from_str::<Value>(&body)
            .ok()
            .and_then(|value| value.get("error")?.as_str().map(str::to_string))
            .is_some_and(|code| HAILO_POST_METADATA_ERROR_CODES.contains(&code.as_str())),
        // Covers both an error response we don't recognize and a timeout
        // (the sidecar is unresponsive on this call) -- don't hang the
        // caller waiting on it; report unavailable and let the next probe
        // (after HAILO_PROBE_TTL) re-check.
        Ok(Err(_)) | Err(_) => false,
    }
}

/// The three failure modes Python's `get_hailo_status` distinguishes, so the
/// UI can render an actionable message instead of an opaque "N/A".
///
/// `src/ts/shared/extension-health.ts` renders `runtime_ok`, `hardware_ok` and
/// `hef_ok` as named rows. The keys Rust used to return instead --
/// `image_backend` and `sidecar_connected` -- are read from nowhere in
/// `src/ts/`, so the shape below is the contract and the old pair was simply a
/// different invention.
///
/// What each flag is derived from here differs from Python by necessity, and
/// the mapping is the whole of it:
///
/// | flag          | Python                        | Rust                                        |
/// |---------------|-------------------------------|---------------------------------------------|
/// | `hardware_ok` | `device_manager` device probe | `analysis::is_hailo_device_available()`      |
/// | `runtime_ok`  | `import hailo_platform`       | sidecar answers `/healthz` and is not a stub |
/// | `hef_ok`      | HEF file exists on disk       | the CLIP image round-trip succeeds           |
///
/// `hef_ok` is the weakest of the three: the sidecar owns the HEF and Rust
/// cannot stat it, so a successful round-trip is the only evidence available.
/// It is therefore reported false only once runtime and hardware are both
/// established -- the same order Python resolves `reason` in -- rather than
/// blaming the HEF for a failure that has an earlier explanation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct HailoImageStatus {
    pub runtime_ok: bool,
    pub hardware_ok: bool,
    pub hef_ok: bool,
}

impl HailoImageStatus {
    pub(crate) fn available(self) -> bool {
        self.runtime_ok && self.hardware_ok && self.hef_ok
    }

    /// Mirrors Python's `if not runtime_ok / elif not hw_ok / elif not hef_ok`
    /// ordering, but says what is true of *this* server. Python's wording names
    /// a `hailo_platform` wheel and a HEF path, neither of which exists in a
    /// standalone Rust process; repeating those sentences here would put a
    /// false statement in front of the operator to make a comparison green.
    pub(crate) fn reason(self) -> &'static str {
        if !self.runtime_ok {
            "Hailo inference sidecar unavailable or built without HailoRT"
        } else if !self.hardware_ok {
            "Hailo device not detected"
        } else if !self.hef_ok {
            "CLIP HEF not usable by the inference sidecar"
        } else {
            ""
        }
    }

    fn to_json(self) -> Value {
        json!({
            "available": self.available(),
            "runtime_ok": self.runtime_ok,
            "hardware_ok": self.hardware_ok,
            "hef_ok": self.hef_ok,
            "reason": self.reason(),
        })
    }
}

/// Full status for the Hailo image backend.
///
/// `available()` is exactly the old single boolean, unchanged, so backend
/// *selection* (`select_image_backend`) behaves identically -- this widens what
/// is reported, not what is chosen.
async fn probe_hailo_image_status(state: &SharedState) -> HailoImageStatus {
    let available = probe_hailo_image_backend(state).await;
    if available {
        return HailoImageStatus {
            runtime_ok: true,
            hardware_ok: true,
            hef_ok: true,
        };
    }
    let hardware_ok = super::analysis::is_hailo_device_available();
    let runtime_ok = match state.infer_client.as_ref() {
        None => false,
        Some(client) => {
            match tokio::time::timeout(HAILO_PROBE_TIMEOUT, client.healthz()).await {
                // A sidecar that says it is a stub build can never reach the
                // device; one that does not say predates the field, and a
                // reachable sidecar is the best evidence of a runtime there is.
                Ok(Ok(body)) => healthz_hailo_stub(&body) != Some(true),
                Ok(Err(_)) | Err(_) => false,
            }
        }
    };
    HailoImageStatus {
        runtime_ok,
        hardware_ok,
        // Not `false` unconditionally: with runtime or hardware missing the HEF
        // was never reached, and claiming it is absent invents a fourth failure.
        hef_ok: runtime_ok && hardware_ok,
    }
}

async fn backends_payload(state: &SharedState) -> Value {
    let text_ready = super::clip_model::model_ready(&state.config.cache_dir);
    let hailo_status = probe_hailo_image_status(state).await;
    let onnx_image_available = probe_onnx_image_backend(state).await;
    backends_payload_for(
        hailo_status,
        onnx_image_available,
        text_ready,
        onnx_model_status(&state.config.cache_dir),
    )
}

/// Mirrors Python's `clip_onnx/model_download.py::get_model_status`.
fn onnx_model_status(cache_dir: &Path) -> Value {
    let path = super::clip_model::vision_model_path(cache_dir);
    let size_mb = std::fs::metadata(&path)
        .ok()
        .filter(|meta| meta.is_file())
        .map_or(0.0, |meta| {
            // Python rounds to two decimals.
            ((meta.len() as f64 / (1024.0 * 1024.0)) * 100.0).round() / 100.0
        });
    json!({
        "repo": ONNX_MODEL_REPO,
        "ready": super::clip_model::vision_model_ready(cache_dir),
        "path": path.to_string_lossy(),
        "size_mb": size_mb,
    })
}

/// The repo id Python's `_DEFAULT_REPO` names; `clip_model::model_dir`
/// already encodes the same value as a directory name.
const ONNX_MODEL_REPO: &str = "Xenova/clip-vit-base-patch16";

fn backends_payload_for(
    hailo_status: HailoImageStatus,
    onnx_image_available: bool,
    text_ready: bool,
    onnx_model_status: Value,
) -> Value {
    let onnx_available = onnx_image_available && text_ready;
    json!({
        "backends": [
            {
                "name": "hailo-10h", "available": hailo_status.available(), "priority": 1,
                "status": hailo_status.to_json(),
            },
            // Python lists this backend on every platform and reports it
            // unavailable off macOS. Rust has no CoreML support at all, so
            // `false` is true here on every platform it ships to; omitting the
            // entry instead would make the two lists differ in length for a
            // backend both agree is unusable.
            {"name": "coreml-ane", "available": false, "priority": 2},
            {
                "name": "onnx", "available": onnx_available, "priority": 3,
                "model_status": onnx_model_status,
            },
        ],
        "text_backend": {"name": "onnx", "available": text_ready, "role": "text_encoder"},
        "any_available": (hailo_status.available() || onnx_available) && text_ready,
    })
}

pub(crate) async fn ensure_current_index(
    state: &SharedState,
) -> Result<(), super::clip_index::ClipIndexError> {
    if let Some(meta) = state.clip_index.active_meta() {
        if !state
            .clip_index
            .is_drifted(&state.vectors_db_read, &meta)
            .await?
        {
            return Ok(());
        }
    }
    if !state
        .clip_index
        .load_if_current(&state.vectors_db_read)
        .await?
    {
        state
            .clip_index
            .rebuild(&state.vectors_db_read, None)
            .await?;
    }
    Ok(())
}

async fn build_filter_ids(
    state: &SharedState,
    args: &SearchQuery,
) -> Result<Option<HashSet<i64>>, sqlx::Error> {
    let mut builder = QueryBuilder::<Sqlite>::new("SELECT id FROM files WHERE is_deleted = 0");
    let mut has_filter = false;
    if let Some(format) = args
        .format
        .as_deref()
        .filter(|value| !value.is_empty() && *value != "all")
    {
        let exts: &[&str] = if format == "image" {
            IMAGE_EXTENSIONS
        } else if format == "video" {
            VIDEO_EXTENSIONS
        } else {
            &[]
        };
        append_extensions(&mut builder, exts, &mut has_filter);
    }
    if let Some(exts) = args.format_exts.as_deref() {
        let valid: Vec<String> = exts
            .split(',')
            .map(str::trim)
            .map(|ext| ext.trim_start_matches('.'))
            .map(str::to_ascii_lowercase)
            .filter(|ext| {
                !ext.is_empty()
                    && ext.len() <= 10
                    && ext
                        .bytes()
                        .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
            })
            .collect();
        let valid_refs: Vec<&str> = valid.iter().map(String::as_str).collect();
        append_extensions(&mut builder, &valid_refs, &mut has_filter);
    }
    for (value, column, end_of_day) in [
        (args.from.as_deref(), "mtime", false),
        (args.to.as_deref(), "mtime", true),
    ] {
        if let Some(value) = value.and_then(parse_date) {
            has_filter = true;
            builder
                .push(" AND ")
                .push(column)
                .push(if end_of_day { " < " } else { " >= " })
                .push_bind(if end_of_day { value + 86_400 } else { value });
        }
    }
    if let Some(model) = args
        .model_filter
        .as_deref()
        .filter(|value| !value.is_empty() && *value != "all")
    {
        has_filter = true;
        builder
            .push(" AND id IN (SELECT file_id FROM templates WHERE meta_source = ")
            .push_bind(model)
            .push(")");
    }
    for (value, column, op) in [
        (args.min_width.as_deref(), "width", ">="),
        (args.max_width.as_deref(), "width", "<="),
        (args.min_height.as_deref(), "height", ">="),
        (args.max_height.as_deref(), "height", "<="),
    ] {
        if let Some(value) = value
            .and_then(|value| value.parse::<i64>().ok())
            .filter(|value| *value > 0)
        {
            has_filter = true;
            builder
                .push(" AND ")
                .push(column)
                .push(" ")
                .push(op)
                .push(" ")
                .push_bind(value);
        }
    }
    if let Some(path) = args.in_path.as_deref().filter(|value| !value.is_empty()) {
        has_filter = true;
        builder
            .push(" AND path LIKE ")
            .push_bind(format!("%{path}%"));
    }
    if args.fav_only.as_deref() == Some("true") {
        has_filter = true;
        builder.push(" AND id IN (SELECT file_id FROM favorites)");
    }
    if !has_filter {
        return Ok(None);
    }
    Ok(Some(
        builder
            .build()
            .fetch_all(&state.db_read)
            .await?
            .into_iter()
            .map(|row| row.get("id"))
            .collect(),
    ))
}

fn append_extensions(
    builder: &mut QueryBuilder<Sqlite>,
    extensions: &[&str],
    has_filter: &mut bool,
) {
    if extensions.is_empty() {
        return;
    }
    *has_filter = true;
    builder.push(" AND (");
    for (index, extension) in extensions.iter().enumerate() {
        if index > 0 {
            builder.push(" OR ");
        }
        builder
            .push("lower(path) LIKE ")
            .push_bind(format!("%.{extension}"));
    }
    builder.push(")");
}

fn parse_date(value: &str) -> Option<i64> {
    Some(
        chrono::NaiveDate::parse_from_str(value, "%Y-%m-%d")
            .ok()?
            .and_hms_opt(0, 0, 0)?
            .and_utc()
            .timestamp(),
    )
}

fn parse_limit(value: Option<&str>) -> Result<usize, &'static str> {
    match value {
        None | Some("") => Ok(DEFAULT_LIMIT),
        Some(value) => value
            .parse::<usize>()
            .ok()
            .filter(|value| (1..=MAX_LIMIT).contains(value))
            .ok_or("limit must be between 1 and 200"),
    }
}
fn parse_threshold(value: Option<&str>) -> Result<f32, &'static str> {
    match value {
        None | Some("") => Ok(DEFAULT_THRESHOLD),
        Some(value) => value
            .parse::<f32>()
            .ok()
            .filter(|value| value.is_finite() && (0.0..=1.0).contains(value))
            .ok_or("threshold must be a finite value between 0.0 and 1.0"),
    }
}

fn candidate_limit(limit: usize, has_filter: bool) -> usize {
    limit.saturating_mul(if has_filter { 4 } else { 2 })
}

/// A `file_id` absent from `paths` means `get_file_paths_by_ids` excluded it
/// (soft-deleted since the CLIP vector was indexed) -- drop the result
/// rather than surface it with an empty `path`, which would otherwise read
/// as a real, openable file to any client.
fn build_search_results(
    matches: Vec<(i64, f32)>,
    paths: &std::collections::HashMap<i64, String>,
) -> Vec<Value> {
    matches
        .into_iter()
        .filter_map(|(file_id, score)| {
            let path = paths.get(&file_id)?;
            Some(json!({
                "file_id": file_id,
                "path": path,
                "score": (score * 10_000.0).round() / 10_000.0,
            }))
        })
        .collect()
}
fn bad_request(message: impl Into<String>) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"status":"error", "message":message.into()})),
    )
        .into_response()
}
fn service_unavailable(message: impl Into<String>) -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"status":"error", "message":message.into()})),
    )
        .into_response()
}
fn internal_error(message: impl Into<String>) -> Response {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"status":"error", "message":message.into()})),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncating_after_path_resolution_recovers_the_full_limit_despite_gaps() {
        // Regression for truncating `matches` to `limit` before soft-deleted
        // candidates are known and excluded: with limit=3 and 2 of the top 5
        // candidates soft-deleted, the old order (`.take(3)` on raw matches,
        // *then* drop invalid ones) would yield only [1, 3] -- one short of
        // the limit even though candidate 5 was available to fill the gap.
        let mut paths = std::collections::HashMap::new();
        paths.insert(1, "a.png".to_string());
        // file_id 2 and 4 simulate soft-deleted matches: present in the
        // index, absent from `paths`.
        paths.insert(3, "c.png".to_string());
        paths.insert(5, "e.png".to_string());
        let matches = vec![(1, 0.9), (2, 0.85), (3, 0.8), (4, 0.75), (5, 0.7)];
        let mut results = build_search_results(matches, &paths);
        results.truncate(3);
        assert_eq!(
            results
                .iter()
                .map(|r| r["file_id"].as_i64().unwrap())
                .collect::<Vec<_>>(),
            vec![1, 3, 5]
        );
    }

    #[test]
    fn build_search_results_drops_matches_missing_a_path() {
        let mut paths = std::collections::HashMap::new();
        paths.insert(1, "a.png".to_string());
        // file_id 2 is intentionally absent -- simulates get_file_paths_by_ids
        // excluding a soft-deleted file that is still in the CLIP index.
        let results = build_search_results(vec![(1, 0.9), (2, 0.5)], &paths);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0]["file_id"], 1);
        assert_eq!(results[0]["path"], "a.png");
    }

    #[test]
    fn validates_numeric_boundaries() {
        assert_eq!(parse_limit(Some("200")), Ok(200));
        assert!(parse_limit(Some("201")).is_err());
        assert_eq!(parse_threshold(Some("0")), Ok(0.0));
        assert_eq!(parse_threshold(Some("1")), Ok(1.0));
        assert!(parse_threshold(Some("NaN")).is_err());
        assert!(parse_threshold(Some("1.01")).is_err());
        assert_eq!(candidate_limit(50, false), 100);
        assert_eq!(candidate_limit(50, true), 200);
    }

    #[tokio::test]
    async fn read_routes_require_admin_scope() {
        let state = crate::state::semantic_test_state(true).await;
        let query = SearchQuery {
            q: Some("cat".to_string()),
            limit: None,
            threshold: None,
            format: None,
            format_exts: None,
            from: None,
            to: None,
            model_filter: None,
            min_width: None,
            max_width: None,
            min_height: None,
            max_height: None,
            in_path: None,
            fav_only: None,
        };
        assert_eq!(
            search_handler(State(state.clone()), None, Query(query))
                .await
                .status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            runtime_handler(State(state.clone()), None).await.status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            backends_handler(State(state), None).await.status(),
            StatusCode::FORBIDDEN
        );
    }

    #[tokio::test]
    async fn search_rejects_empty_and_too_long_queries_before_inference() {
        let state = crate::state::semantic_test_state(false).await;
        for q in [
            "".to_string(),
            " ".to_string(),
            "x".repeat(MAX_QUERY_CHARS + 1),
        ] {
            let response = search_handler(
                State(state.clone()),
                None,
                Query(SearchQuery {
                    q: Some(q),
                    limit: None,
                    threshold: None,
                    format: None,
                    format_exts: None,
                    from: None,
                    to: None,
                    model_filter: None,
                    min_width: None,
                    max_width: None,
                    min_height: None,
                    max_height: None,
                    in_path: None,
                    fav_only: None,
                }),
            )
            .await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        }
    }
}

#[cfg(test)]
mod hailo_backend_tests {
    use super::*;
    use axum::{routing::post, Router};

    /// A sidecar that answers `/healthz` with `healthz_body` and always
    /// answers `/v1/infer/clip-image` with a post-metadata error code -- the
    /// shape a *real* device produces for our garbage payload. Every case
    /// below therefore has a probe that says "available"; anything that comes
    /// out false was decided by the `hailo_stub` gate alone.
    async fn mock_sidecar(healthz_body: Option<Value>) -> Option<InferClient> {
        let clip_image = post(|| async {
            (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "clip_image_invalid_image"})),
            )
        });
        let mut app = Router::new().route("/v1/infer/clip-image", clip_image);
        if let Some(body) = healthz_body {
            app = app.route(
                "/healthz",
                axum::routing::get(move || {
                    let body = body.clone();
                    async move { Json(body) }
                }),
            );
        }
        let listener = match tokio::net::TcpListener::bind("127.0.0.1:0").await {
            Ok(listener) => listener,
            Err(error) if error.kind() == std::io::ErrorKind::PermissionDenied => return None,
            Err(error) => panic!("failed to bind mock sidecar: {error}"),
        };
        let addr = listener.local_addr().expect("mock sidecar has no address");
        tokio::spawn(async move {
            let _ = axum::serve(listener, app).await;
        });
        Some(InferClient::new(format!("http://{addr}"), "t".to_string()))
    }

    #[tokio::test]
    async fn stub_build_is_unavailable_even_when_the_probe_would_pass() {
        let Some(client) = mock_sidecar(Some(json!({"ok": true, "hailo_stub": true}))).await else {
            return;
        };
        assert!(!hailo_image_backend_reachable(&client).await);
    }

    #[tokio::test]
    async fn non_stub_build_still_has_to_prove_it_through_the_probe() {
        let Some(client) = mock_sidecar(Some(json!({"ok": true, "hailo_stub": false}))).await
        else {
            return;
        };
        assert!(hailo_image_backend_reachable(&client).await);
    }

    #[tokio::test]
    async fn sidecar_predating_the_field_falls_through_to_the_probe() {
        // No `hailo_stub` key: yu-hailo-infer before 0.4.0. Absence must not
        // be read as either answer -- the probe decides, as it did before.
        let Some(client) = mock_sidecar(Some(json!({"ok": true}))).await else {
            return;
        };
        assert!(hailo_image_backend_reachable(&client).await);
    }

    #[tokio::test]
    async fn unreachable_healthz_falls_through_to_the_probe() {
        let Some(client) = mock_sidecar(None).await else {
            return;
        };
        assert!(hailo_image_backend_reachable(&client).await);
    }

    #[tokio::test]
    async fn non_bool_hailo_stub_is_not_read_as_true() {
        assert_eq!(healthz_hailo_stub(&json!({"hailo_stub": "true"})), None);
        let Some(client) = mock_sidecar(Some(json!({"hailo_stub": "true"}))).await else {
            return;
        };
        assert!(hailo_image_backend_reachable(&client).await);
    }

    fn text_model_ready(cache_dir: &std::path::Path) -> bool {
        let dir = super::super::clip_model::model_dir(cache_dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("text_model.onnx"), []).unwrap();
        std::fs::write(dir.join("tokenizer.json"), []).unwrap();
        super::super::clip_model::model_ready(cache_dir)
    }

    /// Look a backend up by name rather than by position. The four tests below
    /// indexed `backends[1]`, which silently became the `coreml-ane` entry when
    /// one was added ahead of `onnx`; a positional assertion in a list whose
    /// membership is part of the contract fails to notice it moved.
    fn backend_named<'a>(payload: &'a Value, name: &str) -> &'a Value {
        payload["backends"]
            .as_array()
            .expect("backends is an array")
            .iter()
            .find(|entry| entry["name"] == name)
            .unwrap_or_else(|| panic!("no backend named {name} in {payload}"))
    }

    fn unavailable_hailo() -> HailoImageStatus {
        HailoImageStatus {
            runtime_ok: false,
            hardware_ok: false,
            hef_ok: false,
        }
    }

    #[tokio::test]
    async fn onnx_backend_is_unavailable_when_healthz_reports_false() {
        let Some(client) = mock_sidecar(Some(json!({"clip_image_onnx": false}))).await else {
            return;
        };
        let temp = tempfile::tempdir().unwrap();
        let payload = backends_payload_for(
            unavailable_hailo(),
            onnx_image_backend_reachable(&client).await,
            text_model_ready(temp.path()),
            onnx_model_status(temp.path()),
        );
        assert_eq!(backend_named(&payload, "onnx")["available"], false);
    }

    #[tokio::test]
    async fn onnx_backend_is_available_when_healthz_and_text_model_are_ready() {
        let Some(client) = mock_sidecar(Some(json!({"clip_image_onnx": true}))).await else {
            return;
        };
        let temp = tempfile::tempdir().unwrap();
        let payload = backends_payload_for(
            unavailable_hailo(),
            onnx_image_backend_reachable(&client).await,
            text_model_ready(temp.path()),
            onnx_model_status(temp.path()),
        );
        assert_eq!(backend_named(&payload, "onnx")["available"], true);
    }

    #[tokio::test]
    async fn onnx_backend_fails_closed_when_healthz_field_is_missing() {
        let Some(client) = mock_sidecar(Some(json!({"ok": true}))).await else {
            return;
        };
        let temp = tempfile::tempdir().unwrap();
        let payload = backends_payload_for(
            unavailable_hailo(),
            onnx_image_backend_reachable(&client).await,
            text_model_ready(temp.path()),
            onnx_model_status(temp.path()),
        );
        assert_eq!(backend_named(&payload, "onnx")["available"], false);
    }

    #[tokio::test]
    async fn onnx_backend_is_unavailable_without_text_model() {
        let Some(client) = mock_sidecar(Some(json!({"clip_image_onnx": true}))).await else {
            return;
        };
        let temp = tempfile::tempdir().unwrap();
        let payload = backends_payload_for(
            unavailable_hailo(),
            onnx_image_backend_reachable(&client).await,
            false,
            onnx_model_status(temp.path()),
        );
        assert_eq!(backend_named(&payload, "onnx")["available"], false);
    }

    /// The keys `src/ts/shared/extension-health.ts` renders, and the ones
    /// Python's `get_hailo_status` documents as a contract. The pair Rust used
    /// to emit (`image_backend`, `sidecar_connected`) must not come back.
    #[test]
    fn hailo_status_reports_pythons_three_failure_modes() {
        let temp = tempfile::tempdir().unwrap();
        let payload = backends_payload_for(
            unavailable_hailo(),
            false,
            false,
            onnx_model_status(temp.path()),
        );
        let status = &backend_named(&payload, "hailo-10h")["status"];

        for key in ["available", "runtime_ok", "hardware_ok", "hef_ok", "reason"] {
            assert!(status.get(key).is_some(), "missing {key} in {status}");
        }
        assert!(status.get("image_backend").is_none());
        assert!(status.get("sidecar_connected").is_none());
    }

    #[test]
    fn reason_names_the_earliest_unmet_condition() {
        // Python resolves runtime -> hardware -> HEF in this order, so a server
        // with no runtime must not be told its HEF is the problem.
        let no_runtime = HailoImageStatus {
            runtime_ok: false,
            hardware_ok: false,
            hef_ok: false,
        };
        assert!(no_runtime.reason().contains("sidecar"));

        let no_device = HailoImageStatus {
            runtime_ok: true,
            hardware_ok: false,
            hef_ok: false,
        };
        assert_eq!(no_device.reason(), "Hailo device not detected");

        let no_hef = HailoImageStatus {
            runtime_ok: true,
            hardware_ok: true,
            hef_ok: false,
        };
        assert!(no_hef.reason().contains("HEF"));

        let ready = HailoImageStatus {
            runtime_ok: true,
            hardware_ok: true,
            hef_ok: true,
        };
        assert_eq!(ready.reason(), "");
        assert!(ready.available());
    }

    #[test]
    fn coreml_is_listed_and_unavailable() {
        // Dropping the entry would make the two backend lists differ in length
        // for a backend both implementations agree is unusable here.
        let temp = tempfile::tempdir().unwrap();
        let payload = backends_payload_for(
            unavailable_hailo(),
            false,
            false,
            onnx_model_status(temp.path()),
        );
        assert_eq!(backend_named(&payload, "coreml-ane")["available"], false);
        assert_eq!(backend_named(&payload, "coreml-ane")["priority"], 2);
    }
}

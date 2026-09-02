//! Freeze-pullback animation renderer — port of extensions/builtin_freeze_pullback.
use axum::{
    extract::{Extension, Path, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use image::{imageops::FilterType, RgbImage};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};
use tokio::io::AsyncWriteExt;
use tokio_util::sync::CancellationToken;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::jobs::JobManager;
use crate::sse::{SseEvent, SseHub};
use crate::state::SharedState;

const JOB_ID: &str = "freeze_pullback";
const DEFAULT_OUTPUT_DIR: &str = "exports/freeze_pullback";

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

// ── params ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
pub struct Waypoint {
    pub x: f64,
    pub y: f64,
    pub zoom: Option<f64>,
    pub dwell: Option<f64>,
    pub transition: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GenerateRequest {
    pub file_id: String,
    pub hold_seconds: Option<f64>,
    pub pull_seconds: Option<f64>,
    pub fps: Option<u32>,
    pub scale_start: Option<f64>,
    pub scale_end: Option<f64>,
    pub out_width: Option<u32>,
    pub out_height: Option<u32>,
    pub focus_start: Option<[f64; 2]>,
    pub easing: Option<String>,
    pub vignette: Option<bool>,
    pub output_format: Option<String>,
    pub focus_provider: Option<String>,
    pub waypoints: Option<Vec<Waypoint>>,
}

#[derive(Debug, Clone)]
struct RenderParams {
    file_id: String,
    image_path: PathBuf,
    hold_seconds: f64,
    pull_seconds: f64,
    fps: u32,
    scale_start: f64,
    scale_end: f64,
    out_width: u32,
    out_height: u32,
    focus_start: [f64; 2],
    easing: String,
    vignette: bool,
    output_format: String,
}

fn validate_params(req: &GenerateRequest, image_path: PathBuf) -> Result<RenderParams, String> {
    let hold = req.hold_seconds.unwrap_or(2.0).clamp(1.0, 10.0);
    let pull = req.pull_seconds.unwrap_or(5.0).clamp(1.0, 20.0);
    let fps = req.fps.unwrap_or(30).clamp(15, 60);
    let scale_start = req.scale_start.unwrap_or(2.0).clamp(1.2, 5.0);
    let scale_end = req.scale_end.unwrap_or(1.0).clamp(1.0, scale_start);
    let out_width = req.out_width.unwrap_or(1280).clamp(256, 3840);
    let out_height = req.out_height.unwrap_or(720).clamp(256, 2160);
    let output_format = req.output_format.clone().unwrap_or_else(|| "mp4".into());
    if !["mp4", "gif", "apng", "webp", "webm"].contains(&output_format.as_str()) {
        return Err(format!("invalid output_format: {output_format}"));
    }
    Ok(RenderParams {
        file_id: req.file_id.clone(),
        image_path,
        hold_seconds: hold,
        pull_seconds: pull,
        fps,
        scale_start,
        scale_end,
        out_width,
        out_height,
        focus_start: req.focus_start.unwrap_or([0.5, 0.5]),
        easing: req
            .easing
            .clone()
            .unwrap_or_else(|| "ease_in_out_cubic".into()),
        vignette: req.vignette.unwrap_or(false),
        output_format,
    })
}

// ── easing ────────────────────────────────────────────────────────────────────

fn ease(t: f64, name: &str) -> f64 {
    match name {
        "ease_in_out_cubic" => {
            if t < 0.5 {
                4.0 * t * t * t
            } else {
                1.0 - (-2.0 * t + 2.0).powi(3) / 2.0
            }
        }
        "ease_out_quad" => t * (2.0 - t),
        "ease_in_quad" => t * t,
        "ease_out_expo" => {
            if t == 0.0 {
                0.0
            } else {
                (2.0f64).powf(10.0 * t - 10.0)
            }
        }
        _ => t,
    }
}

// ── camera ────────────────────────────────────────────────────────────────────

#[derive(Clone, Copy)]
struct Viewport {
    x: u32,
    y: u32,
    w: u32,
    h: u32,
}

fn compute_viewport(
    img_w: u32,
    img_h: u32,
    out_w: u32,
    out_h: u32,
    scale: f64,
    cx: f64,
    cy: f64,
) -> Viewport {
    let aspect = out_w as f64 / out_h as f64;
    let crop_h = crate::num::sat_u32(f64::from(img_h) / scale).min(img_h);
    let crop_w = crate::num::sat_u32(f64::from(crop_h) * aspect).min(img_w);
    let crop_h = crop_h.min(img_h);
    let center_x = crate::num::sat_i64(cx * f64::from(img_w));
    let center_y = crate::num::sat_i64(cy * f64::from(img_h));
    let x = u32::try_from(
        (center_x - i64::from(crop_w) / 2).clamp(0, i64::from(img_w.saturating_sub(crop_w))),
    )
    .unwrap_or(0);
    let y = u32::try_from(
        (center_y - i64::from(crop_h) / 2).clamp(0, i64::from(img_h.saturating_sub(crop_h))),
    )
    .unwrap_or(0);
    Viewport {
        x,
        y,
        w: crop_w,
        h: crop_h,
    }
}

// ── vignette ──────────────────────────────────────────────────────────────────

fn build_vignette(w: u32, h: u32) -> Vec<u8> {
    let mut alpha = vec![0u8; (w * h) as usize];
    let cx = w as f64 / 2.0;
    let cy = h as f64 / 2.0;
    for step in 0..20u32 {
        let rx = cx * (1.0 - step as f64 / 20.0);
        let ry = cy * (1.0 - step as f64 / 20.0);
        if rx < 1.0 || ry < 1.0 {
            continue;
        }
        let a = crate::num::sat_u8(60.0 * (f64::from(step) / 20.0).powi(2));
        for y in 0..h {
            for x in 0..w {
                let dx = (x as f64 - cx) / rx;
                let dy = (y as f64 - cy) / ry;
                if dx * dx + dy * dy > 1.0 {
                    let idx = (y * w + x) as usize;
                    if alpha[idx] < a {
                        alpha[idx] = a;
                    }
                }
            }
        }
    }
    alpha
}

fn apply_vignette(frame: &mut [u8], alpha: &[u8]) {
    for (i, &a) in alpha.iter().enumerate() {
        if a == 0 {
            continue;
        }
        let factor = 1.0 - a as f64 / 255.0;
        let base = i * 3;
        frame[base] = crate::num::sat_u8(f64::from(frame[base]) * factor);
        frame[base + 1] = crate::num::sat_u8(f64::from(frame[base + 1]) * factor);
        frame[base + 2] = crate::num::sat_u8(f64::from(frame[base + 2]) * factor);
    }
}

// ── sidecar ───────────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize)]
struct SidecarMetadata {
    file_id: String,
    output_file: String,
    created_at: u64,
}

fn output_dir() -> PathBuf {
    PathBuf::from(DEFAULT_OUTPUT_DIR)
}

/// Resolve a client-supplied output filename to a path guaranteed to stay
/// inside `output_dir()`. Returns `None` for any filename containing a path
/// separator or parent component, or whose canonicalized form escapes the
/// output dir (defends against symlinks placed inside it). A name that does not
/// yet exist is allowed through — the separator/parent guard already restricts
/// it to a single in-dir component, so callers get the normal not-found path.
fn safe_output_path(filename: &str) -> Option<PathBuf> {
    if filename.is_empty()
        || filename.contains('/')
        || filename.contains('\\')
        || filename.contains("..")
    {
        return None;
    }
    let base = std::fs::canonicalize(output_dir()).unwrap_or_else(|_| output_dir());
    let candidate = base.join(filename);
    match std::fs::canonicalize(&candidate) {
        Ok(canon) => canon.starts_with(&base).then_some(canon),
        Err(_) => Some(candidate),
    }
}

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn sse_timestamp() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

fn list_outputs() -> Vec<Value> {
    let mut out = Vec::new();
    let Ok(entries) = std::fs::read_dir(output_dir()) else {
        return out;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
        if ["mp4", "gif", "apng", "webp", "webm"].contains(&ext) {
            let name = path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned();
            let size = entry.metadata().map(|m| m.len()).unwrap_or(0);
            out.push(json!({"filename": name, "size": size}));
        }
    }
    out
}

// ── db helper ─────────────────────────────────────────────────────────────────

async fn resolve_image_path(pool: &sqlx::SqlitePool, file_id: &str) -> Option<PathBuf> {
    sqlx::query_as::<_, (String,)>("SELECT path FROM files WHERE id = ? AND is_deleted = 0")
        .bind(file_id)
        .fetch_optional(pool)
        .await
        .ok()
        .flatten()
        .map(|(p,)| PathBuf::from(p))
}

// ── renderer ──────────────────────────────────────────────────────────────────

fn encoder_args(fmt: &str) -> &'static [&'static str] {
    match fmt {
        "mp4" => &[
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ],
        "webm" => &["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p"],
        "gif" => &["-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"],
        "apng" => &["-f", "apng", "-plays", "0"],
        "webp" => &["-c:v", "libwebp", "-loop", "0"],
        _ => &[],
    }
}

async fn render_video(
    params: RenderParams,
    jm: Arc<JobManager>,
    hub: Arc<SseHub>,
    cancel: CancellationToken,
) -> Result<PathBuf, String> {
    let dir = output_dir();
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let stem = format!("fpb_{}_{}", params.file_id, unix_now());
    let out_path = dir.join(format!("{}.{}", stem, params.output_format));

    // Load source image in blocking thread
    let img_path = params.image_path.clone();
    let (img_w, img_h, raw) =
        tokio::task::spawn_blocking(move || -> Result<(u32, u32, Vec<u8>), String> {
            let img = image::open(&img_path).map_err(|e| e.to_string())?;
            let rgb = img.to_rgb8();
            let (w, h) = rgb.dimensions();
            Ok((w, h, rgb.into_raw()))
        })
        .await
        .map_err(|e| e.to_string())??;

    let raw = Arc::new(raw);

    // Build vignette mask once
    let vignette_mask: Option<Arc<Vec<u8>>> = if params.vignette {
        let (ow, oh) = (params.out_width, params.out_height);
        let mask = tokio::task::spawn_blocking(move || build_vignette(ow, oh))
            .await
            .map_err(|e| e.to_string())?;
        Some(Arc::new(mask))
    } else {
        None
    };

    // Spawn FFmpeg with stdin pipe
    let out_str = out_path.to_string_lossy().into_owned();
    let mut child = tokio::process::Command::new("ffmpeg")
        .args([
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            &format!("{}x{}", params.out_width, params.out_height),
            "-r",
            &params.fps.to_string(),
            "-i",
            "pipe:0",
        ])
        .args(encoder_args(&params.output_format))
        .arg(&out_str)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| format!("ffmpeg spawn: {e}"))?;

    let mut stdin = child.stdin.take().ok_or("no ffmpeg stdin")?;

    let hold_frames = crate::num::sat_u64((params.hold_seconds * f64::from(params.fps)).round());
    let pull_frames = crate::num::sat_u64((params.pull_seconds * f64::from(params.fps)).round());
    let total_frames = hold_frames + pull_frames;
    let (scale_start, scale_end) = (params.scale_start, params.scale_end);
    let focus = params.focus_start;
    let easing = params.easing.clone();
    let (ow, oh) = (params.out_width, params.out_height);

    for frame_idx in 0..total_frames {
        if cancel.is_cancelled() {
            break;
        }

        let t = if frame_idx < hold_frames {
            0.0
        } else {
            (frame_idx - hold_frames) as f64 / pull_frames.max(1) as f64
        };
        let e = ease(t, &easing);
        let scale = scale_start + (scale_end - scale_start) * e;

        let vp = compute_viewport(img_w, img_h, ow, oh, scale, focus[0], focus[1]);
        let raw_clone = raw.clone();
        let vig_clone = vignette_mask.clone();

        let frame_bytes = tokio::task::spawn_blocking(move || -> Result<Vec<u8>, String> {
            let row_stride = img_w as usize * 3;
            let mut cropped = vec![0u8; vp.w as usize * vp.h as usize * 3];
            for row in 0..vp.h {
                let src_off = (vp.y + row) as usize * row_stride + vp.x as usize * 3;
                let dst_off = row as usize * vp.w as usize * 3;
                let len = vp.w as usize * 3;
                cropped[dst_off..dst_off + len].copy_from_slice(&raw_clone[src_off..src_off + len]);
            }
            let crop_img = RgbImage::from_raw(vp.w, vp.h, cropped).ok_or("from_raw failed")?;
            let resized = image::imageops::resize(&crop_img, ow, oh, FilterType::Lanczos3);
            let mut bytes = resized.into_raw();
            if let Some(v) = vig_clone {
                apply_vignette(&mut bytes, &v);
            }
            Ok(bytes)
        })
        .await
        .map_err(|e| e.to_string())??;

        stdin
            .write_all(&frame_bytes)
            .await
            .map_err(|e| e.to_string())?;
        jm.update_progress(JOB_ID, frame_idx + 1, total_frames, None);
    }

    drop(stdin);
    child.wait().await.map_err(|e| e.to_string())?;

    let _ = std::fs::write(
        dir.join(format!("{stem}.json")),
        serde_json::to_string_pretty(&SidecarMetadata {
            file_id: params.file_id.clone(),
            output_file: format!("{}.{}", stem, params.output_format),
            created_at: unix_now(),
        })
        .unwrap_or_default(),
    );

    Ok(out_path)
}

fn send_sse(hub: &SseHub, event_type: &str, data: Value) {
    hub.send(SseEvent {
        event_type: event_type.into(),
        timestamp: sse_timestamp(),
        data,
        source: "freeze_pullback".into(),
    });
}

// ── route handlers ────────────────────────────────────────────────────────────

pub async fn check(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let ffmpeg_available = tokio::task::spawn_blocking(|| {
        std::process::Command::new("ffmpeg")
            .arg("-version")
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    })
    .await
    .unwrap_or(false);
    Json(json!({
        "status": "ok",
        "busy": state.job_manager.is_running(JOB_ID),
        "job_id": JOB_ID,
        "ffmpeg_available": ffmpeg_available,
    }))
    .into_response()
}

pub async fn generate(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(req): Json<GenerateRequest>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if state.job_manager.is_running(JOB_ID) {
        return (
            StatusCode::CONFLICT,
            Json(json!({"error": "render job already running"})),
        )
            .into_response();
    }
    let Some(image_path) = resolve_image_path(&state.db, &req.file_id).await else {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "file not found"})),
        )
            .into_response();
    };
    let params = match validate_params(&req, image_path) {
        Ok(p) => p,
        Err(e) => return (StatusCode::BAD_REQUEST, Json(json!({"error": e}))).into_response(),
    };

    let cancel = state.job_manager.start(JOB_ID, "freeze-pullback render");
    let jm = state.job_manager.clone();
    let hub = state.sse_hub.clone();

    tokio::spawn(async move {
        send_sse(&hub, "fpb.start", json!({"job_id": JOB_ID}));
        match render_video(params, jm.clone(), hub.clone(), cancel).await {
            Ok(path) => {
                let fname = path
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into_owned();
                jm.finish(JOB_ID, Some(json!({"filename": fname})), None);
                send_sse(
                    &hub,
                    "fpb.complete",
                    json!({"job_id": JOB_ID, "filename": fname}),
                );
            }
            Err(e) => {
                jm.finish(JOB_ID, None, Some(e.clone()));
                send_sse(&hub, "fpb.error", json!({"job_id": JOB_ID, "error": e}));
            }
        }
    });

    Json(json!({"status": "started", "job_id": JOB_ID})).into_response()
}

pub async fn status_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match state.job_manager.get_job(JOB_ID) {
        Some(job) => Json(json!({
            "running": job.running,
            "current": job.current,
            "total": job.total,
            "percent": job.percent,
            "error": job.error,
            "result": job.result,
        }))
        .into_response(),
        None => Json(json!({"running": false})).into_response(),
    }
}

pub async fn cancel_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if state.job_manager.cancel_job(JOB_ID) {
        Json(json!({"status": "cancelled"})).into_response()
    } else {
        Json(json!({"status": "not_running"})).into_response()
    }
}

pub async fn outputs_list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    Json(json!({"outputs": list_outputs()})).into_response()
}

pub async fn serve_output(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(filename): Path<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(path) = safe_output_path(&filename) else {
        return (StatusCode::BAD_REQUEST, "invalid filename").into_response();
    };
    let Ok(bytes) = std::fs::read(&path) else {
        return (StatusCode::NOT_FOUND, "not found").into_response();
    };
    let mime = match path.extension().and_then(|e| e.to_str()) {
        Some("mp4") => "video/mp4",
        Some("gif") => "image/gif",
        Some("webm") => "video/webm",
        Some("apng") => "image/apng",
        Some("webp") => "image/webp",
        _ => "application/octet-stream",
    };
    ([(header::CONTENT_TYPE, mime)], bytes).into_response()
}

pub async fn delete_output(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(filename): Path<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(path) = safe_output_path(&filename) else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "invalid filename"})),
        )
            .into_response();
    };
    match std::fs::remove_file(&path) {
        Ok(_) => Json(json!({"status": "deleted"})).into_response(),
        Err(_) => (StatusCode::NOT_FOUND, Json(json!({"error": "not found"}))).into_response(),
    }
}

pub async fn thumbnail(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(image_path) = resolve_image_path(&state.db_read, &file_id).await else {
        return (StatusCode::NOT_FOUND, "not found").into_response();
    };
    let result = tokio::task::spawn_blocking(move || -> Result<Vec<u8>, String> {
        let img = image::open(&image_path).map_err(|e| e.to_string())?;
        let thumb = img.thumbnail(320, 320);
        let mut buf = std::io::Cursor::new(Vec::new());
        thumb
            .write_to(&mut buf, image::ImageFormat::Jpeg)
            .map_err(|e| e.to_string())?;
        Ok(buf.into_inner())
    })
    .await;
    match result {
        Ok(Ok(b)) => ([(header::CONTENT_TYPE, "image/jpeg")], b).into_response(),
        _ => (StatusCode::INTERNAL_SERVER_ERROR, "thumbnail error").into_response(),
    }
}

pub fn routes() -> Router<SharedState> {
    Router::new()
        .route("/ext/freeze-pullback/api/check", get(check))
        .route("/ext/freeze-pullback/api/generate", post(generate))
        .route("/ext/freeze-pullback/api/status", get(status_handler))
        .route("/ext/freeze-pullback/api/cancel", post(cancel_handler))
        .route("/ext/freeze-pullback/api/outputs", get(outputs_list))
        .route(
            "/ext/freeze-pullback/api/outputs/{filename}",
            get(serve_output).delete(delete_output),
        )
        .route(
            "/ext/freeze-pullback/api/thumbnail/{file_id}",
            get(thumbnail),
        )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{body::to_bytes, extract::Extension};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::{
        auth::AuthContext,
        state::{AppState, Config},
    };

    async fn test_state_with_pin_auth(pin_auth_enabled: bool) -> SharedState {
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
                    pin_auth_enabled,
                    min_pin_length: 4,
                    python_url: String::new(),
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
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    async fn json_body(response: axum::response::Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    fn scoped_auth(scopes: Option<Vec<&str>>) -> Extension<AuthContext> {
        Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: scopes.map(|values| values.into_iter().map(str::to_string).collect()),
        })
    }

    #[test]
    fn rejects_path_traversal() {
        // Security-critical: any separator or parent component must be refused
        // before the path is joined to output_dir().
        assert!(safe_output_path("../etc/passwd").is_none());
        assert!(safe_output_path("a/b").is_none());
        assert!(safe_output_path("..\\windows\\system32").is_none());
        assert!(safe_output_path("/etc/passwd").is_none());
        assert!(safe_output_path("").is_none());
        assert!(safe_output_path("foo/../../bar").is_none());
    }

    #[tokio::test]
    async fn generate_requires_admin_scope_when_pin_auth_enabled() {
        let state = test_state_with_pin_auth(true).await;
        let auth = scoped_auth(None);
        let req = GenerateRequest {
            file_id: "missing".to_string(),
            hold_seconds: None,
            pull_seconds: None,
            fps: None,
            scale_start: None,
            scale_end: None,
            out_width: None,
            out_height: None,
            focus_start: None,
            easing: None,
            vignette: None,
            output_format: None,
            focus_provider: None,
            waypoints: None,
        };

        let denied = admin_scope_error(&state, Some(&auth)).expect("admin scope should deny");
        assert_eq!(denied.status(), StatusCode::FORBIDDEN);
        assert_eq!(
            json_body(denied).await,
            json!({"ok": false, "error": "Insufficient scope: requires 'admin'"})
        );

        let response = generate(State(state), Some(auth), Json(req)).await;

        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        assert_eq!(
            json_body(response).await,
            json!({"ok": false, "error": "Insufficient scope: requires 'admin'"})
        );
    }

    #[tokio::test]
    async fn delete_output_skips_admin_scope_when_pin_auth_disabled() {
        let state = test_state_with_pin_auth(false).await;
        let auth = scoped_auth(None);

        assert!(admin_scope_error(&state, Some(&auth)).is_none());

        let response =
            delete_output(State(state), Some(auth), Path("missing.mp4".to_string())).await;

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(json_body(response).await, json!({"error": "not found"}));
    }
}

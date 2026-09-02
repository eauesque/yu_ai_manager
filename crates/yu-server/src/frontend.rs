use std::path::Path;

use axum::{
    extract::{Extension, Path as AxumPath, State},
    http::{header, HeaderValue, StatusCode, Uri},
    response::{Html, IntoResponse, Redirect, Response},
};

use crate::security::CspNonce;
use minijinja::Environment;
use serde_json::json;

use crate::state::SharedState;

pub fn init_env(template_dirs: &[&Path]) -> Environment<'static> {
    let dirs: Vec<std::path::PathBuf> = template_dirs.iter().map(|p| p.to_path_buf()).collect();
    let mut env = Environment::new();
    env.set_loader(move |name: &str| {
        for dir in &dirs {
            let path = dir.join(name);
            if path.exists() {
                return std::fs::read_to_string(&path).map(Some).map_err(|e| {
                    minijinja::Error::new(minijinja::ErrorKind::InvalidOperation, e.to_string())
                });
            }
        }
        Ok(None)
    });
    env
}

pub fn dist_v(project_root: &Path) -> String {
    let info_path = project_root.join("ui/default/static/dist/dist_info.json");
    std::fs::read_to_string(info_path)
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| {
            v["src_hash"]
                .as_str()
                .map(|h| h[..h.len().min(8)].to_string())
        })
        .unwrap_or_else(|| "dev".to_string())
}

pub(crate) fn render(
    state: &SharedState,
    tpl: &str,
    ctx: serde_json::Value,
) -> Result<Html<String>, StatusCode> {
    state
        .env
        .get_template(tpl)
        .and_then(|t| t.render(ctx))
        .map(Html)
        .map_err(|e| {
            tracing::error!("template {tpl}: {e}");
            StatusCode::INTERNAL_SERVER_ERROR
        })
}

macro_rules! page {
    ($name:ident, $tpl:literal, $active:literal) => {
        pub async fn $name(
            State(s): State<SharedState>,
            Extension(CspNonce(nonce)): Extension<CspNonce>,
        ) -> Result<Html<String>, StatusCode> {
            render(
                &s,
                $tpl,
                json!({"csp_nonce": nonce, "dist_v": s.dist_v, "active": $active}),
            )
        }
    };
}

page!(index, "index.html", "search");
page!(stats, "stats.html", "stats");
page!(story, "story.html", "story");
page!(tools, "tools.html", "tools");
page!(extensions, "extensions.html", "extensions");
page!(diagnostics, "diagnostics.html", "diagnostics");
page!(update, "update.html", "diagnostics");
page!(headroom, "headroom.html", "headroom");
page!(inspect, "inspect.html", "inspect");
page!(report, "report.html", "report");
page!(scheduler, "scheduler.html", "scheduler");
page!(llm_router, "llm_router.html", "llm_router");
page!(mesh_inference, "mesh_inference.html", "mesh_inference");
page!(lan_cowork, "lan_cowork.html", "lan_cowork");
page!(scan_jobs, "scan_jobs.html", "scan_jobs");
page!(agent_journal, "agent_journal.html", "tools");
page!(agent_memory, "agent_memory.html", "agent_memory");
page!(nai_bridge, "nai_bridge.html", "nai_bridge");
page!(sd_webui, "sd_webui_bridge.html", "sd_webui");
page!(comfyui_bridge, "comfyui_bridge.html", "comfyui");
page!(help, "help.html", "help");
page!(hailo_genai, "hailo_genai/genai.html", "hailo_genai");
page!(hailo_genai_chat, "hailo_genai/chat.html", "hailo_genai");
page!(
    hailo_yolo,
    "hailo_yolo_detect/yolo_detect.html",
    "hailo_yolo"
);
page!(
    hailo_semantic,
    "hailo_semantic_search/semantic.html",
    "hailo_semantic"
);
page!(
    ext_annotations_notes,
    "annotations/notes.html",
    "annotations"
);
page!(
    ext_speech_to_text,
    "speech_to_text/s2t.html",
    "speech_to_text"
);
page!(
    ext_lora_dataset,
    "lora_dataset/lora_dataset.html",
    "lora_dataset"
);
page!(ext_prompt_library, "prompt_library.html", "prompt_library");
page!(ext_prompt_sim, "simulator.html", "prompt_sim");
page!(
    ext_prompt_sim_manager,
    "wildcard_manager.html",
    "prompt_sim"
);
page!(
    ext_prompt_sim_sweep,
    "sweep_axes_manager.html",
    "prompt_sim"
);
page!(ext_convert, "convert.html", "convert");
page!(ext_chatlog, "chatlog/chatlog.html", "chatlog");
page!(
    ext_cross_search,
    "cross_search/cross_search.html",
    "cross_search"
);
page!(ext_favorites, "favorites_manager.html", "favorites");
page!(
    ext_freeze_pullback,
    "freeze_pullback/freeze_pullback.html",
    "freeze_pullback"
);
page!(ext_md_viewer, "md_viewer/md_viewer.html", "md_viewer");
page!(ext_watcher, "watcher_status.html", "watcher");
page!(ext_github, "github.html", "github");
page!(ext_mcp_client, "mcp_client/mcp_client.html", "mcp_client");

pub async fn settings(
    State(s): State<SharedState>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
) -> Result<Html<String>, StatusCode> {
    let project_root = s.config.project_root.display().to_string();
    render(
        &s,
        "settings.html",
        json!({
            "csp_nonce": nonce,
            "dist_v": s.dist_v,
            "active": "settings",
            "project_root": project_root,
            "python_executable": "",
        }),
    )
}

pub async fn gateway(
    State(s): State<SharedState>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
) -> Result<Html<String>, StatusCode> {
    render(
        &s,
        "gateway.html",
        json!({
            "csp_nonce": nonce,
            "dist_v": s.dist_v,
            "active": "gateway",
            "version": s.version,
        }),
    )
}

pub async fn sweep_view(
    State(s): State<SharedState>,
    AxumPath(sweep_id): AxumPath<String>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
) -> Result<Html<String>, StatusCode> {
    render(
        &s,
        "sweep_view.html",
        json!({
            "csp_nonce": nonce,
            "dist_v": s.dist_v,
            "active": "sweep_view",
            "sweep_id": sweep_id,
        }),
    )
}

pub async fn search_redirect() -> Redirect {
    Redirect::permanent("/")
}

pub async fn lan_cowork_peers_redirect() -> Redirect {
    Redirect::permanent("/ext/lan_cowork/peers")
}

pub async fn scan_jobs_redirect() -> Redirect {
    Redirect::permanent("/scan-jobs")
}

pub async fn agent_journal_redirect() -> Redirect {
    Redirect::permanent("/agent-journal")
}

pub async fn llm_router_redirect() -> Redirect {
    Redirect::permanent("/llm-router")
}

pub async fn mesh_inference_redirect() -> Redirect {
    Redirect::permanent("/mesh-inference")
}

pub async fn lan_cowork_redirect() -> Redirect {
    Redirect::permanent("/lan-cowork")
}

pub async fn agent_memory_redirect() -> Redirect {
    Redirect::permanent("/agent-memory")
}

pub async fn crypto_tools_redirect() -> Redirect {
    Redirect::permanent("/crypto-tools")
}

pub async fn github_redirect() -> Redirect {
    Redirect::permanent("/ext/github")
}

/// GET /sw.js — serve Service Worker with `Service-Worker-Allowed: /` so the
/// SW can intercept requests outside `/static/` (thumbnails, previews, originals).
pub async fn serve_sw(State(s): State<SharedState>) -> Response {
    let path = s.config.project_root.join("ui/default/static/sw.js");
    match std::fs::read_to_string(&path) {
        Ok(body) => (
            StatusCode::OK,
            [
                (
                    header::CONTENT_TYPE,
                    HeaderValue::from_static("application/javascript"),
                ),
                (
                    header::HeaderName::from_static("service-worker-allowed"),
                    HeaderValue::from_static("/"),
                ),
            ],
            body,
        )
            .into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

pub async fn not_found(
    State(s): State<SharedState>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
    uri: Uri,
) -> Response {
    let path = uri.to_string();
    render(
        &s,
        "error.html",
        json!({
            "status_code": 404,
            "message": "Not Found",
            "qr_data": path,
            "qr_label": path,
            "csp_nonce": nonce,
            "dist_v": s.dist_v,
            "back_home": "ホームへ",
            "back_prev": "前のページへ",
            "bundle_json": null,
            "bundle_download_b64": null,
            "bundle_download_name": null,
            "copy_bundle_label": "",
            "download_bundle_label": "",
        }),
    )
    .map(|html| (StatusCode::NOT_FOUND, html).into_response())
    .unwrap_or_else(|_| StatusCode::NOT_FOUND.into_response())
}

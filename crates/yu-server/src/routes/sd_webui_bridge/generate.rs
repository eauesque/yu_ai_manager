use axum::{
    extract::{Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio_util::sync::CancellationToken;

use crate::state::SharedState;

use super::{
    api_err, api_ok, cfg_bool, cfg_i64, cfg_str, ext_config, sd_api_url, sd_get, SD_USER_AGENT,
};

// ---------------------------------------------------------------------------
// Origin check — loopback-only for generate endpoint
// ---------------------------------------------------------------------------

fn check_origin(headers: &HeaderMap) -> bool {
    let Some(origin) = headers.get("origin").and_then(|v| v.to_str().ok()) else {
        return true; // no Origin header = same-origin or non-browser
    };
    // Strip scheme then extract hostname (handles IPv4, IPv6 [::1], named hosts)
    let after_scheme = origin
        .trim_start_matches("https://")
        .trim_start_matches("http://");
    let host = if after_scheme.starts_with('[') {
        // IPv6 literal e.g. [::1] or [::1]:port
        after_scheme
            .trim_start_matches('[')
            .split(']')
            .next()
            .unwrap_or("")
    } else {
        // IPv4 or hostname, strip path/port
        after_scheme
            .split('/')
            .next()
            .unwrap_or("")
            .split(':')
            .next()
            .unwrap_or("")
    };
    matches!(host, "127.0.0.1" | "::1" | "localhost")
}

// ---------------------------------------------------------------------------
// Progress poller — runs as a background tokio task during generation
// ---------------------------------------------------------------------------

async fn run_progress_poller(
    client: reqwest::Client,
    api_url: String,
    job_id: String,
    jm: std::sync::Arc<crate::jobs::JobManager>,
    token: CancellationToken,
) {
    loop {
        tokio::select! {
            _ = token.cancelled() => break,
            _ = tokio::time::sleep(std::time::Duration::from_secs(1)) => {}
        }
        if token.is_cancelled() {
            break;
        }
        let resp = client
            .get(format!("{api_url}/sdapi/v1/progress"))
            .header("User-Agent", SD_USER_AGENT)
            .timeout(std::time::Duration::from_secs(5))
            .send()
            .await;
        if let Ok(r) = resp {
            if let Ok(data) = r.json::<Value>().await {
                let step = data
                    .get("state")
                    .and_then(|s| s.get("sampling_step"))
                    .and_then(Value::as_u64)
                    .unwrap_or(0);
                let total = data
                    .get("state")
                    .and_then(|s| s.get("sampling_steps"))
                    .and_then(Value::as_u64)
                    .unwrap_or(0);
                jm.update_progress(&job_id, step, total, None);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// SD generate (standard path — no Gradio, no sweep_meta)
// ---------------------------------------------------------------------------

async fn generate_standard(state: SharedState, body: Value) -> Response {
    let started_at = std::time::Instant::now();
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    let bridge_managed_save = cfg_bool(&cfg, "bridge_managed_save", false);
    let auto_import = cfg_bool(&cfg, "auto_import", true);
    let save_folder = cfg_str(&cfg, "save_folder", "").to_string();
    let image_format = cfg_str(&cfg, "image_format", "png").to_string();
    let save_naming = cfg_str(&cfg, "save_naming", "daily_folder").to_string();
    let max_batch = resolve_max_batch(&cfg);

    // Clamp batch_size
    let mut body = body;
    if let Some(bs) = body.get("batch_size").and_then(Value::as_u64) {
        if bs > max_batch {
            body["batch_size"] = json!(max_batch);
        }
    }

    if body
        .get("expand_wildcards")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        let seed = body.get("seed").and_then(Value::as_i64);
        // A negative seed is the "random" sentinel: None, never a wrapped value.
        let seed = seed.and_then(|value| u64::try_from(value).ok());
        let wildcards = crate::prompt_sim_core::bridge_wildcards(
            state.config.config_path.to_str().unwrap_or_default(),
            crate::routes::comfyui_bridge::simple_builder::client_wildcards(&body),
        );
        for key in ["prompt", "negative_prompt"] {
            if let Some(text) = body.get(key).and_then(Value::as_str) {
                body[key] = json!(crate::prompt_sim_core::expand_dynamic_prompt(
                    text, seed, &wildcards,
                ));
            }
        }
    }

    // Inject save_images=false when bridge handles saving
    if bridge_managed_save {
        body["save_images"] = json!(false);
        body["do_not_save_samples"] = json!(true);
    }

    // txt2img vs img2img
    let endpoint = if body.get("init_images").is_some() {
        "/sdapi/v1/img2img"
    } else {
        "/sdapi/v1/txt2img"
    };

    // Register job
    let job_id = uuid::Uuid::new_v4().to_string();
    let cancel_token = state.job_manager.start(&job_id, "SD generate");

    // Spawn progress poller
    let poller_token = cancel_token.clone();
    let poller_client = state.python_client.clone();
    let poller_jm = state.job_manager.clone();
    let poller_url = api_url.clone();
    let poller_job = job_id.clone();
    tokio::spawn(run_progress_poller(
        poller_client,
        poller_url,
        poller_job,
        poller_jm,
        poller_token,
    ));

    // POST to SD (300s timeout for generation)
    let sd_result = state
        .python_client
        .post(format!("{api_url}{endpoint}"))
        .header("User-Agent", SD_USER_AGENT)
        .timeout(std::time::Duration::from_secs(300))
        .json(&body)
        .send()
        .await;

    cancel_token.cancel(); // stop poller

    match sd_result {
        Err(e) => {
            state.job_manager.finish(&job_id, None, Some(e.to_string()));
            api_err(&format!("SD error: {e}"), StatusCode::BAD_GATEWAY)
        }
        Ok(resp) => {
            let status = resp.status();
            if !status.is_success() {
                let msg = format!("SD HTTP {status}");
                state.job_manager.finish(&job_id, None, Some(msg.clone()));
                return api_err(&msg, StatusCode::BAD_GATEWAY);
            }
            let raw: Value = match resp.json().await {
                Ok(v) => v,
                Err(e) => {
                    let msg = format!("SD parse error: {e}");
                    state.job_manager.finish(&job_id, None, Some(msg.clone()));
                    return api_err(&msg, StatusCode::BAD_GATEWAY);
                }
            };

            // Extract images with seeds
            // SD returns images[] (base64) and info (JSON-encoded string with seeds[])
            let images = raw
                .get("images")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let seeds: Vec<i64> = raw
                .get("info")
                .and_then(Value::as_str)
                .and_then(|s| serde_json::from_str::<Value>(s).ok())
                .and_then(|info| info.get("all_seeds").and_then(Value::as_array).cloned())
                .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
                .unwrap_or_default();

            let result_images: Vec<Value> = images
                .iter()
                .enumerate()
                .map(|(i, img)| {
                    json!({
                        "base64": img,
                        "seed": seeds.get(i).copied().unwrap_or(-1),
                    })
                })
                .collect();

            // Bridge-managed save to disk
            let (saved_paths, save_errors): (Vec<String>, Vec<String>) =
                if bridge_managed_save && !save_folder.is_empty() {
                    let items: Vec<(&str, i64)> = result_images
                        .iter()
                        .filter_map(|img| {
                            img.get("base64").and_then(Value::as_str).map(|b64| {
                                (b64, img.get("seed").and_then(Value::as_i64).unwrap_or(-1))
                            })
                        })
                        .collect();
                    crate::routes::bridge_save::save_images_to_disk(
                        &items,
                        &save_folder,
                        &image_format,
                        &save_naming,
                    )
                } else {
                    (vec![], vec![])
                };

            // Sweep XMP write + DB upsert (best-effort, PNG only)
            let sweep_meta_val = body.get("sweep_meta").cloned();
            if let Some(sv) = sweep_meta_val {
                if let Some(meta) = crate::routes::sweep_common::validate_sweep_meta(&sv) {
                    if !saved_paths.is_empty() {
                        crate::routes::sweep_common::write_sweep_xmp_to_paths(&saved_paths, &meta);
                        crate::routes::sweep_common::upsert_sweep_db(
                            &state.db,
                            &meta,
                            &saved_paths,
                        )
                        .await;
                    }
                }
            }
            let file_ids = if auto_import && !saved_paths.is_empty() {
                if body.get("sweep_meta").is_some() {
                    crate::routes::sweep_common::upsert_files_from_paths(&state, &saved_paths).await
                } else {
                    let state_for_import = state.clone();
                    let paths_for_import = saved_paths.clone();
                    tokio::spawn(async move {
                        let _ = crate::routes::sweep_common::upsert_files_from_paths(
                            &state_for_import,
                            &paths_for_import,
                        )
                        .await;
                    });
                    Default::default()
                }
            } else {
                Default::default()
            };

            let elapsed_ms = u64::try_from(started_at.elapsed().as_millis()).unwrap_or(u64::MAX);
            let expanded_prompt = body
                .get("prompt")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let final_negative = body
                .get("negative_prompt")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();

            let mut result = json!({
                "images": result_images,
                "task_id": job_id,
                "elapsed_ms": elapsed_ms,
                "expanded_prompt": expanded_prompt,
                "final_negative": final_negative,
                "image_format": image_format,
            });
            if !saved_paths.is_empty() {
                result["saved"] = json!(saved_paths);
                result["saved_paths"] = json!(saved_paths);
                result["saved_items"] = json!(
                    crate::routes::sweep_common::saved_items_from_file_ids(&saved_paths, &file_ids,)
                );
            }
            if !save_errors.is_empty() {
                result["errors"] = json!(save_errors);
            }
            state
                .job_manager
                .finish(&job_id, Some(result.clone()), None);
            api_ok(result).into_response()
        }
    }
}

// ---------------------------------------------------------------------------
// Public handlers
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
pub struct ProgressQuery {
    task_id: Option<String>,
}

/// The configured batch-size ceiling.
///
/// A negative `max_batch_size` used to reach `as u64` and wrap to ~1.8e19, so
/// the `bs > max_batch` clamp downstream never fired and ANY batch size was
/// accepted. Falling back to the default keeps the ceiling meaningful.
fn resolve_max_batch(cfg: &Value) -> u64 {
    u64::try_from(cfg_i64(cfg, "max_batch_size", 8)).unwrap_or(8)
}

pub async fn generate(
    State(state): State<SharedState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    if !check_origin(&headers) {
        return api_err("Origin not allowed", StatusCode::FORBIDDEN);
    }

    // Gradio 4 (Forge) → proxy to Python; sweep_meta is handled natively
    let api_type = body.get("api_type").and_then(Value::as_str).unwrap_or("");
    let is_gradio = api_type == "gradio" || api_type == "gradio4";

    if is_gradio {
        return super::gradio4::generate_gradio(state, body).await;
    }

    generate_standard(state, body).await
}

pub async fn progress(
    State(state): State<SharedState>,
    Query(q): Query<ProgressQuery>,
) -> Response {
    if let Some(task_id) = q.task_id {
        match state.job_manager.get_job(&task_id) {
            None => {
                return (
                    StatusCode::OK,
                    Json(json!({"ok": true, "error": null, "status": "pending", "progress": 0.0, "registered": false})),
                )
                    .into_response();
            }
            Some(job) => {
                let progress_f = job.percent.unwrap_or(0.0) / 100.0;
                let step = job.current.unwrap_or(0);
                let total = job.total.unwrap_or(0);
                return api_ok(json!({
                    "status": if job.running { "running" } else { "done" },
                    "progress": progress_f,
                    "step": step,
                    "total_steps": total,
                    "registered": true,
                    "error_message": job.error,
                }))
                .into_response();
            }
        }
    }

    // No task_id — poll SD directly
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);
    match sd_get(&state.python_client, &api_url, "/sdapi/v1/progress").await {
        Ok(data) => {
            let progress_f = data.get("progress").and_then(Value::as_f64).unwrap_or(0.0);
            let step = data
                .get("state")
                .and_then(|s| s.get("sampling_step"))
                .and_then(Value::as_i64)
                .unwrap_or(0);
            let total = data
                .get("state")
                .and_then(|s| s.get("sampling_steps"))
                .and_then(Value::as_i64)
                .unwrap_or(0);
            let eta = data
                .get("eta_relative")
                .and_then(Value::as_f64)
                .unwrap_or(0.0);
            api_ok(json!({
                "progress": progress_f,
                "step": step,
                "total_steps": total,
                "eta_relative": eta,
            }))
            .into_response()
        }
        Err(_) => api_ok(json!({
            "progress": 0.0,
            "step": 0,
            "total_steps": 0,
            "eta_relative": 0.0,
        }))
        .into_response(),
    }
}

pub async fn cancel(State(state): State<SharedState>, Json(body): Json<Value>) -> Response {
    let task_id = body.get("task_id").and_then(Value::as_str);
    let cfg = ext_config(&state);
    let api_url = sd_api_url(&cfg);

    if let Some(tid) = task_id {
        // Unknown task → 404 (matches Python)
        if state.job_manager.get_job(tid).is_none() {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"ok": false, "error": "task not found"})),
            )
                .into_response();
        }
        let cancelled = state.job_manager.cancel_job(tid);
        // Also interrupt SD regardless of whether job was still running
        let _ = state
            .python_client
            .post(format!("{api_url}/sdapi/v1/interrupt"))
            .header("User-Agent", SD_USER_AGENT)
            .timeout(std::time::Duration::from_secs(5))
            .send()
            .await;
        return api_ok(json!({"cancelled": cancelled})).into_response();
    }

    // No task_id — interrupt SD directly
    match state
        .python_client
        .post(format!("{api_url}/sdapi/v1/interrupt"))
        .header("User-Agent", SD_USER_AGENT)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(_) => api_ok(json!({"cancelled": true})).into_response(),
        Err(e) => api_err(&format!("SD interrupt error: {e}"), StatusCode::BAD_GATEWAY),
    }
}

#[cfg(test)]
mod max_batch_tests {
    use super::resolve_max_batch;
    use serde_json::json;

    #[test]
    fn a_negative_ceiling_falls_back_instead_of_wrapping() {
        let got = resolve_max_batch(&json!({"max_batch_size": -1}));
        assert_eq!(got, 8, "a negative ceiling must not become a huge one");
        assert!(got < 1_000, "the ceiling must stay a plausible batch size");
    }

    #[test]
    fn a_configured_ceiling_is_honoured() {
        assert_eq!(resolve_max_batch(&json!({"max_batch_size": 3})), 3);
    }

    #[test]
    fn an_absent_ceiling_uses_the_default() {
        assert_eq!(resolve_max_batch(&json!({})), 8);
    }
}

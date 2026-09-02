use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use base64::{engine::general_purpose::STANDARD as B64, Engine};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::state::SharedState;

use super::{
    api_err, api_ok, cfg_bool, cfg_i64, cfg_str, comfy_api_url, comfy_get, comfy_post, ext_config,
    get_api_key, COMFY_USER_AGENT,
};

// ---------------------------------------------------------------------------
// Seed extraction helpers
// ---------------------------------------------------------------------------

/// Extract the seed from a ComfyUI workflow JSON.
/// Checks KSampler.inputs.seed and RandomNoise.inputs.noise_seed.
fn extract_seed(workflow: &Value) -> i64 {
    let Some(nodes) = workflow.as_object() else {
        return -1;
    };
    for node in nodes.values() {
        let class = node.get("class_type").and_then(Value::as_str).unwrap_or("");
        let inputs = node.get("inputs").unwrap_or(&Value::Null);
        if class == "KSampler" || class == "KSamplerAdvanced" {
            if let Some(seed) = inputs.get("seed").and_then(Value::as_i64) {
                return seed;
            }
        }
        if class == "RandomNoise" {
            if let Some(seed) = inputs.get("noise_seed").and_then(Value::as_i64) {
                return seed;
            }
        }
    }
    -1
}

// ---------------------------------------------------------------------------
// Shared execution options
// ---------------------------------------------------------------------------

pub struct ExecuteOpts {
    pub seed: i64,
    pub job_label: String,
    pub image_format: String,
    pub bridge_managed_save: bool,
    pub save_folder: String,
    pub save_naming: String,
    pub gen_params: Option<Value>,
    pub expanded_prompt: Option<String>,
    pub final_negative: Option<String>,
    pub sweep_meta: Option<Value>,
}

// ---------------------------------------------------------------------------
// execute_workflow — shared engine for json and simple modes
// ---------------------------------------------------------------------------

fn extract_exec_error(entry: &Value) -> String {
    if let Some(msgs) = entry
        .get("status")
        .and_then(|s| s.get("messages"))
        .and_then(Value::as_array)
    {
        for msg in msgs {
            if let Some(arr) = msg.as_array() {
                if arr.first().and_then(Value::as_str) == Some("execution_error") {
                    if let Some(detail) = arr.get(1) {
                        return detail
                            .get("exception_message")
                            .and_then(Value::as_str)
                            .unwrap_or("unknown")
                            .chars()
                            .take(300)
                            .collect();
                    }
                }
            }
        }
    }
    "unknown execution error".into()
}

pub(super) async fn execute_workflow(
    state: SharedState,
    workflow: Value,
    opts: ExecuteOpts,
) -> Response {
    let started_at = std::time::Instant::now();
    let cfg = ext_config(&state);
    let auto_import = cfg_bool(&cfg, "auto_import", true);
    let api_url = comfy_api_url(&cfg);
    let api_key = get_api_key(&cfg, &state.config.project_root);

    let job_id = uuid::Uuid::new_v4().to_string();
    let cancel_token = state.job_manager.start(&job_id, &opts.job_label);

    // POST /prompt
    let prompt_payload = json!({"prompt": workflow, "client_id": &job_id});
    let prompt_resp = match comfy_post(
        &state.python_client,
        &api_url,
        "/prompt",
        &prompt_payload,
        &api_key,
    )
    .await
    {
        Ok(v) => v,
        Err(e) => {
            let msg = format!("ComfyUI /prompt error: {e}");
            state.job_manager.finish(&job_id, None, Some(msg.clone()));
            return api_err(&msg, StatusCode::BAD_GATEWAY);
        }
    };

    let prompt_id = match prompt_resp.get("prompt_id").and_then(Value::as_str) {
        Some(id) => id.to_string(),
        None => {
            let msg = "ComfyUI did not return prompt_id".to_string();
            state.job_manager.finish(&job_id, None, Some(msg.clone()));
            return api_err(&msg, StatusCode::BAD_GATEWAY);
        }
    };

    // Poll /history/{prompt_id} every 1.5s, up to 300s
    let poll_path = format!("/history/{prompt_id}");
    let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(300);
    let history: Value = loop {
        tokio::select! {
            _ = cancel_token.cancelled() => {
                let _ = comfy_post(
                    &state.python_client, &api_url, "/interrupt", &json!({}), &api_key,
                ).await;
                state.job_manager.finish(&job_id, None, Some("Cancelled".into()));
                return api_err("Cancelled", StatusCode::GONE);
            }
            _ = tokio::time::sleep(std::time::Duration::from_millis(1500)) => {}
        }

        if tokio::time::Instant::now() >= deadline {
            state
                .job_manager
                .finish(&job_id, None, Some("Timeout".into()));
            return api_err("ComfyUI generation timed out", StatusCode::GATEWAY_TIMEOUT);
        }

        match comfy_get(&state.python_client, &api_url, &poll_path, &api_key).await {
            Err(_) => continue,
            Ok(data) => {
                if let Some(entry) = data.get(&prompt_id) {
                    // Error detection: fail-fast on execution_error
                    let status_str = entry
                        .get("status")
                        .and_then(|s| s.get("status_str"))
                        .and_then(Value::as_str)
                        .unwrap_or("");
                    if status_str == "error" {
                        let hint = extract_exec_error(entry);
                        let msg = format!("ComfyUI execution error: {hint}");
                        state.job_manager.finish(&job_id, None, Some(msg.clone()));
                        return api_err(&msg, StatusCode::BAD_GATEWAY);
                    }

                    let completed = entry
                        .get("status")
                        .and_then(|s| s.get("completed"))
                        .and_then(Value::as_bool)
                        .unwrap_or(false);
                    if completed {
                        break entry.clone();
                    }

                    if let Some(msgs) = entry.get("status").and_then(|s| s.get("messages")) {
                        if let Some(arr) = msgs.as_array() {
                            let done = arr
                                .iter()
                                .filter(|m| {
                                    m.get(0).and_then(Value::as_str) == Some("execution_cached")
                                        || m.get(0).and_then(Value::as_str) == Some("executed")
                                })
                                .count() as u64;
                            let total = arr.len() as u64;
                            state
                                .job_manager
                                .update_progress(&job_id, done, total, None);
                        }
                    }
                }
            }
        }
    };

    // Collect image references
    let mut image_refs: Vec<Value> = Vec::new();
    if let Some(outputs) = history.get("outputs").and_then(Value::as_object) {
        for node_output in outputs.values() {
            if let Some(images) = node_output.get("images").and_then(Value::as_array) {
                for img in images {
                    image_refs.push(img.clone());
                }
            }
        }
    }
    if image_refs.is_empty() {
        let msg = "ComfyUI returned no output images".to_string();
        state.job_manager.finish(&job_id, None, Some(msg.clone()));
        return api_err(&msg, StatusCode::BAD_GATEWAY);
    }

    // Fetch images → base64
    let mut result_images: Vec<Value> = Vec::new();
    let mut fetch_errors: Vec<String> = Vec::new();
    for img_ref in &image_refs {
        let filename = img_ref
            .get("filename")
            .and_then(Value::as_str)
            .unwrap_or("");
        let subfolder = img_ref
            .get("subfolder")
            .and_then(Value::as_str)
            .unwrap_or("");
        let img_type = img_ref
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or("output");
        let view_path = format!(
            "/view?filename={}&subfolder={}&type={}",
            urlencoding::encode(filename),
            urlencoding::encode(subfolder),
            urlencoding::encode(img_type),
        );
        let mut req = state
            .python_client
            .get(format!("{api_url}{view_path}"))
            .header("User-Agent", COMFY_USER_AGENT)
            .timeout(std::time::Duration::from_secs(60));
        if !api_key.is_empty() {
            req = req.bearer_auth(&api_key);
        }
        let img_bytes = match req.send().await {
            Err(e) => {
                fetch_errors.push(format!("{filename}: {e}"));
                continue;
            }
            Ok(r) => {
                if !r.status().is_success() {
                    fetch_errors.push(format!("{filename}: HTTP {}", r.status()));
                    continue;
                }
                r.bytes().await.unwrap_or_default()
            }
        };
        if img_bytes.is_empty() {
            fetch_errors.push(format!("{filename}: empty response"));
            continue;
        }
        result_images.push(json!({
            "base64": B64.encode(&img_bytes),
            "filename": filename,
            "seed": opts.seed,
        }));
    }
    if result_images.is_empty() {
        let msg = format!("Failed to fetch images from ComfyUI: {:?}", fetch_errors);
        state.job_manager.finish(&job_id, None, Some(msg.clone()));
        return api_err(&msg, StatusCode::BAD_GATEWAY);
    }

    // Bridge-managed save
    let (saved_paths, save_errors): (Vec<String>, Vec<String>) =
        if opts.bridge_managed_save && !opts.save_folder.is_empty() {
            let items: Vec<(&str, i64)> = result_images
                .iter()
                .filter_map(|img| {
                    img.get("base64")
                        .and_then(Value::as_str)
                        .map(|b| (b, opts.seed))
                })
                .collect();
            crate::routes::bridge_save::save_images_to_disk(
                &items,
                &opts.save_folder,
                &opts.image_format,
                &opts.save_naming,
            )
        } else {
            (vec![], vec![])
        };

    // Sweep XMP + DB
    if let Some(sv) = &opts.sweep_meta {
        if let Some(meta) = crate::routes::sweep_common::validate_sweep_meta(sv) {
            if !saved_paths.is_empty() {
                crate::routes::sweep_common::write_sweep_xmp_to_paths(&saved_paths, &meta);
                crate::routes::sweep_common::upsert_sweep_db(&state.db, &meta, &saved_paths).await;
            }
        }
    }
    let file_ids = if auto_import && !saved_paths.is_empty() {
        if opts.sweep_meta.is_some() {
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

    let count = result_images.len();
    let mut result = json!({
        "images": result_images,
        "task_id": job_id,
        "prompt_id": prompt_id,
        "count": count,
        "elapsed_ms": u64::try_from(started_at.elapsed().as_millis()).unwrap_or(u64::MAX),
        "image_format": opts.image_format,
    });
    if let Some(gp) = opts.gen_params {
        result["_gen_params"] = gp;
    }
    if let Some(prompt) = opts.expanded_prompt {
        result["expanded_prompt"] = json!(prompt);
    }
    if let Some(negative) = opts.final_negative {
        result["final_negative"] = json!(negative);
    }
    if opts.bridge_managed_save {
        result["bridge_managed_save"] = json!(true);
        result["bridge_managed_save_fallback"] = json!(true);
    }
    if !saved_paths.is_empty() {
        result["saved"] = json!(saved_paths);
        result["saved_paths"] = json!(saved_paths);
        result["saved_items"] = json!(crate::routes::sweep_common::saved_items_from_file_ids(
            &saved_paths,
            &file_ids,
        ));
    }
    let mut all_errors = fetch_errors;
    all_errors.extend(save_errors);
    if !all_errors.is_empty() {
        result["errors"] = json!(all_errors);
    }
    state
        .job_manager
        .finish(&job_id, Some(result.clone()), None);
    api_ok(result).into_response()
}

// ---------------------------------------------------------------------------
// JSON mode wrapper
// ---------------------------------------------------------------------------

async fn run_generate_json(state: SharedState, body: Value) -> Response {
    let cfg = ext_config(&state);
    let image_format = cfg_str(&cfg, "image_format", "png").to_string();
    let bridge_managed_save = cfg_bool(&cfg, "bridge_managed_save", false);
    let save_folder = cfg_str(&cfg, "save_folder", "").to_string();
    let save_naming = cfg_str(&cfg, "save_naming", "daily_folder").to_string();

    let workflow = match body.get("workflow").cloned() {
        Some(v) => v,
        None => return api_err("Missing 'workflow' field", StatusCode::UNPROCESSABLE_ENTITY),
    };
    let seed = extract_seed(&workflow);
    let sweep_meta = body.get("sweep_meta").cloned();

    let opts = ExecuteOpts {
        seed,
        job_label: "ComfyUI generate".into(),
        image_format,
        bridge_managed_save,
        save_folder,
        save_naming,
        gen_params: None,
        expanded_prompt: None,
        final_negative: None,
        sweep_meta,
    };
    execute_workflow(state, workflow, opts).await
}

// ---------------------------------------------------------------------------
// Simple mode handler
// ---------------------------------------------------------------------------

async fn run_generate_simple(state: SharedState, body: Value) -> Response {
    use super::simple_builder::{
        build_gen_params, build_workflow, check_bnk_node, detect_te_kind, extract_lora_tokens,
        infer_unet_components, parse_params, resolve_sweep_xmp_target, TeKind,
    };

    let cfg = ext_config(&state);
    let max_batch = cfg_i64(&cfg, "max_batch_size", 8);
    let bridge_managed_save = cfg_bool(&cfg, "bridge_managed_save", false);
    let save_folder = cfg_str(&cfg, "save_folder", "").to_string();
    let image_format = cfg_str(&cfg, "image_format", "png").to_string();
    let save_naming = cfg_str(&cfg, "save_naming", "daily_folder").to_string();
    let auto_save = cfg_bool(&cfg, "auto_save", false);
    let auto_import = cfg_bool(&cfg, "auto_import", true);

    // Sweep XMP target guard
    let sweep_meta = body.get("sweep_meta").cloned();
    if sweep_meta.is_some() && bridge_managed_save {
        let xmp_target = resolve_sweep_xmp_target(&cfg);
        if xmp_target.is_empty() {
            return api_err(
                "Sweep XMP 埋め込みが ON ですが埋め込み先パス (ComfyUI output) が未設定です",
                StatusCode::BAD_REQUEST,
            );
        }
    }

    // Parse + validate
    let config_path = state.config.config_path.to_str().unwrap_or_default();
    let mut params = match parse_params(&body, max_batch, sweep_meta.clone(), config_path) {
        Ok(p) => p,
        Err(resp) => return resp,
    };

    if params.ckpt_name.is_empty() && params.diffusion_model.is_empty() {
        return api_err(
            "ckpt_name または diffusion_model が必須です",
            StatusCode::BAD_REQUEST,
        );
    }

    // separate-load: infer missing vae/te FIRST, then detect te_kind from filled values
    if !params.diffusion_model.is_empty() {
        if let Err(resp) = infer_unet_components(&mut params, &state).await {
            return resp;
        }
        params.te_kind = detect_te_kind(&params.text_encoder_1);
    } else {
        params.te_kind = detect_te_kind(&params.ckpt_name);
    }

    // BNK check: only when a1111_mode=true AND te_kind==Clip
    if params.a1111_mode && params.te_kind == TeKind::Clip && !check_bnk_node(&state).await {
        return api_err(
                "AUTOMATIC1111 互換モードには ComfyUI カスタムノード \
                 'ComfyUI_ADV_CLIP_emb' が必要です。インストールするか、互換モードを OFF にしてください。",
                StatusCode::BAD_REQUEST,
            );
    }

    // Extract LoRA tokens from prompt
    let (cleaned_prompt, extracted_loras) = extract_lora_tokens(&params.prompt);
    params.prompt = cleaned_prompt;
    params.loras.extend(extracted_loras);

    // Resolve seed now so gen_params and workflow share the same value
    if params.seed < 0 {
        params.seed = rand::random::<u32>() as i64;
    }

    // use_save_node: true → SaveImage, false → PreviewImage
    let use_save_node = auto_save && !save_folder.is_empty() && !params.skip_save;

    let loras = params.loras.clone();
    let workflow = build_workflow(&params, &loras, use_save_node);
    let gen_params = build_gen_params(&params, params.seed);

    let opts = ExecuteOpts {
        seed: params.seed,
        job_label: "ComfyUI simple generate".into(),
        image_format,
        bridge_managed_save,
        save_folder,
        save_naming,
        gen_params: Some(gen_params),
        expanded_prompt: Some(params.prompt.clone()),
        final_negative: Some(params.negative_prompt.clone()),
        sweep_meta,
    };
    execute_workflow(state, workflow, opts).await
}

// ---------------------------------------------------------------------------
// Public handlers
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
pub struct ProgressQuery {
    task_id: Option<String>,
}

pub async fn generate(State(state): State<SharedState>, Json(body): Json<Value>) -> Response {
    // Default mode is "simple" (matches Python comfyui_api.py:168)
    let mode = body.get("mode").and_then(Value::as_str).unwrap_or("simple");
    match mode {
        "json" => run_generate_json(state, body).await,
        "simple" => run_generate_simple(state, body).await,
        other => api_err(
            &format!("Unknown mode '{other}'. Use 'simple' or 'json'."),
            StatusCode::BAD_REQUEST,
        ),
    }
}

pub async fn progress(
    State(state): State<SharedState>,
    Query(q): Query<ProgressQuery>,
) -> Response {
    if let Some(task_id) = q.task_id {
        return match state.job_manager.get_job(&task_id) {
            None => api_ok(json!({
                "status": "pending", "progress": 0.0,
                "step": 0, "total_steps": 0, "registered": false,
            }))
            .into_response(),
            Some(job) => api_ok(json!({
                "status": if job.running { "running" } else { "done" },
                "progress": job.percent.unwrap_or(0.0) / 100.0,
                "step": job.current.unwrap_or(0),
                "total_steps": job.total.unwrap_or(0),
                "registered": true,
                "error_message": job.error,
            }))
            .into_response(),
        };
    }
    api_ok(json!({"status": "idle", "progress": 0.0, "step": 0, "total_steps": 0})).into_response()
}

pub async fn cancel(State(state): State<SharedState>, Json(body): Json<Value>) -> Response {
    let cfg = ext_config(&state);
    let api_url = comfy_api_url(&cfg);
    let api_key = get_api_key(&cfg, &state.config.project_root);

    if let Some(tid) = body.get("task_id").and_then(Value::as_str) {
        if state.job_manager.get_job(tid).is_none() {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"ok": false, "error": "task not found"})),
            )
                .into_response();
        }
        let cancelled = state.job_manager.cancel_job(tid);
        let _ = comfy_post(
            &state.python_client,
            &api_url,
            "/interrupt",
            &json!({}),
            &api_key,
        )
        .await;
        return api_ok(json!({"cancelled": cancelled})).into_response();
    }

    match comfy_post(
        &state.python_client,
        &api_url,
        "/interrupt",
        &json!({}),
        &api_key,
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

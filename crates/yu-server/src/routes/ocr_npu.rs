//! `GET /api/ocr/npu` — NPU availability and recommended settings.
//!
//! Port of `core/ocr_api/media_ops.py::api_ocr_npu`, which delegates to
//! `extensions/builtin_ocr/core_impl/npu_offload.py`.
//!
//! **What this measures differs from Python on purpose.** Python's
//! `hailo_available` is `from hailo_platform import VDevice` succeeding — i.e.
//! whether a *Python package* is installed, not whether hardware is present;
//! its docstring says "hardware + runtime" but the code never looks at a
//! device. This server has no Python interpreter to ask, and reproducing an
//! import check would be meaningless here, so it reports the device node
//! instead — the thing it can actually observe, and the stronger claim.
//!
//! `ryzen_available` is reported as `false` unconditionally. That is a
//! measured limitation, not an assumption: Python detects Ryzen AI by asking
//! `onnxruntime` for its execution providers, and this workspace has no
//! `onnxruntime` / `ort` dependency at all (grepped across `crates/Cargo.toml`
//! and every member manifest: zero hits). Nor has Ryzen AI been exercised on
//! this development host, which is Linux/WSL2. Adding `ort` purely to answer
//! this one field would pull a large native runtime into every build.

use axum::{
    extract::{Query, State},
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::config_io::load as load_config_json;
use crate::state::SharedState;

#[derive(Deserialize)]
pub struct NpuQuery {
    task: Option<String>,
}

/// Device-node names Hailo exposes; shared with the analysis routes so the two
/// cannot disagree about whether the accelerator is present.
fn hailo_available() -> bool {
    crate::routes::analysis::is_hailo_device_available()
}

/// The `npu` half of the response.
///
/// Field names are Python's. `any_npu_available` is derived rather than stored
/// so it cannot drift from the two flags it summarises.
fn npu_status(hailo: bool) -> Value {
    let preferred = if hailo { "hailo" } else { "cpu" };
    json!({
        "hailo_available": hailo,
        // Python reports the model name and leaves the driver version empty.
        "hailo_device": if hailo { "Hailo-10H" } else { "" },
        "hailo_driver_version": "",
        "ryzen_available": false,
        "ryzen_npu_name": "",
        "preferred_backend": preferred,
        "any_npu_available": hailo,
    })
}

/// Id of an enabled `hailo_vlm` server, if one is registered.
///
/// Python walks the server registry; the registry is just `ai_servers` in the
/// config, so this reads it directly rather than plumbing a private helper.
fn npu_ocr_server_id(config: &Value) -> Option<String> {
    config
        .get("ai_servers")
        .and_then(Value::as_array)?
        .iter()
        .find(|server| {
            server
                .get("enabled")
                .and_then(Value::as_bool)
                .unwrap_or(true)
                && server.get("type").and_then(Value::as_str) == Some("hailo_vlm")
        })
        .and_then(|server| server.get("id").and_then(Value::as_str))
        .map(str::to_string)
}

/// The `optimization` half. Strings are Python's, verbatim — they are what the
/// tools page renders, so paraphrasing them is a user-visible change.
fn suggest(hailo: bool, task: &str, config: &Value) -> Value {
    if !hailo {
        return json!({
            "available": false,
            "message": "NPU が検出されませんでした",
            "recommendations": [
                "Hailo-10H: M.2 スロットに装着し hailort ドライバをインストール",
                "Ryzen AI: AMD NPU ドライバと ONNX Runtime Vitis AI EP をインストール",
            ],
        });
    }
    let recommendation = match npu_ocr_server_id(config) {
        Some(id) => format!(
            "Hailo VLM サーバー '{id}' が利用可能です。 server_id='{id}' を指定して OCR を実行できます。"
        ),
        None => "Hailo デバイスは検出されましたが、サーバーレジストリに hailo_vlm タイプのサーバーが登録されていません。 AI Settings で hailo_vlm サーバーを追加してください。".to_string(),
    };
    json!({
        "available": true,
        "status": npu_status(hailo),
        "task": task,
        "recommendations": [recommendation],
    })
}

pub async fn ocr_npu(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Query(params): Query<NpuQuery>,
) -> Response {
    if let Some(response) =
        require_admin_scope(s.config.pin_auth_enabled, auth.as_ref().map(|e| &e.0))
    {
        return response;
    }
    let task = params.task.unwrap_or_else(|| "ocr".to_string());
    // Read config from disk: a server added through the settings page must be
    // visible here without a restart.
    let config = load_config_json(&s.config.config_path);
    let hailo = hailo_available();
    Json(json!({
        "ok": true,
        "error": null,
        "data": null,
        "npu": npu_status(hailo),
        "optimization": suggest(hailo, &task, &config),
    }))
    .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_preferred_backend_falls_back_to_cpu_without_an_accelerator() {
        assert_eq!(npu_status(false)["preferred_backend"], "cpu");
        assert_eq!(npu_status(true)["preferred_backend"], "hailo");
    }

    #[test]
    fn any_npu_available_tracks_the_individual_flags() {
        // Derived, not stored: hard-coding it is how the summary field ends up
        // disagreeing with the flags it summarises.
        assert_eq!(npu_status(false)["any_npu_available"], false);
        assert_eq!(npu_status(true)["any_npu_available"], true);
    }

    #[test]
    fn the_device_name_is_only_reported_when_a_device_is_present() {
        assert_eq!(npu_status(true)["hailo_device"], "Hailo-10H");
        assert_eq!(npu_status(false)["hailo_device"], "");
        // Python leaves the driver version empty in both cases; inventing one
        // would be a fabricated reading.
        assert_eq!(npu_status(true)["hailo_driver_version"], "");
    }

    #[test]
    fn ryzen_is_reported_absent_because_this_build_cannot_detect_it() {
        // Pins the documented limitation. If someone later adds `ort` and wires
        // real detection, this test is where they will notice the constant.
        assert_eq!(npu_status(true)["ryzen_available"], false);
        assert_eq!(npu_status(true)["ryzen_npu_name"], "");
    }

    #[test]
    fn the_absent_npu_message_matches_python_verbatim() {
        let value = suggest(false, "ocr", &json!({}));
        assert_eq!(value["available"], false);
        assert_eq!(value["message"], "NPU が検出されませんでした");
        assert_eq!(
            value["recommendations"][0],
            "Hailo-10H: M.2 スロットに装着し hailort ドライバをインストール"
        );
        assert_eq!(
            value["recommendations"][1],
            "Ryzen AI: AMD NPU ドライバと ONNX Runtime Vitis AI EP をインストール"
        );
    }

    #[test]
    fn a_registered_vlm_server_is_named_in_the_recommendation() {
        let config = json!({"ai_servers": [
            {"id": "vlm-1", "type": "hailo_vlm", "enabled": true}
        ]});
        let value = suggest(true, "ocr", &config);
        let text = value["recommendations"][0].as_str().unwrap();
        assert!(text.contains("'vlm-1'"), "{text}");
        assert!(text.contains("server_id='vlm-1'"), "{text}");
    }

    #[test]
    fn a_disabled_vlm_server_does_not_count_as_registered() {
        // Naming a server the user switched off would send them to a dead id.
        let config = json!({"ai_servers": [
            {"id": "vlm-1", "type": "hailo_vlm", "enabled": false}
        ]});
        let text = suggest(true, "ocr", &config)["recommendations"][0]
            .as_str()
            .unwrap()
            .to_string();
        assert!(text.contains("登録されていません"), "{text}");
    }

    #[test]
    fn a_server_of_another_type_does_not_count() {
        let config = json!({"ai_servers": [
            {"id": "ollama-1", "type": "ollama", "enabled": true}
        ]});
        let text = suggest(true, "ocr", &config)["recommendations"][0]
            .as_str()
            .unwrap()
            .to_string();
        assert!(text.contains("登録されていません"), "{text}");
    }

    #[test]
    fn the_task_is_echoed_back() {
        assert_eq!(suggest(true, "caption", &json!({}))["task"], "caption");
    }
}

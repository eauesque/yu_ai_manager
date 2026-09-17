#![allow(clippy::result_large_err)]
//! Agent governance: Tool Classification (Phase D-1).
//!
//! Native port of Python `GET /api/agent/tool-levels`
//! (`routes/agent_governance_scope.py`) backed by
//! `core/agent_safety/tool_classification.py`.
//!
//! Pure, deterministic: a static classification table + prefix rules + optional
//! config.json overrides. No volatile IDs, no in-memory singleton, no DB — so it
//! reaches live-oracle parity with zero parity-mechanism changes. Config
//! overrides are read from `state.config.app_config` (the same config.json Python
//! loads), keeping both sides identical in the parity environment.
//!
//! Scope / auto-approve endpoints (the rest of agent_governance_scope.py) are
//! intentionally NOT ported here yet — see Phase D-2.

use std::collections::{BTreeMap, HashMap};

use axum::{
    extract::{Extension, Query, State},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

// Safety levels: 0=auto (read), 1=notify (write), 2=approve (destructive).
const LEVEL_AUTO: u8 = 0;
const LEVEL_NOTIFY: u8 = 1;
const LEVEL_APPROVE: u8 = 2;

/// Explicit per-tool classification — mirrors Python `_EXPLICIT_LEVELS` exactly.
const EXPLICIT_LEVELS: &[(&str, u8)] = &[
    // Level 2: approve
    ("add_scan_root", LEVEL_APPROVE),
    ("remove_scan_root", LEVEL_APPROVE),
    ("toggle_scan_root", LEVEL_APPROVE),
    ("set_extension_config", LEVEL_APPROVE),
    ("toggle_extension", LEVEL_APPROVE),
    ("create_backup", LEVEL_APPROVE),
    ("restore_backup", LEVEL_APPROVE),
    ("agent_kill", LEVEL_APPROVE),
    ("agent_resume", LEVEL_APPROVE),
    ("archive_cleanup_execute", LEVEL_APPROVE),
    ("shutdown_server", LEVEL_APPROVE),
    ("clear_scan_history", LEVEL_APPROVE),
    ("secrets_rotate", LEVEL_APPROVE),
    // Level 1: notify
    ("llm_backend_disable", LEVEL_NOTIFY),
    ("llm_backend_enable", LEVEL_NOTIFY),
    ("agent_audit_acknowledge", LEVEL_NOTIFY),
    ("rate_images", LEVEL_NOTIFY),
    ("set_tags", LEVEL_NOTIFY),
    ("split_tags", LEVEL_NOTIFY),
    ("set_annotations", LEVEL_NOTIFY),
    ("add_to_collection", LEVEL_NOTIFY),
    ("remove_from_collection", LEVEL_NOTIFY),
    ("create_collection", LEVEL_NOTIFY),
    ("create_prompt", LEVEL_NOTIFY),
    ("update_prompt", LEVEL_NOTIFY),
    ("trigger_scan", LEVEL_NOTIFY),
    ("scan_directory", LEVEL_NOTIFY),
    ("wd_tagger_tag_file", LEVEL_NOTIFY),
    ("wd_tagger_batch", LEVEL_NOTIFY),
    ("wd_tagger_delete_tags", LEVEL_NOTIFY),
    ("wd_tagger_delete_tags_batch", LEVEL_NOTIFY),
    ("wd_tagger_delete_profile", LEVEL_NOTIFY),
    ("wd_tagger_create_profile", LEVEL_NOTIFY),
    ("wd_tagger_update_profile", LEVEL_NOTIFY),
    ("wd_tagger_set_active_model", LEVEL_NOTIFY),
    ("start_lora_training", LEVEL_NOTIFY),
    ("export_lora_dataset", LEVEL_NOTIFY),
    ("preview_lora_train_command", LEVEL_AUTO),
    ("analyze_image", LEVEL_NOTIFY),
    ("analyze_batch", LEVEL_NOTIFY),
    ("compute_hashes", LEVEL_NOTIFY),
    ("semantic_index_start", LEVEL_NOTIFY),
    ("semantic_index_stop", LEVEL_NOTIFY),
    ("import_chat_log", LEVEL_NOTIFY),
    ("reprocess_chat_logs", LEVEL_NOTIFY),
    ("set_md_scan_roots", LEVEL_NOTIFY),
    ("batch_download_zip", LEVEL_NOTIFY),
    ("generate_freeze_pullback", LEVEL_NOTIFY),
    // Level 0: auto (explicit overrides)
    ("agent_budget_reset", LEVEL_AUTO),
    ("agent_circuit_breaker_reset", LEVEL_AUTO),
    // Pre-existing tools missing explicit classification — Level 2
    ("secrets_export", LEVEL_APPROVE),
    ("secrets_import", LEVEL_APPROVE),
    ("migrate_secrets_to_keychain", LEVEL_APPROVE),
    ("agent_undo", LEVEL_APPROVE),
    // Pre-existing tools missing explicit classification — Level 1
    ("agent_anomaly_reset", LEVEL_NOTIFY),
];

/// Prefixes classified as auto — mirrors Python `_AUTO_PREFIXES`.
const AUTO_PREFIXES: &[&str] = &[
    "get_",
    "list_",
    "search_",
    "find_",
    "debug_",
    "text_search",
    "semantic_search",
    "semantic_backend_info",
    "semantic_index_status",
    "wd_tagger_model_status",
    "wd_tagger_stats",
    "wd_tagger_get_",
    "wd_tagger_untagged",
    "wd_tagger_vlm_models",
    "get_analysis_config",
    "get_analysis_result",
    "get_analysis_stats",
    "agent_status",
    "agent_journal",
    "agent_circuit_breaker_status",
    "agent_budget_status",
];

/// Prefixes classified as approve — mirrors Python `_APPROVE_PREFIXES`.
const APPROVE_PREFIXES: &[&str] = &[
    "delete_",
    "remove_",
    "archive_cleanup_execute",
    "uninstall_",
    "restore_backup",
    "share_to_",
    "install_",
];

/// Write prefixes defaulting to notify — mirrors Python `_notify_prefixes`.
const NOTIFY_PREFIXES: &[&str] = &[
    "set_", "add_", "create_", "update_", "rate_", "trigger_", "scan_", "import_", "compute_",
    "switch_", "toggle_",
];

fn level_name(level: u8) -> &'static str {
    match level {
        LEVEL_NOTIFY => "notify",
        LEVEL_APPROVE => "approve",
        _ => "auto",
    }
}

fn name_to_level(name: &str) -> Option<u8> {
    match name {
        "auto" => Some(LEVEL_AUTO),
        "notify" => Some(LEVEL_NOTIFY),
        "approve" => Some(LEVEL_APPROVE),
        _ => None,
    }
}

fn explicit_level(tool: &str) -> Option<u8> {
    EXPLICIT_LEVELS
        .iter()
        .find(|(name, _)| *name == tool)
        .map(|(_, level)| *level)
}

/// Read config.json overrides — mirrors Python `configure`:
/// `config["agent_safety"]["tool_safety_levels"]["overrides"]` of `{tool: name}`.
fn load_overrides(app_config: &Value) -> BTreeMap<String, u8> {
    let mut out = BTreeMap::new();
    let table = app_config
        .get("agent_safety")
        .and_then(|v| v.get("tool_safety_levels"))
        .and_then(|v| v.get("overrides"))
        .and_then(Value::as_object);
    if let Some(map) = table {
        for (tool, level_name_value) in map {
            if let Some(level) = level_name_value.as_str().and_then(name_to_level) {
                out.insert(tool.clone(), level);
            }
        }
    }
    out
}

/// Classify a tool — mirrors Python `classify` priority:
/// config override > explicit > auto-prefix > approve-prefix > `_bridge_` > notify-prefix > auto.
fn classify(tool: &str, overrides: &BTreeMap<String, u8>) -> u8 {
    if let Some(&level) = overrides.get(tool) {
        return level;
    }
    if let Some(level) = explicit_level(tool) {
        return level;
    }
    if AUTO_PREFIXES.iter().any(|p| tool.starts_with(p)) {
        return LEVEL_AUTO;
    }
    if APPROVE_PREFIXES.iter().any(|p| tool.starts_with(p)) {
        return LEVEL_APPROVE;
    }
    if tool.contains("_bridge_") {
        return LEVEL_APPROVE;
    }
    if NOTIFY_PREFIXES.iter().any(|p| tool.starts_with(p)) {
        return LEVEL_NOTIFY;
    }
    LEVEL_AUTO
}

fn classify_name(tool: &str, overrides: &BTreeMap<String, u8>) -> &'static str {
    level_name(classify(tool, overrides))
}

/// Summary of explicitly classified tools — mirrors Python `get_classification_summary`.
/// Note the Python quirk replicated here: a tool whose override level differs from
/// its explicit level appears in BOTH lists (explicit loop + override loop).
fn classification_summary(overrides: &BTreeMap<String, u8>) -> Value {
    let mut auto: Vec<String> = Vec::new();
    let mut notify: Vec<String> = Vec::new();
    let mut approve: Vec<String> = Vec::new();

    for (tool, level) in EXPLICIT_LEVELS {
        match *level {
            LEVEL_NOTIFY => notify.push((*tool).to_string()),
            LEVEL_APPROVE => approve.push((*tool).to_string()),
            _ => auto.push((*tool).to_string()),
        }
    }
    for (tool, level) in overrides {
        let list = match *level {
            LEVEL_NOTIFY => &mut notify,
            LEVEL_APPROVE => &mut approve,
            _ => &mut auto,
        };
        if !list.iter().any(|t| t == tool) {
            list.push(tool.clone());
        }
    }
    auto.sort();
    notify.sort();
    approve.sort();
    json!({"auto": auto, "notify": notify, "approve": approve})
}

/// Config overrides as `{tool: level_name}` — mirrors Python `get_all_overrides`.
fn all_overrides(overrides: &BTreeMap<String, u8>) -> Value {
    let map: serde_json::Map<String, Value> = overrides
        .iter()
        .map(|(tool, level)| (tool.clone(), json!(level_name(*level))))
        .collect();
    Value::Object(map)
}

/// GET /api/agent/tool-levels — tool classification info.
pub async fn tool_levels(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let overrides = load_overrides(&state.config.app_config);

    // Python: `if tool_name:` — empty or absent query param falls to summary mode.
    if let Some(tool) = params.get("tool").filter(|s| !s.is_empty()) {
        return api_result(json!({"tool": tool, "level": classify_name(tool, &overrides)}));
    }
    api_result(json!({
        "summary": classification_summary(&overrides),
        "overrides": all_overrides(&overrides),
    }))
}

/// Mirror Python `api_result`: merge payload at top level, ensure ok/error/data.
fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return Json(json!({"ok": true, "error": null, "data": other})).into_response();
        }
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn no_overrides() -> BTreeMap<String, u8> {
        BTreeMap::new()
    }

    #[test]
    fn explicit_classification_wins_over_prefix() {
        let o = no_overrides();
        // "agent_kill" is explicit approve, though no prefix would match it.
        assert_eq!(classify_name("agent_kill", &o), "approve");
        // "agent_budget_reset" is explicit auto (overrides the write-ish name).
        assert_eq!(classify_name("agent_budget_reset", &o), "auto");
    }

    #[test]
    fn prefix_rules_apply_when_not_explicit() {
        let o = no_overrides();
        assert_eq!(classify_name("get_files", &o), "auto"); // _AUTO_PREFIXES
        assert_eq!(classify_name("delete_thing", &o), "approve"); // _APPROVE_PREFIXES
        assert_eq!(classify_name("set_whatever", &o), "notify"); // _notify_prefixes
        assert_eq!(classify_name("totally_unknown", &o), "auto"); // default
    }

    #[test]
    fn bridge_tools_require_approval() {
        let o = no_overrides();
        assert_eq!(classify_name("comfyui_bridge_generate", &o), "approve");
    }

    #[test]
    fn config_override_wins_over_everything() {
        let mut o = no_overrides();
        // Override agent_kill (explicit approve) down to auto.
        o.insert("agent_kill".to_string(), LEVEL_AUTO);
        assert_eq!(classify_name("agent_kill", &o), "auto");
    }

    #[test]
    fn load_overrides_parses_config_shape() {
        let cfg = json!({
            "agent_safety": {"tool_safety_levels": {"overrides": {
                "foo_tool": "approve",
                "bar_tool": "notify",
                "bad_tool": "nonsense"
            }}}
        });
        let o = load_overrides(&cfg);
        assert_eq!(o.get("foo_tool"), Some(&LEVEL_APPROVE));
        assert_eq!(o.get("bar_tool"), Some(&LEVEL_NOTIFY));
        assert!(!o.contains_key("bad_tool")); // invalid level name ignored
    }

    #[test]
    fn summary_buckets_and_sorts() {
        let o = no_overrides();
        let summary = classification_summary(&o);
        let approve = summary["approve"].as_array().unwrap();
        let auto = summary["auto"].as_array().unwrap();
        // Known members land in the right buckets.
        assert!(approve.iter().any(|v| v == "agent_kill"));
        assert!(auto.iter().any(|v| v == "agent_budget_reset"));
        // Lists are sorted.
        let approve_strs: Vec<&str> = approve.iter().map(|v| v.as_str().unwrap()).collect();
        let mut sorted = approve_strs.clone();
        sorted.sort_unstable();
        assert_eq!(approve_strs, sorted);
    }

    #[test]
    fn summary_includes_override_only_tool() {
        let mut o = no_overrides();
        o.insert("custom_tool".to_string(), LEVEL_NOTIFY);
        let summary = classification_summary(&o);
        assert!(summary["notify"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v == "custom_tool"));
    }

    #[test]
    fn all_overrides_maps_names() {
        let mut o = no_overrides();
        o.insert("t1".to_string(), LEVEL_APPROVE);
        let v = all_overrides(&o);
        assert_eq!(v["t1"], "approve");
    }
}

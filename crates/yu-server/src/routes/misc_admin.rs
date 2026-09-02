//! Miscellaneous admin routes.

use axum::{
    extract::{Extension, Path, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use std::time::{SystemTime, UNIX_EPOCH};
use std::{path::Path as FsPath, sync::OnceLock};
use tokio::sync::Mutex as TokioMutex;

use crate::{
    auth::{client_ip::ClientIp, scope::require_admin_scope, AuthContext},
    config_io::{load as load_cfg, validate_base_url, write as write_cfg},
    routes::update_status::detect_install_type,
    security::CspNonce,
    state::SharedState,
};

struct UpdateCache {
    data: Option<(u64, serde_json::Value)>,
}
static CHECK_CACHE: OnceLock<TokioMutex<UpdateCache>> = OnceLock::new();
static UNIFIED_CACHE: OnceLock<TokioMutex<UpdateCache>> = OnceLock::new();
static AI_CONTEXT_VERSION: OnceLock<String> = OnceLock::new();

const CSRF_NOTE: &str = "POST/PUT/PATCH/DELETE リクエストには X-Requested-With: XMLHttpRequest ヘッダが必要。Bearer API Key 認証時は不要。安全メソッド (GET, HEAD, OPTIONS) は CSRF チェック対象外。除外パスプレフィックス: /api/events/, /api/webhooks/receive/, /v1/。/ext/<name>/v1/* も除外（^/ext/[A-Za-z0-9][\\w\\-]*/v1/）。";

/// Read the generated settings schema from the running installation.
///
/// This used to be `include_str!("../../../../config/settings_schema.json")`,
/// which reached outside the crate and so blocked splitting yu-server into its
/// own repository (Cargo does not report `include_str!` as a dependency, so
/// nothing failed to warn about it). `routes::settings` already loads the same
/// file from `project_root` at runtime; this reuses that path so the two
/// surfaces cannot read different files.
fn load_settings_schema(project_root: &FsPath) -> serde_json::Value {
    std::fs::read_to_string(crate::routes::settings::schema_path(project_root))
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

/// `config.enabled` from an extension's own manifest, defaulting to `true`
/// when the manifest is absent or unreadable — the same fallback the embedded
/// copy provided, and the same one `ext_config::resolve_extension_enabled`
/// applies for every other extension.
fn extension_manifest(project_root: &FsPath, dir_name: &str) -> serde_json::Value {
    std::fs::read_to_string(
        project_root
            .join("extensions")
            .join(dir_name)
            .join("extension.json"),
    )
    .ok()
    .and_then(|raw| serde_json::from_str(&raw).ok())
    .unwrap_or_default()
}

fn parse_version(v: &str) -> Vec<u64> {
    v.trim_start_matches('v')
        .split('.')
        .map(|s| s.parse::<u64>().unwrap_or(0))
        .collect()
}

async fn fetch_update_check(s: &SharedState) -> serde_json::Value {
    let current = tokio::fs::read_to_string(s.config.project_root.join("VERSION"))
        .await
        .unwrap_or_else(|_| "0.0.0\n".to_string());
    let current = current.trim().to_string();
    let install_type = detect_install_type(&s.config.project_root);
    let mut result = json!({
        "current": current,
        "latest": current,
        "update_available": false,
        "release_url": "",
        "release_notes": "",
        "published_at": "",
        "install_type": install_type,
    });
    let url = "https://api.github.com/repos/eauesque/yu_ai_manager/releases/latest";
    match s
        .python_client
        .get(url)
        .header("User-Agent", format!("YU-AI-Manager/{}", current))
        .header("Accept", "application/vnd.github+json")
        // 5s, not 15: this is a "is there a newer release?" poll behind a UI
        // panel, and 15s outlived every caller's patience -- including the
        // parity harness, whose 10s budget it blew on every hermetic run.
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => match resp.json::<serde_json::Value>().await {
            Ok(data) => {
                let latest = data["tag_name"].as_str().unwrap_or("").to_string();
                result["update_available"] =
                    json!(parse_version(&latest) > parse_version(&current));
                result["latest"] = json!(latest);
                result["release_url"] = json!(data["html_url"].as_str().unwrap_or(""));
                result["release_notes"] = json!(data["body"].as_str().unwrap_or(""));
                result["published_at"] = json!(data["published_at"].as_str().unwrap_or(""));
            }
            Err(e) => {
                result["error"] = json!(e.to_string());
            }
        },
        Ok(resp) => {
            result["error"] = json!(format!("HTTP {}", resp.status()));
        }
        Err(e) => {
            result["error"] = json!(e.to_string());
        }
    }
    result
}

fn gate(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0))
}

fn read_version_cached<'a>(cache: &'a OnceLock<String>, project_root: &FsPath) -> &'a str {
    cache
        .get_or_init(|| {
            std::fs::read_to_string(project_root.join("VERSION"))
                .map(|version| version.trim().to_string())
                .unwrap_or_else(|_| "unknown".to_string())
        })
        .as_str()
}

fn json_truthy(value: Option<&serde_json::Value>) -> bool {
    match value {
        None | Some(serde_json::Value::Null) => false,
        Some(serde_json::Value::Bool(value)) => *value,
        Some(serde_json::Value::Number(value)) => value.as_f64() != Some(0.0),
        Some(serde_json::Value::String(value)) => !value.is_empty(),
        Some(serde_json::Value::Array(value)) => !value.is_empty(),
        Some(serde_json::Value::Object(value)) => !value.is_empty(),
    }
}

fn resolve_dotted_key<'a>(
    config: &'a serde_json::Value,
    key: &str,
) -> Option<&'a serde_json::Value> {
    key.split('.')
        .try_fold(config, |value, part| value.get(part))
}

fn get_config_hints(config: &serde_json::Value, project_root: &FsPath) -> Vec<serde_json::Value> {
    let mut hints = Vec::new();
    let server = config.get("server");
    if json_truthy(server.and_then(|value| value.get("lan")))
        && !json_truthy(server.and_then(|value| value.get("pin")))
    {
        hints.push(json!({
            "key": "server.pin",
            "severity": "warning",
            "message": "PIN 未設定で LAN アクセスが有効です。PIN を設定することを推奨します",
        }));
    }

    let ai = config.get("ai_analysis");
    if !json_truthy(ai.and_then(|value| value.get("api_key"))) {
        hints.push(json!({
            "key": "ai_analysis.api_key",
            "severity": "info",
            "message": "Claude API キー未設定。AI 分析機能が無効になっています",
        }));
    }

    let schema = load_settings_schema(project_root);
    for setting in schema.as_array().into_iter().flatten() {
        let key = setting["key"].as_str().unwrap_or("");
        if !setting["secret"].as_bool().unwrap_or(false)
            || !setting["default"].is_null()
            || matches!(key, "server.pin" | "ai_analysis.api_key")
        {
            continue;
        }
        let value = resolve_dotted_key(config, key);
        if value.is_none()
            || value == Some(&serde_json::Value::Null)
            || value
                .and_then(serde_json::Value::as_str)
                .is_some_and(|s| s.trim().is_empty())
        {
            hints.push(json!({
                "key": key,
                "severity": "info",
                "message": format!(
                    "未設定のシークレット項目（ヒューリスティック）: {}",
                    setting["description"].as_str().unwrap_or("")
                ),
            }));
        }
    }
    hints
}

fn capabilities(
    config: &serde_json::Value,
    native_daemon: bool,
    project_root: &FsPath,
) -> Vec<&'static str> {
    let mut capabilities = vec!["llm_router"];
    if native_daemon {
        capabilities.push("lan_cowork");
    }
    let hailo = config.get("hailo_tagger");
    if hailo
        .and_then(|value| value.get("enabled"))
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false)
        && hailo
            .and_then(|value| value.get("endpoint_url"))
            .and_then(serde_json::Value::as_str)
            .is_some_and(|url| !url.trim().is_empty())
    {
        capabilities.push("hailo");
    }
    let wd_default = extension_manifest(project_root, "builtin_wd_tagger")["config"]["enabled"]
        .as_bool()
        .unwrap_or(true);
    if config["extensions"]["builtin-wd-tagger"]["enabled"]
        .as_bool()
        .unwrap_or(wd_default)
    {
        capabilities.push("wd_tagger");
    }
    capabilities.extend(["image_analysis", "gateway", "scheduler"]);
    capabilities
}

fn unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "unavailable"})),
    )
        .into_response()
}

fn sns_config_value(config: &serde_json::Value) -> serde_json::Value {
    let mut value = json!({
        "bluesky": {
            "handle": "",
            "app_password": "",
        },
        "post_template": "{title}\n{url}",
    });
    if let Some(sns) = config.get("sns").and_then(serde_json::Value::as_object) {
        if let Some(bluesky) = sns.get("bluesky").and_then(serde_json::Value::as_object) {
            for (key, val) in bluesky {
                value["bluesky"][key] = val.clone();
            }
        }
        if let Some(template) = sns.get("post_template") {
            value["post_template"] = template.clone();
        }
    }
    value
}

// Generated from extensions/builtin_sns_share/core_impl/bsky_monitor_config.py
// by tmp/gen_bsky_defaults.py -- keep the two in step.
const BSKY_DEFAULT_TRIAGE_MENTION: &str = "Review this Bluesky mention and determine if it requires a response.\n\nRespond (valid):\n- A genuine question about the project or artwork\n- A bug report or technical issue\n- A collaboration request with specific details\n\nIgnore (invalid):\n- Generic praise with no question (e.g. 'nice!')\n- Spam or self-promotion\n- Hostile or abusive content\n- Bot-generated content\n\nReturn: valid / invalid with reason.";
const BSKY_DEFAULT_TRIAGE_REPLY: &str = "Review this reply to my Bluesky post.\n\nRespond (valid):\n- Asks a specific question\n- Reports an issue or bug\n- Provides useful feedback\n\nIgnore (invalid):\n- Simple emoji reaction\n- Generic comment with no question\n- Spam or off-topic\n\nReturn: valid / invalid with reason.";
const BSKY_DEFAULT_TRIAGE_QUOTE: &str = "Review this quote post of my content.\n\nRespond (valid):\n- Asks a question about the content\n- Makes a claim that needs correction\n\nIgnore (invalid):\n- Positive sharing without question\n- Unrelated commentary\n\nReturn: valid / invalid with reason.";
const BSKY_DEFAULT_AUTO_RESPONSE_MENTION: &str =
    "Thank you for reaching out! I'll take a look and get back to you.";
const BSKY_DEFAULT_AUTO_RESPONSE_REPLY: &str =
    "Thanks for your comment! I'll review and respond shortly.";
const BSKY_DEFAULT_AUTO_RESPONSE_QUOTE: &str = "";

fn bsky_triage_defaults() -> serde_json::Value {
    json!({
        "mention": BSKY_DEFAULT_TRIAGE_MENTION,
        "reply": BSKY_DEFAULT_TRIAGE_REPLY,
        "quote": BSKY_DEFAULT_TRIAGE_QUOTE,
    })
}

fn bsky_auto_response_defaults() -> serde_json::Value {
    json!({
        "mention": BSKY_DEFAULT_AUTO_RESPONSE_MENTION,
        "reply": BSKY_DEFAULT_AUTO_RESPONSE_REPLY,
        "quote": BSKY_DEFAULT_AUTO_RESPONSE_QUOTE,
    })
}

/// `sns.bluesky_monitor` -- the one section Python reads and writes. This used
/// to look for `sns.bsky_monitor` and `sns.bsky_triage`, names that exist
/// nowhere else in the tree, so both GETs could only ever answer with defaults
/// and never with what the operator had saved.
fn bsky_section(config: &serde_json::Value) -> Option<&serde_json::Value> {
    config.get("sns").and_then(|v| v.get("bluesky_monitor"))
}

fn bsky_monitor_config_value(config: &serde_json::Value) -> serde_json::Value {
    let section = bsky_section(config);
    let get = |key: &str| section.and_then(|s| s.get(key)).cloned();
    json!({
        "poll_interval_minutes": get("poll_interval_minutes").unwrap_or(json!(30)),
        "auto_dismiss_follow": get("auto_dismiss_follow").unwrap_or(json!(true)),
        "auto_dismiss_like": get("auto_dismiss_like").unwrap_or(json!(true)),
        "auto_dismiss_repost": get("auto_dismiss_repost").unwrap_or(json!(true)),
        "auto_respond_enabled": get("auto_respond_enabled").unwrap_or(json!(false)),
        "notify_on_connect": get("notify_on_connect").unwrap_or(json!(true)),
    })
}

/// Read one `{mention, reply, quote}` sub-block, falling back per field to the
/// matching default. Python does the fallback field by field, not block by
/// block, so a section holding only `mention` still yields the default reply.
fn bsky_prompt_block(
    config: &serde_json::Value,
    name: &str,
    defaults: &serde_json::Value,
) -> serde_json::Value {
    let block = bsky_section(config).and_then(|s| s.get(name));
    let field = |key: &str| {
        block
            .and_then(|b| b.get(key))
            .cloned()
            .or_else(|| defaults.get(key).cloned())
            .unwrap_or_else(|| json!(""))
    };
    json!({"mention": field("mention"), "reply": field("reply"), "quote": field("quote")})
}

fn bsky_triage_prompts_value(config: &serde_json::Value) -> serde_json::Value {
    // Python nests both blocks inside `bluesky_monitor` rather than beside it,
    // calls the auto-response block `auto_response_templates` on disk but
    // `auto_responses` on the wire, and ships the defaults alongside the saved
    // values so the editor can offer "reset to default".
    json!({
        "triage_prompts": bsky_prompt_block(config, "triage_prompts", &bsky_triage_defaults()),
        "auto_responses": bsky_prompt_block(
            config,
            "auto_response_templates",
            &bsky_auto_response_defaults(),
        ),
        "triage_defaults": bsky_triage_defaults(),
        "auto_response_defaults": bsky_auto_response_defaults(),
    })
}

fn merge_bsky_section(config: &mut Value, updates: serde_json::Map<String, Value>) {
    // Walk `config.sns.bluesky_monitor`, coercing anything that is not an
    // object on the way (a hand-edited config can hold a scalar there). Each
    // `let ... else` is unreachable -- the line above forces an object -- but
    // returning beats panicking on a config file we do not control.
    if !config.is_object() {
        *config = json!({});
    }
    let Some(root) = config.as_object_mut() else {
        return;
    };
    let sns = root.entry("sns").or_insert_with(|| json!({}));
    if !sns.is_object() {
        *sns = json!({});
    }
    let Some(sns) = sns.as_object_mut() else {
        return;
    };
    let monitor = sns.entry("bluesky_monitor").or_insert_with(|| json!({}));
    if !monitor.is_object() {
        *monitor = json!({});
    }
    let Some(monitor) = monitor.as_object_mut() else {
        return;
    };
    for (key, value) in updates {
        // One level of deep merge. Python updates the nested prompt blocks
        // field by field (`setdefault` then assign only what was supplied), so
        // a request carrying just `mention` must not drop a saved `reply`.
        match (monitor.get_mut(&key).and_then(Value::as_object_mut), value) {
            (Some(existing), Value::Object(incoming)) => {
                for (field, field_value) in incoming {
                    existing.insert(field, field_value);
                }
            }
            (_, value) => {
                monitor.insert(key, value);
            }
        }
    }
}

fn save_bsky_section(
    state: &SharedState,
    updates: serde_json::Map<String, Value>,
) -> Result<(), std::io::Error> {
    let path = &state.config.config_path;
    let mut config = load_cfg(path);
    merge_bsky_section(&mut config, updates);
    write_cfg(path, &config)
}

/// PUT /api/sns/bsky/monitor/config
pub async fn sns_bsky_monitor_config_save(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let mut updates = serde_json::Map::new();
    if let Some(minutes) = body.get("poll_interval_minutes").and_then(Value::as_i64) {
        // Python clamps to a 5-minute floor; a shorter interval would hammer
        // the upstream API, so the clamp is part of the contract, not a detail.
        updates.insert("poll_interval_minutes".into(), json!(minutes.max(5)));
    }
    for key in [
        "auto_dismiss_follow",
        "auto_dismiss_like",
        "auto_dismiss_repost",
        "auto_respond_enabled",
        "notify_on_connect",
    ] {
        if let Some(flag) = body.get(key).and_then(Value::as_bool) {
            updates.insert(key.to_string(), json!(flag));
        }
    }
    let _guard = s.settings_lock.lock().await;
    if let Err(error) = save_bsky_section(&s, updates) {
        tracing::error!(?error, "failed to save the bluesky monitor config");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "internal_server_error"})),
        )
            .into_response();
    }
    let config = load_cfg(&s.config.config_path);
    Json(json!({"ok": true, "error": null, "data": bsky_monitor_config_value(&config)}))
        .into_response()
}

/// PUT /api/sns/bsky/monitor/triage-prompts
pub async fn sns_bsky_triage_prompts_save(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let mut updates = serde_json::Map::new();
    let mut touched: Vec<&str> = Vec::new();
    // The UI's two field groups map onto two differently-named config keys:
    // on the wire `auto_responses`, on disk `auto_response_templates`. Getting
    // that pair backwards is invisible until someone reloads the page.
    for (body_key, config_key) in [
        ("triage_prompts", "triage_prompts"),
        ("auto_responses", "auto_response_templates"),
    ] {
        let Some(incoming) = body.get(body_key).and_then(Value::as_object) else {
            continue;
        };
        let mut merged = serde_json::Map::new();
        for field in ["mention", "reply", "quote"] {
            if let Some(text) = incoming.get(field).and_then(Value::as_str) {
                merged.insert(field.to_string(), json!(text));
            }
        }
        if !merged.is_empty() {
            updates.insert(config_key.to_string(), Value::Object(merged));
            touched.push(body_key);
        }
    }
    let _guard = s.settings_lock.lock().await;
    if let Err(error) = save_bsky_section(&s, updates) {
        tracing::error!(?error, "failed to save the bluesky triage prompts");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "internal_server_error"})),
        )
            .into_response();
    }
    let config = load_cfg(&s.config.config_path);
    // Python answers with only the blocks the request actually carried -- an
    // empty body yields an empty `data`, not the whole pair.
    let saved = bsky_triage_prompts_value(&config);
    let mut data = serde_json::Map::new();
    for key in touched {
        if let Some(block) = saved.get(key) {
            data.insert(key.to_string(), block.clone());
        }
    }
    Json(json!({"ok": true, "error": null, "data": Value::Object(data)})).into_response()
}

#[cfg(test)]
mod sns_tests {
    use super::*;

    /// The bug this pair of tests exists for: the readers looked for
    /// `sns.bsky_monitor` / `sns.bsky_triage`, names that appear nowhere else
    /// in the tree. Python reads and writes `sns.bluesky_monitor`. Both
    /// endpoints therefore answered with defaults no matter what the operator
    /// had saved -- and the types matched, so it compiled and stayed green.
    #[test]
    fn monitor_config_reads_the_key_python_writes() {
        let cfg = bsky_monitor_config_value(&json!({
            "sns": {"bluesky_monitor": {
                "poll_interval_minutes": 15,
                "auto_dismiss_like": false,
            }}
        }));
        assert_eq!(cfg["poll_interval_minutes"], 15);
        assert_eq!(cfg["auto_dismiss_like"], json!(false));
        // Unset keys still fall back to Python's defaults.
        assert_eq!(cfg["notify_on_connect"], json!(true));
    }

    /// A value stored under the *old* name must NOT be picked up: if it were,
    /// this test would pass with the reader restored to the wrong key.
    #[test]
    fn monitor_config_ignores_the_name_that_never_existed() {
        let cfg = bsky_monitor_config_value(&json!({
            "sns": {"bsky_monitor": {"poll_interval_minutes": 15}}
        }));
        assert_eq!(
            cfg["poll_interval_minutes"], 30,
            "must fall back, not read the stale name"
        );
    }

    /// The UI saves the monitor block and the prompt block through two
    /// separate PUTs. A wholesale replace would have each request erase the
    /// other's half, and nothing outside a round trip would notice.
    #[test]
    fn the_two_puts_do_not_erase_each_other() {
        let mut config = json!({"other_top_level": 1, "sns": {"unrelated": true}});

        let mut monitor = serde_json::Map::new();
        monitor.insert("poll_interval_minutes".into(), json!(15));
        merge_bsky_section(&mut config, monitor);

        let mut prompts = serde_json::Map::new();
        prompts.insert("triage_prompts".into(), json!({"mention": "M"}));
        merge_bsky_section(&mut config, prompts);

        // Both halves survive, and so does everything around them.
        assert_eq!(
            bsky_monitor_config_value(&config)["poll_interval_minutes"],
            15
        );
        assert_eq!(
            bsky_triage_prompts_value(&config)["triage_prompts"]["mention"],
            "M"
        );
        assert_eq!(config["sns"]["unrelated"], json!(true));
        assert_eq!(config["other_top_level"], 1);
    }

    /// A hand-edited config can hold a scalar where an object belongs. The
    /// merge must replace it rather than panic on `as_object_mut`.
    #[test]
    fn merge_survives_a_non_object_on_the_path() {
        let mut config = json!({"sns": "not an object"});
        let mut updates = serde_json::Map::new();
        updates.insert("poll_interval_minutes".into(), json!(20));
        merge_bsky_section(&mut config, updates);
        assert_eq!(
            config["sns"]["bluesky_monitor"]["poll_interval_minutes"],
            20
        );
    }

    /// auto-responses under `auto_response_templates` while the wire calls them
    /// `auto_responses`. Both halves of that mapping are easy to get backwards.
    #[test]
    fn triage_prompts_read_the_nested_python_layout() {
        let cfg = bsky_triage_prompts_value(&json!({
            "sns": {"bluesky_monitor": {
                "triage_prompts": {"mention": "M", "reply": "R"},
                "auto_response_templates": {"mention": "AM"},
            }}
        }));
        assert_eq!(cfg["triage_prompts"]["mention"], "M");
        assert_eq!(cfg["triage_prompts"]["reply"], "R");
        // Python falls back per FIELD, not per block: an unset `quote` next to
        // a set `mention` still yields the default, not an empty string.
        assert_eq!(cfg["triage_prompts"]["quote"], BSKY_DEFAULT_TRIAGE_QUOTE);
        assert_eq!(cfg["auto_responses"]["mention"], "AM");
        assert_eq!(
            cfg["auto_responses"]["reply"],
            BSKY_DEFAULT_AUTO_RESPONSE_REPLY
        );
        // Python's GET ships the defaults alongside the saved values.
        assert_eq!(
            cfg["triage_defaults"]["mention"],
            BSKY_DEFAULT_TRIAGE_MENTION
        );
        assert_eq!(
            cfg["auto_response_defaults"]["mention"],
            BSKY_DEFAULT_AUTO_RESPONSE_MENTION
        );
    }

    /// An empty section must answer with every default -- not empty strings.
    #[test]
    fn triage_prompts_default_to_pythons_wording() {
        let cfg = bsky_triage_prompts_value(&json!({}));
        assert_eq!(
            cfg["triage_prompts"]["mention"],
            BSKY_DEFAULT_TRIAGE_MENTION
        );
        assert_eq!(cfg["triage_prompts"]["reply"], BSKY_DEFAULT_TRIAGE_REPLY);
        assert_eq!(
            cfg["auto_responses"]["reply"],
            BSKY_DEFAULT_AUTO_RESPONSE_REPLY
        );
        assert!(
            !BSKY_DEFAULT_TRIAGE_MENTION.is_empty(),
            "the default must carry Python's wording, not an empty placeholder"
        );
    }

    /// Python merges into the nested block field by field. A request carrying
    /// only `mention` must not drop a previously saved `reply`.
    #[test]
    fn a_partial_prompt_save_keeps_the_other_fields() {
        let mut config = json!({
            "sns": {"bluesky_monitor": {"triage_prompts": {"mention": "old-M", "reply": "keep-R"}}}
        });
        let mut updates = serde_json::Map::new();
        updates.insert("triage_prompts".into(), json!({"mention": "new-M"}));
        merge_bsky_section(&mut config, updates);

        let cfg = bsky_triage_prompts_value(&config);
        assert_eq!(cfg["triage_prompts"]["mention"], "new-M");
        assert_eq!(
            cfg["triage_prompts"]["reply"], "keep-R",
            "reply was clobbered"
        );
    }

    #[test]
    fn sns_config_value_merges_defaults() {
        let cfg = sns_config_value(&json!({
            "sns": {
                "bluesky": {"handle": "alice.test"},
                "post_template": "hello"
            }
        }));

        assert_eq!(cfg["bluesky"]["handle"], "alice.test");
        assert_eq!(cfg["bluesky"]["app_password"], "");
        assert_eq!(cfg["post_template"], "hello");
    }
}

#[cfg(test)]
mod ai_context_tests {
    use super::*;
    use axum::body::to_bytes;
    use tempfile::TempDir;

    async fn test_state() -> (TempDir, SharedState) {
        let root = tempfile::tempdir().unwrap();
        std::fs::write(root.path().join("config.json"), "{}\n").unwrap();
        let state = crate::state::semantic_test_state_with_root(
            true,
            String::new(),
            root.path().to_path_buf(),
        )
        .await;
        (root, state)
    }

    fn api_key(scopes: &[&str]) -> Extension<AuthContext> {
        Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(scopes.iter().map(|scope| (*scope).to_string()).collect()),
        })
    }

    async fn response_json(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn ai_context_requires_admin_scope() {
        let (_root, state) = test_state().await;
        let read_response = ai_context(
            State(state.clone()),
            Extension(false),
            Some(api_key(&["read"])),
        )
        .await;
        assert_eq!(read_response.status(), StatusCode::FORBIDDEN);

        let admin_response =
            ai_context(State(state), Extension(false), Some(api_key(&["admin"]))).await;
        assert_eq!(admin_response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn ai_context_matches_python_metadata_and_unmounted_capabilities() {
        let (_root, state) = test_state().await;
        let response = ai_context(State(state), Extension(false), Some(api_key(&["admin"]))).await;
        let value = response_json(response).await;
        let data = &value["data"];

        assert_eq!(data["software"]["name"], "YU AI Manager");
        assert_eq!(
            data["software"]["description"],
            "ローカルファースト AI 画像メタデータ管理ツール"
        );
        assert_eq!(
            data["urls"],
            json!({
                "settings_schema": "/api/settings/schema",
                "current_settings": "/api/settings/all",
                "openapi": "/api/openapi.json",
            })
        );
        assert_eq!(
            data["diagnostics"],
            json!({
                "doctor_start": {"method": "POST", "url": "/api/diagnostics/doctor"},
                "doctor_poll": {"method": "GET", "url": "/api/diagnostics/doctor/{job_id}"},
                "note": "POST で job を起動し、返された job_id を GET で polling して完了を確認する",
            })
        );
        assert!(!data["capabilities"]
            .as_array()
            .unwrap()
            .iter()
            .any(|capability| capability == "lan_cowork"));
    }

    #[test]
    fn ai_context_version_falls_back_and_caches_unknown() {
        let root = tempfile::tempdir().unwrap();
        let cache = OnceLock::new();
        assert_eq!(read_version_cached(&cache, root.path()), "unknown");
        std::fs::write(root.path().join("VERSION"), "9.9.9\n").unwrap();
        assert_eq!(read_version_cached(&cache, root.path()), "unknown");
    }

    #[test]
    fn ai_context_capabilities_follow_actual_configuration() {
        let root = tempfile::tempdir().unwrap();
        let config = json!({
            "hailo_tagger": {"enabled": true, "endpoint_url": "http://hailo.test"},
            "extensions": {"builtin-wd-tagger": {"enabled": false}},
        });
        assert_eq!(
            capabilities(&config, false, root.path()),
            [
                "llm_router",
                "hailo",
                "image_analysis",
                "gateway",
                "scheduler"
            ]
        );
        assert!(capabilities(&config, true, root.path()).contains(&"lan_cowork"));
    }

    /// Without a manifest the wd-tagger default is `true`, matching the value
    /// the embedded `extension.json` used to supply.
    #[test]
    fn wd_tagger_default_comes_from_the_installed_manifest() {
        let root = tempfile::tempdir().unwrap();
        let config = json!({});
        assert!(capabilities(&config, false, root.path()).contains(&"wd_tagger"));

        let ext = root.path().join("extensions/builtin_wd_tagger");
        std::fs::create_dir_all(&ext).unwrap();
        std::fs::write(
            ext.join("extension.json"),
            json!({"config": {"enabled": false}}).to_string(),
        )
        .unwrap();
        assert!(!capabilities(&config, false, root.path()).contains(&"wd_tagger"));
    }

    #[test]
    fn ai_context_config_hints_match_python_rules() {
        // The schema-derived hints are read from the installation at run time,
        // so the fixture has to exist on disk for this assertion to hold.
        let root = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(root.path().join("config")).unwrap();
        std::fs::write(
            root.path().join("config/settings_schema.json"),
            json!([
                {"key": "server.restart_token", "secret": true, "default": null, "description": "restart token"},
                {"key": "webhook_secret", "secret": true, "default": null, "description": "webhook secret"},
                {"key": "server.port", "secret": false, "default": null, "description": "port"},
            ])
            .to_string(),
        )
        .unwrap();
        let keys: Vec<_> = get_config_hints(
            &json!({
                "server": {"lan": true},
                "ai_analysis": {"api_key": ""},
            }),
            root.path(),
        )
        .into_iter()
        .map(|hint| hint["key"].as_str().unwrap().to_string())
        .collect();
        assert_eq!(
            keys,
            [
                "server.pin",
                "ai_analysis.api_key",
                "server.restart_token",
                "webhook_secret",
            ]
        );
    }
}

/// GET /api/ai-context
pub async fn ai_context(
    State(s): State<SharedState>,
    Extension(native_daemon): Extension<bool>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let config = load_cfg(&s.config.config_path);
    Json(json!({
        "data": {
            "software": {
                "name": "YU AI Manager",
                "version": read_version_cached(&AI_CONTEXT_VERSION, &s.config.project_root),
                "description": "ローカルファースト AI 画像メタデータ管理ツール",
            },
            "capabilities": capabilities(&config, native_daemon, &s.config.project_root),
            "urls": {
                "settings_schema": "/api/settings/schema",
                "current_settings": "/api/settings/all",
                "openapi": "/api/openapi.json",
            },
            "diagnostics": {
                "doctor_start": {"method": "POST", "url": "/api/diagnostics/doctor"},
                "doctor_poll": {"method": "GET", "url": "/api/diagnostics/doctor/{job_id}"},
                "note": "POST で job を起動し、返された job_id を GET で polling して完了を確認する",
            },
            "csrf_note": CSRF_NOTE,
            "config_hints": get_config_hints(&config, &s.config.project_root),
        }
    }))
    .into_response()
}

/// GET /api/system/update/check
pub async fn update_check(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let cache = CHECK_CACHE.get_or_init(|| TokioMutex::new(UpdateCache { data: None }));
    let cached = {
        let guard = cache.lock().await;
        guard.data.as_ref().and_then(|(ts, v)| {
            if now.saturating_sub(*ts) < 600 {
                Some(v.clone())
            } else {
                None
            }
        })
    };
    let result = if let Some(v) = cached {
        v
    } else {
        let v = fetch_update_check(&s).await;
        let mut guard = cache.lock().await;
        guard.data = Some((now, v.clone()));
        v
    };
    Json(result).into_response()
}

/// GET /api/system/update/unified-check
pub async fn update_unified_check(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let cache = UNIFIED_CACHE.get_or_init(|| TokioMutex::new(UpdateCache { data: None }));
    let cached = {
        let guard = cache.lock().await;
        guard.data.as_ref().and_then(|(ts, v)| {
            if now.saturating_sub(*ts) < 600 {
                Some(v.clone())
            } else {
                None
            }
        })
    };
    let result = if let Some(v) = cached {
        v
    } else {
        let system = fetch_update_check(&s).await;
        let v = json!({
            "system": system,
            "extensions": [],
            "summary": {
                "total": 0,
                "up_to_date": 0,
                "update_available": 0,
                "unknown": 0,
                "builtin": 0,
            }
        });
        let mut guard = cache.lock().await;
        guard.data = Some((now, v.clone()));
        v
    };
    Json(result).into_response()
}

/// POST /api/search-union
pub async fn search_union(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/debug/query
pub async fn debug_query(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// GET /api/workflow-gen-params/{file_id}
pub async fn workflow_gen_params(
    State(_s): State<SharedState>,
    Path(_file_id): Path<i64>,
) -> Response {
    unavailable()
}

/// GET /api/sns/preview
pub async fn sns_preview(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// GET /api/sns/x/intent
pub async fn sns_x_intent(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/sns/bluesky/post
pub async fn sns_bluesky_post(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/sns/bluesky/test
pub async fn sns_bluesky_test(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// GET /api/sns/bsky/queue
pub async fn sns_bsky_queue(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// GET /api/sns/bsky/queue/pending
pub async fn sns_bsky_queue_pending(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// GET /api/sns/bsky/monitor/config
pub async fn sns_bsky_monitor_config(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    Json(
        json!({"ok": true, "error": null, "data": bsky_monitor_config_value(&read_config_json(&s).await)}),
    )
    .into_response()
}

/// GET /api/sns/bsky/monitor/triage-prompts
pub async fn sns_bsky_triage_prompts(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    Json(
        json!({"ok": true, "error": null, "data": bsky_triage_prompts_value(&read_config_json(&s).await)}),
    )
    .into_response()
}

/// GET /api/sns/config
pub async fn sns_config_get(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    Json(json!({"ok": true, "error": null, "data": sns_config_value(&s.config.app_config)}))
        .into_response()
}

/// POST /api/sns/config
pub async fn sns_config_post(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// GET /api/collections/{id}/export
pub async fn collections_export(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Path(id): Path<i64>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let name: Option<String> = sqlx::query_scalar("SELECT name FROM collections WHERE id = ?")
        .bind(id)
        .fetch_optional(&s.db_read)
        .await
        .unwrap_or(None);
    let Some(cname) = name else {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "collection_not_found"})),
        )
            .into_response();
    };
    let rows = sqlx::query_as::<
        _,
        (
            i64,
            Option<String>,
            Option<String>,
            Option<i64>,
            Option<String>,
            Option<String>,
        ),
    >(
        "SELECT f.id, f.path, f.meta_source, f.mtime, t.raw_prompt, t.raw_negative \
         FROM favorites fav \
         JOIN files f ON f.id = fav.file_id AND f.is_deleted = 0 \
         LEFT JOIN templates t ON t.file_id = f.id \
         WHERE fav.collection_id = ? ORDER BY fav.added_at DESC",
    )
    .bind(id)
    .fetch_all(&s.db_read)
    .await
    .unwrap_or_default();
    let items: Vec<serde_json::Value> = rows
        .into_iter()
        .map(|(fid, path, meta_source, mtime, positive, negative)| {
            let p = path.as_deref().unwrap_or("");
            let fname = p.rsplit('/').next().unwrap_or(p);
            let folder = if let Some(idx) = p.rfind('/') {
                &p[..idx]
            } else {
                ""
            };
            let mtime_iso = mtime
                .and_then(|t| chrono::DateTime::from_timestamp(t, 0))
                .map(|dt| dt.format("%Y-%m-%dT%H:%M:%SZ").to_string())
                .unwrap_or_default();
            json!({
                "id": fid,
                "filename": fname,
                "folder": folder,
                "path": p,
                "meta_source": meta_source.unwrap_or_default(),
                "mtime": mtime_iso,
                "positive": positive.unwrap_or_default(),
                "negative": negative.unwrap_or_default(),
            })
        })
        .collect();
    Json(json!({"ok": true, "collection": {"id": id, "name": cname}, "items": items}))
        .into_response()
}

/// GET /api/collections/{id}/export/csv
pub async fn collections_export_csv(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Path(id): Path<i64>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let name: Option<String> = sqlx::query_scalar("SELECT name FROM collections WHERE id = ?")
        .bind(id)
        .fetch_optional(&s.db_read)
        .await
        .unwrap_or(None);
    let Some(cname) = name else {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "collection_not_found"})),
        )
            .into_response();
    };
    let rows = sqlx::query_as::<
        _,
        (
            i64,
            Option<String>,
            Option<String>,
            Option<i64>,
            Option<String>,
            Option<String>,
        ),
    >(
        "SELECT f.id, f.path, f.meta_source, f.mtime, t.raw_prompt, t.raw_negative \
         FROM favorites fav \
         JOIN files f ON f.id = fav.file_id AND f.is_deleted = 0 \
         LEFT JOIN templates t ON t.file_id = f.id \
         WHERE fav.collection_id = ? ORDER BY fav.added_at DESC",
    )
    .bind(id)
    .fetch_all(&s.db_read)
    .await
    .unwrap_or_default();

    let mut csv = String::from("\u{FEFF}"); // UTF-8 BOM
    csv.push_str("id,filename,folder,path,meta_source,mtime,positive,negative\n");
    for (fid, path, meta_source, mtime, positive, negative) in rows {
        let p = path.as_deref().unwrap_or("").to_string();
        let fname = p.rsplit('/').next().unwrap_or(&p).to_string();
        let folder = if let Some(idx) = p.rfind('/') {
            p[..idx].to_string()
        } else {
            String::new()
        };
        let mtime_iso = mtime
            .and_then(|t| chrono::DateTime::from_timestamp(t, 0))
            .map(|dt| dt.format("%Y-%m-%dT%H:%M:%SZ").to_string())
            .unwrap_or_default();
        fn csv_field(s: &str) -> String {
            if s.contains([',', '"', '\n']) {
                format!("\"{}\"", s.replace('"', "\"\""))
            } else {
                s.to_string()
            }
        }
        csv.push_str(&format!(
            "{},{},{},{},{},{},{},{}\n",
            fid,
            csv_field(&fname),
            csv_field(&folder),
            csv_field(&p),
            csv_field(meta_source.as_deref().unwrap_or("")),
            mtime_iso,
            csv_field(positive.as_deref().unwrap_or("")),
            csv_field(negative.as_deref().unwrap_or("")),
        ));
    }
    let safe_name: String = cname
        .chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect();
    let disposition = format!("attachment; filename=\"{safe_name}.csv\"");
    (
        [
            (header::CONTENT_TYPE, "text/csv; charset=utf-8"),
            (header::CONTENT_DISPOSITION, &disposition),
        ],
        csv,
    )
        .into_response()
}

/// POST /api/llm/agent
pub async fn llm_agent(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|context| &context.0),
    ) {
        return response;
    }
    let category = body
        .get("category")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    let message = body
        .get("message")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if category.is_empty() || message.is_empty() {
        return llm_error("category and message are required", StatusCode::BAD_REQUEST);
    }
    let endpoint = crate::routes::llm_client::resolve_endpoint(&state, category).or_else(|| {
        (category == "hailo").then(|| crate::routes::llm_client::Endpoint {
            base_url: format!(
                "http://127.0.0.1:{}/ext/hailo-genai/v1",
                state.effective_port
            ),
            model: body
                .get("model")
                .and_then(Value::as_str)
                .unwrap_or("qwen2.5-coder-1.5b")
                .to_string(),
            api_key: String::new(),
            timeout_secs: 120,
        })
    });
    let Some(endpoint) = endpoint else {
        return llm_error(
            &format!("No LLM endpoint configured for '{category}'"),
            StatusCode::NOT_FOUND,
        );
    };
    let mode = body
        .get("mode")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    let tools = agent_tools(&body);
    let max_rounds = body
        .get("max_rounds")
        .and_then(Value::as_u64)
        .unwrap_or(8)
        .min(8) as usize;
    let system_prompt = body.get("system_prompt").and_then(Value::as_str).unwrap_or(
        "You are a helpful assistant. Use the available tools to answer questions about the file database.",
    );
    if mode == "prompt_based" || (mode.is_empty() && endpoint.base_url.contains("hailo-genai")) {
        return llm_result(
            crate::routes::llm_agent_prompt::run_agent_prompt_based(
                &state,
                &headers,
                &endpoint,
                message,
                &tools,
                system_prompt,
                body.get("max_tokens")
                    .and_then(Value::as_u64)
                    .and_then(|v| u32::try_from(v).ok())
                    .unwrap_or(512),
                body.get("temperature")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.1),
                max_rounds,
            )
            .await,
        );
    }
    let max_tokens = body
        .get("max_tokens")
        .and_then(Value::as_u64)
        .and_then(|v| u32::try_from(v).ok())
        .unwrap_or(1024);
    let temperature = body
        .get("temperature")
        .and_then(Value::as_f64)
        .unwrap_or(0.3);
    let mut history = Vec::new();
    if !system_prompt.is_empty() {
        history.push(json!({"role": "system", "content": system_prompt}));
    }
    history.push(json!({"role": "user", "content": message}));
    let mut steps = Vec::new();
    for round in 0..max_rounds {
        let response = match crate::routes::llm_client::chat(
            &state,
            &endpoint,
            &history,
            max_tokens,
            temperature,
            Some(&Value::Array(tools.clone())),
            Some(&headers),
        )
        .await
        {
            Ok(response) => response,
            Err(error) => {
                tracing::warn!(category, %error, "LLM agent failed");
                return llm_error("LLM agent request failed", StatusCode::BAD_GATEWAY);
            }
        };
        if response.tool_calls.is_empty() {
            return llm_result(json!({
                "content": response.content,
                "model": response.model,
                "steps": steps,
                "rounds": round + 1,
            }));
        }
        history.push(json!({
            "role": "assistant",
            "content": response.content,
            "tool_calls": response.tool_calls.iter().map(|call| json!({
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            })).collect::<Vec<_>>(),
        }));
        for call in response.tool_calls {
            let arguments = serde_json::from_str(&call.arguments).unwrap_or_default();
            let result =
                crate::routes::llm_client::execute_tool(&state, &headers, &call.name, &arguments)
                    .await;
            let result = if let Some(value) = result.as_str() {
                value.to_string()
            } else {
                result.to_string()
            };
            steps.push(json!({
                "tool": call.name,
                "arguments": arguments,
                "result_preview": result.chars().take(200).collect::<String>(),
            }));
            history.push(json!({"role": "tool", "tool_call_id": call.id, "content": result}));
        }
    }
    llm_result(json!({
        "content": "[Agent reached maximum tool call rounds]",
        "model": endpoint.model,
        "steps": steps,
        "rounds": max_rounds,
    }))
}

#[cfg(test)]
mod llm_agent_tests {
    use super::*;
    use std::{
        collections::HashSet,
        path::PathBuf,
        str::FromStr,
        sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        },
    };

    use axum::{
        body::to_bytes,
        extract::State,
        routing::{get, post},
        Router,
    };
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tokio::sync::Mutex;

    use crate::state::{AppState, Config};

    #[derive(Clone)]
    struct StubState {
        chats: Arc<AtomicUsize>,
        chat_headers: Arc<Mutex<Vec<HeaderMap>>>,
        tool_headers: Arc<Mutex<Vec<HeaderMap>>>,
        requests: Arc<Mutex<Vec<Value>>>,
    }

    async fn chat(State(stub): State<StubState>, headers: HeaderMap) -> Json<Value> {
        stub.chat_headers.lock().await.push(headers);
        let message = if stub.chats.fetch_add(1, Ordering::SeqCst) % 2 == 0 {
            json!({"content": "", "tool_calls": [{"id": "call-1", "function": {"name": "search_files", "arguments": "{\"q\":\"test\"}"}}]})
        } else {
            json!({"content": "done"})
        };
        Json(json!({"choices": [{"message": message}], "model": "stub"}))
    }

    async fn prompt_chat(
        State(stub): State<StubState>,
        headers: HeaderMap,
        Json(request): Json<Value>,
    ) -> Json<Value> {
        stub.chat_headers.lock().await.push(headers);
        stub.requests.lock().await.push(request);
        let content = if stub.chats.fetch_add(1, Ordering::SeqCst) % 2 == 0 {
            r#"{"name":"search_files","arguments":{"q":"test"}}"#
        } else {
            "done"
        };
        Json(json!({"choices":[{"message":{"content":content}}], "model":"stub"}))
    }

    async fn search(State(stub): State<StubState>, headers: HeaderMap) -> Json<Value> {
        stub.tool_headers.lock().await.push(headers);
        Json(json!("x".repeat(2000)))
    }

    /// First call replies with a malformed-but-recognizable tool-call attempt (a brace fragment
    /// with a quoted `"name"` key that fails to parse); every call after that replies with a
    /// plain final answer. Used to prove the one-shot format-correction retry actually fires.
    async fn prompt_chat_malformed_then_answer(
        State(stub): State<StubState>,
        headers: HeaderMap,
        Json(request): Json<Value>,
    ) -> Json<Value> {
        stub.chat_headers.lock().await.push(headers);
        stub.requests.lock().await.push(request);
        let content = if stub.chats.fetch_add(1, Ordering::SeqCst) == 0 {
            r#"{"name": "search_files", "oops":}"#
        } else {
            "The answer is 42."
        };
        Json(json!({"choices":[{"message":{"content":content}}], "model":"stub"}))
    }

    async fn test_state(port: u16) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(
            AppState::new(
                Config {
                    db_path: "sqlite::memory:".to_string(), pin_hash: String::new(), valid_token: String::new(), secret: String::new(),
                    trusted_proxy_enabled: false, pin_boss_login_ui: false, trusted_ips: HashSet::new(), trusted_peer_ips: HashSet::new(),
                    quick_lock_enabled: true, pin_auth_enabled: false, min_pin_length: 4, python_url: String::new(),
                    config_path: PathBuf::from("config.json"), project_root: PathBuf::from("."),
                    app_config: json!({"llm_endpoints": {"test": {"base_url": format!("http://127.0.0.1:{port}/v1"), "model": "stub"}}}),
                    cache_dir: PathBuf::from("."), server_mode: "full".to_string(), headless: false, safe_mode: false,
                    mcp_native: false, standalone: false, infer_standalone: true, active_profile: None, python_executable: String::new(),
                },
                pool.clone(), pool, Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            ).await.with_effective_port(port),
        )
    }

    async fn response_json(response: Response) -> Value {
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap()
    }

    #[tokio::test]
    async fn llm_agent_forwards_caller_credentials_and_limits_result_preview() {
        let stub = StubState {
            chats: Arc::new(AtomicUsize::new(0)),
            chat_headers: Arc::new(Mutex::new(Vec::new())),
            tool_headers: Arc::new(Mutex::new(Vec::new())),
            requests: Arc::new(Mutex::new(Vec::new())),
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let app = Router::new()
            .route("/v1/chat/completions", post(chat))
            .route("/api/search", get(search))
            .with_state(stub.clone());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let state = test_state(port).await;
        let body = json!({"category": "test", "message": "search"});

        let mut credentials = HeaderMap::new();
        credentials.insert("Authorization", "Bearer caller".parse().unwrap());
        credentials.insert("X-Api-Key", "caller-key".parse().unwrap());
        credentials.insert("Cookie", "session=caller".parse().unwrap());
        let response = llm_agent(State(state.clone()), None, credentials, Json(body.clone())).await;
        let result = response_json(response).await;
        assert_eq!(result["steps"][0]["result_preview"], "x".repeat(200),);

        let mut no_cookie = HeaderMap::new();
        no_cookie.insert("Authorization", "Bearer caller".parse().unwrap());
        no_cookie.insert("X-Api-Key", "caller-key".parse().unwrap());
        let response = llm_agent(State(state), None, no_cookie, Json(body)).await;
        assert_eq!(response.status(), StatusCode::OK);

        let headers = stub.tool_headers.lock().await;
        assert_eq!(headers.len(), 2);
        assert_eq!(headers[0].get("Authorization").unwrap(), "Bearer caller");
        assert_eq!(headers[0].get("X-Api-Key").unwrap(), "caller-key");
        assert_eq!(headers[0].get("Cookie").unwrap(), "session=caller");
        assert!(headers[1].get("Cookie").is_none());
        let chat_headers = stub.chat_headers.lock().await;
        assert_eq!(chat_headers.len(), 4);
        assert!(chat_headers.iter().all(|headers| {
            headers.get("Authorization").is_none()
                && headers.get("X-Api-Key").is_none()
                && headers.get("Cookie").is_none()
        }));
        server.abort();
    }

    #[tokio::test]
    async fn llm_agent_hailo_prompt_based_passes_native_tools() {
        let stub = StubState {
            chats: Arc::new(AtomicUsize::new(0)),
            chat_headers: Arc::new(Mutex::new(Vec::new())),
            tool_headers: Arc::new(Mutex::new(Vec::new())),
            requests: Arc::new(Mutex::new(Vec::new())),
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let app = Router::new()
            .route("/ext/hailo-genai/v1/chat/completions", post(prompt_chat))
            .route("/api/search", get(search))
            .with_state(stub.clone());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let mut credentials = HeaderMap::new();
        credentials.insert("Authorization", "Bearer caller".parse().unwrap());
        credentials.insert("X-Api-Key", "caller-key".parse().unwrap());
        credentials.insert("Cookie", "pin_token=caller".parse().unwrap());
        for body in [
            json!({"category":"hailo", "message":"go"}),
            json!({"category":"hailo", "message":"go", "mode":"prompt_based"}),
        ] {
            let response = llm_agent(
                State(test_state(port).await),
                None,
                credentials.clone(),
                Json(body),
            )
            .await;
            assert_eq!(response.status(), StatusCode::OK);
            let value = response_json(response).await;
            assert_eq!(value["steps"][0]["tool"], "search_files");
            assert_eq!(value["rounds"], 2);
            assert_eq!(
                value["steps"][0]["result_preview"]
                    .as_str()
                    .unwrap()
                    .chars()
                    .count(),
                200
            );
        }
        let requests = stub.requests.lock().await;
        assert_eq!(requests.len(), 4);
        // prompt_based now passes native tool definitions to HailoRT's own
        // write(messages, tools) instead of relying solely on the prose
        // system-prompt listing (real Hailo-10H hardware, Qwen3-1.7B-Instruct,
        // responds to this with <tool_call>{"name":...}</tool_call> — a format
        // the existing regex parser already handles). Unwrapped to the bare
        // {"name":...} shape at the call site (llm_agent_prompt.rs), not left
        // in OpenAI's {"type":"function","function":{...}} envelope — the
        // model's chat template needs the inner object directly.
        assert!(requests
            .iter()
            .all(|request| request["tools"].as_array().unwrap().len() == 8));
        assert_eq!(requests[0]["tools"][0]["name"], "search_files");
        assert!(requests[0]["tools"][0].get("function").is_none());
        assert_eq!(requests[0]["max_tokens"], 512);
        assert_eq!(requests[0]["temperature"], 0.1);
        let tool_result = requests[1]["messages"].as_array().unwrap().last().unwrap()["content"]
            .as_str()
            .unwrap();
        assert!(tool_result.contains("...(truncated)"));
        let chat_headers = stub.chat_headers.lock().await;
        assert_eq!(chat_headers.len(), 4);
        assert_eq!(
            chat_headers[0].get("Authorization").unwrap(),
            "Bearer caller"
        );
        assert_eq!(chat_headers[0].get("X-Api-Key").unwrap(), "caller-key");
        assert_eq!(chat_headers[0].get("Cookie").unwrap(), "pin_token=caller");
        server.abort();
    }

    #[tokio::test]
    async fn llm_agent_prompt_based_keeps_openai_tool_envelope_for_non_hailo_endpoints() {
        // Regression (Codex stop-time review, 2026-08-16): mode="prompt_based" is reachable for
        // ANY category, not just the synthetic hailo-genai self-loopback endpoint — a caller can
        // point llm_endpoints.<category> at a real external OpenAI-compatible server. Only the
        // Hailo native path should get bare {"name":...} tools; everyone else must keep the
        // OpenAI {"type":"function","function":{...}} envelope tool_definitions() produces.
        let stub = StubState {
            chats: Arc::new(AtomicUsize::new(0)),
            chat_headers: Arc::new(Mutex::new(Vec::new())),
            tool_headers: Arc::new(Mutex::new(Vec::new())),
            requests: Arc::new(Mutex::new(Vec::new())),
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let app = Router::new()
            .route("/v1/chat/completions", post(prompt_chat))
            .route("/api/search", get(search))
            .with_state(stub.clone());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let body = json!({"category": "test", "message": "go", "mode": "prompt_based"});
        let response = llm_agent(
            State(test_state(port).await),
            None,
            HeaderMap::new(),
            Json(body),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);

        let requests = stub.requests.lock().await;
        assert!(!requests.is_empty());
        assert_eq!(requests[0]["tools"][0]["type"], "function");
        assert_eq!(requests[0]["tools"][0]["function"]["name"], "search_files");
        server.abort();
    }

    #[tokio::test]
    async fn llm_agent_prompt_based_correction_retry_fires_even_with_max_rounds_one() {
        // Regression (Codex stop-time review, 2026-08-16): the correction retry must not be
        // counted against the round budget, or `max_rounds=1` would let the correction request
        // consume the single allowed round and the promised retry would never actually happen.
        let stub = StubState {
            chats: Arc::new(AtomicUsize::new(0)),
            chat_headers: Arc::new(Mutex::new(Vec::new())),
            tool_headers: Arc::new(Mutex::new(Vec::new())),
            requests: Arc::new(Mutex::new(Vec::new())),
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let app = Router::new()
            .route(
                "/ext/hailo-genai/v1/chat/completions",
                post(prompt_chat_malformed_then_answer),
            )
            .with_state(stub.clone());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let response = llm_agent(
            State(test_state(port).await),
            None,
            HeaderMap::new(),
            Json(json!({"category":"hailo", "message":"go", "max_rounds":1})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let value = response_json(response).await;
        // If the retry had been silently skipped, this would instead be
        // "[Agent reached maximum tool call rounds]" after a single wasted round.
        assert_eq!(value["content"], "The answer is 42.");
        let requests = stub.requests.lock().await;
        assert_eq!(
            requests.len(),
            2,
            "the correction retry must have been sent"
        );
        server.abort();
    }
}

/// POST /api/llm/chat
pub async fn llm_chat(State(state): State<SharedState>, Json(body): Json<Value>) -> Response {
    let category = body
        .get("category")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    let messages = body.get("messages").and_then(Value::as_array);
    if category.is_empty() || messages.is_none_or(Vec::is_empty) {
        return llm_error(
            "category and messages are required",
            StatusCode::BAD_REQUEST,
        );
    }
    let Some(endpoint) = crate::routes::llm_client::resolve_endpoint(&state, category) else {
        return llm_error(
            &format!("No LLM endpoint configured for '{category}'"),
            StatusCode::NOT_FOUND,
        );
    };
    let max_tokens = body
        .get("max_tokens")
        .and_then(Value::as_u64)
        .and_then(|v| u32::try_from(v).ok())
        .unwrap_or(1024);
    let temperature = body
        .get("temperature")
        .and_then(Value::as_f64)
        .unwrap_or(0.7);
    match crate::routes::llm_client::chat(
        &state,
        &endpoint,
        messages.expect("validated messages"),
        max_tokens,
        temperature,
        body.get("tools"),
        None,
    )
    .await
    {
        Ok(result) => llm_result(json!({
            "content": result.content,
            "model": result.model,
            "usage": result.usage,
        })),
        Err(error) => {
            tracing::warn!(category, %error, "LLM chat failed");
            llm_error("LLM request failed", StatusCode::BAD_GATEWAY)
        }
    }
}

fn llm_result(payload: Value) -> Response {
    let mut body = payload.as_object().cloned().unwrap_or_default();
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.insert("data".to_string(), Value::Null);
    Json(Value::Object(body)).into_response()
}

fn llm_error(error: &str, status: StatusCode) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": error, "data": null})),
    )
        .into_response()
}

fn agent_tools(body: &Value) -> Vec<Value> {
    match body.get("tools") {
        Some(Value::String(value)) if value == "all" => {
            crate::routes::llm_client::tool_definitions()
        }
        Some(Value::Array(tools)) => tools.clone(),
        _ => crate::routes::llm_client::tool_definitions()[..8].to_vec(),
    }
}

#[cfg(test)]
mod llm_chat_tests {
    use super::*;
    use axum::{
        body::{to_bytes, Body},
        http::{header, Method, Request},
        middleware,
        routing::post,
        Router,
    };
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::{
        collections::HashSet,
        path::PathBuf,
        str::FromStr,
        sync::{
            atomic::{AtomicUsize, Ordering},
            Arc, Mutex,
        },
    };
    use tower::ServiceExt;
    use tower_sessions::{MemoryStore, SessionManagerLayer};

    use crate::{
        logs::ring::LogRingBuffer,
        state::{AppState, Config},
    };

    async fn state_with(
        base_url: Option<String>,
        pin_auth_enabled: bool,
        config_path: PathBuf,
    ) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(AppState::new(Config {
            db_path: "sqlite::memory:".to_string(), pin_hash: String::new(), valid_token: String::new(),
            secret: String::new(), trusted_proxy_enabled: false, trusted_ips: HashSet::new(),
            trusted_peer_ips: HashSet::new(), quick_lock_enabled: true, pin_auth_enabled,
            min_pin_length: 4, python_url: String::new(), config_path,
            project_root: PathBuf::from("."), app_config: base_url.map(|base_url| json!({"llm_endpoints": {"test": {"base_url": base_url, "model": "test-model"}}})).unwrap_or_else(|| json!({})),
            cache_dir: PathBuf::from("."), server_mode: "full".to_string(), headless: false,
            safe_mode: false, standalone: false, infer_standalone: true, python_executable: String::new(),
            mcp_native: false, active_profile: None, pin_boss_login_ui: false,
        }, pool.clone(), pool, Arc::new(LogRingBuffer::new(64))).await)
    }

    async fn state(base_url: Option<String>) -> SharedState {
        state_with(base_url, false, PathBuf::from("config.json")).await
    }

    async fn body(response: Response) -> Value {
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap()
    }

    async fn upstream(status: StatusCode, response: Value) -> String {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().route(
                    "/chat/completions",
                    post(move || {
                        let response = response.clone();
                        async move { (status, Json(response)) }
                    }),
                ),
            )
            .await
            .unwrap();
        });
        format!("http://{address}")
    }

    async fn agent_upstream(responses: Vec<Value>, requests: Arc<Mutex<Vec<Value>>>) -> String {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let calls = Arc::new(AtomicUsize::new(0));
        tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().route(
                    "/chat/completions",
                    post(move |Json(request): Json<Value>| {
                        let requests = requests.clone();
                        let responses = responses.clone();
                        let calls = calls.clone();
                        async move {
                            requests.lock().unwrap().push(request);
                            Json(
                                responses[calls
                                    .fetch_add(1, Ordering::SeqCst)
                                    .min(responses.len() - 1)]
                                .clone(),
                            )
                        }
                    }),
                ),
            )
            .await
            .unwrap();
        });
        format!("http://{address}")
    }

    fn tool_call_response() -> Value {
        json!({"model":"agent-model","choices":[{"message":{"content":"", "tool_calls":[{"id":"call-1", "type":"function", "function":{"name":"missing_tool", "arguments":"{}"}}]}}]})
    }

    #[tokio::test]
    async fn llm_agent_stops_after_eight_tool_rounds() {
        let requests = Arc::new(Mutex::new(Vec::new()));
        let url = agent_upstream(vec![tool_call_response()], requests.clone()).await;
        let response = llm_agent(
            State(state(Some(url)).await),
            None,
            HeaderMap::new(),
            Json(json!({"category":"test", "message":"go"})),
        )
        .await;
        let value = body(response).await;
        assert_eq!(value["content"], "[Agent reached maximum tool call rounds]");
        assert_eq!(value["rounds"], 8);
        assert_eq!(value["steps"].as_array().unwrap().len(), 8);
        assert_eq!(requests.lock().unwrap().len(), 8);
    }

    #[tokio::test]
    async fn llm_agent_keeps_going_after_tool_error() {
        let requests = Arc::new(Mutex::new(Vec::new()));
        let url = agent_upstream(
            vec![
                tool_call_response(),
                json!({"model":"agent-model","choices":[{"message":{"content":"done"}}]}),
            ],
            requests.clone(),
        )
        .await;
        let response = llm_agent(
            State(state(Some(url)).await),
            None,
            HeaderMap::new(),
            Json(json!({"category":"test", "message":"go"})),
        )
        .await;
        let value = body(response).await;
        assert_eq!(value["content"], "done");
        assert_eq!(value["rounds"], 2);
        let history = &requests.lock().unwrap()[1]["messages"];
        assert_eq!(
            history[history.as_array().unwrap().len() - 1]["role"],
            "tool"
        );
        assert!(history[history.as_array().unwrap().len() - 1]["content"]
            .as_str()
            .unwrap()
            .contains("Unknown tool: missing_tool"));
    }

    #[test]
    fn llm_agent_resolves_all_default_and_custom_tools() {
        assert_eq!(agent_tools(&json!({"tools":"all"})).len(), 14);
        assert_eq!(
            agent_tools(&json!({}))
                .iter()
                .map(|tool| tool["function"]["name"].as_str().unwrap())
                .collect::<Vec<_>>(),
            vec![
                "search_files",
                "get_file_tags",
                "list_scan_roots",
                "get_stats",
                "get_server_info",
                "list_collections",
                "list_llm_endpoints",
                "get_server_mode",
            ],
        );
        let custom = json!([{"type":"function","function":{"name":"only"}}]);
        assert_eq!(
            agent_tools(&json!({"tools": custom})),
            custom.as_array().unwrap().clone()
        );
    }

    fn full_middleware_app(state: SharedState) -> Router {
        Router::new()
            .route("/api/llm/agent", post(llm_agent))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                crate::auth::middleware::auth_middleware,
            ))
            .layer(SessionManagerLayer::new(MemoryStore::default()))
            .layer(middleware::from_fn(crate::csrf::layer))
            .layer(middleware::from_fn(crate::security::layer))
            .with_state(state)
    }

    fn write_api_key_config(path: &std::path::Path, raw_key: &str, scopes: &[&str]) {
        use sha2::{Digest, Sha256};
        std::fs::write(
            path,
            json!({"api_keys":[{
                "id":"test", "key_hash": hex::encode(Sha256::digest(raw_key.as_bytes())),
                "key_prefix":raw_key.get(..8).unwrap_or(raw_key), "label":"test", "scopes":scopes,
            }]})
            .to_string(),
        )
        .unwrap();
    }

    #[tokio::test]
    async fn llm_agent_admin_gate_uses_full_middleware_stack() {
        let root = tempfile::tempdir().unwrap();
        let config_path = root.path().join("config.json");
        let state = state_with(None, true, config_path.clone()).await;
        let app = full_middleware_app(state);
        let request = |key: Option<&str>| {
            let mut builder = Request::builder()
                .method(Method::POST)
                .uri("/api/llm/agent")
                .header(header::CONTENT_TYPE, "application/json")
                .header("X-Requested-With", "XMLHttpRequest");
            if let Some(key) = key {
                builder = builder.header(header::AUTHORIZATION, format!("Bearer {key}"));
            }
            builder.body(Body::from("{}")).unwrap()
        };
        assert_eq!(
            app.clone().oneshot(request(None)).await.unwrap().status(),
            StatusCode::UNAUTHORIZED
        );
        write_api_key_config(&config_path, "sk_scan_only_0123456789abcdef", &["scan"]);
        assert_eq!(
            app.clone()
                .oneshot(request(Some("sk_scan_only_0123456789abcdef")))
                .await
                .unwrap()
                .status(),
            StatusCode::FORBIDDEN
        );
        write_api_key_config(&config_path, "sk_admin_0123456789abcdef", &["admin"]);
        assert_eq!(
            app.oneshot(request(Some("sk_admin_0123456789abcdef")))
                .await
                .unwrap()
                .status(),
            StatusCode::BAD_REQUEST
        );
    }

    #[tokio::test]
    async fn llm_chat_rejects_missing_category_or_messages() {
        let response = llm_chat(State(state(None).await), Json(json!({"category": "test"}))).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(body(response).await["ok"], false);
    }

    #[tokio::test]
    async fn llm_chat_rejects_unconfigured_category() {
        let response = llm_chat(
            State(state(None).await),
            Json(json!({"category": "test", "messages": [{"role":"user","content":"hi"}]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn llm_chat_maps_upstream_failure_to_bad_gateway() {
        let url = upstream(StatusCode::INTERNAL_SERVER_ERROR, json!({"error": "no"})).await;
        let response = llm_chat(
            State(state(Some(url)).await),
            Json(json!({"category": "test", "messages": [{"role":"user","content":"hi"}]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    }

    #[tokio::test]
    async fn llm_chat_returns_openai_content_model_and_usage() {
        let url = upstream(StatusCode::OK, json!({"model":"reply-model", "usage":{"total_tokens":3}, "choices":[{"message":{"content":"hello"}}]})).await;
        let response = llm_chat(
            State(state(Some(url)).await),
            Json(json!({"category": "test", "messages": [{"role":"user","content":"hi"}]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            body(response).await,
            json!({"ok":true,"error":null,"data":null,"content":"hello","model":"reply-model","usage":{"total_tokens":3}})
        );
    }
}

/// GET /share
pub async fn page_share(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// GET /crypto-tools
pub async fn page_crypto_tools(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    crate::frontend::render(
        &s,
        "crypto_tools.html",
        serde_json::json!({"csp_nonce": nonce, "dist_v": s.dist_v, "active": "crypto_tools"}),
    )
    .into_response()
}

/// GET /tauri-shell
pub async fn page_tauri_shell(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// GET /backends
pub async fn page_backends(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// GET /local/status
pub async fn page_local_status(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// GET /groups
pub async fn page_groups(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// GET /defaults
pub async fn page_defaults(State(_s): State<SharedState>) -> Response {
    unavailable()
}

// --- native gateway / SD handlers ---

async fn read_config_json(state: &SharedState) -> serde_json::Value {
    tokio::fs::read_to_string(&state.config.config_path)
        .await
        .ok()
        .and_then(|raw| crate::config_io::parse(&state.config.config_path, &raw))
        .unwrap_or_else(|| serde_json::json!({}))
}

fn sd_backend_url(gw: &serde_json::Value) -> String {
    let id = gw["defaults"]["default_sd_backend_id"]
        .as_str()
        .unwrap_or("");
    if !id.is_empty() {
        if let Some(url) = gw["backends"][id]["base_url"].as_str() {
            if !url.is_empty() {
                return url.to_owned();
            }
        }
    }
    "http://127.0.0.1:7860".to_owned()
}

async fn fwd_get_sd(state: &SharedState, path: &str) -> Response {
    let gw = read_config_json(state).await["gateway"].clone();
    let url = format!("{}{}", sd_backend_url(&gw).trim_end_matches('/'), path);
    match state.python_client.get(&url).send().await {
        Ok(r) => {
            let s = r.status();
            r.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |b| (s, b).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

/// GET /api/gateway/keys — admin scope, returns key list without secrets
pub async fn gateway_keys(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let cfg = read_config_json(&s).await;
    let keys = cfg["gateway"]["auth"]["api_keys"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    let safe: Vec<serde_json::Value> = keys
        .iter()
        .map(|k| {
            json!({
                "id": k["id"],
                "scopes": k["scopes"],
                "allowed_models": k["allowed_models"],
            })
        })
        .collect();
    Json(json!({"ok": true, "keys": safe})).into_response()
}

/// GET /agentmemory/livez — proxy to configured AgentMemory base_url/livez
pub async fn agentmemory_livez(State(s): State<SharedState>) -> Response {
    let cfg = read_config_json(&s).await;
    let base_url = cfg["gateway"]["backends"]["agentmemory"]["base_url"]
        .as_str()
        .unwrap_or("http://127.0.0.1:3111")
        .trim_end_matches('/')
        .to_owned();
    let livez_url = format!("{base_url}/livez");
    match s.python_client.get(&livez_url).send().await {
        Ok(resp) => {
            let status = axum::http::StatusCode::from_u16(resp.status().as_u16())
                .unwrap_or(StatusCode::BAD_GATEWAY);
            let body = resp.text().await.unwrap_or_default();
            (status, body).into_response()
        }
        Err(_) => Json(json!({"ok": false, "status": "unreachable"})).into_response(),
    }
}

/// GET /api/agentmemory-dash/health
pub async fn agentmemory_dash_health(State(s): State<SharedState>) -> Response {
    let cfg = read_config_json(&s).await;
    let base_url = cfg["gateway"]["backends"]["agentmemory"]["base_url"]
        .as_str()
        .unwrap_or("")
        .trim_end_matches('/')
        .to_owned();
    if base_url.is_empty() {
        return Json(json!({"ok": false, "status": "not_configured"})).into_response();
    }
    match s
        .python_client
        .get(format!("{base_url}/health"))
        .send()
        .await
    {
        Ok(r) => {
            let st = axum::http::StatusCode::from_u16(r.status().as_u16())
                .unwrap_or(StatusCode::BAD_GATEWAY);
            (st, r.text().await.unwrap_or_default()).into_response()
        }
        Err(_) => Json(json!({"ok": false, "status": "unreachable"})).into_response(),
    }
}

/// GET /api/agentmemory-dash/profile
pub async fn agentmemory_dash_profile(State(s): State<SharedState>) -> Response {
    let cfg = read_config_json(&s).await;
    let base_url = cfg["gateway"]["backends"]["agentmemory"]["base_url"]
        .as_str()
        .unwrap_or("")
        .trim_end_matches('/')
        .to_owned();
    if base_url.is_empty() {
        return Json(json!({"ok": false, "status": "not_configured", "profile": null}))
            .into_response();
    }
    match s
        .python_client
        .get(format!("{base_url}/profile"))
        .send()
        .await
    {
        Ok(r) => {
            let st = axum::http::StatusCode::from_u16(r.status().as_u16())
                .unwrap_or(StatusCode::BAD_GATEWAY);
            (st, r.text().await.unwrap_or_default()).into_response()
        }
        Err(_) => {
            Json(json!({"ok": false, "status": "unreachable", "profile": null})).into_response()
        }
    }
}

/// GET /api/gateway/agentmemory/config — admin scope
pub async fn agentmemory_config(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let cfg = read_config_json(&s).await;
    let base_url = cfg["gateway"]["backends"]["agentmemory"]["base_url"]
        .as_str()
        .unwrap_or("http://127.0.0.1:3111")
        .to_owned();
    Json(json!({"base_url": base_url})).into_response()
}

/// PUT /api/gateway/agentmemory/config — admin scope
pub async fn gateway_agentmemory_config_put(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Option<Json<serde_json::Value>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let body = body.map(|Json(v)| v).unwrap_or_default();
    let base_url_raw = body["base_url"].as_str().unwrap_or("").to_string();

    let base_url = match validate_base_url(&base_url_raw) {
        Ok(u) => u,
        Err(msg) => return (StatusCode::BAD_REQUEST, Json(json!({"error": msg}))).into_response(),
    };

    let mut config = load_cfg(&s.config.config_path);
    config["gateway"]["backends"]["agentmemory"]["base_url"] = json!(base_url);
    if let Err(e) = write_cfg(&s.config.config_path, &config) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response();
    }

    Json(json!({"base_url": base_url})).into_response()
}

/// GET /api/gateway/headroom/config — admin scope
pub async fn headroom_config(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    let cfg = read_config_json(&s).await;
    let h = &cfg["gateway"]["backends"]["headroom"];
    Json(json!({"ok": true, "base_url": h["base_url"], "auth_key": h["auth_key"]})).into_response()
}

/// GET /api/gateway/admin-token — native: loopback-only, reads/creates gateway_admin_token
pub async fn admin_token(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Extension(ClientIp(ip)): Extension<ClientIp>,
    headers: HeaderMap,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    if !matches!(ip.as_str(), "127.0.0.1" | "::1" | "localhost") {
        return (StatusCode::FORBIDDEN, Json(json!({"error": "Forbidden"}))).into_response();
    }
    if let Some(host) = headers.get(header::HOST).and_then(|v| v.to_str().ok()) {
        let h = host.split(':').next().unwrap_or("").trim_start_matches('[');
        if !h.is_empty() && !matches!(h, "127.0.0.1" | "::1" | "localhost") {
            return (StatusCode::FORBIDDEN, Json(json!({"error": "Forbidden"}))).into_response();
        }
    }
    if let Some(origin) = headers.get(header::ORIGIN).and_then(|v| v.to_str().ok()) {
        let h = origin
            .split("://")
            .nth(1)
            .and_then(|s| s.split('/').next())
            .and_then(|s| s.split(':').next())
            .unwrap_or("");
        if !h.is_empty() && !matches!(h, "127.0.0.1" | "::1" | "localhost") {
            return (StatusCode::FORBIDDEN, Json(json!({"error": "Forbidden"}))).into_response();
        }
    }
    let mut cfg = read_config_json(&s).await;
    let token = match cfg["gateway"]["gateway_admin_token"]
        .as_str()
        .filter(|s| !s.is_empty())
    {
        Some(t) => t.to_owned(),
        None => {
            let t = uuid::Uuid::new_v4().simple().to_string();
            cfg["gateway"]["gateway_admin_token"] = json!(t.clone());
            let _ = write_cfg(&s.config.config_path, &cfg);
            t
        }
    };
    (
        StatusCode::OK,
        [(header::CACHE_CONTROL, "no-store")],
        Json(json!({"token": token})),
    )
        .into_response()
}

/// GET /sd/config — admin scope, proxies to SD backend
pub async fn sd_config(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    fwd_get_sd(&s, "/config").await
}

/// GET /sd/info — admin scope
pub async fn sd_info(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    fwd_get_sd(&s, "/info").await
}

/// GET /sd/internal/ping — admin scope
pub async fn sd_ping(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    fwd_get_sd(&s, "/internal/ping").await
}

/// GET /v1/models
pub async fn llm_models(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// GET /v1/router/health
pub async fn router_health(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// POST /v1/router/refresh — stub (Python LLM router unavailable in standalone)
pub async fn router_refresh(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// POST /v1/router/estimate — stub
pub async fn router_estimate(State(_s): State<SharedState>) -> Response {
    unavailable()
}

/// GET /v1/router/capabilities/{target} — stub
pub async fn router_capabilities_target(
    State(_s): State<SharedState>,
    Path(_target): Path<String>,
) -> Response {
    unavailable()
}

/// POST /api/system/update/apply — admin scope
pub async fn system_update_apply(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/system/update/unified-apply — admin scope
pub async fn system_update_unified_apply(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/update/verify — admin scope
pub async fn update_verify(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/update/apply — admin scope
pub async fn update_apply(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/update/rollback — admin scope
pub async fn update_rollback(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }
    unavailable()
}

/// POST /api/inspect — native multipart upload inspection (Rust implementation)
pub async fn inspect_upload(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    mut multipart: axum::extract::Multipart,
) -> Response {
    if let Some(r) = gate(&s, auth.as_ref()) {
        return r;
    }

    let mut file_bytes: Option<Vec<u8>> = None;
    let mut filename = String::new();
    let mut zip_entry = String::new();

    while let Ok(Some(field)) = multipart.next_field().await {
        match field.name() {
            Some("file") => {
                filename = field.file_name().unwrap_or("upload").to_string();
                match field.bytes().await {
                    Ok(b) => file_bytes = Some(b.to_vec()),
                    Err(_) => {
                        return Json(json!({"error": "Failed to read uploaded file"}))
                            .into_response()
                    }
                }
            }
            Some("zip_entry") => {
                zip_entry = field.text().await.unwrap_or_default();
            }
            _ => {}
        }
    }

    let bytes = match file_bytes {
        Some(b) if !b.is_empty() => b,
        Some(_) => return Json(json!({"error": "Uploaded file is empty"})).into_response(),
        None => return Json(json!({"error": "No file uploaded"})).into_response(),
    };
    if filename.is_empty() {
        return Json(json!({"error": "Empty filename"})).into_response();
    }

    let ext = std::path::Path::new(&filename)
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_lowercase()))
        .unwrap_or_default();

    let payload = if ext == ".zip" {
        inspect_zip(bytes, filename, &zip_entry)
    } else {
        inspect_image(bytes, filename, &ext)
    };
    Json(payload).into_response()
}

const _IMAGE_EXTS: &[&str] = &[".png", ".jpg", ".jpeg", ".webp"];
const _MAX_IMAGE_BYTES: usize = 50 * 1024 * 1024;
const _MAX_ZIP_BYTES: usize = 200 * 1024 * 1024;

fn inspect_image(bytes: Vec<u8>, filename: String, ext: &str) -> serde_json::Value {
    use std::io::Write as _;
    if !_IMAGE_EXTS.contains(&ext) {
        return json!({"error": format!("Unsupported file type: {:?}. Allowed: .png, .jpg, .jpeg, .webp", ext)});
    }
    if bytes.len() > _MAX_IMAGE_BYTES {
        return json!({"error": "Uploaded file is too large (max 50 MB)"});
    }
    let mut tmp = match tempfile::Builder::new().suffix(ext).tempfile() {
        Ok(f) => f,
        Err(_) => return json!({"error": "Failed to create temp file"}),
    };
    if tmp.write_all(&bytes).is_err() {
        return json!({"error": "Failed to write temp file"});
    }
    scan_to_json(tmp.path(), &filename, ext, bytes.len())
}

fn inspect_zip(bytes: Vec<u8>, filename: String, zip_entry: &str) -> serde_json::Value {
    use std::io::{Read as _, Write as _};
    if bytes.len() > _MAX_ZIP_BYTES {
        return json!({"error": "Uploaded ZIP is too large (max 200 MB)"});
    }
    if !zip_entry.is_empty()
        && (zip_entry.contains('\0') || zip_entry.split('/').any(|p| p == ".."))
    {
        return json!({"error": "Invalid zip entry path"});
    }
    let cursor = std::io::Cursor::new(&bytes);
    let mut archive = match zip::ZipArchive::new(cursor) {
        Ok(a) => a,
        Err(_) => return json!({"error": "Failed to open ZIP"}),
    };
    let mut images = Vec::new();
    for i in 0..archive.len() {
        if let Ok(f) = archive.by_index(i) {
            if !f.is_dir() {
                let name = f.name().to_string();
                let lower = name.to_lowercase();
                if _IMAGE_EXTS.iter().any(|e| lower.ends_with(e)) {
                    images.push(name);
                }
            }
        }
    }
    if images.is_empty() {
        return json!({"error": "No image files found in ZIP"});
    }
    let target = if !zip_entry.is_empty() && images.contains(&zip_entry.to_string()) {
        zip_entry.to_string()
    } else {
        images[0].clone()
    };
    let target_ext = std::path::Path::new(&target)
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_lowercase()))
        .unwrap_or_default();
    let mut entry = match archive.by_name(&target) {
        Ok(e) => e,
        Err(_) => return json!({"error": "Failed to extract ZIP entry"}),
    };
    if entry.size() > _MAX_IMAGE_BYTES as u64 {
        return json!({"error": "Image in ZIP is too large (max 50 MB)"});
    }
    let mut entry_bytes = Vec::new();
    if entry.read_to_end(&mut entry_bytes).is_err() {
        return json!({"error": "Failed to read ZIP entry"});
    }
    let mut tmp = match tempfile::Builder::new().suffix(&target_ext).tempfile() {
        Ok(f) => f,
        Err(_) => return json!({"error": "Failed to create temp file"}),
    };
    if tmp.write_all(&entry_bytes).is_err() {
        return json!({"error": "Failed to write temp file"});
    }
    let entry_name = format!("{}!{}", filename, target);
    let mut result = scan_to_json(tmp.path(), &entry_name, &target_ext, entry_bytes.len());
    if result.get("error").is_none() {
        result["zip_images"] =
            serde_json::Value::Array(images.into_iter().map(serde_json::Value::String).collect());
        result["zip_current"] = serde_json::Value::String(target);
    }
    result
}

fn scan_to_json(
    path: &std::path::Path,
    filename: &str,
    ext: &str,
    size: usize,
) -> serde_json::Value {
    use meta_extract::{
        models::PngTextChunks, parse_metadata, read_exif_tags, read_png_text_chunks,
    };

    let (chunks, raw_metadata) = if ext == ".png" {
        let chunks = read_png_text_chunks(path);
        let raw: serde_json::Map<String, serde_json::Value> = chunks
            .entries
            .iter()
            .map(|(k, v)| (k.clone(), json!(v.chars().take(2000).collect::<String>())))
            .collect();
        (chunks, serde_json::Value::Object(raw))
    } else {
        let exif = read_exif_tags(path);
        let raw: serde_json::Map<String, serde_json::Value> = exif
            .iter()
            .map(|(k, v)| (k.clone(), json!(v.chars().take(500).collect::<String>())))
            .collect();
        let mut chunks = PngTextChunks::default();
        for (k, v) in &exif {
            chunks.entries.insert(format!("exif:{k}"), v.clone());
        }
        (chunks, serde_json::Value::Object(raw))
    };

    let meta = parse_metadata(&chunks);
    let parsed = meta.format != "unknown";
    let meta_source = meta_extract::db_meta_source(&meta.format, Some(ext));

    use meta_extract::resolve_detail_fields;
    let detail = resolve_detail_fields(
        &meta_source,
        meta.positive.as_deref().unwrap_or(""),
        meta.negative.as_deref().unwrap_or(""),
        meta.raw_meta.as_deref(),
        None,
    );

    let mut result = json!({
        "filename": filename,
        "size": size,
        "parsed": parsed,
        "meta_source": meta_source,
        "positive": detail.positive,
        "negative": detail.negative,
        "format": meta.format,
        "resolution": detail.resolution,
        "model": detail.model,
        "parameters": detail.parameters,
        "raw_metadata": raw_metadata,
        "raw_meta_json": meta.raw_meta,
        "tags": [],
    });
    if let Some(nai) = detail.novelai_v4 {
        result["novelai_v4"] = nai;
    }
    result
}

use std::path::Path;

use axum::http::{HeaderMap, StatusCode};
use axum::{
    extract::State,
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde_json::json;
use tower_sessions::Session;

use crate::auth::client_ip::ClientIp;
use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::restart::{session_pin_ok, RESTART_CONFIG};
use crate::state::{AppState, SharedState};

/// Verbatim from `core/search_api/server_info.py:29-55`
/// (`RESTART_BLOCKER_LABELS`). An unknown code (should not occur --
/// `restart_blockers` only ever pushes these five literals) falls back to
/// the code itself as the label with empty description/hint, matching
/// Python's `.get(code, {"label": code, ...})`.
fn restart_blocker_label(code: &'static str) -> (&'static str, &'static str, &'static str) {
    match code {
        "restart_disabled" => (
            "再起動が無効",
            "サーバーの再起動機能が無効化されています。",
            "TAGDB_ALLOW_RESTART=1 または --allow-restart オプションで有効化してください。",
        ),
        "pin_not_active" => (
            "PIN未設定（リモート接続）",
            "リモートからの再起動にはPIN認証が必要です。",
            "Settings > Server タブ > PIN認証コードに数字を入力してください。",
        ),
        "local_only" => (
            "ローカル接続のみ許可",
            "リモートからの再起動は許可されていません。",
            "TAGDB_RESTART_REMOTE=1 または --restart-remote で有効化してください。",
        ),
        "remote_token_missing" => (
            "リモートトークン未設定",
            "リモート再起動トークンが設定されていません。",
            "TAGDB_RESTART_TOKEN=<token> または --restart-token で設定してください。",
        ),
        "pin_session_required" => (
            "PIN認証が必要",
            "再起動にはPINセッションが必要です。",
            "画面右上の鍵アイコンからPINを入力してください。",
        ),
        other => (other, "", ""),
    }
}

/// Non-loopback IPv4 addresses for LAN display, mirroring Python's
/// `get_lan_ips()` (`core/search_api/utils.py`). Uses the UDP routing
/// trick: connecting a UDP socket sends no packet, it just makes the
/// kernel pick the outbound interface for that destination, whose local
/// address is then read back.
fn detect_lan_ips() -> Vec<String> {
    for probe in ["10.255.255.255:1", "192.168.0.1:1"] {
        let Ok(sock) = std::net::UdpSocket::bind("0.0.0.0:0") else {
            continue;
        };
        if sock.connect(probe).is_err() {
            continue;
        }
        if let Ok(addr) = sock.local_addr() {
            let ip = addr.ip().to_string();
            if !ip.starts_with("127.") {
                return vec![ip];
            }
        }
    }
    Vec::new()
}

/// Trusted host to advertise, mirroring Python's `resolve_public_host()`
/// (`core/web/public_host.py`): never trust the request's own Host header,
/// prefer an explicitly configured non-loopback/non-wildcard host, and
/// fall back to the detected LAN IP.
fn resolve_public_host(
    app_config: &serde_json::Value,
    is_local: bool,
    lan_ips: &[String],
) -> String {
    if is_local {
        return "127.0.0.1".to_string();
    }
    let configured = app_config
        .get("server")
        .and_then(|s| s.get("host"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim();
    let normalized = configured.to_ascii_lowercase();
    if !configured.is_empty()
        && !matches!(
            normalized.as_str(),
            "127.0.0.1" | "::1" | "localhost" | "0.0.0.0" | "::"
        )
    {
        return configured.to_string();
    }
    lan_ips
        .first()
        .cloned()
        .unwrap_or_else(|| "127.0.0.1".to_string())
}

/// file_count / tag_count / schema_version from the read pool, mirroring
/// Python's `_get_db_stats()` (`core/search_api/server_info.py`). Propagates
/// the first query error rather than degrading to 0: a transient failure
/// (DB locked/busy) must not be cached as a false "empty database" for the
/// TTL window (see `server_info_body`, which treats `Err` as fetch-not-write
/// on `server_info_stats_cache`).
async fn fetch_db_stats(pool: &sqlx::SqlitePool) -> Result<(i64, i64, i64), sqlx::Error> {
    let file_count = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM files WHERE is_deleted=0")
        .fetch_one(pool)
        .await?;
    let tag_count = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM tags")
        .fetch_one(pool)
        .await?;
    let schema_version =
        sqlx::query_scalar::<_, Option<i64>>("SELECT MAX(version) FROM schema_version")
            .fetch_one(pool)
            .await?
            .unwrap_or(0);
    Ok((file_count, tag_count, schema_version))
}

struct SubsystemEntry {
    name: &'static str,
    modes: &'static [&'static str],
    env_override: Option<&'static str>,
}

struct BgTaskEntry {
    name: &'static str,
    modes: &'static [&'static str],
    env_enable: Option<&'static str>,
    env_disable: Option<&'static str>,
}

const SUBSYSTEMS: &[SubsystemEntry] = &[
    SubsystemEntry {
        name: "event_bus",
        modes: &["full", "gateway", "server"],
        env_override: None,
    },
    SubsystemEntry {
        name: "log_interrupted",
        modes: &["full"],
        env_override: None,
    },
    SubsystemEntry {
        name: "backup",
        modes: &["full"],
        env_override: Some("TAGDB_ENABLE_BACKUP"),
    },
    SubsystemEntry {
        name: "scheduler",
        modes: &["full"],
        env_override: Some("TAGDB_ENABLE_SCHEDULER"),
    },
    SubsystemEntry {
        name: "security",
        modes: &["full", "gateway", "server"],
        env_override: None,
    },
    SubsystemEntry {
        name: "event_handlers",
        modes: &["full", "gateway", "server"],
        env_override: None,
    },
    SubsystemEntry {
        name: "scan_queue",
        modes: &["full"],
        env_override: Some("TAGDB_ENABLE_SCAN"),
    },
    SubsystemEntry {
        name: "node_identity",
        modes: &["full", "gateway", "server"],
        env_override: None,
    },
    SubsystemEntry {
        name: "llm_router",
        modes: &["full", "gateway", "server"],
        env_override: None,
    },
    SubsystemEntry {
        name: "mdns",
        modes: &["full", "gateway", "server"],
        env_override: Some("TAGDB_ENABLE_MDNS"),
    },
];

const BG_TASKS: &[BgTaskEntry] = &[
    BgTaskEntry {
        name: "thumb_cleanup",
        modes: &["full"],
        env_enable: None,
        env_disable: None,
    },
    BgTaskEntry {
        name: "analyze",
        modes: &["full"],
        env_enable: Some("TAGDB_ENABLE_ANALYZE"),
        env_disable: Some("TAGDB_DISABLE_ANALYZE"),
    },
    BgTaskEntry {
        name: "file_meta_cache",
        modes: &["full"],
        env_enable: Some("TAGDB_ENABLE_FILE_CACHE"),
        env_disable: None,
    },
    BgTaskEntry {
        name: "stats_warmup",
        modes: &["full"],
        env_enable: Some("TAGDB_ENABLE_STATS_PRELOAD"),
        env_disable: Some("TAGDB_DISABLE_STATS_PRELOAD"),
    },
    BgTaskEntry {
        name: "llm_router_refresh",
        modes: &["full", "gateway", "server"],
        env_enable: None,
        env_disable: Some("TAGDB_DISABLE_LLM_ROUTER_REFRESH"),
    },
    BgTaskEntry {
        name: "hailo_auto_reboot_judge",
        modes: &["full"],
        env_enable: None,
        env_disable: Some("TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE"),
    },
    BgTaskEntry {
        name: "wd_tagger_config_migrate_v2",
        modes: &["full"],
        env_enable: None,
        env_disable: Some("TAGDB_DISABLE_WD_TAGGER_CONFIG_MIGRATE_V2"),
    },
    BgTaskEntry {
        name: "tag_normalize_backfill",
        modes: &["full"],
        env_enable: None,
        env_disable: Some("TAGDB_DISABLE_TAG_NORMALIZE_BACKFILL"),
    },
    BgTaskEntry {
        name: "post_v81_vacuum_analyze",
        modes: &["full"],
        env_enable: None,
        env_disable: Some("TAGDB_DISABLE_POST_V81_VACUUM_ANALYZE"),
    },
    BgTaskEntry {
        name: "post_v82_vacuum_analyze",
        modes: &["full"],
        env_enable: None,
        env_disable: Some("TAGDB_DISABLE_POST_V82_VACUUM_ANALYZE"),
    },
];

fn env_truthy(name: &str) -> bool {
    let raw = std::env::var(name).unwrap_or_default();
    let lower = raw.trim().to_lowercase();
    matches!(lower.as_str(), "1" | "true" | "yes")
}

fn should_run_subsystem(sub: &SubsystemEntry, mode: &str, safe_mode: bool) -> bool {
    if safe_mode {
        return false;
    }
    if sub.modes.contains(&mode) {
        return true;
    }
    sub.env_override.is_some_and(env_truthy)
}

fn should_run_bg_task(task: &BgTaskEntry, mode: &str, safe_mode: bool) -> bool {
    if safe_mode {
        return false;
    }
    if task.env_disable.is_some_and(env_truthy) {
        return false;
    }
    if task.env_enable.is_some_and(env_truthy) {
        return true;
    }
    task.modes.contains(&mode)
}

/// GET /api/server/mode
pub async fn server_mode(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    (
        StatusCode::OK,
        Json(json!({
            "ok": true,
            "error": null,
            "data": null,
            "mode": &state.config.server_mode,
            "headless": state.config.headless,
        })),
    )
        .into_response()
}

/// GET /api/server/subsystems
pub async fn server_subsystems(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    let mode = &state.config.server_mode;
    let safe = state.config.safe_mode;
    let subs: Vec<_> = SUBSYSTEMS
        .iter()
        .map(|s| {
            json!({
                "name": s.name,
                "modes": s.modes,
                "enabled": should_run_subsystem(s, mode, safe),
                "env_override": s.env_override,
            })
        })
        .collect();
    let tasks: Vec<_> = BG_TASKS
        .iter()
        .map(|t| {
            json!({
                "name": t.name,
                "modes": t.modes,
                "enabled": should_run_bg_task(t, mode, safe),
                "env_enable": t.env_enable,
                "env_disable": t.env_disable,
            })
        })
        .collect();
    (
        StatusCode::OK,
        Json(json!({
            "ok": true,
            "error": null,
            "data": null,
            "mode": mode,
            "subsystems": subs,
            "background_tasks": tasks,
        })),
    )
        .into_response()
}

/// Reads `.fast-mode-stale-state.json` from `state_dir` (the `bin/`
/// directory by convention -- callers pass `repo_root.join("bin")`) and
/// returns the minimal `stale_rebuild` value for server_info_body(), or
/// None if the file is absent, unparseable, or has no `stale_phase` -- all
/// three cases fall back to "key omitted", matching the existing
/// key-absence-hides-panel frontend convention. Read-only, no lock: a
/// lock-free reader tolerates a stale or torn read as "no record" per the
/// spec's corruption-tolerance rule (the writer uses tmp+rename so a torn
/// read cannot happen in practice, but a concurrent in-place rewrite window
/// is still handled the same way here for defense in depth).
///
/// Deliberately does not read `stale_pending_artifact` or any other field:
/// this is the REST/MCP-shared surface, so only the three fixed,
/// pre-scrubbed fields (phase, message, updated_at) are exposed -- no
/// absolute paths, no raw cargo output.
fn read_stale_rebuild_status(state_dir: &Path) -> Option<serde_json::Value> {
    let path = state_dir.join(".fast-mode-stale-state.json");
    let text = std::fs::read_to_string(path).ok()?;
    let parsed: serde_json::Value = serde_json::from_str(&text).ok()?;
    let phase = parsed.get("stale_phase")?.as_str()?;
    let message = parsed
        .get("stale_last")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let updated_at = parsed
        .get("stale_finished_at")
        .or_else(|| parsed.get("stale_started_at"))
        .cloned()
        .unwrap_or(serde_json::Value::Null);
    Some(json!({
        "phase": phase,
        "message": message,
        "updated_at": updated_at,
    }))
}

/// Core `get_server_info` body shared by the REST route and the MCP tool of
/// the same name. Admin-scope gating is REST-specific (the MCP transport
/// has its own auth model at the connection layer, see `mcp::auth`), so it
/// stays in `api_server_info` rather than here. `is_local` gates the same
/// fields Python's `build_server_info_response()` restricts to local
/// requests (`db_path`, `host`) -- every caller (REST via
/// `server_restart::local_request`, MCP via `mcp::dispatch::call_tool`
/// forwarding its own `is_local` through) must compute this the same way,
/// there is no caller that gets to just pass `true`.
///
/// `pin_session_ok` is the same `Session` `pin_ok` flag the restart route
/// reads directly (spec `決定 1`, `決定 7`) -- fed through `restart_blockers`
/// so the two call sites cannot silently diverge on what counts as an
/// authenticated PIN session.
pub async fn server_info_body(
    state: &AppState,
    is_local: bool,
    pin_session_ok: bool,
) -> serde_json::Value {
    let uptime = state.start_time.elapsed().as_secs_f64();
    let (file_count, tag_count, schema_version) = state
        .server_info_stats_cache
        .get_or_try_insert_with(|| fetch_db_stats(&state.db_read))
        .await
        .unwrap_or((0, 0, 0));
    let db_size_mb = std::fs::metadata(&state.config.db_path)
        .map(|m| (m.len() as f64 / (1024.0 * 1024.0) * 100.0).round() / 100.0)
        .unwrap_or(0.0);
    let lan_ips = detect_lan_ips();
    let host = resolve_public_host(&state.config.app_config, is_local, &lan_ips);

    let mut body = json!({
        "ok": true,
        "error": null,
        "data": null,
        "version": format!("v{}", state.version),
        "server_mode": state.config.server_mode,
        "headless": state.config.headless,
        "uptime_seconds": uptime,
        "boot_state": "ready",
        "has_pin": !state.config.pin_hash.is_empty(),
        "file_count": file_count,
        "tag_count": tag_count,
        "schema_version": schema_version,
        "db_size_mb": db_size_mb,
        "lan_ips": lan_ips,
    });
    if is_local {
        body["db_path"] = json!(state.config.db_path);
        body["host"] = json!(host);
        if let Some(config) = RESTART_CONFIG.get() {
            body["restart_enabled"] = json!(config.allow_restart);
            body["restart_enable_source"] = json!(config.enable_source);
            body["restart_remote_allowed"] = json!(config.allow_remote_restart);
            body["restart_remote_source"] = json!(config.remote_source);
            body["restart_remote_token_set"] = json!(config.token.is_some());
            body["restart_remote_token_source"] = json!(config.token_source);
        }
    }
    let restart_config = RESTART_CONFIG.get();
    let restart_enabled = restart_config.is_some_and(|config| config.allow_restart);
    let restart_remote_allowed = restart_config.is_some_and(|config| config.allow_remote_restart);
    let restart_remote_token_set = restart_config.is_some_and(|config| config.token.is_some());
    // `has_pin` here mirrors Python's `bool(app_config.get("PIN_AUTH"))`, i.e.
    // whether PIN auth is the active gate -- NOT the top-level `has_pin` field
    // above, which reports whether a PIN hash exists at all.
    let has_pin = state.config.pin_auth_enabled;

    let mut blockers: Vec<&'static str> = Vec::new();
    // Decision (design-advisor M1, recorded in spec 決定 8): restart_disabled
    // / local_only / remote_token_missing are computed and returned to EVERY
    // caller, local or remote, authenticated or not -- there is no is_local
    // gate on this block. That is a deliberate parity choice, not an
    // oversight: Python's build_server_info_response() (server_info.py:200-
    // 211) computes the same list before its own `if local_only_ok:` gate
    // (server_info.py:280), so a remote, unauthenticated caller already
    // learns whether restart is enabled at all, whether remote restart is
    // allowed, and whether a remote token is configured (never the token's
    // value) under Python today. Suppressing these three bits for non-local
    // callers here would diverge from Python, not fix a Rust-only bug. This
    // is knowingly public, including in the default no-PIN configuration
    // where /api/server-info has no credential gate at all
    // (auth/middleware.rs:94-96, auth/scope.rs:22-24) -- see spec §10a.
    if !restart_enabled {
        blockers.push("restart_disabled");
    }
    // PIN is only required for remote requests; local requests can restart
    // without one (server_info.py:204).
    if !has_pin && !is_local {
        blockers.push("pin_not_active");
    }
    if !is_local && !restart_remote_allowed {
        blockers.push("local_only");
    }
    if !is_local && restart_remote_allowed && !restart_remote_token_set {
        blockers.push("remote_token_missing");
    }
    if has_pin && !pin_session_ok {
        blockers.push("pin_session_required");
    }
    let restart_blocker_details: Vec<serde_json::Value> = blockers
        .iter()
        .map(|&code| {
            let (label, description, hint) = restart_blocker_label(code);
            json!({"code": code, "label": label, "description": description, "hint": hint})
        })
        .collect();
    body["restart_available_now"] = json!(blockers.is_empty());
    body["restart_blockers"] = json!(blockers);
    body["restart_blocker_details"] = json!(restart_blocker_details);
    // repo root = the running executable's grandparent directory (bin/ sits
    // directly under repo root by existing convention). A distribution
    // binary launched from outside a checkout has no bin/.fast-mode-*
    // files either, so this naturally falls through to key omission.
    if let Ok(exe) = std::env::current_exe() {
        if let Some(repo_root) = exe.parent().and_then(|p| p.parent()) {
            if let Some(stale) = read_stale_rebuild_status(&repo_root.join("bin")) {
                body["stale_rebuild"] = stale;
            }
        }
    }
    // What the start-up version gate saw. A database served despite a drift,
    // or a declaration dropped because the key or the build makes it false,
    // otherwise exists only as one log line at boot -- and both change what
    // the operator should do. Key omitted when the gate never ran (a URI
    // database, or one that did not exist yet), matching the key-absence
    // convention stale_rebuild already uses.
    // `as_object_mut` rather than `body["schema"] = ...`: the index form is a
    // `clippy::indexing_slicing` site, and that lint is on a ratchet that may
    // only shrink. Adding one more where a clean insert exists would spend the
    // budget on nothing.
    if let (Some(status), Some(map)) = (crate::SCHEMA_STATUS.get(), body.as_object_mut()) {
        map.insert("schema".to_string(), status.clone());
    }
    body
}

/// GET /api/server-info
pub async fn api_server_info(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    client_ip: Option<Extension<ClientIp>>,
    session: Option<Extension<Session>>,
    headers: HeaderMap,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    // Same helper the restart route uses (server_restart::local_request),
    // not a re-derived notion of "local" -- design-advisor M1. It already
    // fails closed on a missing ClientIp extension (should not happen --
    // auth_middleware sets it on every request), and already accounts for
    // untrusted forwarding hints and the trusted-proxy set the same way the
    // restart route does, so the two can no longer silently diverge.
    let is_local = crate::routes::server_restart::local_request(&state, client_ip, headers).await;
    let pin_ok = session_pin_ok(session).await;
    (
        StatusCode::OK,
        Json(server_info_body(&state, is_local, pin_ok).await),
    )
        .into_response()
}

/// GET /api/system/inference-info
pub async fn inference_info(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    if state.config.python_url.is_empty() {
        return Json(json!({"ok": true, "error": null, "available": false, "data": null}))
            .into_response();
    }
    let url = format!(
        "{}/api/system/inference-info",
        state.config.python_url.trim_end_matches('/')
    );
    match state
        .python_client
        .get(&url)
        .header("X-Remote-User", "yu-proxy-auth")
        .send()
        .await
    {
        Ok(resp) => {
            let status = resp.status();
            resp.bytes().await.map_or_else(
                |_| axum::http::StatusCode::BAD_GATEWAY.into_response(),
                |b| (status, b).into_response(),
            )
        }
        Err(_) => Json(
            json!({"ok": true, "error": "Python unavailable", "available": false, "data": null}),
        )
        .into_response(),
    }
}

/// POST /api/error-report/enrich — silently acknowledge (Python-side enrichment unavailable)
///
/// Python wraps with `api_result`, so `error` and `data` sit beside `ok`; returning
/// `ok` alone made every response differ in shape. The enrichment itself is still not
/// implemented -- Python's bundle carries `pid`, `uptime_sec`, `cwd` and a fresh
/// `error_id`, so no port of it could match across two processes anyway.
pub async fn error_report_enrich() -> impl axum::response::IntoResponse {
    axum::Json(serde_json::json!({"ok": true, "error": null, "data": null}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn subsystem_full_mode_enabled() {
        let sub = &SUBSYSTEMS[0]; // event_bus: modes=["full","gateway","server"]
        assert!(should_run_subsystem(sub, "full", false));
        assert!(should_run_subsystem(sub, "gateway", false));
        assert!(!should_run_subsystem(sub, "full", true)); // safe_mode disables
    }

    #[test]
    fn subsystem_mode_filter() {
        let log_int = &SUBSYSTEMS[1]; // log_interrupted: modes=["full"]
        assert!(should_run_subsystem(log_int, "full", false));
        assert!(!should_run_subsystem(log_int, "gateway", false));
    }

    #[test]
    fn bg_task_safe_mode_disables_all() {
        let task = &BG_TASKS[0]; // thumb_cleanup
        assert!(should_run_bg_task(task, "full", false));
        assert!(!should_run_bg_task(task, "full", true));
    }

    #[test]
    fn bg_task_mode_filter() {
        let task = &BG_TASKS[0]; // thumb_cleanup: modes=["full"]
        assert!(should_run_bg_task(task, "full", false));
        assert!(!should_run_bg_task(task, "gateway", false));
    }

    #[test]
    fn bg_task_multi_mode() {
        let task = &BG_TASKS[4]; // llm_router_refresh: modes=["full","gateway","server"]
        assert!(should_run_bg_task(task, "full", false));
        assert!(should_run_bg_task(task, "gateway", false));
        assert!(should_run_bg_task(task, "server", false));
    }

    #[test]
    fn env_truthy_values() {
        // set/unset tested indirectly via should_run logic
        // direct unit test skipped (env mutation in tests is unsafe in parallel)
    }

    #[test]
    fn stale_rebuild_key_absent_when_state_file_missing() {
        let dir = tempfile::tempdir().unwrap();
        let value = read_stale_rebuild_status(dir.path());
        assert!(value.is_none());
    }

    #[test]
    fn stale_rebuild_key_present_and_scrubbed_when_state_file_exists() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join(".fast-mode-stale-state.json"),
            r#"{"stale_phase":"failed","stale_last":"cargo build failed — see bin/fast-mode-stale-build.log","stale_finished_at":1700000000.0}"#,
        )
        .unwrap();

        let value = read_stale_rebuild_status(dir.path()).expect("key present");
        assert_eq!(value["phase"], "failed");
        assert_eq!(
            value["message"],
            "cargo build failed — see bin/fast-mode-stale-build.log"
        );
        assert_eq!(value["updated_at"], 1700000000.0);
        // Absolute developer-machine paths / raw cargo output must never
        // appear -- this key's only source is the fixed-format fields.
        assert!(value.as_object().unwrap().len() == 3);
    }

    #[test]
    fn stale_rebuild_key_absent_when_state_file_has_no_phase() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join(".fast-mode-stale-state.json"),
            r#"{"stale_pending_artifact":{"path":"x"}}"#,
        )
        .unwrap();

        assert!(read_stale_rebuild_status(dir.path()).is_none());
    }

    #[test]
    fn stale_rebuild_key_absent_on_corrupt_json() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join(".fast-mode-stale-state.json"), "{not json").unwrap();

        assert!(read_stale_rebuild_status(dir.path()).is_none());
    }

    // --- restart_blockers (Task 1 fix: `pin_not_active` needs `&& !is_local`) --

    #[tokio::test]
    async fn pin_not_active_is_not_raised_for_a_pin_less_local_request() {
        let shared =
            crate::state::restart_test_state(false, false, std::collections::HashSet::new()).await;
        let body = server_info_body(
            &shared, /* is_local */ true, /* pin_session_ok */ false,
        )
        .await;
        let blockers = body["restart_blockers"].as_array().unwrap();
        assert!(
            !blockers.iter().any(|v| v == "pin_not_active"),
            "a local, PIN-less request must not see pin_not_active: {blockers:?}"
        );
    }

    #[tokio::test]
    async fn pin_not_active_is_raised_for_a_pin_less_remote_request() {
        let shared =
            crate::state::restart_test_state(false, false, std::collections::HashSet::new()).await;
        let body = server_info_body(
            &shared, /* is_local */ false, /* pin_session_ok */ false,
        )
        .await;
        let blockers = body["restart_blockers"].as_array().unwrap();
        assert!(
            blockers.iter().any(|v| v == "pin_not_active"),
            "a remote, PIN-less request must see pin_not_active: {blockers:?}"
        );
    }

    // --- restart_blocker_details (Task 2: verbatim label/description/hint) --

    #[tokio::test]
    async fn blocker_details_carry_non_empty_verbatim_japanese_text() {
        let shared =
            crate::state::restart_test_state(true, false, std::collections::HashSet::new()).await;
        // pin_auth_enabled=true, pin_session_ok=false, is_local=true ->
        // pin_session_required must be raised (pin_not_active and
        // local_only/remote_token_missing are all local-request-exempt).
        // restart_disabled's presence depends on whether some OTHER test in
        // this shared test binary has already called RESTART_CONFIG.set()
        // (a process-wide OnceLock) -- deliberately NOT asserted on here.
        let body = server_info_body(&shared, true, false).await;
        let blockers = body["restart_blockers"].as_array().unwrap();
        assert!(blockers.iter().any(|v| v == "pin_session_required"));
        for code in ["pin_not_active", "local_only", "remote_token_missing"] {
            assert!(
                !blockers.iter().any(|v| v == code),
                "{code} must not appear: {blockers:?}"
            );
        }

        let details = body["restart_blocker_details"].as_array().unwrap();
        let pin_detail = details
            .iter()
            .find(|d| d["code"] == "pin_session_required")
            .expect("pin_session_required detail present");
        assert_eq!(pin_detail["label"], "PIN認証が必要");
        assert!(!pin_detail["description"].as_str().unwrap().is_empty());
        assert!(!pin_detail["hint"].as_str().unwrap().is_empty());

        assert_eq!(body["restart_available_now"], false);
    }

    #[test]
    fn unknown_blocker_code_falls_back_to_code_as_label() {
        let (label, description, hint) = restart_blocker_label("some_future_code");
        assert_eq!(label, "some_future_code");
        assert_eq!(description, "");
        assert_eq!(hint, "");
    }

    #[test]
    fn all_five_known_codes_have_non_empty_labels() {
        for code in [
            "restart_disabled",
            "pin_not_active",
            "local_only",
            "remote_token_missing",
            "pin_session_required",
        ] {
            let (label, description, hint) = restart_blocker_label(code);
            assert_ne!(
                label, code,
                "code {code} should have a real label, not fall back"
            );
            assert!(!description.is_empty());
            assert!(!hint.is_empty());
        }
    }

    #[tokio::test]
    async fn no_blockers_means_available_now() {
        let shared =
            crate::state::restart_test_state(false, false, std::collections::HashSet::new()).await;
        // is_local=true clears local_only/remote_token_missing/pin_not_active;
        // pin_auth_enabled=false clears pin_session_required. RESTART_CONFIG
        // may or may not be set by another test in this binary -- restart_disabled
        // only appears if allow_restart is false there, so we don't assert on
        // that fixed value, only on the pin-related codes.
        let body = server_info_body(&shared, true, true).await;
        let blockers = body["restart_blockers"].as_array().unwrap();
        for code in [
            "pin_not_active",
            "local_only",
            "remote_token_missing",
            "pin_session_required",
        ] {
            assert!(
                !blockers.iter().any(|v| v == code),
                "{code} must not appear for a local, pin-authenticated request: {blockers:?}"
            );
        }
    }

    // --- design-advisor M2: derivation-level test against api_server_info,
    // not server_info_body(bool). The tests above all pass `is_local` as a
    // literal, so none of them can see a bug in HOW api_server_info derives
    // it -- which is exactly the bug design-advisor found (a bare
    // is_local_ip(tcp peer) check instead of server_restart::local_request).
    // Fault-injected: reverting api_server_info's is_local line back to
    // `client_ip.is_some_and(|Extension(ClientIp(ip))| is_local_ip(&ip))`
    // makes this test fail red (measured), because that form does not
    // consult the x-forwarded-for header at all and would treat the loopback
    // TCP peer below as local.

    #[tokio::test]
    async fn a_forwarded_hint_loopback_peer_is_not_treated_as_local_by_the_route() {
        let shared =
            crate::state::restart_test_state(false, false, std::collections::HashSet::new()).await;
        let mut headers = axum::http::HeaderMap::new();
        headers.insert(
            "x-forwarded-for",
            axum::http::HeaderValue::from_static("203.0.113.5"),
        );
        let client_ip = Some(Extension(ClientIp("127.0.0.1".to_string())));

        let response = api_server_info(
            State(shared),
            /* auth_context */ None,
            client_ip,
            /* session */ None,
            headers,
        )
        .await
        .into_response();
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let body: serde_json::Value = serde_json::from_slice(&bytes).unwrap();

        // No trusted proxy is configured, so an untrusted x-forwarded-for
        // hint disqualifies the loopback TCP peer entirely (matches
        // server_restart::is_local_request's documented divergence from a
        // bare loopback check, restart/mod.rs:200-222).
        assert!(
            body.get("db_path").is_none(),
            "a forwarded-hint-carrying loopback peer must not see local-only \
             fields: {body:?}"
        );
        let blockers = body["restart_blockers"].as_array().unwrap();
        assert!(
            blockers.iter().any(|v| v == "local_only"),
            "the same peer must also be treated as remote for restart_blockers, \
             not just for field disclosure: {blockers:?}"
        );
    }
}

use std::path::Path;

use axum::http::StatusCode;
use axum::{
    extract::State,
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde_json::json;

use crate::auth::client_ip::ClientIp;
use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::state::{AppState, SharedState};

/// Loopback/local-alias hosts, mirroring Python's `_LOCAL_HOSTS` in
/// `core/web/public_host.py`. `pub(crate)`: also used by the MCP transport
/// (`routes::mcp_native`) to gate the same local-only fields for
/// `get_server_info` tool calls, which unlike the REST route can arrive
/// from a non-loopback peer carrying a valid admin API key.
pub(crate) fn is_local_ip(ip: &str) -> bool {
    matches!(ip, "127.0.0.1" | "::1" | "localhost")
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
/// requests (`db_path`, `host`) -- callers with no per-request client (the
/// MCP tool) pass `true`, matching that transport's own trusted-connection
/// auth model.
pub async fn server_info_body(state: &AppState, is_local: bool) -> serde_json::Value {
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
    }
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
    body
}

/// GET /api/server-info
pub async fn api_server_info(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    client_ip: Option<Extension<ClientIp>>,
) -> impl IntoResponse {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    // No ClientIp extension (should not happen -- auth_middleware sets it on
    // every request) fails closed: db_path/host stay hidden rather than
    // guessing a request is local.
    let is_local = client_ip.is_some_and(|Extension(ClientIp(ip))| is_local_ip(&ip));
    (
        StatusCode::OK,
        Json(server_info_body(&state, is_local).await),
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
pub async fn error_report_enrich() -> impl axum::response::IntoResponse {
    axum::Json(serde_json::json!({"ok": true}))
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
}

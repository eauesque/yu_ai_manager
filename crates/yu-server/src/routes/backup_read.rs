//! `/api/tools/backup/list` and `/api/tools/backup/status` — Rust native.
//!
//! Mirrors Python `core/tools_api/routes_backup.py` (admin scope, then a small
//! JSON body) over `core/tools_api/backup_ops.py` and
//! `extensions/builtin_backup/core_impl/`.
//!
//! Only the two read endpoints live here. `create`, `restore` and `delete`
//! stay 503 (`auto_stubs`): they need sqlite's online backup API, retention
//! and a pre-restore snapshot, none of which exist in Rust.
//!
//! Both handlers previously returned an invented 200 — `backup_list` claimed
//! there were no backups at all, `backup_status` claimed the subsystem was
//! switched off — and then a 503 refusal. They now read the real backup
//! directory and the real config, so neither guesses.
//!
//! The config read goes through `ext_config::read_config_for_profile`, not bare
//! `read_config`: a profile's `backup` section replaces the top-level one, and
//! reading the file unmerged answered from a section the running server is not
//! using.

use std::path::{Path, PathBuf};

use axum::{extract::State, response::Response, Extension};
use serde_json::{json, Value};

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::routes::wd_tagger::api_result;
use crate::state::SharedState;

/// `extensions/builtin_backup/core_impl/backup_utils.py`.
const PREFIX: &str = "yu_ai_manager_";
const SUFFIX: &str = ".db";
const META_SUFFIX: &str = ".meta.json";

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

/// Python `_resolve_backup_dir`: `backup.backup_dir` when set, else
/// `<db parent>/backup`.
///
/// Python also `mkdir(parents=True, exist_ok=True)`s the directory. This does
/// not: a GET that creates a directory is a write, and for listing, "missing"
/// and "empty" produce the same answer anyway.
fn resolve_backup_dir(config: &Value, db_path: &str) -> Option<PathBuf> {
    let configured = config
        .get("backup")
        .and_then(|b| b.get("backup_dir"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if !configured.is_empty() {
        return Some(PathBuf::from(configured));
    }
    // `sqlite::memory:` and other URI forms have no parent directory on disk.
    if db_path.is_empty() || db_path.starts_with("sqlite:") {
        return None;
    }
    let parent = Path::new(db_path).parent()?;
    if parent.as_os_str().is_empty() {
        return None;
    }
    Some(parent.join("backup"))
}

/// Python `_read_meta`: the sidecar is `<name>.db.meta.json`. A missing or
/// unparsable sidecar reads as `{}`, which is what supplies the defaults below.
fn read_meta(backup_path: &Path) -> Value {
    let mut meta_path = backup_path.as_os_str().to_os_string();
    meta_path.push(META_SUFFIX);
    std::fs::read_to_string(PathBuf::from(meta_path))
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_else(|| json!({}))
}

/// Python `list_backups`: newest first, by filename descending.
fn backups_from_dir(dir: &Path) -> Vec<Value> {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut paths: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
                return false;
            };
            // Python globs `yu_ai_manager_*.db` and then drops `.meta.json`;
            // the second filter is redundant against that glob but kept so the
            // two implementations reject the same set.
            name.starts_with(PREFIX) && name.ends_with(SUFFIX) && !name.ends_with(META_SUFFIX)
        })
        .collect();
    paths.sort_unstable();
    paths.reverse();

    paths
        .iter()
        .map(|path| {
            let meta = read_meta(path);
            let size = std::fs::metadata(path).map_or(0, |m| m.len());
            json!({
                "filename": path.file_name().and_then(|n| n.to_str()).unwrap_or(""),
                "size_bytes": size,
                "reason": meta.get("reason").and_then(Value::as_str).unwrap_or("unknown"),
                "created_at": meta.get("created_at").and_then(Value::as_str).unwrap_or(""),
                "schema_version": meta.get("schema_version").cloned().unwrap_or(Value::Null),
            })
        })
        .collect()
}

fn cfg_bool(config: &Value, key: &str, default: bool) -> bool {
    config
        .get("backup")
        .and_then(|b| b.get(key))
        .and_then(Value::as_bool)
        .unwrap_or(default)
}

fn cfg_num(config: &Value, key: &str, default: i64) -> Value {
    config
        .get("backup")
        .and_then(|b| b.get(key))
        .filter(|v| v.is_number())
        .cloned()
        .unwrap_or_else(|| json!(default))
}

/// Python `get_backup_status_payload`.
///
/// The last three fields are not stubs. `scheduler_running` is Python's
/// `backup_scheduler.running`, and this process runs no backup scheduler, so
/// `false` is the fact. `last_backup_time` is Python's `_last_backup_time`, a
/// module global set only by `create_backup` **in the current process**; a
/// freshly started Python server reports `None` too, and this server never
/// creates backups, so `None` is likewise the fact — not "there are no
/// backups", which is what the listing answers. `within_cooldown` is derived
/// from `last_backup_time` and is `false` whenever it is `None`.
///
/// Deliberately not derived from the newest file on disk: that would answer a
/// different question than Python's, and the cooldown it feeds is about what
/// this process did.
fn status_from_config(config: &Value) -> Value {
    json!({
        "enabled": cfg_bool(config, "enabled", true),
        "backup_on_scan_complete": cfg_bool(config, "backup_on_scan_complete", true),
        "periodic_interval_hours": cfg_num(config, "periodic_interval_hours", 24),
        "max_generations": cfg_num(config, "max_generations", 5),
        "cooldown_minutes": cfg_num(config, "cooldown_minutes", 5),
        "scheduler_running": false,
        "last_backup_time": Value::Null,
        "within_cooldown": false,
    })
}

/// GET /api/tools/backup/list
pub async fn backup_list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let config = crate::ext_config::read_config_for_profile(
        &state.config.config_path,
        &state.config.project_root,
        state.config.active_profile.as_deref(),
    );
    let backups = resolve_backup_dir(&config, &state.config.db_path)
        .map(|dir| backups_from_dir(&dir))
        .unwrap_or_default();
    // Python routes both of these through `api_result`, which wraps the payload
    // in the `{ok, error, data}` envelope while keeping the payload's own keys
    // at the top level. Returning the bare payload made both endpoints differ
    // from Python on exactly those three keys.
    api_result(json!({"count": backups.len(), "backups": backups}))
}

/// GET /api/tools/backup/status
pub async fn backup_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let config = crate::ext_config::read_config_for_profile(
        &state.config.config_path,
        &state.config.project_root,
        state.config.active_profile.as_deref(),
    );
    api_result(status_from_config(&config))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write(dir: &Path, name: &str, body: &str) {
        std::fs::write(dir.join(name), body).unwrap();
    }

    #[test]
    fn listing_reports_each_backup_with_its_sidecar_metadata() {
        let root = tempfile::tempdir().unwrap();
        write(root.path(), "yu_ai_manager_20260101_000000.db", "aa");
        write(
            root.path(),
            "yu_ai_manager_20260101_000000.db.meta.json",
            r#"{"reason":"scheduled","created_at":"2026-01-01T00:00:00","schema_version":42}"#,
        );

        let listed = backups_from_dir(root.path());
        assert_eq!(listed.len(), 1);
        assert_eq!(
            listed[0]["filename"],
            json!("yu_ai_manager_20260101_000000.db")
        );
        assert_eq!(listed[0]["size_bytes"], json!(2));
        assert_eq!(listed[0]["reason"], json!("scheduled"));
        assert_eq!(listed[0]["created_at"], json!("2026-01-01T00:00:00"));
        assert_eq!(listed[0]["schema_version"], json!(42));
    }

    #[test]
    fn a_backup_without_a_sidecar_still_appears() {
        let root = tempfile::tempdir().unwrap();
        write(root.path(), "yu_ai_manager_20260101_000000.db", "a");

        let listed = backups_from_dir(root.path());
        assert_eq!(listed.len(), 1, "a missing sidecar must not hide the file");
        assert_eq!(listed[0]["reason"], json!("unknown"));
        assert_eq!(listed[0]["created_at"], json!(""));
        assert_eq!(listed[0]["schema_version"], Value::Null);
    }

    #[test]
    fn listing_is_newest_first_and_excludes_sidecars_and_strangers() {
        let root = tempfile::tempdir().unwrap();
        for name in [
            "yu_ai_manager_20260101_000000.db",
            "yu_ai_manager_20260303_000000.db",
            "yu_ai_manager_20260202_000000.db",
        ] {
            write(root.path(), name, "x");
        }
        write(
            root.path(),
            "yu_ai_manager_20260303_000000.db.meta.json",
            "{}",
        );
        write(root.path(), "unrelated.db", "x");
        write(root.path(), "tags.db", "x");

        let names: Vec<String> = backups_from_dir(root.path())
            .iter()
            .map(|b| b["filename"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(
            names,
            [
                "yu_ai_manager_20260303_000000.db",
                "yu_ai_manager_20260202_000000.db",
                "yu_ai_manager_20260101_000000.db",
            ],
            "newest first, sidecars and non-backups excluded"
        );
    }

    #[test]
    fn a_missing_backup_directory_lists_nothing_and_creates_nothing() {
        let root = tempfile::tempdir().unwrap();
        let absent = root.path().join("never-made");
        assert!(backups_from_dir(&absent).is_empty());
        assert!(!absent.exists(), "listing must not create the directory");
    }

    #[test]
    fn backup_dir_falls_back_to_the_db_parent() {
        assert_eq!(
            resolve_backup_dir(&json!({}), "/data/tags.db"),
            Some(PathBuf::from("/data/backup"))
        );
        assert_eq!(
            resolve_backup_dir(&json!({"backup": {"backup_dir": ""}}), "/data/tags.db"),
            Some(PathBuf::from("/data/backup")),
            "an empty configured dir is Python's unset"
        );
        assert_eq!(
            resolve_backup_dir(
                &json!({"backup": {"backup_dir": "/elsewhere"}}),
                "/data/tags.db"
            ),
            Some(PathBuf::from("/elsewhere"))
        );
        assert_eq!(
            resolve_backup_dir(&json!({}), "sqlite::memory:"),
            None,
            "an in-memory DB has no backup directory"
        );
    }

    #[test]
    fn status_defaults_match_python_and_are_not_inverted() {
        let status = status_from_config(&json!({}));
        // The bug this replaces reported all three of these the other way.
        assert_eq!(status["enabled"], json!(true));
        assert_eq!(status["backup_on_scan_complete"], json!(true));
        assert_eq!(status["cooldown_minutes"], json!(5));
        assert_eq!(status["periodic_interval_hours"], json!(24));
        assert_eq!(status["max_generations"], json!(5));
    }

    #[test]
    fn status_reads_the_configured_values() {
        let status = status_from_config(&json!({
            "backup": {
                "enabled": false,
                "backup_on_scan_complete": false,
                "periodic_interval_hours": 6,
                "max_generations": 12,
                "cooldown_minutes": 30,
            }
        }));
        assert_eq!(status["enabled"], json!(false));
        assert_eq!(status["backup_on_scan_complete"], json!(false));
        assert_eq!(status["periodic_interval_hours"], json!(6));
        assert_eq!(status["max_generations"], json!(12));
        assert_eq!(status["cooldown_minutes"], json!(30));
        assert_eq!(
            status["scheduler_running"],
            json!(false),
            "no scheduler runs here regardless of config"
        );
        assert_eq!(status["last_backup_time"], Value::Null);
        assert_eq!(status["within_cooldown"], json!(false));
    }

    #[test]
    fn an_active_profile_backup_section_wins_over_the_top_level_one() {
        // Startup merges the profile once and runs from the result. These
        // handlers re-read config.json so a settings write lands without a
        // restart -- and the re-read gives back the *unmerged* file. Reading it
        // bare answered from a `backup` section the running server is not
        // using: the wrong directory, the wrong retention, the wrong settings.
        let root = tempfile::tempdir().unwrap();
        let config_path = root.path().join("config.json");
        std::fs::write(
            &config_path,
            r#"{"active_profile":"work",
                "backup":{"backup_dir":"/top/level","max_generations":5,"enabled":true}}"#,
        )
        .unwrap();
        std::fs::create_dir(root.path().join("profiles")).unwrap();
        std::fs::write(
            root.path().join("profiles/work.json"),
            r#"{"backup":{"backup_dir":"/profile/dir","max_generations":9,"enabled":false}}"#,
        )
        .unwrap();

        let merged =
            crate::ext_config::read_config_for_profile(&config_path, root.path(), Some("work"));
        assert_eq!(
            resolve_backup_dir(&merged, "/data/tags.db"),
            Some(PathBuf::from("/profile/dir")),
            "the listing must read the profile's backup directory"
        );
        let status = status_from_config(&merged);
        assert_eq!(status["max_generations"], json!(9));
        assert_eq!(status["enabled"], json!(false));

        // Without the profile the top-level section is what applies, so the
        // assertions above are not passing for want of anything to lose to.
        let unmerged = crate::ext_config::read_config_for_profile(&config_path, root.path(), None);
        assert_eq!(
            resolve_backup_dir(&unmerged, "/data/tags.db"),
            Some(PathBuf::from("/top/level"))
        );
        assert_eq!(status_from_config(&unmerged)["max_generations"], json!(5));
    }

    #[test]
    fn the_profile_is_found_next_to_the_project_root_not_next_to_the_config_file() {
        // The two coincide in a normal checkout, which is why looking beside the
        // config file went unnoticed. Separate them the way `--config` does --
        // and the way the parity harness does, which is how this was measured:
        // Python applied the profile, Rust logged "profile not found, ignoring"
        // and served the unmerged config.
        let project_root = tempfile::tempdir().unwrap();
        let config_dir = tempfile::tempdir().unwrap();
        let config_path = config_dir.path().join("config.json");
        std::fs::write(
            &config_path,
            r#"{"active_profile":"work","backup":{"max_generations":5}}"#,
        )
        .unwrap();
        // profiles/ lives beside the project root, NOT beside the config file.
        std::fs::create_dir(project_root.path().join("profiles")).unwrap();
        std::fs::write(
            project_root.path().join("profiles/work.json"),
            r#"{"backup":{"max_generations":9}}"#,
        )
        .unwrap();
        assert!(
            !config_dir.path().join("profiles").exists(),
            "the config file must have no profiles/ beside it, or this proves nothing"
        );

        let merged = crate::ext_config::read_config_for_profile(
            &config_path,
            project_root.path(),
            Some("work"),
        );
        assert_eq!(
            status_from_config(&merged)["max_generations"],
            json!(9),
            "the profile must be found under the project root"
        );
    }

    #[test]
    fn a_profile_that_sets_no_backup_section_leaves_the_top_level_one() {
        let root = tempfile::tempdir().unwrap();
        let config_path = root.path().join("config.json");
        std::fs::write(
            &config_path,
            r#"{"active_profile":"work","backup":{"max_generations":5}}"#,
        )
        .unwrap();
        std::fs::create_dir(root.path().join("profiles")).unwrap();
        std::fs::write(
            root.path().join("profiles/work.json"),
            r#"{"label":"Work","db":"work.db"}"#,
        )
        .unwrap();

        let merged =
            crate::ext_config::read_config_for_profile(&config_path, root.path(), Some("work"));
        assert_eq!(status_from_config(&merged)["max_generations"], json!(5));
    }
}

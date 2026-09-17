use std::path::{Path, PathBuf};

use serde_json::{json, Value};

pub fn read_config(config_path: &Path) -> Result<Value, std::io::Error> {
    match std::fs::read_to_string(config_path) {
        Ok(text) => crate::config_io::parse_strict(config_path, &text),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(json!({})),
        Err(error) => Err(error),
    }
}

/// Read config.json and apply the active profile's overlay, the way startup does.
///
/// Startup merges the profile once (`main::merge_profile`) and hands the result
/// to every subsystem, but a route that re-reads the file to see writes made
/// since boot gets the *unmerged* config back. A profile that sets a section --
/// `backup`, say -- replaces the top-level one, so such a route answers from a
/// section the running server is not using: the wrong backup directory, the
/// wrong retention, the wrong everything under that key.
///
/// Use this instead of bare `read_config` wherever a handler reads settings a
/// profile can carry. Pass `active_profile` from `state.config.active_profile`,
/// which startup already resolved from `--profile` / `YU_PROFILE` /
/// `config["active_profile"]` -- do not re-derive it from the file, or a
/// `--profile` flag that overrode the file would be lost again.
pub fn read_config_for_profile(
    config_path: &Path,
    project_root: &Path,
    active_profile: Option<&str>,
) -> Value {
    let config = read_config(config_path).unwrap_or_else(|_| json!({}));
    match active_profile {
        Some(name) => merge_profile(&config, name, project_root).0,
        None => config,
    }
}

/// Where profiles live, resolved the way Python does.
///
/// Python: `core/paths.py::get_profiles_dir` — `TAGDB_PROFILES_DIR` if set,
/// else `<cwd>/profiles`, and the server's cwd is `project_root`.
///
/// Deliberately NOT `<config file>/../profiles`. Those two coincide in a normal
/// checkout, which is why the difference went unnoticed, but they part company
/// the moment `--config` points elsewhere -- and then Rust looked in a directory
/// that has no `profiles/` at all, logged "profile not found, ignoring", and ran
/// the whole server on the unmerged config. Measured 2026-09-05 under the parity
/// harness, which does exactly that: it copies config.json to a tmp dir. Python
/// applied the profile, Rust did not, and the two disagreed on every key the
/// profile set. The same lookup decides the profile's `db` override, so the
/// mismatch can also mean opening the wrong database.
pub fn profiles_dir(project_root: &Path) -> PathBuf {
    std::env::var("TAGDB_PROFILES_DIR")
        .ok()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| project_root.join("profiles"))
}

/// Returns (merged_config, optional_db_override, profile_was_found).
///
/// The third element exists because the first two cannot distinguish "no such
/// profile" from "the profile exists but sets no db". Both yield `None`, and
/// the caller falls back to the default database path either way. That is
/// harmless while the server only opens existing databases, but genesis must
/// refuse the first case: a mistyped `--profile` would otherwise create an
/// empty new library at the default path, which a user cannot tell apart from
/// having lost everything.
///
/// Mirrors Python `core/configuration/api.py::resolve_profile_config`.
pub fn merge_profile(
    config: &Value,
    name: &str,
    project_root: &Path,
) -> (Value, Option<String>, bool) {
    let dir = profiles_dir(project_root);
    let prof = {
        let file = dir.join(format!("{name}.json"));
        if file.exists() {
            std::fs::read_to_string(&file)
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
        } else {
            config.get("profiles").and_then(|p| p.get(name)).cloned()
        }
    };
    let Some(prof) = prof else {
        tracing::warn!("profile '{}' not found, ignoring", name);
        return (config.clone(), None, false);
    };
    const SKIP: &[&str] = &[
        "label",
        "db",
        "name",
        "description",
        "favorite",
        "last_used_at",
        "created_at",
    ];
    let mut merged = config.clone();
    if let (Some(obj), Some(m)) = (prof.as_object(), merged.as_object_mut()) {
        for (k, v) in obj {
            if SKIP.contains(&k.as_str()) {
                continue;
            }
            if k == "server" {
                if let Some(srv) = m.get_mut("server").and_then(|s| s.as_object_mut()) {
                    if let Some(pobj) = v.as_object() {
                        for (sk, sv) in pobj {
                            srv.insert(sk.clone(), sv.clone());
                        }
                    }
                } else {
                    m.insert(k.clone(), v.clone());
                }
            } else {
                m.insert(k.clone(), v.clone());
            }
        }
        m.insert(
            "active_profile".to_string(),
            Value::String(name.to_string()),
        );
    }
    let prof_db = prof
        .get("db")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    if let Some(ref db) = prof_db {
        // ponytail: minimal path-traversal guard; more thorough validation belongs at startup
        if db.contains("..")
            || db.starts_with("/etc")
            || db.starts_with("/proc")
            || db.starts_with("/sys")
        {
            tracing::error!("profile '{}' unsafe db path '{}', ignoring", name, db);
            return (merged, None, true);
        }
    }
    (merged, prof_db, true)
}

pub fn extension_value(config: &Value, ext_name: &str, key: &str) -> Option<Value> {
    config
        .get("extensions")
        .and_then(Value::as_object)
        .and_then(|extensions| extensions.get(ext_name))
        .and_then(Value::as_object)
        .and_then(|ext| ext.get(key))
        .cloned()
}

pub fn save_extension_value(
    config_path: &Path,
    ext_name: &str,
    key: &str,
    value: Value,
) -> Result<(), std::io::Error> {
    let mut config = read_config(config_path)?;
    if !config.is_object() {
        config = json!({});
    }
    let root = config.as_object_mut().expect("object set above");
    let extensions = root.entry("extensions").or_insert_with(|| json!({}));
    if !extensions.is_object() {
        *extensions = json!({});
    }
    let ext_map = extensions.as_object_mut().expect("object set above");
    let ext = ext_map.entry(ext_name).or_insert_with(|| json!({}));
    if !ext.is_object() {
        *ext = json!({});
    }
    ext.as_object_mut()
        .expect("object set above")
        .insert(key.to_string(), value);
    crate::config_io::write(config_path, &config)
}

/// Insert or remove `<section>.<key>` at the top level of config.json,
/// creating the section when needed. `Some(value)` writes, `None` removes.
/// Returns whether the key was present beforehand, which Python's
/// `revoke_permissions` reports.
///
/// This is a sibling of `save_extension_value`, which only ever writes under
/// `extensions.<name>`. Permission grants live in their own top-level
/// `extension_permissions` section
/// (`core/extensions_core/validation/extension_permissions.py`), so they need
/// a helper that is not hard-wired to the `extensions` key.
pub fn save_section_entry(
    config_path: &Path,
    section: &str,
    key: &str,
    value: Option<Value>,
) -> Result<bool, std::io::Error> {
    let mut config = read_config(config_path)?;
    if !config.is_object() {
        config = json!({});
    }
    let root = config.as_object_mut().expect("object set above");
    let entry = root.entry(section).or_insert_with(|| json!({}));
    if !entry.is_object() {
        *entry = json!({});
    }
    let map = entry.as_object_mut().expect("object set above");
    let existed = map.contains_key(key);
    match value {
        Some(v) => {
            map.insert(key.to_string(), v);
        }
        None => {
            map.remove(key);
        }
    }
    crate::config_io::write(config_path, &config)?;
    Ok(existed)
}

/// Resolve an extension's `enabled` flag exactly as Python's manifest loader
/// does (`core/extensions_core/lifecycle/extensions_loader_manifest.py::load_manifest`):
/// a per-extension override recorded in the user's config.json under
/// `extensions.<name>.enabled` wins first; failing that, fall back to the
/// extension's own `extension.json` `config.enabled`; failing that, default
/// to `true`. Shared by `routes::auto_stubs::list_extensions`
/// (GET /api/extensions) and `routes::extensions_admin::extension_detail`
/// (GET /api/extensions/{name}) so the two surfaces cannot silently drift.
pub fn resolve_extension_enabled(config: &Value, name: &str, manifest_json: &Value) -> bool {
    extension_value(config, name, "enabled")
        .and_then(|v| v.as_bool())
        .unwrap_or_else(|| {
            manifest_json
                .get("config")
                .and_then(|c| c.get("enabled"))
                .and_then(Value::as_bool)
                .unwrap_or(true)
        })
}

pub fn string_roots(value: Option<Value>) -> Option<Vec<String>> {
    value.and_then(|value| {
        value.as_array().map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
    })
}

/// One enabled scan root, with its per-root `recursive` flag.
pub struct ScanRootCfg {
    pub path: String,
    pub recursive: bool,
}

/// Enabled scan roots from config.json `scan_roots`, keeping the per-root
/// `recursive` flag that `global_scan_roots` (path-only) discards.
/// A bare string entry defaults to `recursive: true`, matching Python's
/// `core.scan.scan_worker_cli` root_cfg.get("recursive", True).
pub fn scan_root_configs(config: &Value) -> Vec<ScanRootCfg> {
    config
        .get("scan_roots")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    if let Some(path) = item.as_str() {
                        return Some(ScanRootCfg {
                            path: path.to_string(),
                            recursive: true,
                        });
                    }
                    let obj = item.as_object()?;
                    if !obj.get("enabled").and_then(Value::as_bool).unwrap_or(true) {
                        return None;
                    }
                    let path = obj.get("path").and_then(Value::as_str)?.to_string();
                    let recursive = obj
                        .get("recursive")
                        .and_then(Value::as_bool)
                        .unwrap_or(true);
                    Some(ScanRootCfg { path, recursive })
                })
                .collect()
        })
        .unwrap_or_default()
}

/// Every configured scan root path, enabled or not. Used for orphan-purge
/// safety: a root the user has merely disabled must not have its files
/// treated as orphaned and deleted (`scan_root_configs`/`global_scan_roots`
/// both drop disabled roots, which is correct for walking but wrong for
/// deciding what counts as "no longer registered").
pub fn all_scan_root_paths(config: &Value) -> Vec<String> {
    config
        .get("scan_roots")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    if let Some(path) = item.as_str() {
                        return Some(path.to_string());
                    }
                    item.as_object()?
                        .get("path")
                        .and_then(Value::as_str)
                        .map(str::to_string)
                })
                .collect()
        })
        .unwrap_or_default()
}

pub fn global_scan_roots(config: &Value) -> Vec<String> {
    config
        .get("scan_roots")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    if let Some(path) = item.as_str() {
                        return Some(path.to_string());
                    }
                    let obj = item.as_object()?;
                    if obj.get("enabled").and_then(Value::as_bool).unwrap_or(true) {
                        obj.get("path").and_then(Value::as_str).map(str::to_string)
                    } else {
                        None
                    }
                })
                .collect()
        })
        .unwrap_or_default()
}

/// The per-format scan toggles (`extract_a1111` / `extract_comfyui`) as the
/// parser sees them. Both default to true, matching
/// `core/configuration/defaults.py`.
///
/// Python has had these settings, a UI switch and an env override since long
/// before the port, but nothing in its scan ever read them; the Rust scan is
/// the live one, so honouring them here is what makes the switch mean
/// something.
pub fn parser_toggles(config: &Value) -> meta_extract::ParserToggles {
    let flag = |key: &str| config.get(key).and_then(Value::as_bool).unwrap_or(true);
    meta_extract::ParserToggles {
        a1111: flag("extract_a1111"),
        comfyui: flag("extract_comfyui"),
    }
}

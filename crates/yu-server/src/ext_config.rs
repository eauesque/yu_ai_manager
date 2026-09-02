use std::path::Path;

use serde_json::{json, Value};

pub fn read_config(config_path: &Path) -> Result<Value, std::io::Error> {
    match std::fs::read_to_string(config_path) {
        Ok(text) => crate::config_io::parse_strict(config_path, &text),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(json!({})),
        Err(error) => Err(error),
    }
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

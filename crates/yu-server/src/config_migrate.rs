use std::path::{Path, PathBuf};

use chrono::Local;
use serde::Serialize;
use serde_json::Value;

use crate::config_io;

#[derive(Debug, Serialize)]
pub(crate) struct LegacyMigrationStatus {
    pub pending: bool,
    pub primary: String,
    pub legacy: Option<String>,
    pub keys: Vec<String>,
    pub error: Option<String>,
}

#[derive(Debug, Serialize)]
pub(crate) struct MigrationOutcome {
    pub migrated: bool,
    pub merged_keys: Vec<String>,
    pub backup: Option<String>,
    pub primary: String,
    pub error: Option<String>,
}

fn filename(path: &Path) -> String {
    path.file_name()
        .unwrap_or(path.as_os_str())
        .to_string_lossy()
        .into_owned()
}

fn is_toml(path: &Path) -> bool {
    path.extension().and_then(|extension| extension.to_str()) == Some("toml")
}

fn legacy_path(primary: &Path) -> PathBuf {
    primary
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("config.json")
}

fn read_config(path: &Path) -> Result<Value, String> {
    let raw = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
    config_io::parse(path, &raw).ok_or_else(|| format!("{} is not valid config", path.display()))
}

fn remove_nulls(value: &mut Value) {
    if let Value::Object(values) = value {
        for value in values.values_mut() {
            remove_nulls(value);
        }
        values.retain(|_, value| {
            !value.is_null() && !value.as_object().is_some_and(|map| map.is_empty())
        });
    } else if let Value::Array(values) = value {
        // TOML arrays cannot contain null, so drop null elements while preserving remaining order.
        values.retain(|value| !value.is_null());
        for value in values {
            remove_nulls(value);
        }
    }
}

fn merged_config(legacy: &Value, primary: &Value) -> Value {
    let mut merged = legacy.clone();
    merge_primary(&mut merged, primary);
    remove_nulls(&mut merged);
    merged
}

fn merged_keys(legacy: &Value, primary: &Value) -> Vec<String> {
    let merged = merged_config(legacy, primary);
    let mut keys: Vec<_> = merged
        .as_object()
        .into_iter()
        .flat_map(|merged| merged.iter())
        .filter(|(key, value)| primary.get(key) != Some(*value))
        .map(|(key, _)| key.clone())
        .collect();
    keys.sort();
    keys
}

fn merge_primary(base: &mut Value, primary: &Value) {
    match (base, primary) {
        (Value::Object(base), Value::Object(primary)) => {
            for (key, value) in primary {
                match base.get_mut(key) {
                    Some(existing) => merge_primary(existing, value),
                    None => {
                        base.insert(key.clone(), value.clone());
                    }
                }
            }
        }
        (base, primary) => *base = primary.clone(),
    }
}

pub(crate) fn legacy_migration_status(primary: &Path) -> LegacyMigrationStatus {
    let legacy = legacy_path(primary);
    let mut status = LegacyMigrationStatus {
        pending: false,
        primary: filename(primary),
        legacy: None,
        keys: Vec::new(),
        error: None,
    };
    // Report legacy only when the primary can be a TOML migration target.
    if !is_toml(primary) || !legacy.exists() {
        return status;
    }
    status.legacy = Some(filename(&legacy));
    match (read_config(&legacy), read_config(primary)) {
        (Ok(legacy_config), Ok(primary_config)) => {
            status.keys = merged_keys(&legacy_config, &primary_config);
            status.pending = !status.keys.is_empty();
        }
        (Err(error), _) | (_, Err(error)) => status.error = Some(error),
    }
    status
}

pub(crate) fn migrate_legacy_config(primary: &Path) -> MigrationOutcome {
    let legacy = legacy_path(primary);
    let primary_name = filename(primary);
    if !is_toml(primary) || !legacy.exists() {
        return MigrationOutcome {
            migrated: false,
            merged_keys: Vec::new(),
            backup: None,
            primary: primary_name,
            error: None,
        };
    }

    let (legacy_config, primary_config) = match (read_config(&legacy), read_config(primary)) {
        (Ok(legacy), Ok(primary)) => (legacy, primary),
        (Err(error), _) | (_, Err(error)) => {
            return MigrationOutcome {
                migrated: false,
                merged_keys: Vec::new(),
                backup: None,
                primary: primary_name,
                error: Some(error),
            }
        }
    };
    let merged_keys = merged_keys(&legacy_config, &primary_config);
    if merged_keys.is_empty() {
        return MigrationOutcome {
            migrated: false,
            merged_keys,
            backup: None,
            primary: primary_name,
            error: None,
        };
    }
    let merged = merged_config(&legacy_config, &primary_config);
    if let Err(error) = config_io::write(primary, &merged) {
        return MigrationOutcome {
            migrated: false,
            merged_keys,
            backup: None,
            primary: primary_name,
            error: Some(error.to_string()),
        };
    }
    let backup = legacy.with_file_name(format!(
        "config.json.pre-toml-{}.bak",
        Local::now().format("%Y%m%d%H%M%S")
    ));
    if let Err(error) = std::fs::rename(&legacy, &backup) {
        return MigrationOutcome {
            migrated: false,
            merged_keys,
            backup: None,
            primary: primary_name,
            error: Some(error.to_string()),
        };
    }
    MigrationOutcome {
        migrated: true,
        merged_keys,
        backup: Some(filename(&backup)),
        primary: primary_name,
        error: None,
    }
}

pub(crate) fn should_auto_migrate(config_was_explicit: bool) -> bool {
    !config_was_explicit
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn migration_deep_merges_and_preserves_primary_values() {
        let root = tempfile::tempdir().unwrap();
        let primary = root.path().join("config.toml");
        std::fs::write(&primary, "port = 5001\n[server]\nlan = true\n").unwrap();
        std::fs::write(
            root.path().join("config.json"),
            r#"{"port":5000,"server":{"host":"127.0.0.1","lan":false},"extensions":{"builtin-nai-bridge":{"api_token":"secret"}}}"#,
        )
        .unwrap();

        let outcome = migrate_legacy_config(&primary);
        assert!(outcome.migrated, "{outcome:?}");
        assert_eq!(outcome.merged_keys, ["extensions", "server"]);
        let migrated = read_config(&primary).unwrap();
        assert_eq!(migrated["port"], json!(5001));
        assert_eq!(migrated["server"]["lan"], json!(true));
        assert_eq!(migrated["server"]["host"], json!("127.0.0.1"));
        assert_eq!(
            migrated["extensions"]["builtin-nai-bridge"]["api_token"],
            json!("secret")
        );
    }

    #[test]
    fn migration_renames_legacy_and_is_idempotent() {
        let root = tempfile::tempdir().unwrap();
        let primary = root.path().join("config.toml");
        std::fs::write(&primary, "port = 5000\n").unwrap();
        std::fs::write(root.path().join("config.json"), r#"{"timezone":"UTC"}"#).unwrap();

        let first = migrate_legacy_config(&primary);
        let backup = first.backup.as_ref().unwrap();
        assert!(first.migrated);
        assert_eq!(first.primary, "config.toml");
        assert!(!root.path().join("config.json").exists());
        assert!(root.path().join(backup).exists());
        assert!(backup.starts_with("config.json.pre-toml-"));

        let second = migrate_legacy_config(&primary);
        assert!(!second.migrated);
        assert!(second.merged_keys.is_empty());
        assert!(second.backup.is_none());
        assert!(second.error.is_none());
    }

    #[test]
    fn migration_removes_nulls_before_writing_toml() {
        let root = tempfile::tempdir().unwrap();
        let primary = root.path().join("config.toml");
        std::fs::write(&primary, "enable_fts = true\n").unwrap();
        std::fs::write(
            root.path().join("config.json"),
            r#"{"timezone":null,"server":{"pin":null,"port":5000},"extensions":{"builtin-nai-bridge":{"api_token":"enc:v2:LEGACY"}}}"#,
        )
        .unwrap();

        let outcome = migrate_legacy_config(&primary);
        assert!(outcome.migrated, "{outcome:?}");
        let migrated =
            config_io::parse(&primary, &std::fs::read_to_string(&primary).unwrap()).unwrap();
        assert_eq!(
            migrated["extensions"]["builtin-nai-bridge"]["api_token"],
            json!("enc:v2:LEGACY")
        );
        assert_eq!(migrated["server"]["port"], json!(5000));
        assert!(migrated.get("timezone").is_none());
        assert!(migrated["server"].get("pin").is_none());
        assert!(!root.path().join("config.json").exists());
        assert!(root
            .path()
            .join(outcome.backup.as_deref().unwrap())
            .exists());
    }

    #[test]
    fn null_only_legacy_config_is_not_pending() {
        let root = tempfile::tempdir().unwrap();
        let primary = root.path().join("config.toml");
        std::fs::write(&primary, "enable_fts = true\n").unwrap();
        std::fs::write(
            root.path().join("config.json"),
            r#"{"timezone":null,"server":{"pin":null}}"#,
        )
        .unwrap();

        let status = legacy_migration_status(&primary);
        assert!(!status.pending);
        assert_eq!(status.primary, "config.toml");
        assert_eq!(status.legacy.as_deref(), Some("config.json"));
        assert!(status.error.is_none());
    }

    #[test]
    fn non_toml_primary_does_not_report_legacy() {
        let root = tempfile::tempdir().unwrap();
        let primary = root.path().join("config.json");
        std::fs::write(&primary, r#"{"timezone":"UTC"}"#).unwrap();

        let status = legacy_migration_status(&primary);
        assert!(!status.pending);
        assert!(status.legacy.is_none());
    }

    #[test]
    fn status_reports_config_parse_errors() {
        let root = tempfile::tempdir().unwrap();
        let primary = root.path().join("config.toml");
        std::fs::write(&primary, "invalid = [").unwrap();
        std::fs::write(root.path().join("config.json"), "{}").unwrap();

        let status = legacy_migration_status(&primary);
        assert!(!status.pending);
        assert!(status.error.is_some());
    }
}

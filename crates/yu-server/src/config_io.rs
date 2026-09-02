use std::path::{Path, PathBuf};

use serde_json::{json, Value};

pub(crate) fn validate_base_url(s: &str) -> Result<String, &'static str> {
    let normalized = s.trim().trim_end_matches('/').to_string();
    if normalized.is_empty() {
        return Err("base_url must not be empty");
    }
    let lower = normalized.to_ascii_lowercase();
    let rest = if lower.starts_with("https://") {
        &normalized[8..]
    } else if lower.starts_with("http://") {
        &normalized[7..]
    } else {
        return Err("scheme must be http or https");
    };
    if rest.split('/').next().unwrap_or("").is_empty() {
        return Err("host is required");
    }
    if normalized.contains('?') {
        return Err("query string not allowed");
    }
    if normalized.contains('#') {
        return Err("fragment not allowed");
    }
    Ok(normalized)
}

pub(crate) fn load(config_path: &Path) -> Value {
    load_from_paths([
        config_path.to_path_buf(),
        PathBuf::from("config.json"),
        PathBuf::from("tagdb_config.json"),
    ])
}

/// True when the path names the TOML config format.
///
/// `main.rs` resolves the startup config path to `config.toml` whenever that
/// file exists, and hands that same path to every route through
/// `AppState::config.config_path`. Parsing it as JSON therefore used to yield
/// an empty object for every route-side read — and, worse, a subsequent write
/// replaced the operator's TOML file with JSON. The format follows the file.
fn is_toml(path: &Path) -> bool {
    path.extension().and_then(|ext| ext.to_str()) == Some("toml")
}

/// Parse config text according to the format its path names.
///
/// Every reader of `AppState::config.config_path` must go through this: that
/// path is `config.toml` whenever the file exists, so a bare
/// `serde_json::from_str` yields an error (or an empty config) for the whole
/// deployment. Returns `None` when the text does not parse as its format.
pub(crate) fn parse(path: &Path, raw: &str) -> Option<Value> {
    if is_toml(path) {
        let table: toml::Table = toml::from_str(raw).ok()?;
        serde_json::to_value(table).ok()
    } else {
        serde_json::from_str(raw).ok()
    }
}

/// `parse` with the `InvalidData` error the direct readers report.
pub(crate) fn parse_strict(path: &Path, raw: &str) -> Result<Value, std::io::Error> {
    parse(path, raw).ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!(
                "{} is not valid {}",
                path.display(),
                if is_toml(path) { "TOML" } else { "JSON" }
            ),
        )
    })
}

fn load_from_paths(paths: [PathBuf; 3]) -> Value {
    for path in paths {
        if path.exists() {
            return std::fs::read_to_string(&path)
                .ok()
                .and_then(|raw| parse(&path, &raw))
                .unwrap_or_else(|| json!({}));
        }
    }
    json!({})
}

fn serialize(path: &Path, config: &Value) -> Result<String, std::io::Error> {
    let invalid = |error: String| std::io::Error::new(std::io::ErrorKind::InvalidData, error);
    if is_toml(path) {
        // TOML has no null; dropping keys silently would lose settings, so
        // refuse instead of writing a file that no longer round-trips.
        let table = toml::Value::try_from(config)
            .map_err(|error| invalid(format!("config is not representable as TOML: {error}")))?;
        return toml::to_string_pretty(&table)
            .map_err(|error| invalid(format!("failed to serialize TOML config: {error}")));
    }
    serde_json::to_string_pretty(config).map_err(|error| invalid(error.to_string()))
}

pub(crate) fn write(config_path: &Path, config: &Value) -> Result<(), std::io::Error> {
    let parent = config_path.parent().unwrap_or_else(|| Path::new("."));
    std::fs::create_dir_all(parent)?;
    let tmp = parent.join(format!(
        ".config_{}_{}.tmp",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or(0)
    ));
    let text = serialize(config_path, config)?;
    std::fs::write(&tmp, format!("{text}\n"))?;
    std::fs::rename(&tmp, config_path)?;
    restrict_owner_only(config_path);
    Ok(())
}

pub(crate) fn restrict_owner_only(path: &Path) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = std::fs::metadata(path) {
            let mut permissions = metadata.permissions();
            permissions.set_mode(0o600);
            let _ = std::fs::set_permissions(path, permissions);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A Windows scan root must come back byte-identical.
    ///
    /// Reported from a real Windows run: every configured root failed
    /// canonicalization with ERROR_INVALID_NAME, and the log -- which formats
    /// with Display, not Debug -- showed `"H:\dwhelper"` WITH quotes, so the
    /// quotes were in the value. Roots that certainly exist
    /// (`C:\Users\...\Downloads`) failed too, which rules out a missing drive.
    #[test]
    fn windows_scan_root_paths_survive_a_toml_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        let original = json!({
            "scan_roots": [
                {"path": r"H:\dwhelper", "enabled": true, "recursive": true},
                {"path": r"C:\Users\someone\Downloads", "enabled": true, "recursive": true},
                {"path": "/home/someone/pictures", "enabled": true, "recursive": true},
            ]
        });

        write(&path, &original).expect("write");
        let raw = std::fs::read_to_string(&path).unwrap();
        let parsed = parse(&path, &raw).expect("parse");

        let roots = parsed["scan_roots"].as_array().unwrap();
        assert_eq!(roots.len(), 3);
        for (index, root) in roots.iter().enumerate() {
            let read_back = root["path"].as_str().unwrap();
            let expected = original["scan_roots"][index]["path"].as_str().unwrap();
            assert_eq!(
                read_back, expected,
                "scan root {index} changed across the round trip:\n{raw}"
            );
            assert!(
                !read_back.contains('"'),
                "scan root {index} came back quoted ({read_back:?}); \
                 canonicalize would then fail with ERROR_INVALID_NAME"
            );
        }
    }

    #[test]
    fn validate_base_url_rejects_invalid_and_normalizes_valid_urls() {
        assert_eq!(validate_base_url(""), Err("base_url must not be empty"));
        assert_eq!(
            validate_base_url("example.com"),
            Err("scheme must be http or https")
        );
        assert_eq!(
            validate_base_url("ftp://example.com"),
            Err("scheme must be http or https")
        );
        assert_eq!(validate_base_url("http:///path"), Err("host is required"));
        assert_eq!(
            validate_base_url("https://example.com/path?x=1"),
            Err("query string not allowed")
        );
        assert_eq!(
            validate_base_url("https://example.com/path#section"),
            Err("fragment not allowed")
        );
        assert_eq!(
            validate_base_url("  HTTPS://example.com/path///  "),
            Ok("HTTPS://example.com/path".to_string())
        );
    }

    #[test]
    fn load_missing_file_returns_empty_object() {
        let root = tempfile::tempdir().unwrap();
        assert_eq!(
            load_from_paths([
                root.path().join("missing.json"),
                root.path().join("config.json"),
                root.path().join("tagdb_config.json"),
            ]),
            json!({})
        );
    }

    #[test]
    fn load_broken_json_returns_empty_object() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("config.json");
        std::fs::write(&path, "{").unwrap();
        assert_eq!(load(&path), json!({}));
    }

    #[test]
    fn write_and_load_round_trip() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("nested/config.json");
        let config = json!({"scan_roots": ["images"], "enabled": true});
        write(&path, &config).unwrap();
        assert_eq!(load(&path), config);
    }

    /// `main.rs` points `config_path` at `config.toml` when that file exists,
    /// so a route-side read of it must see the operator's settings — not the
    /// empty object a JSON parser returns for TOML.
    #[test]
    fn load_reads_toml_when_the_config_path_is_toml() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("config.toml");
        std::fs::write(&path, "port = 5000\n\n[server]\nlan = true\n").unwrap();
        let loaded = load(&path);
        assert_eq!(loaded["port"], json!(5000));
        assert_eq!(loaded["server"]["lan"], json!(true));
    }

    /// Writing must preserve the file's own format. Emitting JSON into
    /// `config.toml` would leave a file that the next startup cannot parse.
    #[test]
    fn write_keeps_toml_files_in_toml() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("config.toml");
        write(&path, &json!({"port": 5000, "server": {"lan": true}})).unwrap();
        let raw = std::fs::read_to_string(&path).unwrap();
        assert!(
            !raw.trim_start().starts_with('{'),
            "wrote JSON into a .toml file: {raw}"
        );
        assert!(
            toml::from_str::<toml::Table>(&raw).is_ok(),
            "not valid TOML: {raw}"
        );
        assert_eq!(load(&path)["server"]["lan"], json!(true));
    }

    /// TOML cannot express null. Silently dropping such keys would lose
    /// settings, so the write is refused instead.
    #[test]
    fn write_refuses_toml_it_cannot_represent() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("config.toml");
        std::fs::write(&path, "port = 5000\n").unwrap();
        let err = write(&path, &json!({"port": 5000, "api_key": null})).unwrap_err();
        assert_eq!(err.kind(), std::io::ErrorKind::InvalidData);
        assert_eq!(
            std::fs::read_to_string(&path).unwrap(),
            "port = 5000\n",
            "the existing config must survive a refused write"
        );
    }

    /// Pins that `load` + `write` are NOT internally serialized: the lock is
    /// what prevents lost updates. Removing the `lock().await` below makes this
    /// test fail (verified 2026-08-10).
    ///
    /// This proves the mechanism, not the wiring. That every handler actually
    /// takes `AppState::settings_lock`, and that `main.rs` hands the very same
    /// `Arc` to `LanCoworkState`, is enforced by review, not by this test.
    #[tokio::test]
    async fn settings_lock_serializes_config_rmw() {
        const TASKS: u64 = 16;
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("config.json");
        write(&path, &json!({"counter": 0})).unwrap();
        let lock = std::sync::Arc::new(tokio::sync::Mutex::new(()));

        let mut tasks = Vec::new();
        for _ in 0..TASKS {
            let path = path.clone();
            let lock = std::sync::Arc::clone(&lock);
            tasks.push(tokio::spawn(async move {
                let _guard = lock.lock().await;
                let mut config = load(&path);
                let counter = config["counter"].as_u64().unwrap();
                // Without the lock, every task reads before this yield and lost updates
                // leave the final counter below TASKS.
                tokio::task::yield_now().await;
                config["counter"] = json!(counter + 1);
                write(&path, &config).unwrap();
            }));
        }
        for task in tasks {
            task.await.unwrap();
        }

        assert_eq!(load(&path)["counter"], TASKS);
    }

    #[cfg(unix)]
    #[test]
    fn write_restricts_permissions_to_owner() {
        use std::os::unix::fs::PermissionsExt;

        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("config.json");
        write(&path, &json!({})).unwrap();
        assert_eq!(
            std::fs::metadata(path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[test]
    fn write_leaves_no_temporary_file() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("config.json");
        write(&path, &json!({})).unwrap();
        assert!(std::fs::read_dir(root.path()).unwrap().all(|entry| {
            !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with(".config_")
        }));
    }
}

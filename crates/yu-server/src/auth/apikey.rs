use std::{
    collections::HashMap,
    fs,
    path::Path,
    sync::{Mutex, OnceLock},
    time::{Duration, Instant},
};

use serde::Deserialize;
use sha2::{Digest, Sha256};

const RATE_LIMIT_MAX: usize = 120;
const RATE_LIMIT_WINDOW: Duration = Duration::from_secs(60);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KeyInfo {
    pub id: String,
    pub label: String,
    pub key_prefix: String,
    pub scopes: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
struct ConfigFile {
    #[serde(default)]
    api_keys: Vec<ApiKeyEntry>,
}

#[derive(Debug, Deserialize)]
struct ApiKeyEntry {
    id: String,
    key_hash: String,
    #[serde(default)]
    key_prefix: String,
    #[serde(default)]
    label: String,
    scopes: Option<Vec<String>>,
}

static RATE_LIMITER: OnceLock<Mutex<HashMap<String, Vec<Instant>>>> = OnceLock::new();

fn rate_limiter() -> &'static Mutex<HashMap<String, Vec<Instant>>> {
    RATE_LIMITER.get_or_init(|| Mutex::new(HashMap::new()))
}

pub fn verify_key(config_path: &Path, bearer_token: &str) -> Option<KeyInfo> {
    if !bearer_token.starts_with("sk_") {
        return None;
    }
    let raw = fs::read_to_string(config_path).ok()?;
    // Goes through config_io so a `config.toml` deployment authenticates API
    // keys instead of silently seeing an empty key list.
    let config: ConfigFile =
        serde_json::from_value(crate::config_io::parse(config_path, &raw)?).ok()?;
    let digest = Sha256::digest(bearer_token.as_bytes());
    let digest_hex = hex::encode(digest);
    for key in config.api_keys {
        let matched = auth_core::verify_token(&key.key_hash, &digest_hex);
        if matched {
            // Python updates last_used_at here. Rust intentionally does not write
            // config.json from native routes to avoid racing the Python process.
            return Some(KeyInfo {
                id: key.id,
                label: key.label,
                key_prefix: key.key_prefix,
                scopes: key.scopes,
            });
        }
    }
    None
}

pub fn key_has_scope(key_info: &KeyInfo, required_scope: &str) -> bool {
    match key_info.scopes.as_ref().filter(|scopes| !scopes.is_empty()) {
        Some(scopes) => scopes.iter().any(|scope| scope == required_scope),
        None => required_scope == "read",
    }
}

pub fn get_required_scope(method: &str, path: &str) -> Option<&'static str> {
    if method == "GET" {
        return None;
    }
    for (prefix, scope) in [
        ("/api/ratings/", "rate"),
        ("/api/tags/", "tag.write"),
        ("/api/collections/", "collection.write"),
        ("/api/favorites/", "collection.write"),
        ("/api/annotations/", "annotate"),
        ("/api/scan/", "scan"),
        ("/api/apikeys", "admin"),
        ("/api/settings/", "admin"),
        ("/api/tools/restore", "admin"),
        ("/api/tools/clear-cache", "admin"),
        ("/api/tools/rebuild-groups", "admin"),
        ("/api/tools/debug-log/clear", "admin"),
    ] {
        if path.starts_with(prefix) {
            return Some(scope);
        }
    }
    Some("admin")
}

pub fn check_rate_limit(key_id: &str) -> bool {
    let now = Instant::now();
    let cutoff = now - RATE_LIMIT_WINDOW;
    let mut hits = rate_limiter().lock().expect("api key rate limiter lock");
    let timestamps = hits.entry(key_id.to_string()).or_default();
    timestamps.retain(|hit| *hit > cutoff);
    if timestamps.len() >= RATE_LIMIT_MAX {
        return false;
    }
    timestamps.push(now);
    true
}

#[cfg(test)]
pub fn reset_rate_limit_for_test(key_id: &str) {
    let mut hits = rate_limiter().lock().expect("api key rate limiter lock");
    hits.remove(key_id);
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn raw_key() -> String {
        "sk_0123456789abcdef0123456789abcdef".to_string()
    }

    fn temp_config(scopes: Option<Vec<&str>>) -> std::path::PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("yu-server-apikey-{suffix}.json"));
        let hash = hex::encode(Sha256::digest(raw_key().as_bytes()));
        let mut entry = json!({
            "id": "ak_test",
            "key_hash": hash,
            "key_prefix": "sk_0123456",
            "label": "Test key",
            "created_at": 1,
            "last_used_at": null
        });
        if let Some(scopes) = scopes {
            entry["scopes"] = json!(scopes);
        }
        fs::write(&path, json!({"api_keys": [entry]}).to_string()).unwrap();
        path
    }

    #[test]
    fn verify_key_matches_valid_sk_key() {
        let path = temp_config(Some(vec!["admin"]));

        let info = verify_key(&path, &raw_key()).unwrap();

        assert_eq!(info.id, "ak_test");
        assert_eq!(info.label, "Test key");
        assert_eq!(info.key_prefix, "sk_0123456");
        assert_eq!(info.scopes, Some(vec!["admin".to_string()]));
        let _ = fs::remove_file(path);
    }

    #[test]
    fn verify_key_rejects_wrong_key() {
        let path = temp_config(Some(vec!["admin"]));

        assert!(verify_key(&path, "sk_ffffffffffffffffffffffffffffffff").is_none());
        let _ = fs::remove_file(path);
    }

    #[test]
    fn verify_key_rejects_non_sk_key() {
        let path = temp_config(Some(vec!["admin"]));

        assert!(verify_key(&path, "internal_token").is_none());
        let _ = fs::remove_file(path);
    }

    #[test]
    fn get_required_scope_matches_python_rules() {
        assert_eq!(get_required_scope("GET", "/api/unknown"), None);
        assert_eq!(get_required_scope("POST", "/api/ratings/x"), Some("rate"));
        assert_eq!(get_required_scope("POST", "/api/unknown"), Some("admin"));
    }

    #[test]
    fn no_scope_key_is_read_only() {
        let key = KeyInfo {
            id: "ak_test".to_string(),
            label: String::new(),
            key_prefix: String::new(),
            scopes: None,
        };

        assert!(key_has_scope(&key, "read"));
        assert!(!key_has_scope(&key, "admin"));
    }

    /// `main.rs` hands routes a `config.toml` path whenever that file exists.
    /// Parsing it as JSON left the key list empty, so every Bearer key was
    /// rejected on such deployments.
    #[test]
    fn verify_key_reads_a_toml_config() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("yu-server-apikey-{suffix}.toml"));
        let hash = hex::encode(Sha256::digest(raw_key().as_bytes()));
        fs::write(
            &path,
            format!(
                "[[api_keys]]\nid = \"ak_test\"\nkey_hash = \"{hash}\"\n\
                 key_prefix = \"sk_0123456\"\nlabel = \"Test key\"\n\
                 created_at = 1\nscopes = [\"admin\"]\n"
            ),
        )
        .unwrap();

        let info = verify_key(&path, &raw_key()).expect("TOML config must authenticate");
        assert_eq!(info.id, "ak_test");
        assert_eq!(info.scopes, Some(vec!["admin".to_string()]));
        let _ = fs::remove_file(path);
    }
}

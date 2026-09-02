//! Gateway API-key auth for the wildcard proxies (`/ollama/*`).
//!
//! This is a *second* key system, separate from [`crate::auth::apikey`] (the
//! app's own `api_keys` with read/admin scopes). Gateway keys live under
//! `gateway.auth.api_keys`, carry scopes like `ollama:proxy`, and are stored
//! encrypted. A key that is valid for one system means nothing to the other —
//! do not route one through the other.
//!
//! Port of `core/gateway/auth.py`. Only the read path (verification) is here;
//! creating, patching and revoking keys stays in Python.

use std::path::Path;

use axum::http::HeaderMap;
use base64::Engine;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::secret_store;

/// Python `core/gateway/auth.py:_MAX_TOKEN_BYTES`.
const MAX_TOKEN_BYTES: usize = 256;
const SCOPE_WILDCARD: &str = "*";
pub const SCOPE_OLLAMA_PROXY: &str = "ollama:proxy";
// Python `core/gateway/scopes.py`. SD splits into three tiers because model
// switching and option writes are administrative, not generation.
pub const SCOPE_SD_GENERATE: &str = "sd:generate";
pub const SCOPE_SD_QUERY: &str = "sd:query";
pub const SCOPE_SD_ADMIN: &str = "sd:admin";
pub const SCOPE_LLM_MODELS: &str = "llm:models";
pub const SCOPE_NODE_STATUS: &str = "node:status";

/// One gateway API key, decrypted and hashed once at startup.
///
/// Decryption is deliberately not done per request: with `YU_SECRET_PASSPHRASE`
/// set, every `secret_store::decrypt` call runs PBKDF2 600k times, which would
/// hand any local process a cheap way to burn the server's CPU.
pub struct GatewayKey {
    id: String,
    digest: [u8; 32],
    scopes: Vec<String>,
}

pub struct GatewayAuthResult {
    pub key_id: String,
    pub scopes: Vec<String>,
}

/// Extract the gateway credential, matching `core/gateway/auth.py:extract_bearer`.
///
/// An `Authorization` header that carries a known prefix but an empty value
/// yields `None` *without* falling through to `x-api-key` — Python's `or None`
/// returns from inside the branch.
pub fn extract_bearer(headers: &HeaderMap) -> Option<String> {
    let header = headers
        .get("authorization")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();

    if let Some(token) = header.strip_prefix("Bearer ") {
        return (!token.is_empty()).then(|| token.to_string());
    }
    if let Some(encoded) = header.strip_prefix("Basic ") {
        let decoded = base64::engine::general_purpose::STANDARD
            .decode(encoded.as_bytes())
            .ok()?;
        let decoded = String::from_utf8(decoded).ok()?;
        // Basic auth: the password field is the key; the username is ignored.
        let password = decoded.split_once(':').map(|(_, pass)| pass)?;
        return (!password.is_empty()).then(|| password.to_string());
    }

    headers
        .get("x-api-key")
        .and_then(|value| value.to_str().ok())
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

/// Resolve the effective `gateway.auth` block, mirroring
/// `core/gateway/auth.py:load_config_from_app_config`.
pub fn auth_config(app_config: &Value) -> Value {
    if let Some(gateway) = app_config.get("gateway") {
        return gateway.get("auth").cloned().unwrap_or_else(|| json!({}));
    }

    let legacy = app_config
        .pointer("/llm_router/auth")
        .filter(|value| value.is_object() && !value.as_object().is_some_and(|m| m.is_empty()));
    let Some(legacy) = legacy else {
        return json!({"allow_loopback_bypass": true, "api_keys": []});
    };

    let mode = legacy
        .get("mode")
        .and_then(Value::as_str)
        .unwrap_or("loopback");
    tracing::warn!(
        mode,
        "gateway: migrated legacy llm_router.auth; please reconfigure via the \
         gateway.auth schema and rotate keys."
    );
    if matches!(mode, "loopback" | "none") {
        return json!({"allow_loopback_bypass": true, "api_keys": []});
    }

    // The legacy secret may be stored either encrypted or in the clear; decrypt
    // passes non-`enc:` values through unchanged, so load_keys handles both.
    json!({
        "allow_loopback_bypass": legacy
            .get("allow_loopback_bypass")
            .and_then(Value::as_bool)
            .unwrap_or(true),
        "api_keys": [{
            "id": "legacy",
            "secret_enc": legacy.get("api_key").and_then(Value::as_str).unwrap_or(""),
            "scopes": [SCOPE_WILDCARD],
        }],
    })
}

pub fn loopback_bypass_enabled(auth_cfg: &Value) -> bool {
    auth_cfg
        .get("allow_loopback_bypass")
        .and_then(Value::as_bool)
        .unwrap_or(true)
}

/// Decrypt every configured key once and keep only its SHA-256 digest.
pub fn load_keys(auth_cfg: &Value, project_root: &Path) -> Vec<GatewayKey> {
    let Some(entries) = auth_cfg.get("api_keys").and_then(Value::as_array) else {
        return Vec::new();
    };

    let mut keys = Vec::new();
    for entry in entries {
        let id = entry.get("id").and_then(Value::as_str).unwrap_or_default();
        let secret_enc = entry
            .get("secret_enc")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if secret_enc.is_empty() {
            continue;
        }
        // decrypt returns an empty string on failure. Registering the digest of
        // "" would authenticate an empty credential, so a key we cannot read is
        // dropped rather than trusted.
        let plaintext = secret_store::decrypt(secret_enc, project_root);
        if plaintext.is_empty() {
            tracing::warn!(
                key_id = id,
                "gateway: failed to decrypt API key; skipping. The secret was \
                 encrypted with a key that is no longer available — recreate it."
            );
            continue;
        }
        keys.push(GatewayKey {
            id: id.to_string(),
            digest: Sha256::digest(plaintext.as_bytes()).into(),
            scopes: entry
                .get("scopes")
                .and_then(Value::as_array)
                .map(|scopes| {
                    scopes
                        .iter()
                        .filter_map(Value::as_str)
                        .map(str::to_string)
                        .collect()
                })
                .unwrap_or_default(),
        });
    }
    keys
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    left.len() == right.len()
        && left
            .iter()
            .zip(right)
            .fold(0_u8, |acc, (a, b)| acc | (a ^ b))
            == 0
}

fn check_bearer(keys: &[GatewayKey], token: &str) -> Option<GatewayAuthResult> {
    if token.len() > MAX_TOKEN_BYTES {
        return None;
    }
    let presented: [u8; 32] = Sha256::digest(token.as_bytes()).into();
    // Every key is compared, and the last match wins — the same walk Python
    // does. Returning early would both change which scopes a duplicated secret
    // gets and leak the matching position through timing.
    let mut matched = None;
    for key in keys {
        if constant_time_eq(&presented, &key.digest) {
            matched = Some(GatewayAuthResult {
                key_id: key.id.clone(),
                scopes: key.scopes.clone(),
            });
        }
    }
    matched
}

/// Authenticate one proxy request. `None` means 401.
///
/// The loopback bypass is checked *before* the bearer, exactly as Python does.
/// Verifying a presented bearer first would reject the dummy `Authorization`
/// header every OpenAI-compatible client sends, and would buy nothing: when the
/// bypass is on, no credential is required in the first place.
pub fn check_request(
    keys: &[GatewayKey],
    bypass_enabled: bool,
    headers: &HeaderMap,
    client_ip: &str,
) -> Option<GatewayAuthResult> {
    // `is_loopback_addr` is wider than Python's {127.0.0.1, ::1}: it accepts all
    // of 127.0.0.0/8 and "localhost". That is deliberate — the same predicate
    // already decides L1, and a client that L1 lets through only to be refused
    // here would be a confusing split.
    if bypass_enabled && crate::auth::chain::is_loopback_addr(client_ip) {
        return Some(GatewayAuthResult {
            key_id: "loopback".to_string(),
            scopes: vec![SCOPE_WILDCARD.to_string()],
        });
    }
    check_bearer(keys, &extract_bearer(headers)?)
}

pub fn has_scope(result: &GatewayAuthResult, needed: &str) -> bool {
    result
        .scopes
        .iter()
        .any(|scope| scope == SCOPE_WILDCARD || scope == needed)
}

#[cfg(test)]
mod tests {
    use std::{path::PathBuf, str::FromStr};

    use axum::http::{HeaderName, HeaderValue};
    use base64::Engine as _;

    use super::*;

    /// A project root carrying its own `data/secret.key`, so the sealed values
    /// below decrypt here and nowhere else.
    fn temp_root(name: &str) -> (PathBuf, String) {
        let root =
            std::env::temp_dir().join(format!("yu-gateway-auth-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("data")).unwrap();
        let key = base64::engine::general_purpose::URL_SAFE.encode([29_u8; 32]);
        std::fs::write(root.join("data").join("secret.key"), &key).unwrap();
        (root, key)
    }

    fn seal(plaintext: &str, key: &str) -> String {
        format!(
            "enc:{}",
            crate::secret_store::encrypt_for_test(plaintext, key.as_bytes())
        )
    }

    fn headers(pairs: &[(&str, &str)]) -> HeaderMap {
        let mut map = HeaderMap::new();
        for (name, value) in pairs {
            map.insert(
                HeaderName::from_str(name).unwrap(),
                HeaderValue::from_str(value).unwrap(),
            );
        }
        map
    }

    fn basic(user: &str, password: &str) -> String {
        format!(
            "Basic {}",
            base64::engine::general_purpose::STANDARD.encode(format!("{user}:{password}"))
        )
    }

    #[test]
    fn bearer_is_extracted_from_all_three_shapes() {
        assert_eq!(
            extract_bearer(&headers(&[("authorization", "Bearer tok-a")])).as_deref(),
            Some("tok-a")
        );
        assert_eq!(
            extract_bearer(&headers(&[("authorization", &basic("ignored", "tok-b"))])).as_deref(),
            Some("tok-b")
        );
        assert_eq!(
            extract_bearer(&headers(&[("x-api-key", "tok-c")])).as_deref(),
            Some("tok-c")
        );
    }

    #[test]
    fn an_empty_bearer_does_not_fall_through_to_x_api_key() {
        // Python returns from inside the `Bearer` branch, so a present-but-empty
        // Authorization header hides x-api-key rather than deferring to it.
        let map = headers(&[("authorization", "Bearer "), ("x-api-key", "tok")]);
        assert_eq!(extract_bearer(&map), None);
    }

    #[test]
    fn basic_auth_with_broken_base64_yields_no_bearer() {
        assert_eq!(
            extract_bearer(&headers(&[("authorization", "Basic !!!not-base64!!!")])),
            None
        );
    }

    #[test]
    fn oversized_token_is_rejected_before_hashing() {
        let (root, key) = temp_root("oversized");
        let long = "z".repeat(MAX_TOKEN_BYTES + 1);
        let cfg = json!({
            "allow_loopback_bypass": false,
            "api_keys": [{"id": "k", "secret_enc": seal(&long, &key), "scopes": [SCOPE_OLLAMA_PROXY]}],
        });
        let keys = load_keys(&cfg, &root);

        // The key itself loaded; only the presented token is refused for length.
        assert_eq!(keys.len(), 1);
        assert!(check_bearer(&keys, &long).is_none());
    }

    #[test]
    fn loopback_without_bearer_gets_wildcard_when_bypass_enabled() {
        let result = check_request(&[], true, &HeaderMap::new(), "127.0.0.1").expect("bypass");
        assert_eq!(result.key_id, "loopback");
        assert!(has_scope(&result, SCOPE_OLLAMA_PROXY));
    }

    #[test]
    fn a_dummy_bearer_still_passes_when_bypass_is_enabled() {
        // OpenAI-compatible clients always send an Authorization header even
        // when the endpoint needs no key. Verifying it first would 401 them all.
        let map = headers(&[("authorization", "Bearer sk-not-a-registered-key")]);
        let result = check_request(&[], true, &map, "127.0.0.1").expect("bypass");
        assert_eq!(result.key_id, "loopback");
    }

    #[test]
    fn loopback_without_bearer_is_rejected_when_bypass_disabled() {
        assert!(check_request(&[], false, &HeaderMap::new(), "127.0.0.1").is_none());
    }

    #[test]
    fn a_wrong_bearer_is_rejected_when_bypass_disabled() {
        let (root, key) = temp_root("wrong-bearer");
        let cfg = json!({
            "api_keys": [{"id": "k", "secret_enc": seal("right", &key), "scopes": [SCOPE_OLLAMA_PROXY]}],
        });
        let keys = load_keys(&cfg, &root);

        let wrong = headers(&[("authorization", "Bearer wrong")]);
        assert!(check_request(&keys, false, &wrong, "127.0.0.1").is_none());

        let right = headers(&[("authorization", "Bearer right")]);
        let result = check_request(&keys, false, &right, "127.0.0.1").expect("right key");
        assert_eq!(result.key_id, "k");
    }

    #[test]
    fn a_key_whose_secret_cannot_be_decrypted_is_skipped() {
        let (root, _key) = temp_root("undecryptable");
        let foreign = base64::engine::general_purpose::URL_SAFE.encode([7_u8; 32]);
        let cfg = json!({
            "api_keys": [{
                "id": "lost",
                "secret_enc": seal("secret", &foreign),
                "scopes": [SCOPE_OLLAMA_PROXY],
            }],
        });

        // Dropped, not registered as the digest of "" — otherwise an empty
        // credential would authenticate.
        assert!(load_keys(&cfg, &root).is_empty());
    }

    #[test]
    fn a_malformed_key_entry_is_skipped() {
        let (root, key) = temp_root("malformed");
        let cfg = json!({
            "api_keys": [
                "not-an-object",
                {"id": "no-secret", "scopes": [SCOPE_OLLAMA_PROXY]},
                {"id": "good", "secret_enc": seal("live", &key), "scopes": [SCOPE_OLLAMA_PROXY]},
            ],
        });
        let keys = load_keys(&cfg, &root);
        assert_eq!(keys.len(), 1);
        assert_eq!(keys[0].id, "good");
    }

    #[test]
    fn the_last_matching_key_wins() {
        let (root, key) = temp_root("duplicate");
        let cfg = json!({
            "api_keys": [
                {"id": "first", "secret_enc": seal("same", &key), "scopes": []},
                {"id": "second", "secret_enc": seal("same", &key), "scopes": [SCOPE_OLLAMA_PROXY]},
            ],
        });
        let keys = load_keys(&cfg, &root);
        let result = check_bearer(&keys, "same").expect("match");
        assert_eq!(result.key_id, "second");
        assert!(has_scope(&result, SCOPE_OLLAMA_PROXY));
    }

    #[test]
    fn key_without_scopes_has_no_scope() {
        let result = GatewayAuthResult {
            key_id: "k".to_string(),
            scopes: Vec::new(),
        };
        assert!(!has_scope(&result, SCOPE_OLLAMA_PROXY));
    }

    #[test]
    fn wildcard_scope_satisfies_any_requirement() {
        let result = GatewayAuthResult {
            key_id: "k".to_string(),
            scopes: vec![SCOPE_WILDCARD.to_string()],
        };
        assert!(has_scope(&result, SCOPE_OLLAMA_PROXY));
        assert!(has_scope(&result, "anything:else"));
    }

    #[test]
    fn missing_gateway_and_legacy_config_leaves_the_bypass_on() {
        let cfg = auth_config(&json!({}));
        assert!(loopback_bypass_enabled(&cfg));
        assert!(load_keys(&cfg, &PathBuf::from(".")).is_empty());
    }

    #[test]
    fn legacy_loopback_mode_yields_bypass_and_no_keys() {
        let cfg = auth_config(&json!({
            "llm_router": {"auth": {"mode": "loopback", "api_key": "ignored"}},
        }));
        assert!(loopback_bypass_enabled(&cfg));
        assert_eq!(cfg["api_keys"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn legacy_llm_router_auth_is_migrated() {
        let (root, key) = temp_root("legacy");
        let cfg = auth_config(&json!({
            "llm_router": {"auth": {
                "mode": "api_key",
                "allow_loopback_bypass": false,
                "api_key": seal("legacy-secret", &key),
            }},
        }));

        // The knob must survive the migration; ignoring it is the very defect
        // this gate exists to close.
        assert!(!loopback_bypass_enabled(&cfg));

        let keys = load_keys(&cfg, &root);
        let map = headers(&[("authorization", "Bearer legacy-secret")]);
        let result = check_request(&keys, false, &map, "127.0.0.1").expect("legacy key");
        assert_eq!(result.key_id, "legacy");
        // Legacy keys carried no scopes of their own; Python grants wildcard.
        assert!(has_scope(&result, SCOPE_OLLAMA_PROXY));
    }

    #[test]
    fn gateway_present_without_auth_block_keeps_defaults() {
        let cfg = auth_config(&json!({"gateway": {"backends": {}}}));
        assert!(loopback_bypass_enabled(&cfg));
        assert!(load_keys(&cfg, &PathBuf::from(".")).is_empty());
    }
}

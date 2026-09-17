//! Secret handling for `stream_config.json`.
//!
//! One walk serves three purposes — encrypt on write, decrypt on read, mask on
//! response — so the three can never disagree about what counts as a secret.
//! `actions[]` and `conditions` are free-form JSON, so protection is keyed on the
//! field name at any depth rather than on a fixed schema. See
//! `docs/superpowers/specs/2026-08-14-stream-config-secret-store-design.md`.
//!
//! Adding an action that carries a credential under a name absent from
//! `SECRET_KEYS` stores it in the clear. Extend the set when adding one.

use std::path::Path;

use serde_json::{Map, Value};

use crate::secret_store::{mask_secret, mask_url};

use super::rules::{DetectionRule, StreamConfig, StreamSourceConfig};

const SECRET_KEYS: &[&str] = &[
    "secret",
    "token",
    "api_key",
    "apikey",
    "password",
    "passwd",
    "authorization",
    "auth",
    "access_token",
    "refresh_token",
];

const URL_KEYS: &[&str] = &["url", "endpoint", "webhook_url", "callback_url"];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum Protected {
    /// Masked whole; the value has no non-secret part worth showing.
    Secret,
    /// Masked per component; scheme/host/path identify the source to a human.
    Url,
}

fn classify(key: &str) -> Option<Protected> {
    let key = key.to_ascii_lowercase();
    if SECRET_KEYS.contains(&key.as_str()) {
        Some(Protected::Secret)
    } else if URL_KEYS.contains(&key.as_str()) {
        Some(Protected::Url)
    } else {
        None
    }
}

fn is_encrypted(value: &str) -> bool {
    value.starts_with("enc:")
}

/// Visit every protected string in a free-form JSON value.
fn walk_value(value: &mut Value, visit: &mut dyn FnMut(Protected, &mut String)) {
    match value {
        Value::Object(map) => {
            for (key, child) in map.iter_mut() {
                match (classify(key), child) {
                    (Some(kind), Value::String(text)) => visit(kind, text),
                    (_, child) => walk_value(child, visit),
                }
            }
        }
        Value::Array(items) => {
            for item in items {
                walk_value(item, visit);
            }
        }
        _ => {}
    }
}

fn walk_map(map: &mut Map<String, Value>, visit: &mut dyn FnMut(Protected, &mut String)) {
    let mut wrapper = Value::Object(std::mem::take(map));
    walk_value(&mut wrapper, visit);
    if let Value::Object(restored) = wrapper {
        *map = restored;
    }
}

fn walk_rule(rule: &mut DetectionRule, visit: &mut dyn FnMut(Protected, &mut String)) {
    for action in &mut rule.actions {
        walk_value(action, visit);
    }
    walk_map(&mut rule.conditions, visit);
}

fn walk_source(source: &mut StreamSourceConfig, visit: &mut dyn FnMut(Protected, &mut String)) {
    visit(Protected::Url, &mut source.url);
}

/// Outcome of reading a config from disk.
pub(super) struct LoadOutcome {
    pub(super) config: StreamConfig,
    /// Some encrypted value could not be decrypted. Nothing is loaded and nothing
    /// is written.
    ///
    /// Dropping just the unreadable entries looks tidier but destroys data: a key
    /// that is temporarily unavailable, or a v1 value whose passphrase changed
    /// while v2 values still decrypt, would be silently deleted on the next write.
    /// Refusing wholesale keeps the file intact and is still fail-closed — an
    /// unloaded rule cannot fire an unsigned webhook.
    pub(super) locked: bool,
    /// At least one protected value was stored in the clear.
    pub(super) migration_needed: bool,
}

#[derive(Default)]
struct DecryptTally {
    failed: usize,
    plaintext: bool,
}

fn decrypt_item(
    walk: impl FnOnce(&mut dyn FnMut(Protected, &mut String)),
    project_root: &Path,
    tally: &mut DecryptTally,
) {
    walk(&mut |_kind, text| {
        if text.is_empty() {
            return;
        }
        if !is_encrypted(text) {
            tally.plaintext = true;
            return;
        }
        // `encrypt` never encrypts an empty string, so ciphertext in and empty
        // out can only mean the decryption failed.
        let plain = crate::secret_store::decrypt(text, project_root);
        if plain.is_empty() {
            tally.failed += 1;
        } else {
            *text = plain;
        }
    });
}

pub(super) fn decrypt_config(raw: StreamConfig, project_root: &Path) -> LoadOutcome {
    let mut tally = DecryptTally::default();
    let mut config = raw;

    for source in &mut config.sources {
        decrypt_item(|visit| walk_source(source, visit), project_root, &mut tally);
    }
    for rule in &mut config.rules {
        decrypt_item(|visit| walk_rule(rule, visit), project_root, &mut tally);
    }

    if tally.failed > 0 {
        tracing::error!(
            failed = tally.failed,
            "stream config is locked: some encrypted values could not be decrypted. \
             Loading nothing and writing nothing so the file is not lost. \
             Restore the secret key, or remove the unreadable entries by hand."
        );
        return LoadOutcome {
            config: StreamConfig::default(),
            locked: true,
            migration_needed: false,
        };
    }

    LoadOutcome {
        config,
        locked: false,
        migration_needed: tally.plaintext,
    }
}

/// Encrypt every protected value. `encrypt` returns its input unchanged when it
/// cannot encrypt, so the result is checked rather than trusted; a partially
/// plaintext config must never reach disk.
pub(super) fn encrypt_config(
    config: &StreamConfig,
    project_root: &Path,
) -> Result<StreamConfig, String> {
    let mut encrypted = config.clone();
    let mut failures = 0usize;
    let mut visit = |_kind: Protected, text: &mut String| {
        if text.is_empty() {
            return;
        }
        let sealed = crate::secret_store::encrypt(text, project_root);
        if is_encrypted(&sealed) {
            *text = sealed;
        } else {
            failures += 1;
        }
    };
    for source in &mut encrypted.sources {
        walk_source(source, &mut visit);
    }
    for rule in &mut encrypted.rules {
        walk_rule(rule, &mut visit);
    }
    if failures > 0 {
        return Err(format!(
            "{failures} stream config secret(s) could not be encrypted"
        ));
    }
    Ok(encrypted)
}

fn mask_in_place(value: &mut Value) {
    walk_value(value, &mut |kind, text| {
        *text = match kind {
            Protected::Secret => mask_secret(text),
            Protected::Url => mask_url(text),
        };
    });
}

/// Mask a value on its way into an HTTP response.
///
/// Masking belongs here and nowhere else. Putting it in a `Serialize` impl would
/// feed masked values back to the writer, which persists the same types.
pub(super) fn masked_response(value: &impl serde::Serialize) -> Value {
    let mut json = serde_json::to_value(value).unwrap_or(Value::Null);
    mask_in_place(&mut json);
    json
}

/// Restore protected values that a client echoed back in masked form.
///
/// A client that GETs a rule, edits one field and PUTs it back would otherwise
/// store `****` as the secret and lose the original beyond recovery. Actions have
/// no stable identity, so correspondence is positional.
///
/// A secret is only restored when the destination it authenticates to is
/// unchanged. Otherwise "point the webhook somewhere else and echo the mask back"
/// would hand the stored secret to the new address.
fn destination_changed(new_map: &Map<String, Value>, old_map: &Map<String, Value>) -> bool {
    new_map.iter().any(|(key, new_value)| {
        if classify(key) != Some(Protected::Url) {
            return false;
        }
        let Some(Value::String(stored)) = old_map.get(key) else {
            return false;
        };
        match new_value {
            // The mask stands for the stored value, so it is not a change.
            Value::String(shown) => shown != stored && *shown != mask_url(stored),
            _ => true,
        }
    })
}

fn preserve_masked_value(incoming: &mut Value, existing: &Value) {
    match (incoming, existing) {
        (Value::Object(new_map), Value::Object(old_map)) => {
            let keep_secrets = !destination_changed(new_map, old_map);
            for (key, new_child) in new_map.iter_mut() {
                let Some(old_child) = old_map.get(key) else {
                    continue;
                };
                let kind = classify(key);
                if kind == Some(Protected::Secret) && !keep_secrets {
                    continue;
                }
                match (kind, &new_child, old_child) {
                    (Some(kind), Value::String(shown), Value::String(stored)) => {
                        let masked = match kind {
                            Protected::Secret => mask_secret(stored),
                            Protected::Url => mask_url(stored),
                        };
                        if shown.as_str() == masked && !stored.is_empty() {
                            *new_child = Value::String(stored.clone());
                        }
                    }
                    _ => preserve_masked_value(new_child, old_child),
                }
            }
        }
        (Value::Array(new_items), Value::Array(old_items)) => {
            for (new_item, old_item) in new_items.iter_mut().zip(old_items) {
                preserve_masked_value(new_item, old_item);
            }
        }
        _ => {}
    }
}

pub(super) fn preserve_masked_rule(incoming: &mut DetectionRule, existing: &DetectionRule) {
    for (action, old_action) in incoming.actions.iter_mut().zip(&existing.actions) {
        preserve_masked_value(action, old_action);
    }
    let mut conditions = Value::Object(std::mem::take(&mut incoming.conditions));
    preserve_masked_value(&mut conditions, &Value::Object(existing.conditions.clone()));
    if let Value::Object(restored) = conditions {
        incoming.conditions = restored;
    }
}

pub(super) fn preserve_masked_source(incoming: &mut StreamSourceConfig, existing_url: &str) {
    if !existing_url.is_empty() && incoming.url == mask_url(existing_url) {
        incoming.url = existing_url.to_string();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn rule_with(actions: Value) -> DetectionRule {
        serde_json::from_value(json!({
            "id": "r1",
            "actions": actions,
        }))
        .expect("rule fixture is valid")
    }

    fn config_with(url: &str, secret: &str) -> StreamConfig {
        StreamConfig {
            sources: vec![StreamSourceConfig {
                id: "cam".to_string(),
                url: url.to_string(),
                name: "cam".to_string(),
            }],
            rules: vec![rule_with(json!([
                {"type": "webhook", "url": "http://hook.test/h", "secret": secret}
            ]))],
        }
    }

    fn temp_root(name: &str) -> std::path::PathBuf {
        let root =
            std::env::temp_dir().join(format!("yu-stream-secrets-{name}-{}", std::process::id()));
        std::fs::create_dir_all(root.join("data")).expect("temp root");
        root
    }

    #[test]
    fn round_trip_restores_every_protected_value() {
        let root = temp_root("round-trip");
        let plain = config_with("rtsp://u:p@cam.test/live", "hmac-secret");
        let sealed = encrypt_config(&plain, &root).expect("encrypt");

        assert!(sealed.sources[0].url.starts_with("enc:"));
        let sealed_secret = sealed.rules[0].actions[0]["secret"].as_str().unwrap();
        assert!(sealed_secret.starts_with("enc:"), "{sealed_secret}");

        let outcome = decrypt_config(sealed, &root);
        assert!(!outcome.locked);
        assert!(!outcome.migration_needed);
        assert_eq!(outcome.config, plain);
    }

    #[test]
    fn encrypting_twice_is_a_no_op() {
        let root = temp_root("idempotent");
        let once = encrypt_config(&config_with("rtsp://cam.test/live", "s"), &root).expect("once");
        let twice = encrypt_config(&once, &root).expect("twice");
        assert_eq!(once, twice);
    }

    #[test]
    fn plaintext_config_is_reported_for_migration() {
        let root = temp_root("migration");
        let outcome = decrypt_config(config_with("rtsp://cam.test/live", "s"), &root);
        assert!(outcome.migration_needed);
        assert!(!outcome.locked);
        assert_eq!(outcome.config.sources.len(), 1);
    }

    #[test]
    fn empty_secret_is_left_alone_and_does_not_fail_encryption() {
        let root = temp_root("empty-secret");
        // An unsigned webhook is a legitimate configuration.
        let sealed = encrypt_config(&config_with("rtsp://cam.test/live", ""), &root)
            .expect("empty secret must not fail the write");
        assert_eq!(sealed.rules[0].actions[0]["secret"], json!(""));
    }

    #[test]
    fn undecryptable_value_locks_instead_of_being_dropped() {
        let root = temp_root("locked");
        let mut sealed =
            encrypt_config(&config_with("rtsp://cam.test/live", "s"), &root).expect("encrypt");
        // The source still decrypts, so the key works — yet a single unreadable
        // value must still lock rather than silently delete the rule that holds it.
        sealed.rules[0].actions[0]["secret"] = json!("enc:v2:missing:broken");

        let outcome = decrypt_config(sealed, &root);
        assert!(
            outcome.locked,
            "an unreadable value must lock the config, never delete it"
        );
        assert!(!outcome.migration_needed);
        assert!(outcome.config.sources.is_empty());
        assert!(outcome.config.rules.is_empty());
    }

    /// `encrypt` reports failure by returning its input, not by erroring, so the
    /// only thing standing between a key problem and a plaintext config on disk is
    /// the post-check. Deny the key store and the whole write must fail.
    #[cfg(unix)]
    #[test]
    fn a_config_that_cannot_be_encrypted_is_not_written_in_the_clear() {
        use std::os::unix::fs::PermissionsExt;

        let root = temp_root("no-key");
        let data = root.join("data");
        std::fs::create_dir_all(&data).expect("data dir");
        // Read+execute only: the key store can neither read an existing key nor
        // create one.
        std::fs::set_permissions(&data, std::fs::Permissions::from_mode(0o500)).expect("chmod");

        let result = encrypt_config(&config_with("rtsp://u:p@cam.test/live", "s"), &root);

        std::fs::set_permissions(&data, std::fs::Permissions::from_mode(0o700)).expect("restore");
        assert!(
            result.is_err(),
            "a config that could not be encrypted must not be handed to the writer"
        );
    }

    #[test]
    fn nested_secret_keys_are_protected() {
        let root = temp_root("nested");
        let config = StreamConfig {
            sources: Vec::new(),
            rules: vec![rule_with(json!([
                {"type": "webhook", "headers": {"Authorization": "Bearer deep-token"}}
            ]))],
        };
        let sealed = encrypt_config(&config, &root).expect("encrypt");
        let stored = sealed.rules[0].actions[0]["headers"]["Authorization"]
            .as_str()
            .unwrap();
        assert!(stored.starts_with("enc:"), "{stored}");
        assert!(!stored.contains("deep-token"));
    }

    #[test]
    fn masked_response_hides_credentials_but_keeps_the_host() {
        let rule = rule_with(json!([
            {"type": "webhook", "url": "https://u:p@hook.test/h?k=v", "secret": "hmac-secret-long"}
        ]));
        let masked = masked_response(&rule);
        let action = &masked["actions"][0];
        assert_eq!(action["url"], json!("https://***@hook.test/h?k=***"));
        assert_eq!(action["secret"], json!("h****g"));
        assert_eq!(action["type"], json!("webhook"));
    }

    #[test]
    fn echoing_a_masked_rule_back_keeps_the_stored_secret() {
        let existing = rule_with(json!([
            {"type": "webhook", "url": "https://u:p@hook.test/h", "secret": "hmac-secret-long"}
        ]));
        let masked = masked_response(&existing);
        let mut incoming: DetectionRule =
            serde_json::from_value(masked).expect("masked rule round-trips");

        preserve_masked_rule(&mut incoming, &existing);

        assert_eq!(incoming.actions, existing.actions);
    }

    #[test]
    fn changing_the_destination_does_not_hand_it_the_old_secret() {
        let existing = rule_with(json!([
            {"type": "webhook", "url": "https://hook.test/h", "secret": "hmac-secret-long"}
        ]));
        let masked = masked_response(&existing);
        let mut incoming: DetectionRule =
            serde_json::from_value(masked).expect("masked rule round-trips");
        incoming.actions[0]["url"] = json!("https://attacker.test/h");

        preserve_masked_rule(&mut incoming, &existing);

        assert_ne!(
            incoming.actions[0]["secret"],
            json!("hmac-secret-long"),
            "a new destination must not receive the secret held for the old one"
        );
    }

    #[test]
    fn clearing_a_secret_is_still_possible() {
        let existing = rule_with(json!([
            {"type": "webhook", "url": "https://hook.test/h", "secret": "hmac-secret-long"}
        ]));
        let mut incoming = rule_with(json!([
            {"type": "webhook", "url": "https://hook.test/h", "secret": ""}
        ]));

        preserve_masked_rule(&mut incoming, &existing);

        assert_eq!(incoming.actions[0]["secret"], json!(""));
    }
}

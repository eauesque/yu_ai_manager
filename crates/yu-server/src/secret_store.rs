//! Minimal Python secret-store port for outbound credential use.
//!
//! Python can also load the primary key from the OS keychain. The Rust server
//! intentionally implements only passphrase, keyring-file, and file-key
//! backends; when a secret depends on an unavailable keychain key, decrypt
//! returns an empty string instead of leaking ciphertext.

use std::path::{Path, PathBuf};

use base64::Engine;
use hmac::{Hmac, Mac};
use openssl::rand::rand_bytes;
use openssl::symm::{Cipher, Crypter, Mode};
use pbkdf2::pbkdf2_hmac;
use sha2::Sha256;

const ENC_PREFIX: &str = "enc:";
const ENC_V2_PREFIX: &str = "enc:v2:";
const PBKDF2_ITERATIONS: u32 = 600_000;

type HmacSha256 = Hmac<Sha256>;

pub fn decrypt(stored: &str, project_root: &Path) -> String {
    if stored.is_empty() || !stored.starts_with(ENC_PREFIX) {
        return stored.to_string();
    }
    if let Some(rest) = stored.strip_prefix(ENC_V2_PREFIX) {
        let Some((key_id, token)) = rest.split_once(':') else {
            return String::new();
        };
        let Some(key) = key_by_id(project_root, key_id) else {
            return String::new();
        };
        return decrypt_fernet(token, &key).unwrap_or_default();
    }
    let Some(key) = primary_key(project_root) else {
        return String::new();
    };
    decrypt_fernet(&stored[ENC_PREFIX.len()..], &key).unwrap_or_default()
}

pub fn encrypt(plaintext: &str, project_root: &Path) -> String {
    if plaintext.is_empty() || plaintext.starts_with(ENC_PREFIX) {
        return plaintext.to_string();
    }
    if let Some((key_id, key)) = active_key_with_id(project_root) {
        let token = encrypt_fernet(plaintext, &key).unwrap_or_default();
        if !token.is_empty() {
            return format!("{ENC_V2_PREFIX}{key_id}:{token}");
        }
    }
    if let Some(key) = primary_or_generated_key(project_root) {
        if let Some(token) = encrypt_fernet(plaintext, &key) {
            return format!("{ENC_PREFIX}{token}");
        }
    }
    plaintext.to_string()
}

pub fn encrypt_with_key_id(plaintext: &str, key_id: &str, key: &[u8]) -> Option<String> {
    if plaintext.is_empty() || plaintext.starts_with(ENC_PREFIX) {
        return Some(plaintext.to_string());
    }
    let token = encrypt_fernet(plaintext, key)?;
    Some(format!("{ENC_V2_PREFIX}{key_id}:{token}"))
}

pub fn mask_secret(plaintext: &str) -> String {
    if plaintext.is_empty() {
        String::new()
    } else if plaintext.chars().count() > 12 {
        let first = plaintext.chars().next().unwrap_or_default();
        let last = plaintext.chars().last().unwrap_or_default();
        format!("{first}****{last}")
    } else {
        "****".to_string()
    }
}

#[cfg(test)]
pub(crate) fn encrypt_for_test(plaintext: &str, fernet_key: &[u8]) -> String {
    encrypt_fernet_for_test(plaintext, fernet_key)
}

/// Mask the secret-bearing parts of a URL while keeping it recognisable.
///
/// `mask_secret` is wrong for URLs: the URL is the only human-readable handle a
/// stream source has, so masking it whole makes several cameras indistinguishable
/// in the UI. Only userinfo, query values and the fragment can carry credentials;
/// scheme, host, port and path cannot.
///
/// Anything that does not parse as a URL is returned unchanged when it cannot
/// hold a credential (`0`, `/dev/video0`), and falls back to `mask_secret`
/// otherwise.
pub fn mask_url(raw: &str) -> String {
    // `user:pass@host` parses as scheme `user:` with an opaque path, so parsing alone
    // is not enough — without an authority there is no userinfo to strip and the
    // password would survive untouched.
    let parsed = url::Url::parse(raw).ok().filter(url::Url::has_authority);
    let Some(mut url) = parsed else {
        // No delimiter, no credential. A bare device index or path is not a secret.
        if !raw.contains([':', '@', '?', '#']) {
            return raw.to_string();
        }
        return mask_secret(raw);
    };

    if !url.username().is_empty() || url.password().is_some() {
        // Mask the username too: `http://<token>@host/` puts the whole credential there.
        if url.set_username("***").is_err() || url.set_password(None).is_err() {
            return mask_secret(raw);
        }
    }

    if let Some(query) = url.query() {
        let masked: Vec<String> = url
            .query_pairs()
            .map(|(key, _)| format!("{}=***", urlencoding::encode(&key)))
            .collect();
        if query.is_empty() {
            url.set_query(Some(""));
        } else {
            url.set_query(Some(&masked.join("&")));
        }
    }

    if url.fragment().is_some() {
        url.set_fragment(Some("***"));
    }

    url.to_string()
}

pub fn data_dir(project_root: &Path) -> PathBuf {
    std::env::var_os("TAGDB_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| project_root.join("data"))
}

fn primary_key(project_root: &Path) -> Option<Vec<u8>> {
    passphrase_key(project_root).or_else(|| file_key(project_root))
}

fn primary_or_generated_key(project_root: &Path) -> Option<Vec<u8>> {
    primary_key(project_root).or_else(|| generate_and_store_file_key(project_root))
}

fn passphrase_key(project_root: &Path) -> Option<Vec<u8>> {
    let passphrase = std::env::var("YU_SECRET_PASSPHRASE").ok()?;
    if passphrase.is_empty() {
        return None;
    }
    let salt = std::fs::read(data_dir(project_root).join("secret.salt")).ok()?;
    let mut derived = [0_u8; 32];
    pbkdf2_hmac::<Sha256>(
        passphrase.as_bytes(),
        &salt,
        PBKDF2_ITERATIONS,
        &mut derived,
    );
    Some(
        base64::engine::general_purpose::URL_SAFE
            .encode(derived)
            .into_bytes(),
    )
}

fn file_key(project_root: &Path) -> Option<Vec<u8>> {
    let key = std::fs::read(data_dir(project_root).join("secret.key")).ok()?;
    let trimmed = String::from_utf8_lossy(&key).trim().as_bytes().to_vec();
    (!trimmed.is_empty()).then_some(trimmed)
}

fn generate_and_store_file_key(project_root: &Path) -> Option<Vec<u8>> {
    let mut raw = [0_u8; 32];
    rand_bytes(&mut raw).ok()?;
    let key = base64::engine::general_purpose::URL_SAFE
        .encode(raw)
        .into_bytes();
    let path = data_dir(project_root).join("secret.key");
    std::fs::create_dir_all(path.parent()?).ok()?;
    std::fs::write(&path, &key).ok()?;
    restrict_owner_only(&path);
    Some(key)
}

fn key_by_id(project_root: &Path, key_id: &str) -> Option<Vec<u8>> {
    let raw = std::fs::read_to_string(data_dir(project_root).join("keyring.json")).ok()?;
    let data = serde_json::from_str::<serde_json::Value>(&raw).ok()?;
    let encoded = data
        .get("keys")
        .and_then(serde_json::Value::as_object)?
        .get(key_id)?
        .as_str()?;
    // Python stores urlsafe_b64encode(Fernet-key-form) in keyring.json.
    // Decode once here to recover the 44-byte Fernet key form.
    base64::engine::general_purpose::URL_SAFE
        .decode(encoded.as_bytes())
        .ok()
}

const EXPORT_VERSION: u32 = 1;
const EXPORT_PBKDF2_ITERATIONS: u32 = 600_000;
const MIN_PASSWORD_LENGTH: usize = 8;

/// Export the current encryption key as password-protected JSON (Python-compatible format).
pub fn export_key(password: &str, project_root: &Path) -> serde_json::Value {
    if password.len() < MIN_PASSWORD_LENGTH {
        return serde_json::json!({
            "success": false,
            "export_data": null,
            "message": format!("パスワードは{}文字以上必要です", MIN_PASSWORD_LENGTH),
        });
    }
    let Some(key) = primary_or_generated_key(project_root) else {
        return serde_json::json!({
            "success": false,
            "export_data": null,
            "message": "暗号化鍵が見つかりません",
        });
    };

    let mut salt = [0_u8; 16];
    if rand_bytes(&mut salt).is_err() {
        return serde_json::json!({
            "success": false,
            "export_data": null,
            "message": "乱数生成に失敗しました",
        });
    }

    let wrapper_key = derive_wrapper_key(password.as_bytes(), &salt);
    let key_str = String::from_utf8_lossy(&key).to_string();
    let Some(encrypted_key) = encrypt_fernet(&key_str, &wrapper_key) else {
        return serde_json::json!({
            "success": false,
            "export_data": null,
            "message": "暗号化に失敗しました",
        });
    };

    use sha2::Digest;
    let checksum = format!("{:x}", sha2::Sha256::digest(&key));
    let salt_b64 = base64::engine::general_purpose::STANDARD.encode(salt);

    serde_json::json!({
        "success": true,
        "export_data": {
            "version": EXPORT_VERSION,
            "salt": salt_b64,
            "iterations": EXPORT_PBKDF2_ITERATIONS,
            "encrypted_key": encrypted_key,
            "checksum": checksum,
        },
        "message": "エクスポートが完了しました",
    })
}

/// Import an encryption key from password-protected JSON (Python-compatible format).
pub fn import_key(
    export_data: &serde_json::Value,
    password: &str,
    project_root: &Path,
) -> serde_json::Value {
    if let Some(err) = validate_export_data(export_data) {
        return serde_json::json!({"success": false, "message": err, "backend": null});
    }
    if password.len() < MIN_PASSWORD_LENGTH {
        return serde_json::json!({
            "success": false,
            "message": format!("パスワードは{}文字以上必要です", MIN_PASSWORD_LENGTH),
            "backend": null,
        });
    }

    let salt_b64 = export_data["salt"].as_str().unwrap_or("");
    let Ok(salt) = base64::engine::general_purpose::STANDARD.decode(salt_b64) else {
        return serde_json::json!({"success": false, "message": "ソルトのデコードに失敗しました", "backend": null});
    };

    let wrapper_key = derive_wrapper_key(password.as_bytes(), &salt);
    let encrypted_key = export_data["encrypted_key"].as_str().unwrap_or("");
    let Some(decrypted_key_str) = decrypt_fernet(encrypted_key, &wrapper_key) else {
        return serde_json::json!({
            "success": false,
            "message": "パスワードが正しくないか、データが破損しています",
            "backend": null,
        });
    };

    let decrypted_key = decrypted_key_str.into_bytes();
    use sha2::Digest;
    let checksum = format!("{:x}", sha2::Sha256::digest(&decrypted_key));
    let expected = export_data["checksum"].as_str().unwrap_or("");
    if checksum != expected {
        return serde_json::json!({
            "success": false,
            "message": "チェックサム不一致: データが改竄されている可能性があります",
            "backend": null,
        });
    }

    let key_path = data_dir(project_root).join("secret.key");
    if let Some(parent) = key_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if std::fs::write(&key_path, &decrypted_key).is_err() {
        return serde_json::json!({"success": false, "message": "鍵ファイルの書き込みに失敗しました", "backend": null});
    }
    restrict_owner_only(&key_path);

    serde_json::json!({
        "success": true,
        "message": "鍵のインポートが完了しました",
        "backend": "file",
    })
}

/// Migrate encryption key to OS keychain (stub — keychain not supported in Rust server).
pub fn migrate_to_keychain(_project_root: &Path) -> serde_json::Value {
    serde_json::json!({
        "success": false,
        "message": "OS keychain migration は Rust サーバーでは未対応です。Python サーバーを使用してください。",
        "backend": "file",
    })
}

fn validate_export_data(data: &serde_json::Value) -> Option<String> {
    for field in ["version", "salt", "iterations", "encrypted_key", "checksum"] {
        if data.get(field).is_none() {
            return Some(format!("必須フィールドが不足しています: {field}"));
        }
    }
    if data["version"].as_u64() != Some(EXPORT_VERSION as u64) {
        return Some(format!("未対応のバージョンです: {}", data["version"]));
    }
    if data["iterations"].as_u64().is_none_or(|v| v < 1) {
        return Some("iterations が不正です".to_string());
    }
    None
}

fn derive_wrapper_key(password: &[u8], salt: &[u8]) -> Vec<u8> {
    let mut derived = [0_u8; 32];
    pbkdf2_hmac::<Sha256>(password, salt, EXPORT_PBKDF2_ITERATIONS, &mut derived);
    base64::engine::general_purpose::URL_SAFE
        .encode(derived)
        .into_bytes()
}

pub fn keyring_info(project_root: &Path) -> serde_json::Value {
    let Some(data) = read_keyring(project_root) else {
        return serde_json::json!({"active_key_id": serde_json::Value::Null, "key_ids": []});
    };
    let key_ids = data
        .get("keys")
        .and_then(serde_json::Value::as_object)
        .map(|keys| {
            keys.keys()
                .cloned()
                .map(serde_json::Value::String)
                .collect()
        })
        .unwrap_or_else(Vec::new);
    serde_json::json!({
        "active_key_id": data.get("active").cloned().unwrap_or(serde_json::Value::Null),
        "key_ids": key_ids,
    })
}

pub fn generate_new_active_key(project_root: &Path) -> Option<(String, Vec<u8>)> {
    let mut raw = [0_u8; 32];
    rand_bytes(&mut raw).ok()?;
    let key = base64::engine::general_purpose::URL_SAFE
        .encode(raw)
        .into_bytes();
    let key_id = generate_key_id();
    save_keyring(project_root, &key_id, &key).ok()?;
    Some((key_id, key))
}

fn active_key_with_id(project_root: &Path) -> Option<(String, Vec<u8>)> {
    if let Some(data) = read_keyring(project_root) {
        let active = data.get("active").and_then(serde_json::Value::as_str)?;
        if let Some(key) = key_by_id(project_root, active) {
            return Some((active.to_string(), key));
        }
    }
    let primary = primary_or_generated_key(project_root)?;
    let key_id = generate_key_id();
    save_keyring(project_root, &key_id, &primary).ok()?;
    Some((key_id, primary))
}

fn read_keyring(project_root: &Path) -> Option<serde_json::Value> {
    let raw = std::fs::read_to_string(data_dir(project_root).join("keyring.json")).ok()?;
    serde_json::from_str::<serde_json::Value>(&raw).ok()
}

fn save_keyring(
    project_root: &Path,
    active_key_id: &str,
    key: &[u8],
) -> Result<(), std::io::Error> {
    let path = data_dir(project_root).join("keyring.json");
    let mut data = read_keyring(project_root).unwrap_or_else(|| serde_json::json!({"keys": {}}));
    if !data.get("keys").is_some_and(serde_json::Value::is_object) {
        data["keys"] = serde_json::json!({});
    }
    data["keys"][active_key_id] =
        serde_json::json!(base64::engine::general_purpose::URL_SAFE.encode(key));
    data["active"] = serde_json::json!(active_key_id);
    std::fs::create_dir_all(path.parent().unwrap_or_else(|| Path::new(".")))?;
    std::fs::write(
        &path,
        serde_json::to_string_pretty(&data).unwrap_or_default(),
    )?;
    restrict_owner_only(&path);
    Ok(())
}

fn generate_key_id() -> String {
    let mut suffix = [0_u8; 4];
    let _ = rand_bytes(&mut suffix);
    format!(
        "k_{}{}",
        chrono::Utc::now().format("%Y%m%d"),
        hex::encode(suffix)
    )
}

fn decrypt_fernet(token: &str, key: &[u8]) -> Option<String> {
    let key = base64::engine::general_purpose::URL_SAFE.decode(key).ok()?;
    decrypt_fernet_with_raw_key(token, &key)
}

fn encrypt_fernet(plaintext: &str, key: &[u8]) -> Option<String> {
    let key = base64::engine::general_purpose::URL_SAFE.decode(key).ok()?;
    encrypt_fernet_with_raw_key(plaintext, &key)
}

fn encrypt_fernet_with_raw_key(plaintext: &str, key: &[u8]) -> Option<String> {
    if key.len() != 32 {
        return None;
    }
    let signing_key = &key[..16];
    let encryption_key = &key[16..];
    let mut iv = [0_u8; 16];
    rand_bytes(&mut iv).ok()?;
    let ciphertext = openssl::symm::encrypt(
        Cipher::aes_128_cbc(),
        encryption_key,
        Some(&iv),
        plaintext.as_bytes(),
    )
    .ok()?;
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs();
    let mut signed = vec![0x80];
    signed.extend_from_slice(&timestamp.to_be_bytes());
    signed.extend_from_slice(&iv);
    signed.extend_from_slice(&ciphertext);
    let mut mac = HmacSha256::new_from_slice(signing_key).ok()?;
    mac.update(&signed);
    let sig = mac.finalize().into_bytes();
    signed.extend_from_slice(&sig);
    Some(base64::engine::general_purpose::URL_SAFE.encode(signed))
}

fn decrypt_fernet_with_raw_key(token: &str, key: &[u8]) -> Option<String> {
    if key.len() != 32 {
        return None;
    }
    let signing_key = &key[..16];
    let encryption_key = &key[16..];
    let token = base64::engine::general_purpose::URL_SAFE
        .decode(token.as_bytes())
        .ok()?;
    if token.len() < 1 + 8 + 16 + 32 || token[0] != 0x80 {
        return None;
    }
    let signed_len = token.len().checked_sub(32)?;
    let (signed, expected_sig) = token.split_at(signed_len);
    let mut mac = HmacSha256::new_from_slice(signing_key).ok()?;
    mac.update(signed);
    mac.verify_slice(expected_sig).ok()?;
    let iv = &token[9..25];
    let ciphertext = &token[25..signed_len];
    let cipher = Cipher::aes_128_cbc();
    let mut crypter = Crypter::new(cipher, Mode::Decrypt, encryption_key, Some(iv)).ok()?;
    crypter.pad(true);
    let mut out = vec![0_u8; ciphertext.len() + cipher.block_size()];
    let count = crypter.update(ciphertext, &mut out).ok()?;
    let rest = crypter.finalize(&mut out[count..]).ok()?;
    out.truncate(count + rest);
    String::from_utf8(out).ok()
}

#[cfg(test)]
fn encrypt_fernet_for_test(plaintext: &str, key: &[u8]) -> String {
    let decoded = base64::engine::general_purpose::URL_SAFE
        .decode(key)
        .unwrap();
    let signing_key = &decoded[..16];
    let encryption_key = &decoded[16..];
    let iv = [3_u8; 16];
    let ciphertext = openssl::symm::encrypt(
        Cipher::aes_128_cbc(),
        encryption_key,
        Some(&iv),
        plaintext.as_bytes(),
    )
    .unwrap();
    let mut signed = vec![0x80];
    signed.extend_from_slice(&0_i64.to_be_bytes());
    signed.extend_from_slice(&iv);
    signed.extend_from_slice(&ciphertext);
    let mut mac = HmacSha256::new_from_slice(signing_key).unwrap();
    mac.update(&signed);
    let sig = mac.finalize().into_bytes();
    signed.extend_from_slice(&sig);
    base64::engine::general_purpose::URL_SAFE.encode(signed)
}

fn restrict_owner_only(path: &Path) {
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
    use serde_json::Value;

    fn temp_root(name: &str) -> PathBuf {
        let root =
            std::env::temp_dir().join(format!("yu-secret-store-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("data")).unwrap();
        root
    }

    fn fernet_token(plaintext: &str, key: &[u8]) -> String {
        encrypt_fernet_for_test(plaintext, key)
    }

    #[test]
    fn mask_url_golden_vectors() {
        // Pinned so a `url` crate upgrade cannot silently change what we disclose.
        let cases: &[(&str, &str)] = &[
            // userinfo: the username is masked too, it can be the whole credential
            (
                "rtsp://user:pass@cam.local/live",
                "rtsp://***@cam.local/live",
            ),
            (
                "http://tokenonly@cam.local/live",
                "http://***@cam.local/live",
            ),
            ("rtsp://user:@cam.local/live", "rtsp://***@cam.local/live"),
            // query values go, keys stay
            (
                "rtsp://cam.local/live?token=abc123",
                "rtsp://cam.local/live?token=***",
            ),
            ("https://h/p?a=&b=1", "https://h/p?a=***&b=***"),
            ("https://h/p?a=1&a=2", "https://h/p?a=***&a=***"),
            ("https://h/p?a%20b=1", "https://h/p?a%20b=***"),
            // fragment can carry an access token
            ("https://h/cb#access_token=xyz", "https://h/cb#***"),
            // nothing secret to remove
            ("http://127.0.0.1:8080/hook", "http://127.0.0.1:8080/hook"),
            ("https://h/p?", "https://h/p?"),
            // not a URL, cannot hold a credential
            ("0", "0"),
            ("/dev/video0", "/dev/video0"),
            ("", ""),
            // not a URL but holds a delimiter: fall back to a full mask
            ("://:@?", "****"),
            ("user:pass@host", "u****t"),
        ];
        for (input, expected) in cases {
            assert_eq!(&mask_url(input), expected, "mask_url({input:?})");
        }
    }

    #[test]
    fn mask_url_keeps_no_credential_substring() {
        let secrets = ["camera-password", "abc123", "tokenonly"];
        let inputs = [
            "rtsp://camera-user:camera-password@example.test/live?t=abc123",
            "http://tokenonly@example.test/live",
        ];
        for input in inputs {
            let masked = mask_url(input);
            for secret in secrets {
                assert!(
                    !masked.contains(secret),
                    "mask_url({input:?}) leaked {secret:?}: {masked}"
                );
            }
        }
    }

    #[test]
    fn decrypt_plaintext_passthrough() {
        assert_eq!(decrypt("plain", Path::new(".")), "plain");
        assert_eq!(decrypt("", Path::new(".")), "");
    }

    #[test]
    fn decrypt_legacy_file_key_token() {
        let root = temp_root("legacy");
        let key = base64::engine::general_purpose::URL_SAFE.encode([9_u8; 32]);
        std::fs::write(root.join("data").join("secret.key"), &key).unwrap();
        let token = fernet_token("secret-value", key.as_bytes());
        assert_eq!(decrypt(&format!("enc:{token}"), &root), "secret-value");
    }

    #[test]
    fn decrypt_failure_returns_empty_without_ciphertext_leak() {
        let root = temp_root("failure");
        assert_eq!(decrypt("enc:not-a-token", &root), "");
    }

    #[test]
    fn decrypt_v2_uses_key_id_from_keyring_file() {
        let root = temp_root("v2");
        let key = base64::engine::general_purpose::URL_SAFE.encode([7_u8; 32]);
        let keyring_key = base64::engine::general_purpose::URL_SAFE.encode(key.as_bytes());
        let keyring = serde_json::json!({"active": "k_test", "keys": {"k_test": keyring_key}});
        std::fs::write(
            root.join("data").join("keyring.json"),
            serde_json::to_string(&keyring).unwrap(),
        )
        .unwrap();
        let token = fernet_token("v2-secret", key.as_bytes());
        assert_eq!(
            decrypt(&format!("enc:v2:k_test:{token}"), &root),
            "v2-secret"
        );
    }

    #[test]
    fn decrypts_python_generated_file_and_keyring_fixture() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join("secret_store");
        let tokens = std::fs::read_to_string(root.join("tokens.json")).unwrap();
        let tokens: serde_json::Value = serde_json::from_str(&tokens).unwrap();
        let plaintext = tokens.get("plaintext").and_then(Value::as_str).unwrap();
        let legacy = tokens.get("legacy").and_then(Value::as_str).unwrap();
        let v2 = tokens.get("v2").and_then(Value::as_str).unwrap();

        assert_eq!(decrypt(legacy, &root), plaintext);
        assert_eq!(decrypt(v2, &root), plaintext);
    }

    #[test]
    fn encrypt_writes_v2_keyring_value_and_rust_decrypts_it() {
        let root = temp_root("encrypt-v2");
        let encrypted = encrypt("rust-secret", &root);

        assert!(encrypted.starts_with(ENC_V2_PREFIX));
        assert_eq!(decrypt(&encrypted, &root), "rust-secret");
        assert!(root.join("data").join("keyring.json").exists());
    }

    #[test]
    fn encrypt_uses_python_generated_keyring_fixture() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join("secret_store");
        let encrypted = encrypt("rust-to-python-secret", &root);

        // Read the id from the fixture rather than pinning it, so regenerating
        // with `scripts/internal/gen_secret_store_fixture.py` does not break this.
        let tokens: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(root.join("tokens.json")).unwrap())
                .unwrap();
        let key_id = tokens.get("key_id").and_then(Value::as_str).unwrap();
        assert!(
            encrypted.starts_with(&format!("enc:v2:{key_id}:")),
            "encrypted={encrypted}"
        );
        assert_eq!(decrypt(&encrypted, &root), "rust-to-python-secret");
    }

    #[test]
    fn python_decrypts_rust_encrypted_keyring_fixture() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join("secret_store");
        let repo = fixture
            .parent()
            .and_then(Path::parent)
            .and_then(Path::parent)
            .and_then(Path::parent)
            .and_then(Path::parent)
            .unwrap();
        let encrypted = encrypt("rust-to-python-secret", &fixture);
        let script = r#"
import os, sys
from pathlib import Path
from core.paths import init_app_paths
init_app_paths(data_dir=Path(os.environ["TAGDB_DATA_DIR"]))
from core.settings_core.secret_store import decrypt
value = decrypt(sys.argv[1])
raise SystemExit(0 if value == "rust-to-python-secret" else 1)
"#;
        let status = std::process::Command::new("uv")
            .arg("run")
            .arg("python")
            .arg("-c")
            .arg(script)
            .arg(&encrypted)
            .current_dir(repo)
            .env("TAGDB_DATA_DIR", fixture.join("data"))
            .env(
                "UV_CACHE_DIR",
                std::env::temp_dir().join("yu-server-test-uv-cache"),
            )
            .status()
            .expect("failed to run Python decrypt fixture");

        assert!(status.success());
    }
}

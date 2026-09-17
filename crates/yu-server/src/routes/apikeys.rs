//! API key issuance endpoint (POST /api/apikeys).
//!
//! Ported from `core/web/apikey_auth/key_routes.py::api_create_key` and
//! `key_store.py::create_key`.
//!
//! Auth note: the Python route does **not** call `_require_admin_scope()` on
//! POST (only on GET), but `key_scopes.py:31` maps `/api/apikeys` to the
//! `admin` scope for API-key callers, and `require_admin_scope` passes PIN
//! sessions through on both sides. The check below is therefore behaviourally
//! equivalent to Python, not stricter.
//!
//! When `pin_auth_enabled` is false, `require_admin_scope` returns `None` for
//! every caller (`auth/scope.rs`), so an unauthenticated request can mint an
//! admin key. That matches Python and is stated here because this endpoint
//! issues credentials.

use axum::extract::{Extension, Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::Json;
use serde_json::{json, Map, Value};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::auth::scope::{require_admin_scope, AuthContext};
use crate::config_io;
use crate::ext_config;
use crate::routes::webhook::{api_error, api_success, config_array_mut, random_hex};
use crate::state::SharedState;

/// Mirrors `key_scopes.py::VALID_SCOPES`.
const VALID_SCOPES: &[&str] = &[
    "read",
    "rate",
    "tag.write",
    "collection.write",
    "annotate",
    "scan",
    "admin",
];

/// `sorted(VALID_SCOPES)` as Python renders it in the error message.
const VALID_SCOPES_SORTED_REPR: &str =
    "['admin', 'annotate', 'collection.write', 'rate', 'read', 'scan', 'tag.write']";

/// Render a JSON value the way CPython's `repr()` would.
///
/// `key_scopes.py:46` interpolates the offending element with `{s!r}`, so the
/// message text depends on Python repr rules: `None`/`True`/`False` rather than
/// `null`/`true`/`false`, single-quoted strings, and `, `-separated containers.
fn py_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".to_string(),
        Value::Bool(true) => "True".to_string(),
        Value::Bool(false) => "False".to_string(),
        Value::Number(n) => n.to_string(),
        // Python prefers single quotes and only escapes the quote it used.
        Value::String(s) => format!("'{}'", s.replace('\\', "\\\\").replace('\'', "\\'")),
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(py_repr).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(fields) => format!(
            "{{{}}}",
            fields
                .iter()
                .map(|(k, v)| format!("{}: {}", py_repr(&Value::String(k.clone())), py_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

/// Port of `key_scopes.py::validate_scopes`. Returns the error message, if any.
fn validate_scopes(scopes: &Value) -> Option<String> {
    let Some(items) = scopes.as_array() else {
        return Some("scopes must be an array".to_string());
    };
    for item in items {
        let valid = matches!(item, Value::String(s) if VALID_SCOPES.contains(&s.as_str()));
        if !valid {
            return Some(format!(
                "invalid scope: {}. Valid: {VALID_SCOPES_SORTED_REPR}",
                py_repr(item)
            ));
        }
    }
    None
}

/// Port of `key_store.py::_hash_key`. Must agree with `auth::apikey::verify_key`,
/// which hashes the presented bearer token the same way.
fn sha256_hex(value: &str) -> String {
    use sha2::Digest;
    hex::encode(sha2::Sha256::digest(value.as_bytes()))
}

/// A freshly minted key: the stored entry, plus the raw secret shown once.
struct NewKey {
    /// Stored in `config.api_keys`. Holds `key_hash`, never the raw key.
    entry: Value,
    /// Returned to the caller exactly once; never logged.
    raw_key: String,
}

/// Port of `key_store.py::create_key`.
///
/// `last_used_at` is deliberately **not** written: TOML has no null, and
/// `config_io::write` rejects values it cannot represent, so writing it would
/// make every issuance fail with 500 under a `config.toml` deployment. The GET
/// handler supplies `last_used_at: null` from its fixed field list instead, so
/// the response body still matches Python.
fn new_key(label: String, scopes: Option<&Value>) -> NewKey {
    let raw_key = format!("sk_{}", random_hex(16));
    let created_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;

    let mut entry = Map::new();
    entry.insert("id".into(), json!(format!("ak_{}", random_hex(8))));
    entry.insert("key_hash".into(), json!(sha256_hex(&raw_key)));
    entry.insert("key_prefix".into(), json!(raw_key[..10].to_string()));
    entry.insert(
        "label".into(),
        // `label or f"Key {now}"` — an empty label falls back to a timestamp.
        json!(if label.is_empty() {
            format!("Key {created_at}")
        } else {
            label
        }),
    );
    entry.insert("created_at".into(), json!(created_at));
    // `if scopes:` — an empty list is falsy in Python and stores no field.
    if let Some(list) = scopes.and_then(Value::as_array).filter(|l| !l.is_empty()) {
        entry.insert("scopes".into(), Value::Array(list.clone()));
    }

    NewKey {
        entry: Value::Object(entry),
        raw_key,
    }
}

/// Read the request body as a JSON object, or return the error response.
///
/// Port of `api_request.py::require_json_dict`, which keeps three distinct
/// messages. `webhook.rs::json_object_from_body` collapses them into one and
/// ignores Content-Type, so it cannot be reused here.
async fn json_object_body(
    request: axum::extract::Request,
) -> Result<Map<String, Value>, axum::response::Response> {
    let content_type = request
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    // Quart's `request.is_json` accepts `application/json` and `*/*+json`,
    // ignoring parameters such as `; charset=utf-8`.
    let mime = content_type
        .split(';')
        .next()
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase();

    if mime != "application/json" && !mime.ends_with("+json") {
        return Err(api_error("JSON body is required", StatusCode::BAD_REQUEST).into_response());
    }

    // The body holds a label and a scope list. Cap it rather than reading an
    // unbounded stream from an endpoint that mints credentials.
    const MAX_BODY: usize = 64 * 1024;
    let bytes = match axum::body::to_bytes(request.into_body(), MAX_BODY).await {
        Ok(b) => b,
        Err(_) => {
            return Err(api_error("Invalid JSON body", StatusCode::BAD_REQUEST).into_response())
        }
    };

    let Ok(parsed) = serde_json::from_slice::<Value>(&bytes) else {
        return Err(api_error("Invalid JSON body", StatusCode::BAD_REQUEST).into_response());
    };
    // `if not isinstance(data, dict)` — every other JSON shape is rejected.
    if let Value::Object(map) = parsed {
        Ok(map)
    } else {
        Err(api_error("JSON object body is required", StatusCode::BAD_REQUEST).into_response())
    }
}

/// POST /api/apikeys
pub async fn create_apikey(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    request: axum::extract::Request,
) -> impl IntoResponse {
    if let Some(err) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return err.into_response();
    }

    let body_obj = match json_object_body(request).await {
        Ok(body) => body,
        Err(response) => return response,
    };

    // `data.get("label", "")`, then `if not isinstance(label, str): label = ""`.
    // Python does not truncate; neither may we.
    let label = match body_obj.get("label") {
        Some(Value::String(s)) => s.clone(),
        _ => String::new(),
    };

    let scopes = body_obj.get("scopes").filter(|v| !v.is_null());
    if let Some(value) = scopes {
        if let Some(message) = validate_scopes(value) {
            return api_error(&message, StatusCode::BAD_REQUEST).into_response();
        }
    }

    let new = new_key(label, scopes);
    // One lock for the whole read-modify-write. A separate lock would not
    // exclude the settings writers, and one of the two writes would vanish.
    let _guard = state.settings_lock.lock().await;

    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(e) => {
            return api_error(
                &format!("Failed to read config: {e}"),
                StatusCode::INTERNAL_SERVER_ERROR,
            )
            .into_response()
        }
    };
    config_array_mut(&mut config, "api_keys").push(new.entry.clone());

    if let Err(e) = config_io::write(&state.config.config_path, &config) {
        return api_error(
            &format!("Failed to write config: {e}"),
            StatusCode::INTERNAL_SERVER_ERROR,
        )
        .into_response();
    }

    let mut result = Map::new();
    result.insert("id".into(), new.entry["id"].clone());
    result.insert("key".into(), json!(new.raw_key));
    result.insert("key_prefix".into(), new.entry["key_prefix"].clone());
    result.insert("label".into(), new.entry["label"].clone());
    result.insert("created_at".into(), new.entry["created_at"].clone());
    if let Some(scopes) = new.entry.get("scopes") {
        result.insert("scopes".into(), scopes.clone());
    }

    api_success(Value::Object(result), StatusCode::CREATED).into_response()
}

/// Remove the entry with `key_id`. Returns false when nothing matched.
///
/// Split out of the handler so the miss path is testable: `edit_api_keys` only
/// writes when this reports a hit, and a 404 that still rewrote the config
/// would be a silent corruption no status code reveals.
fn remove_key(keys: &mut Vec<Value>, key_id: &str) -> bool {
    let before = keys.len();
    keys.retain(|key| key.get("id").and_then(Value::as_str) != Some(key_id));
    keys.len() != before
}

/// Set the label of the entry with `key_id`. Returns false when nothing matched.
fn relabel_key(keys: &mut [Value], key_id: &str, label: &str) -> bool {
    for key in keys.iter_mut() {
        if key.get("id").and_then(Value::as_str) == Some(key_id) {
            key["label"] = json!(label);
            return true;
        }
    }
    false
}

/// `label[:100]` in `key_store.py::update_key_label`.
///
/// POST does not truncate at all (`create_key` stores the label as given), so
/// the two endpoints genuinely disagree. That asymmetry is in the source, not
/// in this port; faithfulness wins over tidiness here.
fn truncate_label(label: &str) -> String {
    label.chars().take(100).collect()
}

/// Read the config, hand `edit` the `api_keys` array, write it back if `edit`
/// reports a hit. Returns the handler's response.
///
/// `delete_key` and `update_key_label` are the same read-modify-write as
/// `create_key`, over the same array and under the same lock; only the mutation
/// and the success payload differ. `edit` returns false when no entry matched,
/// which is Python's `return False` -> 404 and, importantly, leaves the config
/// unwritten -- a miss must not rewrite the file.
async fn edit_api_keys(
    state: &SharedState,
    success: Value,
    edit: impl FnOnce(&mut Vec<Value>) -> bool,
) -> axum::response::Response {
    let _guard = state.settings_lock.lock().await;

    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(e) => {
            return api_error(
                &format!("Failed to read config: {e}"),
                StatusCode::INTERNAL_SERVER_ERROR,
            )
            .into_response()
        }
    };

    if !edit(config_array_mut(&mut config, "api_keys")) {
        return api_error("API key not found", StatusCode::NOT_FOUND).into_response();
    }

    if let Err(e) = config_io::write(&state.config.config_path, &config) {
        return api_error(
            &format!("Failed to write config: {e}"),
            StatusCode::INTERNAL_SERVER_ERROR,
        )
        .into_response();
    }

    api_success(success, StatusCode::OK).into_response()
}

/// DELETE /api/apikeys/{key_id}
///
/// Port of `key_routes.py::api_delete_key` / `key_store.py::delete_key`.
/// Without this the UI can mint keys it cannot revoke: `apikeys-keys.ts`
/// calls this path from its Revoke button.
pub async fn delete_apikey(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(key_id): Path<String>,
) -> impl IntoResponse {
    if let Some(err) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return err.into_response();
    }

    let success = json!({ "deleted": key_id });
    edit_api_keys(&state, success, |keys| remove_key(keys, &key_id)).await
}

/// PATCH /api/apikeys/{key_id}
///
/// Port of `key_routes.py::api_update_key` / `key_store.py::update_key_label`.
pub async fn update_apikey(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(key_id): Path<String>,
    request: axum::extract::Request,
) -> impl IntoResponse {
    if let Some(err) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return err.into_response();
    }

    let body = match json_object_body(request).await {
        Ok(body) => body,
        Err(response) => return response,
    };

    // Python rejects a non-string label here, where POST silently coerces it to
    // "". Faithful port: the two endpoints really do differ.
    let Some(Value::String(label)) = body.get("label") else {
        return api_error("label must be a string", StatusCode::BAD_REQUEST).into_response();
    };
    let label = truncate_label(label);

    let success = json!({ "updated": key_id });
    edit_api_keys(&state, success, |keys| relabel_key(keys, &key_id, &label)).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn delete_removes_only_the_named_key() {
        let mut keys = vec![
            json!({"id": "ak_1", "label": "one"}),
            json!({"id": "ak_2", "label": "two"}),
        ];
        assert!(remove_key(&mut keys, "ak_1"));
        assert_eq!(keys.len(), 1);
        assert_eq!(keys[0]["id"], "ak_2");
    }

    /// A miss must report false so `edit_api_keys` skips the write. A 404 that
    /// still rewrote the config would corrupt it with no status code saying so.
    #[test]
    fn delete_reports_a_miss_and_leaves_the_array_alone() {
        let mut keys = vec![json!({"id": "ak_1", "label": "one"})];
        let before = keys.clone();
        assert!(!remove_key(&mut keys, "ak_missing"));
        assert_eq!(keys, before);
    }

    #[test]
    fn patch_relabels_only_the_named_key() {
        let mut keys = vec![
            json!({"id": "ak_1", "label": "one"}),
            json!({"id": "ak_2", "label": "two"}),
        ];
        assert!(relabel_key(&mut keys, "ak_2", "renamed"));
        assert_eq!(keys[0]["label"], "one");
        assert_eq!(keys[1]["label"], "renamed");
    }

    #[test]
    fn patch_reports_a_miss_and_leaves_the_array_alone() {
        let mut keys = vec![json!({"id": "ak_1", "label": "one"})];
        let before = keys.clone();
        assert!(!relabel_key(&mut keys, "ak_missing", "renamed"));
        assert_eq!(keys, before);
    }

    /// Relabelling must not disturb the fields that authenticate the key.
    #[test]
    fn patch_preserves_the_hash_and_scopes() {
        let mut keys = vec![json!({
            "id": "ak_1", "label": "one", "key_hash": "abc",
            "key_prefix": "sk_012345", "created_at": 1, "scopes": ["read"]
        })];
        assert!(relabel_key(&mut keys, "ak_1", "renamed"));
        assert_eq!(keys[0]["key_hash"], "abc");
        assert_eq!(keys[0]["key_prefix"], "sk_012345");
        assert_eq!(keys[0]["created_at"], 1);
        assert_eq!(keys[0]["scopes"], json!(["read"]));
    }

    /// PATCH truncates at 100; POST does not truncate at all. The asymmetry is
    /// in `key_store.py`, so a port that tidied it up would diverge.
    #[test]
    fn patch_truncates_at_a_hundred_where_post_does_not() {
        let long = "x".repeat(300);
        assert_eq!(truncate_label(&long), "x".repeat(100));

        // Python slices by character. Compare the text, not its length: a
        // byte-wise `take(100)` also yields 100 chars' worth of a 3-byte
        // character and would pass a length-only assertion while producing
        // 33 characters plus a mangled tail.
        let kana = "あ".repeat(300);
        assert_eq!(
            truncate_label(&kana),
            "あ".repeat(100),
            "truncation must count characters, not bytes"
        );

        // Mixed widths, so a byte-wise cut lands mid-character and cannot
        // coincide with the correct answer.
        let mixed: String = "aあ".repeat(200);
        let expected: String = mixed.chars().take(100).collect();
        assert_eq!(truncate_label(&mixed), expected);

        // A label already under the cap is returned whole.
        assert_eq!(truncate_label("short"), "short");

        // POST's path leaves the label whole -- proven here beside its opposite
        // so the two cannot silently converge.
        assert_eq!(new_key(long.clone(), None).entry["label"], json!(long));
    }

    #[test]
    fn py_repr_matches_cpython_rendering() {
        assert_eq!(py_repr(&json!(null)), "None");
        assert_eq!(py_repr(&json!(true)), "True");
        assert_eq!(py_repr(&json!(false)), "False");
        assert_eq!(py_repr(&json!(5)), "5");
        assert_eq!(py_repr(&json!("read")), "'read'");
        assert_eq!(py_repr(&json!(["a", 1])), "['a', 1]");
        assert_eq!(py_repr(&json!({"a": 1})), "{'a': 1}");
    }

    #[test]
    fn non_array_scopes_report_the_python_message() {
        assert_eq!(
            validate_scopes(&json!("read")).as_deref(),
            Some("scopes must be an array")
        );
        assert_eq!(
            validate_scopes(&json!({"a": 1})).as_deref(),
            Some("scopes must be an array")
        );
    }

    #[test]
    fn valid_scopes_are_accepted_and_invalid_ones_named() {
        assert_eq!(validate_scopes(&json!([])), None);
        assert_eq!(validate_scopes(&json!(["read", "admin"])), None);
        // Every rejected element uses one message shape, containers included.
        for (input, rendered) in [
            (json!(["nope"]), "'nope'"),
            (json!([5]), "5"),
            (json!([null]), "None"),
            (json!([true]), "True"),
            (json!([["read"]]), "['read']"),
            (json!([{"a": 1}]), "{'a': 1}"),
        ] {
            assert_eq!(
                validate_scopes(&input),
                Some(format!(
                    "invalid scope: {rendered}. Valid: {VALID_SCOPES_SORTED_REPR}"
                ))
            );
        }
    }

    #[test]
    fn labels_are_not_truncated() {
        // `webhook.rs::create_webhook` truncates at 128; `key_store.py` does not.
        let long = "x".repeat(300);
        let key = new_key(long.clone(), None);
        assert_eq!(key.entry["label"], json!(long));
    }

    #[test]
    fn empty_label_falls_back_to_a_timestamp() {
        let key = new_key(String::new(), None);
        let label = key.entry["label"].as_str().unwrap().to_string();
        assert!(label.starts_with("Key "), "unexpected label: {label}");
    }

    #[test]
    fn entry_omits_last_used_at_and_empty_scopes() {
        // TOML cannot hold null, so the field must be absent, not null.
        let key = new_key("dev".into(), Some(&json!([])));
        assert!(key.entry.get("last_used_at").is_none());
        assert!(key.entry.get("scopes").is_none());

        let scoped = new_key("dev".into(), Some(&json!(["read"])));
        assert_eq!(scoped.entry["scopes"], json!(["read"]));
    }

    /// The issued key must authenticate. `new_key` and `verify_key` derive the
    /// hash independently, so this goes red if either side's algorithm drifts.
    #[test]
    fn issued_key_verifies_against_auth() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.json");
        let key = new_key("dev".into(), Some(&json!(["read"])));

        std::fs::write(&config_path, json!({ "api_keys": [key.entry] }).to_string()).unwrap();

        let info = crate::auth::apikey::verify_key(&config_path, &key.raw_key)
            .expect("the freshly issued key must authenticate");
        assert_eq!(
            info.scopes.as_deref(),
            Some(["read".to_string()].as_slice())
        );

        // A key that was never issued must not authenticate.
        assert!(
            crate::auth::apikey::verify_key(&config_path, "sk_deadbeef").is_none(),
            "an unissued token authenticated"
        );
    }

    #[test]
    fn stored_entry_never_holds_the_raw_key() {
        let key = new_key("dev".into(), None);
        let serialized = key.entry.to_string();
        assert!(
            !serialized.contains(&key.raw_key),
            "raw key leaked into the stored entry: {serialized}"
        );
        assert_eq!(
            key.entry["key_prefix"],
            json!(key.raw_key[..10].to_string())
        );
    }
}

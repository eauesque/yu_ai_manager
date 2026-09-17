//! Validation for the server-discovery request bodies, mirroring Python's models.
//!
//! `core/analysis_api/server_discovery_request_models.py` defines four models over
//! `ApiModel` (`extra="forbid"`), and `validate_json_model` reports every error at once
//! as `{ok: false, error: "loc: msg; …", code: "validation_error", detail: "N …"}`.
//! These handlers used to answer `{"success": false, "error": "base_url is required"}`
//! -- a different contract for the same condition, and `success` is a key Python does
//! not have. Measured at 400/400 on six endpoints in v4.734.5.

use serde_json::Value;

/// Pydantic v2's wording, not a paraphrase: the message text is the contract the
/// parity run compares.
const MSG_REQUIRED: &str = "Field required";
const MSG_NOT_STRING: &str = "Input should be a valid string";
const MSG_TOO_SHORT: &str = "String should have at least 1 character";
const MSG_PROVIDER: &str = "Input should be 'ollama', 'openai_compat' or 'hailo_genai'";
const MSG_EXTRA: &str = "Extra inputs are not permitted";

const PROVIDERS: [&str; 3] = ["ollama", "openai_compat", "hailo_genai"];

/// A `StrictStr = Field(min_length=1)` field.
fn required_nonempty_str(
    obj: &serde_json::Map<String, Value>,
    key: &str,
    errors: &mut Vec<String>,
) {
    match obj.get(key) {
        None | Some(Value::Null) => errors.push(format!("{key}: {MSG_REQUIRED}")),
        Some(Value::String(s)) if s.is_empty() => errors.push(format!("{key}: {MSG_TOO_SHORT}")),
        Some(Value::String(_)) => {}
        Some(_) => errors.push(format!("{key}: {MSG_NOT_STRING}")),
    }
}

/// An optional `StrictStr | None` field: absent and null are both fine.
fn optional_str(obj: &serde_json::Map<String, Value>, key: &str, errors: &mut Vec<String>) {
    match obj.get(key) {
        None | Some(Value::Null) | Some(Value::String(_)) => {}
        Some(_) => errors.push(format!("{key}: {MSG_NOT_STRING}")),
    }
}

fn required_provider(obj: &serde_json::Map<String, Value>, errors: &mut Vec<String>) {
    match obj.get("provider") {
        None | Some(Value::Null) => errors.push(format!("provider: {MSG_REQUIRED}")),
        Some(Value::String(s)) if PROVIDERS.contains(&s.as_str()) => {}
        Some(_) => errors.push(format!("provider: {MSG_PROVIDER}")),
    }
}

/// `extra="forbid"`: an unknown key is a 400, not a courtesy.
fn reject_extras(obj: &serde_json::Map<String, Value>, allowed: &[&str], errors: &mut Vec<String>) {
    for key in obj.keys() {
        if !allowed.contains(&key.as_str()) {
            errors.push(format!("{key}: {MSG_EXTRA}"));
        }
    }
}

fn as_object(body: &Value) -> Result<&serde_json::Map<String, Value>, Vec<String>> {
    body.as_object()
        .ok_or_else(|| vec!["Input should be a valid dictionary".to_string()])
}

/// `IgnoreDiscoveredCandidateRequest`: `base_url` only.
pub fn validate_ignore(body: &Value) -> Result<(), Vec<String>> {
    let obj = as_object(body)?;
    let mut errors = Vec::new();
    required_nonempty_str(obj, "base_url", &mut errors);
    reject_extras(obj, &["base_url"], &mut errors);
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors)
    }
}

/// `MatchDiscoveredCandidateRequest`: provider, base_url, then server_id (inherited
/// fields first, which is the order Pydantic reports).
pub fn validate_match(body: &Value) -> Result<(), Vec<String>> {
    let obj = as_object(body)?;
    let mut errors = Vec::new();
    required_provider(obj, &mut errors);
    required_nonempty_str(obj, "base_url", &mut errors);
    required_nonempty_str(obj, "server_id", &mut errors);
    reject_extras(obj, &["provider", "base_url", "server_id"], &mut errors);
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors)
    }
}

/// `RegisterDiscoveredCandidateRequest` and `TestDiscoveredCandidateRequest` (which is
/// `pass` over Register, so one function serves both).
pub fn validate_register(body: &Value) -> Result<(), Vec<String>> {
    let obj = as_object(body)?;
    let mut errors = Vec::new();
    required_provider(obj, &mut errors);
    required_nonempty_str(obj, "base_url", &mut errors);
    for key in ["name", "model", "model_name", "api_key"] {
        optional_str(obj, key, &mut errors);
    }
    reject_extras(
        obj,
        &[
            "provider",
            "base_url",
            "name",
            "model",
            "model_name",
            "api_key",
        ],
        &mut errors,
    );
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// The measured case: the harness sends `{}`, and Python reports every missing
    /// field at once, in declaration order.
    #[test]
    fn an_empty_body_reports_every_missing_field_in_order() {
        assert_eq!(
            validate_ignore(&json!({})).unwrap_err(),
            vec!["base_url: Field required"]
        );
        assert_eq!(
            validate_match(&json!({})).unwrap_err(),
            vec![
                "provider: Field required",
                "base_url: Field required",
                "server_id: Field required",
            ]
        );
        assert_eq!(
            validate_register(&json!({})).unwrap_err(),
            vec!["provider: Field required", "base_url: Field required"]
        );
    }

    #[test]
    fn a_bad_provider_names_the_three_allowed_values() {
        assert_eq!(
            validate_register(&json!({"provider": "nope", "base_url": "http://x"})).unwrap_err(),
            vec!["provider: Input should be 'ollama', 'openai_compat' or 'hailo_genai'"]
        );
    }

    #[test]
    fn strictness_is_not_coercion() {
        // StrictStr: a number is not a string, unlike a lenient model.
        assert_eq!(
            validate_ignore(&json!({"base_url": 8080})).unwrap_err(),
            vec!["base_url: Input should be a valid string"]
        );
        // min_length=1: empty is not absent, and gets its own message.
        assert_eq!(
            validate_ignore(&json!({"base_url": ""})).unwrap_err(),
            vec!["base_url: String should have at least 1 character"]
        );
    }

    #[test]
    fn unknown_keys_are_refused() {
        assert_eq!(
            validate_ignore(&json!({"base_url": "http://x", "oops": 1})).unwrap_err(),
            vec!["oops: Extra inputs are not permitted"]
        );
    }

    #[test]
    fn a_complete_body_passes() {
        assert!(validate_ignore(&json!({"base_url": "http://x"})).is_ok());
        assert!(validate_register(&json!({
            "provider": "ollama", "base_url": "http://x", "name": null
        }))
        .is_ok());
        assert!(validate_match(&json!({
            "provider": "ollama", "base_url": "http://x", "server_id": "s1"
        }))
        .is_ok());
    }
}

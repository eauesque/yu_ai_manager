use std::sync::LazyLock;

use regex::Regex;
use serde_json::Value;

/// What replaces a secret. The key is kept: `token=***` is still a usable log
/// line, a bare `***` is not.
pub(crate) const MASK: &str = "***";

/// Keys whose value is a secret wherever it appears. Word-bounded, so
/// `token_count` and `pinned` survive untouched.
const SECRET_KEYS: &str =
    "api_key|apikey|authorization|cookie|db_key|passphrase|password|pin|secret|session_key|token";

static KV: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(&format!(
        r#"(?i)(?P<key>\b(?:{SECRET_KEYS})\b)(?P<sep>\s*["']?\s*[=:]\s*["']?)(?P<value>[^\s,;&"'}}\]]+)"#
    ))
    .expect("secret key-value pattern is a literal")
});

static BEARER: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(?P<scheme>bearer|basic)\s+(?P<value>[A-Za-z0-9._~+/=-]{8,})")
        .expect("bearer pattern is a literal")
});

static CLI_FLAG: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(&format!(
        r#"(?i)(?P<flag>--(?:{SECRET_KEYS}|db-key|session-key)(?:=|\s+))(?P<value>[^\s,;"']+)"#
    ))
    .expect("cli flag pattern is a literal")
});

/// Replace secret-looking values in `text` with [`MASK`].
///
/// Mirrors `core/infra_core/log_scrub.py`; the two rings serve the same
/// `/api/logs/*` shape and the fleet stream hands lines to a *remote* peer, so
/// a rule that exists on one side only leaves the other side leaking.
pub(crate) fn scrub_secrets(text: &str) -> String {
    let step = CLI_FLAG.replace_all(text, format!("${{flag}}{MASK}"));
    let step = BEARER.replace_all(&step, format!("${{scheme}} {MASK}"));
    KV.replace_all(&step, format!("${{key}}${{sep}}{MASK}"))
        .into_owned()
}

/// Scrub a structured field value in place.
///
/// The Python ring has only a message; this one also carries `fields`, and a
/// tracing call site that records `token = %tok` puts the secret there and not
/// in the message at all -- scrubbing only the message would miss every one.
pub(crate) fn scrub_value(key: &str, value: &mut Value) {
    let key_is_secret = SECRET_KEYS.split('|').any(|k| key.eq_ignore_ascii_case(k));
    match value {
        Value::String(s) => {
            if key_is_secret {
                *s = MASK.to_string();
            } else {
                let scrubbed = scrub_secrets(s);
                if &scrubbed != s {
                    *s = scrubbed;
                }
            }
        }
        _ if key_is_secret => *value = Value::String(MASK.to_string()),
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The shapes this codebase actually produces, not invented ones.
    const LEAKS: &[(&str, &str)] = &[
        (
            "peer request failed: http://10.0.0.5:8765/api/peer/pull?token=abc123DEF",
            "abc123DEF",
        ),
        (
            "spawning: yu-server --db /x/tags.db --pin 4821 --port 8765",
            "4821",
        ),
        (
            "headers={'Authorization': 'Bearer eyJhbGciOi.J9payload.sig'}",
            "eyJhbGciOi.J9payload.sig",
        ),
        (
            r#"body={"api_key": "sk-live-9f8e7d6c5b4a"}"#,
            "sk-live-9f8e7d6c5b4a",
        ),
        (
            "connect failed (db_key=yu-ai-manager-v1-cipher-2026)",
            "yu-ai-manager-v1-cipher-2026",
        ),
        ("Cookie: session=8ac1f0e2b7", "8ac1f0e2b7"),
        ("login rejected: password=hunter2", "hunter2"),
    ];

    #[test]
    fn scrub_removes_the_secret_but_keeps_the_key() {
        for (line, secret) in LEAKS {
            let out = scrub_secrets(line);
            assert!(!out.contains(secret), "{secret} survived in {out}");
            assert!(out.contains(MASK), "no mask in {out}");
        }
    }

    #[test]
    fn scrub_leaves_ordinary_lines_alone() {
        // An over-eager redactor makes the log useless, which is its own outage.
        for line in [
            "scan finished: token_count=1841",
            "pinned 3 items to the board",
            "GET /api/files?limit=20 200 in 12ms",
            "tokenizer loaded (vocab=32000)",
        ] {
            assert_eq!(scrub_secrets(line), line);
        }
    }

    #[test]
    fn scrub_value_masks_a_secret_field_whatever_its_type() {
        let mut s = Value::String("abc123DEF".into());
        scrub_value("token", &mut s);
        assert_eq!(s, Value::String(MASK.into()));

        // A numeric PIN is still a PIN.
        let mut n = Value::from(4821);
        scrub_value("pin", &mut n);
        assert_eq!(n, Value::String(MASK.into()));

        let mut keep = Value::from(1841);
        scrub_value("token_count", &mut keep);
        assert_eq!(keep, Value::from(1841));
    }

    #[test]
    fn scrub_value_still_scans_a_non_secret_field_for_embedded_secrets() {
        let mut url = Value::String("http://p/api/pull?token=abc123DEF".into());
        scrub_value("url", &mut url);
        assert_eq!(
            url,
            Value::String(format!("http://p/api/pull?token={MASK}"))
        );
    }
}

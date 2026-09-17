use std::error::Error;
use std::net::ToSocketAddrs;
use std::time::Duration;

use reqwest::Url;
use serde_json::{json, Value};

const BLOCKED_HOSTNAMES: &[&str] = &["metadata.google.internal", "metadata.goog"];
const PROBE_TIMEOUT: Duration = Duration::from_secs(10);

/// Per-IP portion of the blocklist check, with NO DNS resolution of its own.
/// Callers that already hold a resolved `IpAddr` (e.g. one they intend to
/// pin the connection to) must use this directly instead of
/// `is_blocked_address`, which re-resolves the hostname internally and can
/// therefore validate a different IP than the one actually connected to
/// (DNS-rebinding TOCTOU gap: the validation query and the connect query
/// can get two different answers from an attacker-controlled DNS server).
pub(crate) fn is_blocked_ip(ip: std::net::IpAddr, allow_local: bool) -> bool {
    if ip.is_unspecified() || ip.is_ipv4() && ip.to_string().starts_with("169.254.") {
        return true;
    }
    if ip.is_ipv6() && ip.to_string().to_ascii_lowercase().starts_with("fe80:") {
        return true;
    }
    if !allow_local && (ip.is_loopback() || is_private_ip(ip)) {
        return true;
    }
    false
}

/// Hostname-literal portion of the blocklist (no DNS involved).
pub(crate) fn is_blocked_hostname_literal(hostname: &str) -> bool {
    BLOCKED_HOSTNAMES
        .iter()
        .any(|blocked| hostname.eq_ignore_ascii_case(blocked))
}

/// Convenience wrapper for probe/connection-test call sites that don't hold
/// a pre-resolved IP: resolves `hostname` itself and checks every returned
/// address. NOT safe to use for the actual outbound request client — for
/// that, resolve once via `to_socket_addrs()`, check the single resulting
/// IP with `is_blocked_ip`, and pin the client to that same IP (see
/// `analysis_engines::http_client::build_pinned_client`).
pub(crate) fn is_blocked_address(hostname: &str, allow_local: bool) -> bool {
    if is_blocked_hostname_literal(hostname) {
        return true;
    }
    let addrs = match (hostname, 0).to_socket_addrs() {
        Ok(addrs) => addrs,
        Err(_) => return false,
    };
    addrs
        .map(|addr| addr.ip())
        .any(|ip| is_blocked_ip(ip, allow_local))
}

fn is_private_ip(ip: std::net::IpAddr) -> bool {
    match ip {
        std::net::IpAddr::V4(ip) => ip.is_private(),
        std::net::IpAddr::V6(ip) => {
            let segments = ip.segments();
            (segments[0] & 0xfe00) == 0xfc00
        }
    }
}

fn validate_url(url: &str, allow_local: bool) -> Option<String> {
    let parsed = match Url::parse(url) {
        Ok(parsed) => parsed,
        Err(_) => return Some("Invalid URL".to_string()),
    };
    if !matches!(parsed.scheme(), "http" | "https") {
        return Some("Only http/https URLs are allowed".to_string());
    }
    let Some(hostname) = parsed.host_str().filter(|host| !host.is_empty()) else {
        return Some("No hostname specified".to_string());
    };
    if is_blocked_address(hostname, allow_local) {
        return Some("Blocked address".to_string());
    }
    None
}

pub fn is_private_url(url: &str) -> bool {
    let Ok(parsed) = Url::parse(url) else {
        return false;
    };
    let host = parsed.host_str().unwrap_or("");
    if host == "localhost" || host.is_empty() {
        return true;
    }
    if let Ok(ip) = host.parse::<std::net::IpAddr>() {
        return ip.is_loopback() || is_private_ip(ip);
    }
    match (host, 0).to_socket_addrs() {
        Ok(mut addrs) => addrs
            .next()
            .map(|addr| {
                let ip = addr.ip();
                ip.is_loopback() || is_private_ip(ip)
            })
            .unwrap_or(false),
        Err(_) => false,
    }
}

pub fn validate_ollama_url(url: &str) -> Option<String> {
    validate_url(url, true)
}

pub fn validate_openai_compat_url(url: &str, allow_local: bool) -> Option<String> {
    validate_url(url, allow_local)
}

fn probe_client() -> Result<reqwest::Client, reqwest::Error> {
    reqwest::Client::builder().timeout(PROBE_TIMEOUT).build()
}

pub async fn check_ollama_connection(base_url: &str) -> Value {
    if let Some(error) = validate_ollama_url(base_url) {
        return json!({"connected": false, "models": [], "error": error});
    }
    let Ok(client) = probe_client() else {
        return json!({"connected": false, "models": [], "error": "failed to build HTTP client"});
    };
    let url = format!("{}/api/tags", base_url.trim_end_matches('/'));
    match client
        .get(url)
        .header(reqwest::header::ACCEPT, "application/json")
        .send()
        .await
    {
        Ok(response) => match response.json::<Value>().await {
            Ok(body) => {
                let models = body
                    .get("models")
                    .and_then(Value::as_array)
                    .map(|models| {
                        models
                            .iter()
                            .map(|model| {
                                json!({
                                    "name": model.get("name").and_then(Value::as_str).unwrap_or(""),
                                    "size": model.get("size").and_then(Value::as_i64).unwrap_or(0),
                                })
                            })
                            .collect::<Vec<_>>()
                    })
                    .unwrap_or_default();
                json!({"connected": true, "models": models, "error": null})
            }
            Err(error) => json!({"connected": false, "models": [], "error": error.to_string()}),
        },
        Err(error) => {
            json!({"connected": false, "models": [], "error": format!("Cannot connect: {}", connection_reason(&error))})
        }
    }
}

pub async fn check_openai_compat_connection(base_url: &str, api_key: &str) -> Value {
    check_openai_compat_connection_with_policy(base_url, api_key, false).await
}

pub async fn check_openai_compat_connection_allowing_local(base_url: &str, api_key: &str) -> Value {
    check_openai_compat_connection_with_policy(base_url, api_key, true).await
}

pub async fn list_openai_compat_models(base_url: &str) -> Result<Vec<Value>, reqwest::Error> {
    let client = probe_client()?;
    let response = client
        .get(format!("{}/v1/models", base_url.trim_end_matches('/')))
        .header(reqwest::header::ACCEPT, "application/json")
        .send()
        .await?
        .error_for_status()?;
    let body = response.json::<Value>().await?;
    Ok(body
        .get("data")
        .and_then(Value::as_array)
        .map(|models| {
            models
                .iter()
                .map(|model| {
                    json!({
                        "id": model.get("id").and_then(Value::as_str).unwrap_or(""),
                        "owned_by": model.get("owned_by").and_then(Value::as_str).unwrap_or(""),
                    })
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default())
}

pub async fn check_openai_compat_connection_without_key(base_url: &str) -> Value {
    let Ok(client) = probe_client() else {
        return json!({"connected": false, "models": [], "error": "failed to build HTTP client"});
    };
    let request = client
        .get(format!("{}/v1/models", base_url.trim_end_matches('/')))
        .header(reqwest::header::ACCEPT, "application/json");
    match request.send().await {
        Ok(response) => {
            let status = response.status();
            if status == reqwest::StatusCode::UNAUTHORIZED {
                return json!({"connected": false, "models": [], "error": "Authentication failed (401)"});
            }
            if !status.is_success() {
                return json!({"connected": false, "models": [], "error": format!("HTTP {}", status.as_u16())});
            }
            match response.json::<Value>().await {
                Ok(body) => {
                    let models = body
                        .get("data")
                        .and_then(Value::as_array)
                        .map(|models| {
                            models
                                .iter()
                                .map(|model| {
                                    json!({
                                        "id": model.get("id").and_then(Value::as_str).unwrap_or(""),
                                        "owned_by": model.get("owned_by").and_then(Value::as_str).unwrap_or(""),
                                    })
                                })
                                .collect::<Vec<_>>()
                        })
                        .unwrap_or_default();
                    json!({"connected": true, "models": models, "error": null})
                }
                Err(error) => json!({"connected": false, "models": [], "error": error.to_string()}),
            }
        }
        Err(error) if error.is_timeout() => {
            json!({"connected": false, "models": [], "error": "Connection timeout"})
        }
        Err(error) => {
            json!({"connected": false, "models": [], "error": format!("Cannot connect: {}", connection_reason(&error))})
        }
    }
}

async fn check_openai_compat_connection_with_policy(
    base_url: &str,
    api_key: &str,
    allow_local: bool,
) -> Value {
    if let Some(error) = validate_openai_compat_url(base_url, allow_local) {
        return json!({"connected": false, "models": [], "error": error});
    }
    let Ok(client) = probe_client() else {
        return json!({"connected": false, "models": [], "error": "failed to build HTTP client"});
    };
    let url = format!("{}/v1/models", base_url.trim_end_matches('/'));
    let mut request = client
        .get(url)
        .header(reqwest::header::ACCEPT, "application/json");
    if !api_key.is_empty() {
        request = request.bearer_auth(api_key);
    }
    match request.send().await {
        Ok(response) => {
            let status = response.status();
            if status == reqwest::StatusCode::UNAUTHORIZED {
                return json!({"connected": false, "models": [], "error": "Authentication failed (401)"});
            }
            if !status.is_success() {
                return json!({"connected": false, "models": [], "error": format!("HTTP {}", status.as_u16())});
            }
            match response.json::<Value>().await {
                Ok(body) => {
                    let models = body
                        .get("data")
                        .and_then(Value::as_array)
                        .map(|models| {
                            models
                                .iter()
                                .map(|model| {
                                    json!({
                                        "id": model.get("id").and_then(Value::as_str).unwrap_or(""),
                                        "owned_by": model.get("owned_by").and_then(Value::as_str).unwrap_or(""),
                                    })
                                })
                                .collect::<Vec<_>>()
                        })
                        .unwrap_or_default();
                    json!({"connected": true, "models": models, "error": null})
                }
                Err(error) => json!({"connected": false, "models": [], "error": error.to_string()}),
            }
        }
        Err(error) => {
            json!({"connected": false, "models": [], "error": format!("Cannot connect: {}", connection_reason(&error))})
        }
    }
}

fn connection_reason(error: &reqwest::Error) -> String {
    if error.is_timeout() {
        return "Connection timeout".to_string();
    }
    if error.is_connect() {
        return "[Errno 111] Connection refused".to_string();
    }
    let message = error
        .source()
        .map(ToString::to_string)
        .unwrap_or_else(|| error.to_string());
    if message.contains("Connection refused") || message.contains("os error 111") {
        return "[Errno 111] Connection refused".to_string();
    }
    message
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validator_blocks_metadata_hostname() {
        assert_eq!(
            validate_ollama_url("http://metadata.google.internal"),
            Some("Blocked address".to_string())
        );
    }

    #[test]
    fn validator_blocks_link_local_ip_literal() {
        assert_eq!(
            validate_ollama_url("http://169.254.169.254"),
            Some("Blocked address".to_string())
        );
    }

    #[test]
    fn validator_rejects_bad_scheme() {
        assert_eq!(
            validate_openai_compat_url("file:///tmp/socket", false),
            Some("Only http/https URLs are allowed".to_string())
        );
    }

    #[test]
    fn ollama_validator_allows_localhost() {
        assert_eq!(validate_ollama_url("http://localhost:11434"), None);
    }

    #[test]
    fn openai_compat_validator_blocks_localhost_by_default() {
        assert_eq!(
            validate_openai_compat_url("http://localhost:8000", false),
            Some("Blocked address".to_string())
        );
    }

    #[test]
    fn openai_compat_validator_allows_localhost_when_requested() {
        assert_eq!(
            validate_openai_compat_url("http://localhost:8000", true),
            None
        );
    }

    #[test]
    fn openai_compat_validator_allows_loopback_ip_when_requested() {
        assert_eq!(
            validate_openai_compat_url("http://127.0.0.1:8000", true),
            None
        );
    }

    #[test]
    fn openai_compat_validator_still_blocks_metadata_when_local_is_allowed() {
        assert_eq!(
            validate_openai_compat_url("http://metadata.google.internal", true),
            Some("Blocked address".to_string())
        );
    }

    #[test]
    fn private_url_detection_matches_python_gate_examples() {
        assert!(is_private_url("http://localhost:11434"));
        assert!(is_private_url("http://127.0.0.1:11434"));
        assert!(is_private_url("http://192.168.1.20:8000"));
        assert!(!is_private_url("https://example.com"));
        assert!(!is_private_url("not a url"));
    }

    #[test]
    fn is_blocked_ip_covers_loopback_link_local_and_private_without_dns() {
        use std::net::IpAddr;
        // These must be blockable from a pre-resolved IpAddr alone, with no
        // hostname resolution — this is what closes the DNS-rebinding gap
        // in analysis_engines::http_client::build_pinned_client, which
        // resolves once and must validate that exact IP, not re-resolve.
        assert!(is_blocked_ip("127.0.0.1".parse::<IpAddr>().unwrap(), false));
        assert!(is_blocked_ip(
            "169.254.169.254".parse::<IpAddr>().unwrap(),
            false
        ));
        assert!(is_blocked_ip(
            "192.168.1.20".parse::<IpAddr>().unwrap(),
            false
        ));
        assert!(is_blocked_ip("0.0.0.0".parse::<IpAddr>().unwrap(), false));
        assert!(!is_blocked_ip("8.8.8.8".parse::<IpAddr>().unwrap(), false));
        // allow_local=true permits loopback/private but not link-local/metadata/unspecified.
        assert!(!is_blocked_ip("127.0.0.1".parse::<IpAddr>().unwrap(), true));
        assert!(is_blocked_ip(
            "169.254.169.254".parse::<IpAddr>().unwrap(),
            true
        ));
    }

    #[test]
    fn is_blocked_hostname_literal_covers_metadata_hostnames_without_dns() {
        assert!(is_blocked_hostname_literal("metadata.google.internal"));
        assert!(is_blocked_hostname_literal("METADATA.GOOGLE.INTERNAL"));
        assert!(is_blocked_hostname_literal("metadata.goog"));
        assert!(!is_blocked_hostname_literal("example.com"));
    }
}

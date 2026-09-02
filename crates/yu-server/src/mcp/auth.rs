use std::path::Path;

use axum::http::StatusCode;

use crate::auth::apikey::{check_rate_limit, key_has_scope, verify_key};

/// Inline MCP auth — replaces Python `_check_mcp_auth()`.
///
/// Returns None if the request may proceed, Some(status) to deny.
/// Order: loopback bypass → Bearer required → key verify → scope (admin) → rate limit.
/// Scope is checked BEFORE rate limit (matches Python auth.py:66-71).
pub fn check_mcp_auth(
    resolved_ip: &str,
    auth_header: &str,
    config_path: &Path,
) -> Option<StatusCode> {
    let ip = resolved_ip.trim();
    // Loopback never requires auth (matches Python _is_localhost())
    if matches!(ip, "127.0.0.1" | "::1" | "localhost") {
        return None;
    }

    let bearer = match auth_header.strip_prefix("Bearer ") {
        Some(b) => b.trim(),
        None => return Some(StatusCode::UNAUTHORIZED),
    };

    let key_info = match verify_key(config_path, bearer) {
        Some(k) => k,
        None => return Some(StatusCode::UNAUTHORIZED),
    };

    // Scope first, then rate limit (Python auth.py:66-71 order)
    if !key_has_scope(&key_info, "admin") {
        return Some(StatusCode::FORBIDDEN);
    }

    if !check_rate_limit(&key_info.id) {
        return Some(StatusCode::TOO_MANY_REQUESTS);
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn no_config() -> PathBuf {
        PathBuf::from("/tmp/nonexistent-mcp-auth-test-config.json")
    }

    #[test]
    fn loopback_127_allowed_without_bearer() {
        assert!(check_mcp_auth("127.0.0.1", "", &no_config()).is_none());
    }

    #[test]
    fn loopback_colon1_allowed() {
        assert!(check_mcp_auth("::1", "", &no_config()).is_none());
    }

    #[test]
    fn lan_ip_without_bearer_gets_401() {
        assert_eq!(
            check_mcp_auth("192.168.1.10", "", &no_config()),
            Some(StatusCode::UNAUTHORIZED)
        );
    }

    #[test]
    fn lan_ip_with_invalid_key_gets_401() {
        assert_eq!(
            check_mcp_auth("192.168.1.10", "Bearer invalid-key", &no_config()),
            Some(StatusCode::UNAUTHORIZED)
        );
    }

    #[test]
    fn raw_token_without_bearer_prefix_gets_401() {
        assert_eq!(
            check_mcp_auth("10.0.0.5", "sk_abc123", &no_config()),
            Some(StatusCode::UNAUTHORIZED)
        );
    }
}

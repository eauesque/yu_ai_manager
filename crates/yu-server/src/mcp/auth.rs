use std::path::Path;

use axum::http::StatusCode;

use crate::auth::apikey::{check_rate_limit, key_has_scope, verify_key};

/// Inline MCP auth deliberately diverges from Python `_check_mcp_auth()`.
/// Authentication is unconditional because a same-host reverse proxy makes a loopback
/// source address forgeable.
///
/// Returns None if the request may proceed, Some(status) to deny.
/// Order: Bearer required → key verify → scope (admin) → rate limit.
/// Scope is checked BEFORE rate limit (matches Python auth.py:66-71).
pub fn check_mcp_auth(auth_header: &str, config_path: &Path) -> Option<StatusCode> {
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
    fn missing_header_gets_401() {
        assert_eq!(
            check_mcp_auth("", &no_config()),
            Some(StatusCode::UNAUTHORIZED)
        );
    }

    #[test]
    fn header_without_bearer_prefix_gets_401() {
        assert_eq!(
            check_mcp_auth("sk_abc123", &no_config()),
            Some(StatusCode::UNAUTHORIZED)
        );
    }

    #[test]
    fn unknown_bearer_gets_401() {
        assert_eq!(
            check_mcp_auth("Bearer unknown-key", &no_config()),
            Some(StatusCode::UNAUTHORIZED)
        );
    }
}

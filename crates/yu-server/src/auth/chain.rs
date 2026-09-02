use std::collections::HashSet;
use std::net::IpAddr;

#[derive(Debug, Clone, PartialEq)]
pub struct AuthResult {
    pub passed: bool,
    pub reason: String,
}

impl AuthResult {
    fn allow(reason: &str) -> Self {
        Self {
            passed: true,
            reason: reason.to_string(),
        }
    }
    fn deny(reason: &str) -> Self {
        Self {
            passed: false,
            reason: reason.to_string(),
        }
    }
}

/// All parameters needed to run the auth chain in a single request.
pub struct ChainParams<'a> {
    pub path: &'a str,
    pub method: &'a str,
    pub auth_header: &'a str,
    pub is_locked: bool,
    pub trusted_proxy_enabled: bool,
    /// Resolved client IP (from XFF when trusted_proxy_enabled, else TCP peer).
    pub remote_addr: &'a str,
    /// Raw TCP peer IP — used for trusted-proxy origin check.
    pub tcp_peer: &'a str,
    /// IPs/CIDRs trusted as proxy upstreams.
    pub trusted_ips: &'a HashSet<String>,
    /// IPs trusted as internal peers (for /ext/<name>/v1/ routes).
    pub trusted_peer_ips: &'a HashSet<String>,
    pub remote_user_header: &'a str,
    pub session_pin_ok: bool,
    pub cookie_token: &'a str,
    pub valid_token: &'a str,
}

/// Port of auth_chain_runner.run_chain. Returns None if no check matched
/// (caller should deny).
pub fn run_chain(p: &ChainParams<'_>) -> Option<AuthResult> {
    for check in [check_static_bypass, check_share_bypass, check_pin_bypass] {
        if let Some(r) = check(p.path) {
            return Some(r);
        }
    }
    if let Some(r) = check_loopback_status_bypass(p.path, p.method, p.remote_addr) {
        return Some(r);
    }
    if let Some(r) = check_trusted_peer(p.path, p.remote_addr, p.is_locked, p.trusted_peer_ips) {
        return Some(r);
    }
    if let Some(r) = check_api_key(p.path, p.auth_header) {
        return Some(r);
    }
    if let Some(r) = check_quick_lock(p.is_locked, p.path) {
        return Some(r);
    }
    if let Some(r) = check_trusted_proxy(
        p.trusted_proxy_enabled,
        p.tcp_peer,
        p.trusted_ips,
        p.remote_user_header,
    ) {
        return Some(r);
    }
    if let Some(r) = check_session(p.session_pin_ok) {
        return Some(r);
    }
    check_cookie(p.cookie_token, p.valid_token)
}

// ── individual checks ─────────────────────────────────────────────────────────

pub fn check_static_bypass(path: &str) -> Option<AuthResult> {
    if path.starts_with("/static/") || path == "/favicon.ico" {
        return Some(AuthResult::allow("static"));
    }
    if path.starts_with("/help") || path.starts_with("/api/help/") {
        return Some(AuthResult::allow("help"));
    }
    if path.starts_with("/mcp") {
        return Some(AuthResult::allow("mcp"));
    }
    if path.starts_with("/v1/") {
        return Some(AuthResult::allow("llm_router"));
    }
    // gateway bypass paths
    if path.starts_with("/agentmemory/")
        || path == "/api/gateway/auth/reload"
        || path == "/api/gateway/keys"
        || path.starts_with("/api/gateway/keys/")
    {
        return Some(AuthResult::allow("gateway"));
    }
    // wildcard proxy — handler 内で loopback-only ガードを実施
    if path.starts_with("/ollama/") || path.starts_with("/sd/") {
        return Some(AuthResult::allow("gateway"));
    }
    // E-1 stub パス個別 bypass（blanket 禁止: headroom/config 等 admin ルートを守るため）
    if matches!(
        path,
        "/api/gateway/groups"
            | "/api/gateway/defaults"
            | "/api/gateway/scan/stream"
            | "/api/gateway/scan"
            | "/api/gateway/auth/status"
    ) || path == "/api/gateway/backends"
    {
        return Some(AuthResult::allow("gateway"));
    }
    if path == "/api/mdns/identity" || path == "/api/mdns/peers" {
        return Some(AuthResult::allow("mdns_identity"));
    }
    if path.starts_with("/api/webhooks/receive/") {
        return Some(AuthResult::allow("webhook_inbound"));
    }
    crate::routes::BYPASS_ROUTES
        .iter()
        .find_map(|(pattern, kind, reason)| {
            kind.matches(pattern, path)
                .then(|| AuthResult::allow(reason))
        })
}

pub fn check_share_bypass(path: &str) -> Option<AuthResult> {
    if path.starts_with("/s/") {
        Some(AuthResult::allow("share"))
    } else {
        None
    }
}

pub fn check_pin_bypass(path: &str) -> Option<AuthResult> {
    if path == "/_pin" || path == "/_pin_check" || path == "/api/lock/status" {
        Some(AuthResult::allow("pin_endpoint"))
    } else {
        None
    }
}

pub fn check_loopback_status_bypass(
    path: &str,
    method: &str,
    remote_addr: &str,
) -> Option<AuthResult> {
    if path != "/api/llm_router/status" || method != "GET" {
        return None;
    }
    let addr = remote_addr.trim().to_lowercase();
    if matches!(addr.as_str(), "127.0.0.1" | "::1" | "localhost") {
        Some(AuthResult::allow("llm_router_status_loopback"))
    } else {
        None
    }
}

fn is_valid_ext_name(name: &str) -> bool {
    let mut chars = name.chars();
    match chars.next() {
        Some(c) if c.is_alphanumeric() => {}
        _ => return false,
    }
    chars.all(|c| c.is_alphanumeric() || c == '_' || c == '-')
}

pub(crate) fn is_loopback_addr(addr: &str) -> bool {
    if let Ok(ip) = addr.parse::<IpAddr>() {
        return ip.is_loopback();
    }
    matches!(addr.trim().to_lowercase().as_str(), "localhost")
}

pub(crate) fn ip_in_set(addr: &str, set: &HashSet<String>) -> bool {
    if set.contains(addr) {
        return true;
    }
    let Ok(ip) = addr.parse::<IpAddr>() else {
        return false;
    };
    for entry in set {
        if let Some((net_str, prefix_str)) = entry.split_once('/') {
            let Ok(net_ip) = net_str.parse::<IpAddr>() else {
                continue;
            };
            let Ok(prefix) = prefix_str.parse::<u32>() else {
                continue;
            };
            let matched = match (ip, net_ip) {
                (IpAddr::V4(a), IpAddr::V4(b)) => {
                    let shift = 32u32.saturating_sub(prefix);
                    u32::from(a) >> shift == u32::from(b) >> shift
                }
                (IpAddr::V6(a), IpAddr::V6(b)) => {
                    let shift = 128u32.saturating_sub(prefix);
                    u128::from(a) >> shift == u128::from(b) >> shift
                }
                _ => false,
            };
            if matched {
                return true;
            }
        }
    }
    false
}

pub fn check_trusted_peer(
    path: &str,
    remote_addr: &str,
    is_locked: bool,
    trusted_peer_ips: &HashSet<String>,
) -> Option<AuthResult> {
    let parts: Vec<&str> = path.splitn(5, '/').collect();
    // expect ["", "ext", "<name>", "v1", ...]
    if parts.len() < 4 || parts[1] != "ext" || parts[3] != "v1" {
        return None;
    }
    if !is_valid_ext_name(parts[2]) {
        return None;
    }
    if !ip_in_set(remote_addr, trusted_peer_ips) {
        return None;
    }
    if is_loopback_addr(remote_addr) {
        return Some(AuthResult::allow("trusted_peer_loopback"));
    }
    if is_locked {
        return None; // locked — let quick_lock handle it
    }
    Some(AuthResult::allow("trusted_peer"))
}

pub fn check_api_key(path: &str, auth_header: &str) -> Option<AuthResult> {
    let is_api = path.starts_with("/api/") || (path.contains("/api/") && path.starts_with("/ext/"));
    if is_api && auth_header.starts_with("Bearer ") {
        Some(AuthResult::allow("api_key_candidate"))
    } else {
        None
    }
}

pub fn check_quick_lock(is_locked: bool, path: &str) -> Option<AuthResult> {
    if !is_locked {
        return None;
    }
    if path == "/api/lock/unlock" {
        Some(AuthResult::allow("lock_unlock"))
    } else {
        Some(AuthResult::deny("locked"))
    }
}

pub fn check_trusted_proxy(
    enabled: bool,
    remote_addr: &str,
    trusted_ips: &HashSet<String>,
    remote_user_header: &str,
) -> Option<AuthResult> {
    if !enabled {
        return None;
    }
    if !ip_in_set(remote_addr, trusted_ips) {
        return None;
    }
    let user = remote_user_header.trim();
    if user.is_empty() {
        return None;
    }
    // reject control characters
    if user.chars().any(|c| c < ' ' || c == '\x7f') {
        return None;
    }
    Some(AuthResult::allow("trusted_proxy"))
}

pub fn check_session(session_pin_ok: bool) -> Option<AuthResult> {
    if session_pin_ok {
        Some(AuthResult::allow("session"))
    } else {
        None
    }
}

/// Constant-time cookie comparison. Port of hmac.compare_digest.
pub fn check_cookie(cookie_token: &str, valid_token: &str) -> Option<AuthResult> {
    if cookie_token.is_empty() || valid_token.is_empty() {
        return None;
    }
    let eq = auth_core::verify_token(cookie_token, valid_token);
    if eq {
        Some(AuthResult::allow("cookie"))
    } else {
        None
    }
}

// ── tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_set() -> HashSet<String> {
        HashSet::new()
    }

    fn set(items: &[&str]) -> HashSet<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    /// The pairing handshake must reach its handlers without auth: an unpaired
    /// peer has neither a session nor a token yet. Without these entries the
    /// global auth middleware 401s both paths whenever PIN auth is on, which
    /// silently breaks pairing entirely.
    #[test]
    fn lan_cowork_pairing_handshake_bypasses_auth() {
        for path in [
            "/ext/lan_cowork/api/peer/pair/request",
            "/ext/lan_cowork/api/peer/pair/verify",
        ] {
            let result = check_static_bypass(path).unwrap_or_else(|| panic!("{path} must bypass"));
            assert!(result.passed);
        }
    }

    /// The operator-facing pairing routes must stay behind the auth gate — the
    /// bypass above is deliberately exact-path, never a prefix.
    #[test]
    fn lan_cowork_operator_pairing_routes_do_not_bypass_auth() {
        for path in [
            "/ext/lan_cowork/api/peer/pair/approve",
            "/ext/lan_cowork/api/peer/pair/reject",
            "/ext/lan_cowork/api/peer/pair/requests",
        ] {
            assert!(
                check_static_bypass(path).is_none(),
                "{path} must remain authenticated"
            );
        }
    }

    #[test]
    fn lan_cowork_client_pairing_routes_do_not_bypass_auth() {
        for path in [
            "/ext/lan_cowork/api/client/pair/request",
            "/ext/lan_cowork/api/client/pair/verify",
        ] {
            assert!(
                check_static_bypass(path).is_none(),
                "{path} must remain authenticated"
            );
        }
    }

    #[test]
    fn discover_status_bypass_is_exact_path_only() {
        // The two read endpoints bypass the session gate (Python auth_route
        // bypass_session=True, require="peer"). Handler still gates token richness via
        // session_ok, so unauthenticated callers get the public dict only.
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/discover").is_some());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/status").is_some());
        // Exact-path only: neighbours and prefixes must NOT be bypassed.
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/discovery").is_none());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/status/extra").is_none());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/tokens").is_none());
    }

    #[test]
    fn register_bypass_is_exact_path_only() {
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/register").is_some());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/register/extra").is_none());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/registers").is_none());
    }

    #[test]
    fn token_renew_bypass_is_exact_path_only() {
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/token/renew").is_some());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/token/renew/extra").is_none());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/token").is_none());
    }

    #[test]
    fn event_bypass_is_exact_path_only() {
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/event").is_some());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/event/extra").is_none());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/events").is_none());
    }

    #[test]
    fn heartbeat_bypass_is_exact_path_only() {
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/heartbeat").is_some());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/heartbeat/extra").is_none());
        assert!(check_static_bypass("/ext/lan_cowork/api/peer/heartbeats").is_none());
    }

    #[test]
    fn fleet_bypass_is_limited_to_the_fourteen_peer_routes() {
        for path in [
            "/ext/lan_cowork/fleet/consent/request",
            "/ext/lan_cowork/fleet/consent/respond",
            "/ext/lan_cowork/fleet/consent/status/token",
            "/ext/lan_cowork/fleet/consent/pending",
            "/ext/lan_cowork/fleet/consent/relay/request",
            "/ext/lan_cowork/fleet/consent/relay/status",
            "/ext/lan_cowork/fleet/allowlists/grant",
            "/ext/lan_cowork/fleet/allowlists/revoke",
            "/ext/lan_cowork/fleet/allowlists/check",
            "/ext/lan_cowork/fleet/info",
            "/ext/lan_cowork/fleet/logs/stream",
            "/ext/lan_cowork/fleet/restart",
            "/ext/lan_cowork/fleet/update",
            "/ext/lan_cowork/fleet/update/status",
        ] {
            assert!(check_static_bypass(path).is_some(), "{path}");
        }
        for path in [
            "/ext/lan_cowork/fleet/logs",
            "/ext/lan_cowork/fleet/logs/stream/extra",
            "/ext/lan_cowork/fleet/settings",
            "/ext/lan_cowork/fleet/update/dispatch",
            "/ext/lan_cowork/fleet/restart/dispatch",
            "/ext/lan_cowork/fleet/update/dispatch/status",
            "/ext/lan_cowork/fleet/consent/status/a/b",
        ] {
            assert!(check_static_bypass(path).is_none(), "{path}");
        }
    }

    #[test]
    fn remote_import_bypass_allows_only_peer_routes() {
        for path in [
            "/ext/lan_cowork/api/peer/import/meta",
            "/ext/lan_cowork/api/peer/import/diff",
            "/ext/lan_cowork/api/peer/import/zip",
            "/ext/lan_cowork/api/peer/import/file/1",
            "/ext/lan_cowork/api/peer/import/stream/1",
        ] {
            let result = check_static_bypass(path).unwrap_or_else(|| panic!("{path} must bypass"));
            assert!(result.passed);
        }
        for path in [
            "/ext/lan_cowork/api/peer/import/sessions",
            "/ext/lan_cowork/api/peer/import/session/123",
            "/ext/lan_cowork/api/peer/import/session",
            "/ext/lan_cowork/api/peer/import/execute",
            "/ext/lan_cowork/api/peer/import/index",
        ] {
            assert!(
                check_static_bypass(path).is_none(),
                "{path} must remain session-authenticated"
            );
        }
    }

    #[tokio::test]
    async fn session_gate_is_open_when_pin_auth_is_disabled() {
        assert!(crate::auth::scope::require_session(false, None)
            .await
            .is_none());
    }

    // static bypass
    #[test]
    fn static_path_bypasses() {
        assert!(check_static_bypass("/static/app.js").unwrap().passed);
        assert!(check_static_bypass("/favicon.ico").unwrap().passed);
        assert!(check_static_bypass("/mcp/info").unwrap().passed);
        assert!(check_static_bypass("/v1/chat").unwrap().passed);
    }

    #[test]
    fn non_bypass_static_returns_none() {
        assert!(check_static_bypass("/api/files").is_none());
    }

    // share / pin bypass
    #[test]
    fn share_bypass() {
        assert!(check_share_bypass("/s/abc").unwrap().passed);
        assert!(check_share_bypass("/api/files").is_none());
    }

    #[test]
    fn pin_bypass() {
        assert!(check_pin_bypass("/_pin").unwrap().passed);
        assert!(check_pin_bypass("/_pin_check").unwrap().passed);
        assert!(check_pin_bypass("/api/lock/status").unwrap().passed);
        assert!(check_pin_bypass("/api/files").is_none());
    }

    // loopback status bypass
    #[test]
    fn loopback_status_bypass_allowed() {
        let r = check_loopback_status_bypass("/api/llm_router/status", "GET", "127.0.0.1");
        assert!(r.unwrap().passed);
    }

    #[test]
    fn loopback_status_bypass_denied_non_loopback() {
        assert!(check_loopback_status_bypass("/api/llm_router/status", "GET", "1.2.3.4").is_none());
    }

    // quick lock
    #[test]
    fn quick_lock_blocks_when_locked() {
        let r = check_quick_lock(true, "/api/files").unwrap();
        assert!(!r.passed);
        assert_eq!(r.reason, "locked");
    }

    #[test]
    fn quick_lock_allows_unlock_path() {
        let r = check_quick_lock(true, "/api/lock/unlock").unwrap();
        assert!(r.passed);
    }

    #[test]
    fn quick_lock_noop_when_unlocked() {
        assert!(check_quick_lock(false, "/api/files").is_none());
    }

    // trusted proxy
    #[test]
    fn trusted_proxy_allows_valid() {
        let trusted = set(&["10.0.0.1"]);
        let r = check_trusted_proxy(true, "10.0.0.1", &trusted, "alice");
        assert!(r.unwrap().passed);
    }

    #[test]
    fn trusted_proxy_cidr_match() {
        let trusted = set(&["10.0.0.0/8"]);
        let r = check_trusted_proxy(true, "10.42.0.5", &trusted, "bob");
        assert!(r.unwrap().passed);
    }

    #[test]
    fn trusted_proxy_disabled() {
        let trusted = set(&["10.0.0.1"]);
        assert!(check_trusted_proxy(false, "10.0.0.1", &trusted, "alice").is_none());
    }

    // session
    #[test]
    fn session_allows_when_ok() {
        assert!(check_session(true).unwrap().passed);
        assert!(check_session(false).is_none());
    }

    // cookie
    #[test]
    fn cookie_constant_time_match() {
        assert!(check_cookie("abc123", "abc123").unwrap().passed);
    }

    #[test]
    fn cookie_mismatch_returns_none() {
        assert!(check_cookie("abc123", "xyz999").is_none());
    }

    #[test]
    fn cookie_empty_returns_none() {
        assert!(check_cookie("", "abc123").is_none());
        assert!(check_cookie("abc123", "").is_none());
    }

    // run_chain integration
    #[test]
    fn run_chain_pin_path_bypasses() {
        let params = ChainParams {
            path: "/_pin",
            method: "GET",
            auth_header: "",
            is_locked: true,
            trusted_proxy_enabled: false,
            remote_addr: "1.2.3.4",
            tcp_peer: "1.2.3.4",
            trusted_ips: &empty_set(),
            trusted_peer_ips: &empty_set(),
            remote_user_header: "",
            session_pin_ok: false,
            cookie_token: "",
            valid_token: "",
        };
        let r = run_chain(&params).unwrap();
        assert!(r.passed);
        assert_eq!(r.reason, "pin_endpoint");
    }

    #[test]
    fn run_chain_locked_denies_normal_path() {
        let params = ChainParams {
            path: "/api/files",
            method: "GET",
            auth_header: "",
            is_locked: true,
            trusted_proxy_enabled: false,
            remote_addr: "1.2.3.4",
            tcp_peer: "1.2.3.4",
            trusted_ips: &empty_set(),
            trusted_peer_ips: &empty_set(),
            remote_user_header: "",
            session_pin_ok: false,
            cookie_token: "",
            valid_token: "",
        };
        let r = run_chain(&params).unwrap();
        assert!(!r.passed);
        assert_eq!(r.reason, "locked");
    }

    #[test]
    fn run_chain_session_allows() {
        let params = ChainParams {
            path: "/api/files",
            method: "GET",
            auth_header: "",
            is_locked: false,
            trusted_proxy_enabled: false,
            remote_addr: "1.2.3.4",
            tcp_peer: "1.2.3.4",
            trusted_ips: &empty_set(),
            trusted_peer_ips: &empty_set(),
            remote_user_header: "",
            session_pin_ok: true,
            cookie_token: "",
            valid_token: "",
        };
        let r = run_chain(&params).unwrap();
        assert!(r.passed);
        assert_eq!(r.reason, "session");
    }

    #[test]
    fn run_chain_no_match_returns_none() {
        let params = ChainParams {
            path: "/api/files",
            method: "GET",
            auth_header: "",
            is_locked: false,
            trusted_proxy_enabled: false,
            remote_addr: "1.2.3.4",
            tcp_peer: "1.2.3.4",
            trusted_ips: &empty_set(),
            trusted_peer_ips: &empty_set(),
            remote_user_header: "",
            session_pin_ok: false,
            cookie_token: "",
            valid_token: "",
        };
        assert!(run_chain(&params).is_none());
    }
}

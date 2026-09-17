use std::collections::HashSet;
use std::net::IpAddr;

use crate::auth::chain::ip_in_set;

/// Resolved client IP extracted by auth middleware.
#[derive(Clone, Debug)]
pub struct ClientIp(pub String);

/// Resolve real client IP, mirroring Python api_rate_limit.get_client_ip().
///
/// Builds access_route = XFF IPs + [tcp_ip] (werkzeug Request.access_route semantics),
/// then walks right-to-left and returns the first IP not in trusted_ips.
pub fn resolve_client_ip(
    tcp_ip: &str,
    xff: Option<&str>,
    trusted_proxy_enabled: bool,
    trusted_ips: &HashSet<String>,
) -> String {
    // Python: if not trusted_ips → remote_addr. Rust adds trusted_proxy_enabled as opt-out.
    if !trusted_proxy_enabled || trusted_ips.is_empty() || !ip_in_set(tcp_ip, trusted_ips) {
        return tcp_ip.to_string();
    }
    // access_route = XFF IPs + [tcp_ip], mirroring Python/werkzeug semantics.
    let mut route: Vec<String> = xff
        .map(|s| {
            s.split(',')
                .map(|p| p.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect()
        })
        .unwrap_or_default();
    route.push(tcp_ip.to_string());

    // Walk right-to-left, return first non-trusted IP (Python get_client_ip step ④).
    for ip in route.iter().rev() {
        if !ip_in_set(ip, trusted_ips) {
            if xff_loopback_spoofed_from_external_peer(ip, tcp_ip) {
                return tcp_ip.to_string();
            }
            return ip.clone();
        }
    }
    // All trusted → leftmost, i.e. XFF[0] or tcp_ip if no XFF (Python step ⑤).
    // Note: port-suffixed XFF entries (non-standard) fail ip_in_set parse and are
    // treated as untrusted — safe fail-closed behaviour.
    let leftmost = route
        .into_iter()
        .next()
        .unwrap_or_else(|| tcp_ip.to_string());
    if xff_loopback_spoofed_from_external_peer(&leftmost, tcp_ip) {
        return tcp_ip.to_string();
    }
    leftmost
}

fn xff_loopback_spoofed_from_external_peer(candidate: &str, tcp_ip: &str) -> bool {
    is_loopback_ip(candidate) && !is_loopback_ip(tcp_ip)
}

fn is_loopback_ip(ip: &str) -> bool {
    ip.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ips(list: &[&str]) -> HashSet<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    // Python ①: trusted_ips 空 → trusted_proxy=true でも tcp_ip を返す
    #[test]
    fn empty_trusted_ips_returns_tcp_ip() {
        let result = resolve_client_ip("1.2.3.4", Some("9.9.9.9"), true, &ips(&[]));
        assert_eq!(result, "1.2.3.4");
    }

    // trusted_proxy=false → XFF 無視
    #[test]
    fn proxy_disabled_returns_tcp_ip() {
        let result = resolve_client_ip("1.2.3.4", Some("9.9.9.9"), false, &ips(&["1.2.3.4"]));
        assert_eq!(result, "1.2.3.4");
    }

    // Python ③: tcp_ip が trusted でない → XFF を無視して tcp_ip を返す
    #[test]
    fn untrusted_tcp_returns_tcp_ip() {
        let result = resolve_client_ip("5.5.5.5", Some("9.9.9.9"), true, &ips(&["1.2.3.4"]));
        assert_eq!(result, "5.5.5.5");
    }

    // Python ④: XFF あり・tcp_ip trusted → access_route を右から走査して最初の非 trusted を返す
    #[test]
    fn trusted_proxy_xff_returns_rightmost_untrusted() {
        // access_route = ["192.168.1.100", "10.0.0.1(xff)", "10.0.0.1(tcp)"]
        // 右から: 10.0.0.1(tcp=trusted), 10.0.0.1(xff=trusted), 192.168.1.100(非trusted)
        let result = resolve_client_ip(
            "10.0.0.1",
            Some("192.168.1.100, 10.0.0.1"),
            true,
            &ips(&["10.0.0.1"]),
        );
        assert_eq!(result, "192.168.1.100");
    }

    // Python ⑤: 全 trusted → 最左 (XFF 先頭)
    #[test]
    fn all_trusted_xff_returns_leftmost() {
        // access_route = ["10.0.0.1", "10.0.0.2(xff)", "10.0.0.2(tcp)"]
        let result = resolve_client_ip(
            "10.0.0.2",
            Some("10.0.0.1, 10.0.0.2"),
            true,
            &ips(&["10.0.0.1", "10.0.0.2"]),
        );
        assert_eq!(result, "10.0.0.1");
    }

    // XFF なし・tcp_ip が trusted → access_route = [tcp_ip] → 全 trusted → tcp_ip
    #[test]
    fn trusted_proxy_no_xff_returns_tcp_ip() {
        let result = resolve_client_ip("10.0.0.1", None, true, &ips(&["10.0.0.1"]));
        assert_eq!(result, "10.0.0.1");
    }

    // CIDR: trusted_ips に CIDR 記法が含まれる場合
    #[test]
    fn cidr_trusted_proxy_uses_ip_in_set() {
        // tcp_ip=10.0.0.5 は 10.0.0.0/8 に含まれる → trusted → XFF を解析
        let result = resolve_client_ip(
            "10.0.0.5",
            Some("203.0.113.1, 10.0.0.5"),
            true,
            &ips(&["10.0.0.0/8"]),
        );
        // "203.0.113.1" は /8 に含まれない → 返却
        assert_eq!(result, "203.0.113.1");
    }

    // loopback bypass parity: 外部 peer が XFF=127.0.0.1 を偽装 + proxy disabled
    // → XFF は無視され外部 IP を返す（変更前 Rust は XFF 先頭採用で loopback bypass 突破可能だった）
    #[test]
    fn xff_spoof_loopback_ignored_when_proxy_disabled() {
        let result = resolve_client_ip("203.0.113.1", Some("127.0.0.1"), false, &ips(&[]));
        assert_eq!(result, "203.0.113.1");
    }

    #[test]
    fn xff_spoof_rejected_when_external_peer_with_trusted_proxy() {
        let result = resolve_client_ip("10.0.0.1", Some("127.0.0.1"), true, &ips(&["10.0.0.1"]));
        assert_ne!(result, "127.0.0.1");
    }
}

#[cfg(test)]
mod rate_limit_trusted_proxy_tests {
    use super::*;

    fn set(entries: &[&str]) -> HashSet<String> {
        entries.iter().map(|s| (*s).to_string()).collect()
    }

    /// The default -- no proxies configured -- must resolve to the TCP peer.
    ///
    /// This is what makes adding `Config::rate_limit_trusted_proxies` safe to
    /// land on its own: every deployment that does not set
    /// `server.trusted_proxy_ips` behaves exactly as it does today.
    #[test]
    fn empty_proxy_set_resolves_to_the_tcp_peer() {
        let empty = HashSet::new();
        assert_eq!(
            resolve_client_ip("203.0.113.9", Some("198.51.100.7"), false, &empty),
            "203.0.113.9"
        );
        // Even with the flag on, an empty set cannot trust anything.
        assert_eq!(
            resolve_client_ip("203.0.113.9", Some("198.51.100.7"), true, &empty),
            "203.0.113.9"
        );
    }

    /// A configured proxy hands back the forwarded client, not the proxy.
    ///
    /// Keying the limiter on the proxy's own address would put every user
    /// behind it in one bucket -- DESTRUCTIVE's 12/min shared by the whole LAN,
    /// which is the rate limiter becoming the denial of service.
    #[test]
    fn a_trusted_proxy_yields_the_forwarded_client() {
        let proxies = set(&["10.0.0.1"]);
        assert_eq!(
            resolve_client_ip("10.0.0.1", Some("198.51.100.7"), true, &proxies),
            "198.51.100.7",
            "the bucket key must be the user, not the proxy"
        );
    }

    /// Two users behind the same proxy must not share a bucket.
    #[test]
    fn users_behind_one_proxy_get_distinct_keys() {
        let proxies = set(&["10.0.0.1"]);
        let a = resolve_client_ip("10.0.0.1", Some("198.51.100.7"), true, &proxies);
        let b = resolve_client_ip("10.0.0.1", Some("198.51.100.8"), true, &proxies);
        assert_ne!(a, b);
    }

    /// An untrusted peer's XFF is ignored: otherwise anyone could pick their
    /// own bucket key and the limit would mean nothing.
    #[test]
    fn an_untrusted_peer_cannot_choose_its_own_key() {
        let proxies = set(&["10.0.0.1"]);
        assert_eq!(
            resolve_client_ip("203.0.113.9", Some("198.51.100.7"), true, &proxies),
            "203.0.113.9"
        );
    }
}

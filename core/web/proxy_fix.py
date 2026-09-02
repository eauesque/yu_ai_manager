"""ASGI ProxyFix middleware -- Quart/ASGI equivalent of werkzeug.ProxyFix.

When running behind a reverse proxy (e.g. nginx), this middleware reflects
X-Forwarded-For / X-Forwarded-Proto / X-Forwarded-Host headers into the
ASGI scope so that request.remote_addr / request.scheme / request.host
return correct client information.

Security:
- Only trusts headers from connections originating from trusted_proxy_ips
- Empty list = disabled (safe default)
- X-Forwarded-For chain is traversed right-to-left, skipping trusted IPs,
  and the first untrusted IP is adopted as the real client
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# ASGI type aliases
Scope = dict[str, Any]
Receive = Callable[..., Any]
Send = Callable[..., Any]


def _parse_trusted_ips(raw: set) -> tuple[set[str], list]:
    """Separate trusted_proxy_ips into individual IPs and CIDR networks.

    config.json trusted_proxy_ips accepts entries like ["127.0.0.1", "10.0.0.0/8"].
    Individual IPs use set lookup; CIDRs use network containment checks.
    """
    exact: set[str] = set()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw:
        entry = str(entry).strip()
        if not entry:
            continue
        if "/" in entry:
            try:
                networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                logger.warning("ProxyFix: invalid CIDR: %s", entry)
        else:
            exact.add(entry)
    return exact, networks


def _is_trusted(ip: str, exact: set[str], networks: list) -> bool:
    """Determine whether the IP is a trusted proxy."""
    if ip in exact:
        return True
    if not networks:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in networks)
    except ValueError:
        return False


def _is_loopback_ip(ip: str) -> bool:
    """Return whether *ip* is a valid IPv4 or IPv6 loopback address.

    This mirrors ``is_loopback_ip`` in Rust's ``auth/client_ip.rs``.
    Malformed X-Forwarded-For entries are not loopback addresses.
    """
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _xff_loopback_spoofed_from_external_peer(candidate: str, tcp_ip: str) -> bool:
    """Detect loopback XFF spoofing, paired with Rust ``auth/client_ip.rs``.

    An external TCP peer cannot legitimately represent the client as loopback.
    """
    return _is_loopback_ip(candidate) and not _is_loopback_ip(tcp_ip)


def _find_header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    """Retrieve a header value from the ASGI headers list (case-insensitive)."""
    name_lower = name.lower()
    for key, value in headers:
        if key.lower() == name_lower:
            return value.decode("latin-1")
    return None


def _replace_header(
    headers: list[tuple[bytes, bytes]],
    name: bytes,
    value: str,
) -> list[tuple[bytes, bytes]]:
    """Replace a header in the ASGI headers list (append if absent)."""
    name_lower = name.lower()
    new_headers = [(k, v) for k, v in headers if k.lower() != name_lower]
    new_headers.append((name, value.encode("latin-1")))
    return new_headers


class ProxyFixMiddleware:
    """ASGI middleware: patch ASGI scope from X-Forwarded-* headers.

    Provides the same functionality as Flask's werkzeug.ProxyFix at the
    ASGI level. Ensures Quart's request.remote_addr / request.scheme /
    request.host return correct values even behind a proxy.

    Usage:
        app.asgi_app = ProxyFixMiddleware(app.asgi_app, trusted_ips)
    """

    def __init__(
        self,
        app: Any,
        trusted_ips: set[str],
        *,
        x_for: int = 1,
        x_proto: bool = True,
        x_host: bool = True,
    ) -> None:
        """
        Parameters
        ----------
        app : ASGI application
        trusted_ips : Trusted proxy IPs (individual IPs + CIDRs)
        x_for : How many hops to traverse in the X-Forwarded-For chain (1 = nearest proxy)
        x_proto : Whether to apply X-Forwarded-Proto to scheme
        x_host : Whether to apply X-Forwarded-Host to host
        """
        self._app = app
        self._x_for = x_for
        self._x_proto = x_proto
        self._x_host = x_host
        self._exact_ips, self._networks = _parse_trusted_ips(trusted_ips)
        self._enabled = bool(self._exact_ips or self._networks)

        if self._enabled:
            logger.info(
                "ProxyFix ASGI middleware enabled: %d exact IPs, %d CIDR ranges",
                len(self._exact_ips),
                len(self._networks),
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not self._enabled:
            return await self._app(scope, receive, send)

        # ASGI scope["client"] = (host, port)
        client = scope.get("client")
        if not client:
            return await self._app(scope, receive, send)

        remote_addr = client[0]
        remote_port = client[1]

        # Ignore headers if the direct connection is not from a trusted proxy
        if not _is_trusted(remote_addr, self._exact_ips, self._networks):
            return await self._app(scope, receive, send)

        headers = list(scope.get("headers", []))
        modified = False

        # --- X-Forwarded-For → scope["client"] ---
        xff = _find_header(headers, b"x-forwarded-for")
        if xff:
            ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
            # Skip trusted IPs from the right (closest to proxy)
            real_ip = None
            for ip in reversed(ips):
                if not _is_trusted(ip, self._exact_ips, self._networks):
                    if _xff_loopback_spoofed_from_external_peer(ip, remote_addr):
                        real_ip = remote_addr
                        break
                    real_ip = ip
                    break
            if real_ip is None and ips:
                # All trusted (multi-hop proxy) -- leftmost is the client
                real_ip = ips[0]
                if _xff_loopback_spoofed_from_external_peer(real_ip, remote_addr):
                    real_ip = remote_addr
            if real_ip:
                scope["client"] = (real_ip, remote_port)
                modified = True

        # --- X-Forwarded-Proto → scope["scheme"] ---
        if self._x_proto:
            proto = _find_header(headers, b"x-forwarded-proto")
            if proto:
                scheme = proto.strip().lower()
                if scheme in ("http", "https"):
                    scope["scheme"] = scheme
                    modified = True

        # --- X-Forwarded-Host -> Host header override ---
        if self._x_host:
            fwd_host = _find_header(headers, b"x-forwarded-host")
            if fwd_host:
                scope["headers"] = _replace_header(
                    headers, b"host", fwd_host.strip()
                )
                modified = True

        if modified:
            logger.debug(
                "ProxyFix: %s -> client=%s scheme=%s",
                remote_addr,
                scope.get("client", ("?", 0))[0],
                scope.get("scheme", "?"),
            )

        return await self._app(scope, receive, send)

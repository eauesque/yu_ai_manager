"""Shared address helpers used by mDNS advertising and the identity endpoint.

Kept separate from advertiser.py / runtime_subsystems.py so both consumers
can import the same logic without circular dependencies.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def _pick_lan_ip(*, allow_ipv6: bool = True) -> str | None:
    """Return the first non-loopback LAN IP address string, or None.

    Prefers IPv4 addresses; falls back to IPv6 when no IPv4 is available
    and *allow_ipv6* is True (the default).
    """
    from core.search_api.utils import get_lan_ips

    raw = get_lan_ips()
    ipv4 = [
        ip for ip in raw
        if ip and not ip.startswith("127.") and ":" not in ip
    ]
    if ipv4:
        return ipv4[0]
    if not allow_ipv6:
        return None
    ipv6 = [
        ip for ip in raw
        if ip and ":" in ip and not ip.startswith("::1") and ip != "::1"
    ]
    return ipv6[0] if ipv6 else None


def _is_ipv6(ip: str) -> bool:
    """Return True if *ip* looks like an IPv6 address (contains colon)."""
    return ":" in ip


def _rewrite_host_to_lan(url: str, lan_ip: str) -> str | None:
    """Replace the host of a loopback URL with a LAN-reachable IP.

    Returns None for anything that is not a valid loopback URL — this covers
    invalid strings, non-http schemes, non-loopback hosts, and so on. All of
    these are filtered by a single ``host not in (loopback set)`` check,
    since ``urlparse`` almost never raises on string input (garbage like
    ``"not a url"`` just parses as ``scheme='' hostname=None``).

    Uses urllib.parse so that URLs containing the word "localhost" in their
    **path** (e.g. ``http://localhost/localhost/v1``) only have their
    **netloc** rewritten, not path segments.

    Supports both IPv4 and IPv6 replacement IPs. IPv6 addresses are
    automatically wrapped in brackets for the netloc (e.g. ``[::1]``).

    Behaviour:
      - ``http://localhost:8000/v1`` + ``192.168.1.10`` →
        ``http://192.168.1.10:8000/v1`` (port preserved)
      - ``http://localhost/v1`` + ``192.168.1.10`` →
        ``http://192.168.1.10/v1`` (portless URL → no port in netloc)
      - ``http://localhost:8000/v1`` + ``fe80::1`` →
        ``http://[fe80::1]:8000/v1`` (IPv6 bracket notation)
      - ``http://localhost/v1`` + ``fe80::1`` →
        ``http://[fe80::1]/v1`` (IPv6 portless)
      - ``http://localhost/localhost/v1`` + ``192.168.1.10`` →
        ``http://192.168.1.10/localhost/v1`` (path unchanged)
      - ``http://example.com/v1`` (non-loopback host) → None
      - ``"not a url"`` (garbage) → None (hostname ends up empty)

    The ``except ValueError`` below is defensive belt-and-braces for the
    rare case urlparse receives something truly exotic (e.g. bytes with
    non-ASCII content); the normal garbage-in case flows through the
    ``host not in (...)`` branch.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in ("localhost", "127.0.0.1", "::1"):
        return None
    port = parsed.port  # may be None if the URL did not include a port
    # Wrap IPv6 addresses in brackets for valid URL netloc
    host_part = f"[{lan_ip}]" if _is_ipv6(lan_ip) else lan_ip
    new_netloc = f"{host_part}:{port}" if port else host_part
    return urlunparse(parsed._replace(netloc=new_netloc))

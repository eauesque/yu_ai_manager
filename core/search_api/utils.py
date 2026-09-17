"""Shared helper utilities for search API services."""

import logging
import socket

from core.infra_core.api_params import SQLITE_MAX_INT, SQLITE_MIN_INT, clamp_sqlite_int

# Re-export so existing callers of `from core.search_api.utils import SQLITE_MAX_INT`
# (search_params.py, routes/files_routes.py) keep working without changes.
__all__ = [
    "SQLITE_MAX_INT",
    "SQLITE_MIN_INT",
    "as_int_or_none",
    "clamp_sqlite_int",
    "get_lan_ips",
    "safe_int",
]

logger = logging.getLogger(__name__)


def safe_int(value) -> int | None:
    # Clamp to SQLite signed-64 range so bind params never overflow.
    if not value:
        return None
    try:
        return clamp_sqlite_int(int(value))
    except ValueError:
        return None


def as_int_or_none(value) -> int | None:
    # Only accepts digit strings; clamp to SQLite signed-64 range.
    return clamp_sqlite_int(int(value)) if value and str(value).isdigit() else None


def get_lan_ips():
    """Return non-loopback IPv4 addresses for LAN display.

    Uses UDP routing trick as the primary method because hostname resolution
    on Linux often resolves to 127.0.1.1 (loopback alias in /etc/hosts),
    missing the real interface IP.
    """
    seen: set[str] = set()
    lan_ips: list[str] = []

    def _add(ip: str) -> None:
        if ip and ip not in seen and not ip.startswith("127."):
            seen.add(ip)
            lan_ips.append(ip)

    # Method 1: UDP routing trick — no packet is sent; the kernel consults the
    # routing table to pick the outbound interface, giving us its IP.
    for probe in ("10.255.255.255", "192.168.0.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 1))
                _add(s.getsockname()[0])
            break
        except Exception:
            logger.debug("search step failed", exc_info=True)

    # Method 2: fallback — hostname resolution (may return loopback on Linux)
    if not lan_ips:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                _add(info[4][0])
        except Exception as exc:
            logger.debug("Failed to get LAN IPs via hostname: %s", exc)

    return lan_ips

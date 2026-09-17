"""Resolve a trusted public host/base URL without trusting request Host."""

from __future__ import annotations

from core.search_api.utils import get_lan_ips

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
_WILDCARD_HOSTS = {"0.0.0.0", "::"}


def resolve_public_host(remote_addr: str | None) -> str:
    from core.services_core.db_state import get_config

    remote = (remote_addr or "").strip().lower()
    if remote in _LOCAL_HOSTS:
        return "127.0.0.1"

    config = get_config() or {}
    server = config.get("server") or {}
    configured_host = str(server.get("host", "") or "").strip()
    normalized = configured_host.lower()
    if configured_host and normalized not in _LOCAL_HOSTS and normalized not in _WILDCARD_HOSTS:
        return configured_host

    lan_ips = get_lan_ips()
    return lan_ips[0] if lan_ips else "127.0.0.1"


def resolve_public_port() -> int:
    from core.services_core.db_state import get_config

    config = get_config() or {}
    server = config.get("server") or {}
    try:
        port = int(server.get("port", 5000))
    except (TypeError, ValueError):
        port = 5000
    return port if 1 <= port <= 65535 else 5000


def resolve_public_base_url(remote_addr: str | None, *, port: int | None = None, scheme: str = "http") -> str:
    public_port = resolve_public_port() if port is None else port
    return f"{scheme}://{resolve_public_host(remote_addr)}:{public_port}"

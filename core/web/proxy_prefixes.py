"""Shared transparent proxy path prefixes and browser-origin checks."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlsplit

PROXY_PREFIXES = ("/sd/", "/comfy/", "/ollama/", "/agentmemory/", "/gradio/", "/headroom/")


def is_proxy_path(path: str) -> bool:
    return path.startswith(PROXY_PREFIXES)


def _host_port(value: str, *, is_url: bool) -> tuple[str, int | None] | None:
    try:
        parsed = urlparse(value) if is_url else urlsplit(f"//{value}")
        if is_url and parsed.scheme not in {"http", "https"}:
            return None
        host = parsed.hostname
        if not host:
            return None
        return host.lower(), parsed.port
    except ValueError:
        return None


def proxy_origin_allowed(req: Any) -> bool:
    """Return False when browser Origin/Referer targets a different host."""
    headers = req.headers
    request_host = headers.get("Host", "") or getattr(req, "host", "")
    expected = _host_port(request_host, is_url=False)
    if expected is None:
        return False

    for header_name in ("Origin", "Referer"):
        value = headers.get(header_name, "")
        if not value:
            continue
        observed = _host_port(value, is_url=True)
        if observed != expected:
            return False
    return True

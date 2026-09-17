"""Shared HTTP probes and URL normalization helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

_DEFAULT_USER_AGENT = "yu_ai_manager/discovery"


def normalize_base_url(url: str) -> str:
    """Normalize endpoint base URLs for comparison and storage."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    scheme = (parsed.scheme or "http").lower()
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    port = parsed.port
    default_port = 80 if scheme == "http" else 443 if scheme == "https" else None
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parsed.path.rstrip("/")
    if path and not path.startswith("/"):
        path = f"/{path}"
    return urllib.parse.urlunparse((scheme, netloc, path, "", "", ""))


def probe_ollama_tags(url: str, timeout: float = 3.0, user_agent: str = _DEFAULT_USER_AGENT) -> bool:
    """Return True if ``<url>/api/tags`` responds with HTTP 200."""
    base = normalize_base_url(url)
    if not base:
        return False
    try:
        req = urllib.request.Request(
            f"{base}/api/tags",
            headers={"User-Agent": user_agent},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False


def probe_openai_compat_models(
    url: str,
    *,
    api_key: str = "",
    timeout: float = 3.0,
    user_agent: str = _DEFAULT_USER_AGENT,
) -> tuple[bool, str | None]:
    """Probe ``<url>/v1/models`` and return ``(reachable, reason)``.

    ``reachable`` is True only on HTTP 200. Authentication failures are
    reported as ``("auth_required")`` so callers can distinguish them from
    transport-level failures.
    """
    base = normalize_base_url(url)
    if not base:
        return False, "connection_failed"
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        req = urllib.request.Request(f"{base}/v1/models", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            if resp.status != 200:
                return False, "connection_failed"
            try:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                return False, "invalid_response"
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                return True, None
            return False, "invalid_response"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "auth_required"
        if exc.code == 404:
            return False, "probe_not_found"
        return False, "connection_failed"
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False, "connection_failed"

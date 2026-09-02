from __future__ import annotations

from urllib.parse import urlparse

_REQ_STRIP = frozenset({
    "authorization", "x-api-key", "cookie", "host",
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "user-agent",
    "connection", "keep-alive", "te", "trailers", "transfer-encoding", "upgrade",
    "proxy-authenticate", "proxy-authorization",
})
_RESP_STRIP = frozenset({
    "server", "set-cookie",
    "connection", "keep-alive", "te", "trailers", "transfer-encoding", "upgrade",
    "proxy-authenticate", "proxy-authorization",
})

_MiB = 1024 * 1024
_DEFAULT_BASE_URL = "http://127.0.0.1:3111"

_BODY_LIMITS: dict[str, int] = {
    "/agentmemory/vision-search":       50 * _MiB,
    "/agentmemory/vision-embed":        50 * _MiB,
    "/agentmemory/replay/import-jsonl": 50 * _MiB,
    "/agentmemory/import":              50 * _MiB,
    "/agentmemory/obsidian/export":     20 * _MiB,
}
_DEFAULT_LIMIT = 1 * _MiB

_base_url: str = _DEFAULT_BASE_URL
_upstream_secret: str | None = None


def validate_base_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"agentmemory base_url must use http or https scheme, got: {url!r}"
        )
    if not parsed.hostname:
        raise ValueError(
            f"agentmemory base_url must include a host, got: {url!r}"
        )
    if parsed.query:
        raise ValueError(
            f"agentmemory base_url must not include a query string, got: {url!r}"
        )
    if parsed.fragment:
        raise ValueError(
            f"agentmemory base_url must not include a fragment, got: {url!r}"
        )


def configure(base_url: str | None, secret_plaintext: str | None) -> None:
    """Called once at application startup. Validates and stores base_url and upstream secret."""
    global _base_url, _upstream_secret
    url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
    validate_base_url(url)
    _base_url = url
    _upstream_secret = secret_plaintext


def get_upstream_base_url() -> str:
    return _base_url


def get_body_limit(path: str) -> int:
    return _BODY_LIMITS.get(path, _DEFAULT_LIMIT)


def build_request_headers(headers: dict, client_ip: str) -> dict:
    out = {k: v for k, v in headers.items() if k.lower() not in _REQ_STRIP}
    out["X-Forwarded-For"] = client_ip
    if _upstream_secret:
        out["Authorization"] = f"Bearer {_upstream_secret}"
    return out


def filter_response_headers(headers: dict) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in _RESP_STRIP}

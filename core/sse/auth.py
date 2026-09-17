"""Auth helpers for the dedicated SSE server."""

from __future__ import annotations

import hmac
import time
from hashlib import sha256
from urllib.parse import urlparse

_TOKEN_TTL_SECONDS = 300
_EARLY_REFRESH_SECONDS = 30

_secret: bytes | None = None
_app_port: int | None = None


def configure_sse_auth(secret: str | bytes, app_port: int) -> None:
    """Configure shared auth state used by Quart and the SSE sidecar."""
    global _secret, _app_port
    _secret = secret.encode("utf-8") if isinstance(secret, str) else secret
    _app_port = int(app_port)


def is_configured() -> bool:
    return bool(_secret) and bool(_app_port)


def issue_sse_token(remote_addr: str | None) -> tuple[str, int]:
    """Return a signed token and its expiry for the given client IP."""
    if not _secret:
        raise RuntimeError("SSE auth is not configured")
    ip = (remote_addr or "").strip()
    expires_at = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{expires_at}:{ip}".encode()
    sig = hmac.new(_secret, payload, sha256).hexdigest()
    return f"{expires_at}.{sig}", expires_at


def validate_sse_token(token: str, remote_addr: str | None) -> bool:
    """Validate a signed SSE token for the given client IP."""
    if not _secret:
        return False
    raw = (token or "").strip()
    try:
        expires_raw, sig = raw.split(".", 1)
        expires_at = int(expires_raw)
    except (ValueError, AttributeError):
        return False
    now = int(time.time())
    if expires_at < now:
        return False
    ip = (remote_addr or "").strip()
    payload = f"{expires_at}:{ip}".encode()
    expected = hmac.new(_secret, payload, sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def get_auth_refresh_deadline() -> int:
    """Return the epoch time after which the frontend should refresh auth."""
    return int(time.time()) + _TOKEN_TTL_SECONDS - _EARLY_REFRESH_SECONDS


def is_allowed_sse_origin(origin: str) -> bool:
    """Allow only origins served from the main app port."""
    if not origin or not _app_port:
        return False
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False
    return parsed.port == _app_port

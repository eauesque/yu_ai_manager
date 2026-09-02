from __future__ import annotations

from urllib.parse import urlparse

_DEFAULT_BASE_URL = "http://127.0.0.1:8787"

_base_url: str = _DEFAULT_BASE_URL
_auth_key: str = ""


def validate_base_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("headroom base_url must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("headroom base_url must not contain credentials")
    if not parsed.hostname:
        raise ValueError("headroom base_url must include a host")
    if parsed.query:
        raise ValueError("headroom base_url must not include a query string")
    if parsed.fragment:
        raise ValueError("headroom base_url must not include a fragment")


def configure(base_url: str | None) -> None:
    """Called once at application startup (or on live config update)."""
    global _base_url
    url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
    validate_base_url(url)
    _base_url = url


def configure_auth_key(key: str | None) -> None:
    global _auth_key
    _auth_key = (key or "").strip()


def get_upstream_base_url() -> str:
    return _base_url


def get_upstream_auth_key() -> str:
    return _auth_key

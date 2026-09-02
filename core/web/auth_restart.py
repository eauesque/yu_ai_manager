"""Restart authorization helpers."""

import hmac
import logging
import socket

logger = logging.getLogger(__name__)

from quart import current_app, request

from core.infra_core.api_params import get_str_arg
from core.web.api_rate_limit import get_client_ip

_LOOPBACK_ADDRS = {"127.0.0.1", "::1", "localhost"}
_FORWARDED_HINT_HEADERS = ("X-Forwarded-For", "X-Real-IP", "Forwarded")


def is_truthy_env(v: str | None) -> bool:
    s = (v or "").strip().lower()
    return s in {"1", "true", "yes", "on", "enabled"}


def _hostname_local_ips() -> set[str]:
    local_ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = (info[4][0] or "").strip().lower()
            if ip:
                local_ips.add(ip)
    except Exception as exc:
        logger.debug("Local IP resolution failed: %s", exc)
    return local_ips


def _has_untrusted_forwarded_hints() -> bool:
    trusted_ips = current_app.config.get("TRUSTED_PROXY_IPS", set())
    if trusted_ips:
        return False
    return any(request.headers.get(header) for header in _FORWARDED_HINT_HEADERS)


def _resolved_client_ip() -> str:
    try:
        client_ip = (get_client_ip() or "").strip().lower()
    except Exception:
        client_ip = ""
    resolved = client_ip or (request.remote_addr or "").strip().lower()
    if resolved == "<local>":
        try:
            if bool(current_app.testing):
                return "127.0.0.1"
        except Exception:
            logger.warning("web startup step failed", exc_info=True)
    return resolved


def snapshot_request_origin() -> dict:
    """Capture request-context-dependent origin info for use off-thread.

    Quart's request proxy is bound via contextvars and is not propagated to
    `loop.run_in_executor` worker threads. Call this from inside a request
    handler to snapshot what's needed, then pass the dict into executor work
    and use `is_local_request_from()` / `is_loopback_request_from()` there.
    """
    resolved = _resolved_client_ip()
    has_untrusted = _has_untrusted_forwarded_hints()
    remote = (request.remote_addr or "").strip().lower()
    return {
        "resolved_ip": resolved,
        "remote_addr": remote,
        "has_untrusted_forwarded_hints": has_untrusted,
    }


def is_loopback_request_from(origin: dict) -> bool:
    """Off-thread variant of `is_loopback_request` using a snapshot."""
    if origin.get("has_untrusted_forwarded_hints") and origin.get("remote_addr") in _LOOPBACK_ADDRS:
        return False
    return origin.get("resolved_ip") in _LOOPBACK_ADDRS


def is_local_request_from(origin: dict) -> bool:
    """Off-thread variant of `is_local_request` using a snapshot."""
    client_ip = origin.get("resolved_ip") or ""
    if client_ip in _LOOPBACK_ADDRS:
        return True
    if origin.get("has_untrusted_forwarded_hints"):
        return False
    return client_ip in _hostname_local_ips()


def is_loopback_request() -> bool:
    """Strict localhost check, hardened against untrusted proxy headers."""
    return is_loopback_request_from(snapshot_request_origin())


def is_local_request() -> bool:
    """Local-origin request check for admin/restart APIs."""
    return is_local_request_from(snapshot_request_origin())


def has_remote_restart_token() -> bool:
    tok = current_app.config.get("RESTART_REMOTE_TOKEN")
    return bool(str(tok or "").strip())


def is_remote_restart_authorized(data: dict | None = None) -> bool:
    expected = str(current_app.config.get("RESTART_REMOTE_TOKEN") or "").strip()
    if not expected:
        return False
    supplied = request.headers.get("X-Restart-Token") or get_str_arg(
        (data or {}),
        ("restart_token", "restartToken", "token"),
        "",
    )
    supplied = str(supplied).strip()
    if not supplied:
        return False
    return hmac.compare_digest(expected, supplied)


restart_state = {
    "in_progress": False,
    "last_requested_at": 0.0,
}

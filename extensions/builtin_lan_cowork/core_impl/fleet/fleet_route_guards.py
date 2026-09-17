"""Shared guard helpers for fleet route modules."""
from __future__ import annotations


def ensure_manager(mgr, *, message: str | None = None):
    if mgr is None:
        payload = {"error": "service_unavailable"}
        if message:
            payload["message"] = message
        return payload, 503
    return None


def ensure_session(session_ok, *, ok_key: bool = False):
    if session_ok():
        return None
    payload = {"error": "session required"}
    if ok_key:
        payload = {"ok": False, "error": "session required"}
    return payload, 401


def ensure_chief(mgr, *, ok_key: bool = False, message: str | None = None, status_code: int = 403):
    if "chief" in (mgr.local_peer.roles or []):
        return None
    payload = {"error": "not_chief"}
    if ok_key:
        payload = {"ok": False, "error": "not_chief"}
    if message:
        payload["message"] = message
    return payload, status_code


def build_manager_getter(get_manager, *, message: str | None = None):
    def require_manager():
        mgr = get_manager()
        failure = ensure_manager(mgr, message=message)
        if failure:
            return None, failure
        return mgr, None

    return require_manager


def build_local_chief_getter(
    require_manager,
    session_ok,
    *,
    ok_key: bool = False,
    message: str | None = None,
    status_code: int = 403,
):
    def require_local_chief():
        mgr, failure = require_manager()
        if failure:
            return None, failure
        failure = ensure_session(session_ok, ok_key=ok_key)
        if failure:
            return None, failure
        failure = ensure_chief(mgr, ok_key=ok_key, message=message, status_code=status_code)
        if failure:
            return None, failure
        return mgr, None

    return require_local_chief

"""Inbound webhook CRUD on config.json."""

from __future__ import annotations

import os
import secrets
import threading
import time
from typing import Any

from core.configuration.json_rw import load_config_json, save_config_json

_inbound_cache: list[dict[str, Any]] | None = None
_inbound_lock = threading.Lock()


def _invalidate_inbound_cache() -> None:
    global _inbound_cache
    _inbound_cache = None


def _load_inbound() -> list[dict[str, Any]]:
    cfg = load_config_json()
    return cfg.get("inbound_webhooks", [])


def _save_inbound(hooks: list[dict[str, Any]]) -> None:
    cfg = load_config_json()
    cfg["inbound_webhooks"] = hooks
    save_config_json(cfg)


def create_inbound_webhook(
    label: str = "",
    allowed_events: list[str] | None = None,
) -> dict[str, Any]:
    """Create an inbound webhook. Returns entry with token."""
    entry = {
        "id": "iwh_" + os.urandom(8).hex(),
        "token": secrets.token_hex(32),
        "label": (label or f"Inbound {int(time.time())}")[:128],
        "allowed_events": [str(e)[:64] for e in (allowed_events or [])[:50]],
        "active": True,
        "created_at": int(time.time()),
    }
    with _inbound_lock:
        hooks = _load_inbound()
        hooks.append(entry)
        _save_inbound(hooks)
        _invalidate_inbound_cache()
    return entry


def list_inbound_webhooks() -> list[dict[str, Any]]:
    global _inbound_cache
    with _inbound_lock:
        if _inbound_cache is not None:
            return [dict(wh) for wh in _inbound_cache]
        _inbound_cache = _load_inbound()
        return [dict(wh) for wh in _inbound_cache]


def list_inbound_webhooks_redacted() -> list[dict[str, Any]]:
    """List inbound webhooks without returning bearer tokens."""
    hooks = list_inbound_webhooks()
    result: list[dict[str, Any]] = []
    for wh in hooks:
        item = dict(wh)
        item.pop("token", None)
        result.append(item)
    return result


def get_inbound_by_token(token: str) -> dict[str, Any] | None:
    """Look up inbound webhook by token. Returns None if not found or inactive.

    Uses constant-time comparison to prevent timing side-channel attacks.
    """
    for wh in list_inbound_webhooks():
        if secrets.compare_digest(wh.get("token", ""), token) and wh.get("active", True):
            return wh
    return None


def get_inbound_webhook(wh_id: str) -> dict[str, Any] | None:
    for wh in list_inbound_webhooks():
        if wh.get("id") == wh_id:
            return wh
    return None


def update_inbound_webhook(
    wh_id: str, updates: dict[str, Any]
) -> dict[str, Any] | None:
    with _inbound_lock:
        hooks = _load_inbound()
        for wh in hooks:
            if wh.get("id") == wh_id:
                for key in ("label", "allowed_events", "active"):
                    if key in updates:
                        wh[key] = updates[key]
                _save_inbound(hooks)
                _invalidate_inbound_cache()
                return wh
    return None


def delete_inbound_webhook(wh_id: str) -> bool:
    with _inbound_lock:
        hooks = _load_inbound()
        new_hooks = [w for w in hooks if w.get("id") != wh_id]
        if len(new_hooks) == len(hooks):
            return False
        _save_inbound(new_hooks)
        _invalidate_inbound_cache()
    return True

"""Webhook CRUD on config.json."""

from __future__ import annotations

import os
import threading
import time
from typing import Any
from urllib.parse import urlparse

from core.configuration.json_rw import load_config_json, save_config_json
from core.extensions_core.sandbox.sandbox_http import _is_private_ip as _sandbox_private_ip
from core.settings_core.secret_store import decrypt, encrypt, is_encrypted

# ------------------------------------------------------------------
# Webhook list cache -- avoid re-reading config.json every time
# Invalidate with _invalidate_webhook_cache() on CRUD operations
# ------------------------------------------------------------------
_webhook_cache: list[dict[str, Any]] | None = None
_config_lock = threading.Lock()


def _invalidate_webhook_cache() -> None:
    """Invalidate cache so next list_webhooks() call reloads."""
    global _webhook_cache
    _webhook_cache = None


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/reserved IP address (SSRF protection)."""
    return _sandbox_private_ip(hostname)


def validate_webhook_url(url: str) -> str | None:
    """Validate a webhook URL. Returns error message or None if valid."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "URL must use http or https scheme"
    if not parsed.hostname:
        return "URL must have a valid hostname"
    # Block credentials in URL
    if parsed.username or parsed.password:
        return "URL must not contain credentials"
    # SSRF protection: block private/internal IP ranges
    # ALLOW_LOOPBACK_WEBHOOK=1 disables this check for development/testing
    if not os.environ.get("ALLOW_LOOPBACK_WEBHOOK") and _is_private_ip(parsed.hostname):
        return "URL must not point to a private or internal address"
    return None


def _load_webhooks() -> list[dict[str, Any]]:
    cfg = load_config_json()
    return cfg.get("webhooks", [])


def _save_webhooks(webhooks: list[dict[str, Any]]) -> None:
    cfg = load_config_json()
    cfg["webhooks"] = webhooks
    save_config_json(cfg)


def _ensure_secret() -> str:
    """Ensure webhook_secret exists in config; auto-generate if absent. Stored encrypted."""
    cfg = load_config_json()
    secret = cfg.get("webhook_secret")
    if not secret:
        secret = os.urandom(32).hex()
        cfg["webhook_secret"] = encrypt(secret)
        save_config_json(cfg)
        return secret
    # Decrypt and return if encrypted
    if is_encrypted(secret):
        return decrypt(secret)
    return secret


def get_secret() -> str:
    return _ensure_secret()


def create_webhook(url: str, events: list[str], label: str = "") -> dict[str, Any]:
    """Register a new webhook. Returns the created entry.

    Raises ValueError if the URL fails SSRF validation.
    """
    url_err = validate_webhook_url(url)
    if url_err:
        raise ValueError(url_err)
    _ensure_secret()
    wh_id = "wh_" + os.urandom(8).hex()
    now = int(time.time())
    entry = {
        "id": wh_id,
        "url": url,
        "events": [str(e)[:64] for e in events[:50]],
        "label": (label or f"Webhook {now}")[:128],
        "active": True,
        "created_at": now,
    }
    with _config_lock:
        hooks = _load_webhooks()
        hooks.append(entry)
        _save_webhooks(hooks)
        _invalidate_webhook_cache()
    return entry


def list_webhooks() -> list[dict[str, Any]]:
    global _webhook_cache
    with _config_lock:
        if _webhook_cache is not None:
            return _webhook_cache
        _webhook_cache = _load_webhooks()
        return _webhook_cache


def get_webhook(wh_id: str) -> dict[str, Any] | None:
    for wh in list_webhooks():
        if wh.get("id") == wh_id:
            return wh
    return None


def update_webhook(wh_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update webhook fields. Returns updated entry or None if not found.

    Raises ValueError if a new URL fails SSRF validation.
    """
    if "url" in updates:
        url_err = validate_webhook_url(updates["url"])
        if url_err:
            raise ValueError(url_err)
    with _config_lock:
        hooks = _load_webhooks()
        for wh in hooks:
            if wh.get("id") == wh_id:
                for key in ("url", "events", "label", "active"):
                    if key in updates:
                        wh[key] = updates[key]
                _save_webhooks(hooks)
                _invalidate_webhook_cache()
                return wh
    return None


def delete_webhook(wh_id: str) -> bool:
    with _config_lock:
        hooks = _load_webhooks()
        new_hooks = [w for w in hooks if w.get("id") != wh_id]
        if len(new_hooks) == len(hooks):
            return False
        _save_webhooks(new_hooks)
        _invalidate_webhook_cache()
    return True

"""API key CRUD on config.json.

Keys are stored as hashes; the raw key is only returned at creation time.
Format: sk_ + 32 hex chars (128-bit).
Stored fields per key:
  {id, key_hash, key_prefix, label, created_at, last_used_at}
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

from core.configuration.json_rw import load_config_json, save_config_json

logger = logging.getLogger(__name__)


def _gen_key() -> str:
    """Generate a new API key: sk_ + 32 hex."""
    return "sk_" + os.urandom(16).hex()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _load_keys() -> list[dict[str, Any]]:
    cfg = load_config_json()
    return cfg.get("api_keys", [])


def _save_keys(keys: list[dict[str, Any]]) -> None:
    cfg = load_config_json()
    cfg["api_keys"] = keys
    save_config_json(cfg)


def create_key(label: str = "", scopes: list[str] | None = None) -> dict[str, Any]:
    """Create a new API key. Returns dict including the raw key (one-time).

    scopes: list of scope strings. Empty list or None = full access.
    """
    raw_key = _gen_key()
    key_id = "ak_" + os.urandom(8).hex()
    now = int(time.time())
    entry: dict[str, Any] = {
        "id": key_id,
        "key_hash": _hash_key(raw_key),
        "key_prefix": raw_key[:10],
        "label": label or f"Key {now}",
        "created_at": now,
        "last_used_at": None,
    }
    if scopes:
        entry["scopes"] = list(scopes)
    keys = _load_keys()
    keys.append(entry)
    _save_keys(keys)
    result: dict[str, Any] = {
        "id": key_id,
        "key": raw_key,
        "key_prefix": raw_key[:10],
        "label": entry["label"],
        "created_at": now,
    }
    if scopes:
        result["scopes"] = list(scopes)
    return result


def list_keys() -> list[dict[str, Any]]:
    """List all API keys (without hashes, prefix only)."""
    result = []
    for k in _load_keys():
        entry: dict[str, Any] = {
            "id": k["id"],
            "key_prefix": k.get("key_prefix", ""),
            "label": k.get("label", ""),
            "created_at": k.get("created_at"),
            "last_used_at": k.get("last_used_at"),
        }
        scopes = k.get("scopes")
        if scopes:
            entry["scopes"] = scopes
        result.append(entry)
    return result


def delete_key(key_id: str) -> bool:
    """Delete (revoke) an API key by id. Returns True if found."""
    keys = _load_keys()
    new_keys = [k for k in keys if k.get("id") != key_id]
    if len(new_keys) == len(keys):
        return False
    _save_keys(new_keys)
    return True


def update_key_label(key_id: str, label: str) -> bool:
    """Update the label of an existing API key. Returns True if found."""
    keys = _load_keys()
    for k in keys:
        if k.get("id") == key_id:
            k["label"] = label[:100]
            _save_keys(keys)
            return True
    return False


def verify_key(raw_key: str) -> dict[str, Any] | None:
    """Verify a raw API key. Returns key entry (without hash) or None."""
    if not raw_key or not raw_key.startswith("sk_"):
        return None
    key_hash = _hash_key(raw_key)
    keys = _load_keys()
    for k in keys:
        if hmac.compare_digest(k.get("key_hash", ""), key_hash):
            _touch_last_used(k["id"])
            info: dict[str, Any] = {
                "id": k["id"],
                "label": k.get("label", ""),
                "key_prefix": k.get("key_prefix", ""),
            }
            scopes = k.get("scopes")
            if scopes:
                info["scopes"] = scopes
            return info
    return None


def _touch_last_used(key_id: str) -> None:
    """Update last_used_at timestamp (best-effort, no lock)."""
    try:
        cfg = load_config_json()
        keys = cfg.get("api_keys", [])
        for k in keys:
            if k.get("id") == key_id:
                k["last_used_at"] = int(time.time())
                break
        cfg["api_keys"] = keys
        save_config_json(cfg)
    except Exception:
        logger.warning("web startup step failed", exc_info=True)

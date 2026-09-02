"""Bitwarden read operations: retrieve secrets, resolve config mappings, list folders."""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

from .bw_cli import (
    BW_TIMEOUT,
    get_cache,
    is_available,
    key_to_field_name,
    parse_bw_error,
    run_bw,
)

logger = logging.getLogger(__name__)


# -- Secret Reading --------------------------------------------------------


def read_secret(item_id: str, field_name: str, ttl: int = 300) -> str | None:
    """Retrieve a field value from a bw item via `bw get item`.

    Returns cached value within TTL seconds.

    Args:
        item_id: Item ID or item name.
        field_name: Custom field name, or "password" for login password.
        ttl: Cache validity period (seconds).

    Returns:
        Field value, or None on error.
    """
    import json as _json

    _cache = get_cache()
    cache_key = f"{item_id}:{field_name}"
    now = time.time()

    # Cache hit
    if cache_key in _cache:
        value, expiry = _cache[cache_key]
        if now < expiry:
            return value

    if not is_available():
        logger.warning("bw CLI not found")
        return None

    try:
        r = run_bw(["get", "item", item_id])

        if r.returncode != 0:
            msg = parse_bw_error(r.stderr)
            logger.warning("bw get item failed: %s", msg)
            return None

        item = _json.loads(r.stdout)

        # Return login password if field_name is "password"
        if field_name == "password":
            login = item.get("login")
            if login and login.get("password"):
                value = login["password"]
                _cache[cache_key] = (value, now + ttl)
                return value
            logger.warning("bw: item '%s' has no login password", item_id)
            return None

        # Search in custom fields
        fields = item.get("fields") or []
        for f in fields:
            if f.get("name") == field_name:
                value = f.get("value", "")
                _cache[cache_key] = (value, now + ttl)
                return value

        logger.warning(
            "bw: field '%s' not found in item '%s'",
            field_name, item_id,
        )
        return None

    except subprocess.TimeoutExpired:
        logger.warning("bw get item timeout (%ds): %s", BW_TIMEOUT, item_id)
        return None
    except FileNotFoundError:
        logger.warning("bw CLI not found")
        return None
    except (_json.JSONDecodeError, Exception) as e:
        logger.warning("bw get item error: %s", e)
        return None


def resolve_secret(key: str, config: dict[str, Any]) -> str | None:
    """Resolve a secret via config's bw_secrets mapping and fetch with bw get.

    Returns None if the key is not in bw_secrets (local value should be used).

    bw_secrets format:
        {"server.pin": {"item": "YU AI Manager", "field": "server_pin"}}

    Args:
        key: Dot-notation key (e.g. "server.pin").
        config: config.json dict.
    """
    bw_map = config.get("bw_secrets", {})
    if not isinstance(bw_map, dict):
        return None

    entry = bw_map.get(key)
    if not entry:
        return None

    # String format: treat as item name, auto-convert field name from key
    if isinstance(entry, str):
        return read_secret(entry, key_to_field_name(key))

    # Dict format: {"item": "...", "field": "..."}
    if isinstance(entry, dict):
        item_id = entry.get("item", "")
        field_name = entry.get("field", key_to_field_name(key))
        if not item_id:
            return None
        return read_secret(item_id, field_name)

    return None


# -- Folder Listing --------------------------------------------------------


def list_folders() -> list:
    """List bw folders via `bw list folders`.

    Returns:
        [{"id": "...", "name": "..."}, ...] or empty list on error.
    """
    import json as _json

    if not is_available():
        logger.warning("bw CLI not found")
        return []

    try:
        r = run_bw(["list", "folders"])

        if r.returncode != 0:
            logger.warning("bw list folders failed: %s", r.stderr.strip())
            return []

        folders = _json.loads(r.stdout)
        return [{"id": f.get("id", ""), "name": f.get("name", "")} for f in folders]

    except subprocess.TimeoutExpired:
        logger.warning("bw list folders timeout (%ds)", BW_TIMEOUT)
        return []
    except (FileNotFoundError, Exception) as e:
        logger.warning("bw list folders error: %s", e)
        return []

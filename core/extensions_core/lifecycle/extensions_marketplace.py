"""Extension marketplace (index search)."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# 24-hour cache
_CACHE_TTL = 24 * 60 * 60
_cache: dict[str, Any] | None = None
_cache_time: float = 0


def get_index_url() -> str:
    """Return the extension index URL.

    Reads from ``extension_index_url`` in the config file.
    Returns an empty string if not configured or on error.
    """
    try:
        from core.services_core.db_api import get_config

        config = get_config()
        return config.get("extension_index_url", "")
    except Exception:
        return ""


def fetch_index(force: bool = False) -> list[dict[str, Any]]:
    """Fetch the extension index. Cached with 24h TTL.

    Args:
        force: If True, bypass cache and re-fetch.
    """
    global _cache, _cache_time

    if (
        not force
        and _cache is not None
        and (time.time() - _cache_time) < _CACHE_TTL
    ):
        return _cache.get("extensions", [])

    url = get_index_url()
    if not url:
        return []

    try:
        from .extensions_marketplace_fetch import fetch_json

        data = fetch_json(url)
        if isinstance(data, list):
            _cache = {"extensions": data}
        elif isinstance(data, dict):
            _cache = data
        else:
            _cache = {"extensions": []}
        _cache_time = time.time()
        return _cache.get("extensions", [])
    except Exception as exc:
        logger.warning("Extension index fetch failed: %s", exc)
        return []


def search_index(
    query: str = "",
    installed: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Search the index by keyword.

    Performs partial match search on name, description, and author fields.
    If installed is provided, adds an installed flag to each result.
    """
    extensions = fetch_index()
    if not query:
        results = list(extensions)
    else:
        q = query.lower()
        results = [
            ext
            for ext in extensions
            if q in ext.get("name", "").lower()
            or q in ext.get("description", "").lower()
            or q in ext.get("author", "").lower()
        ]

    # Add installed flag
    if installed:
        for ext in results:
            ext["installed"] = ext.get("name", "") in installed

    return results


def clear_cache() -> None:
    """Clear the cache."""
    global _cache, _cache_time
    _cache = None
    _cache_time = 0

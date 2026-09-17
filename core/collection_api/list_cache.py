"""TTL cache for the collections list endpoint.

Mirrors the cache layer pattern under ``core/search_api/`` so callers can
import a single helper instead of constructing one per route.
"""

from __future__ import annotations

from core.infra_core.simple_ttl_cache import SimpleTTLCache

# 3s window. Sidebar re-renders fan out a burst of identical GETs; the
# collections list itself rarely mutates, so a tiny window collapses
# duplicate cold reads without making the UI feel stale.
_LIST_CACHE = SimpleTTLCache(ttl_seconds=3.0, max_entries=8)
_LIST_KEY = "collections_list"


def peek_list():
    return _LIST_CACHE.peek(_LIST_KEY)


def put_list(value) -> None:
    _LIST_CACHE.put(_LIST_KEY, value)


def invalidate_list() -> None:
    _LIST_CACHE.invalidate(_LIST_KEY)

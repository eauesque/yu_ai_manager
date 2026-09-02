"""High-level response builders for the favorites endpoints.

Routes stay thin — they handle auth, async dispatch, and Response construction.
Validation and domain calls live here. Favorites share the ``favorites`` table
with collections (a favorite is a row keyed by ``collection_id``), so the
service layer is grouped together under ``core/collection_api/``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from core.infra_core.api_params import clamp_sqlite_int
from core.infra_core.simple_ttl_cache import SimpleTTLCache

_fav_mod = import_module("extensions.builtin_favorites_manager.core_impl")
check_collections_for_file = _fav_mod.check_collections_for_file
check_favorites = _fav_mod.check_favorites
list_favorites = _fav_mod.list_favorites
toggle_favorite = _fav_mod.toggle_favorite

# Short TTL cache for /api/favorites/check. Polled on every grid render with
# the same (sorted-ids, collection_id) tuple, so a 5s window collapses repeats
# without making toggle latency visible to the user — toggle invalidates the
# whole cache (the affected file_id may belong to any cached batch).
_check_cache = SimpleTTLCache(ttl_seconds=5.0, max_entries=128)


def invalidate_favorites_check_cache() -> None:
    """Clear the /api/favorites/check TTL cache.

    Call from any mutation path (toggle / batch add / batch remove). The
    affected file_id may sit in any cached batch, so we wipe the lot —
    cheaper than tracking which (ids, collection_id) tuples touched it.
    """
    _check_cache.invalidate()


def build_toggle_response(data: dict | None) -> tuple[dict, int]:
    if not isinstance(data, dict):
        return {"error": "JSON object required"}, 400
    file_id = data.get("file_id")
    if not file_id or not isinstance(file_id, int):
        return {"error": "file_id required"}, 400
    file_id = clamp_sqlite_int(file_id)
    collection_id = data.get("collection_id", 1)
    if not isinstance(collection_id, int) or collection_id < 1:
        collection_id = 1
    collection_id = clamp_sqlite_int(collection_id)
    result = toggle_favorite(file_id, collection_id)
    _check_cache.invalidate()
    return result, 200


def parse_check_args(ids_str: str, collection_id_str: str) -> tuple[list[int] | None, int | None, dict | None]:
    """Return (ids, collection_id, error_payload). ids=None means short-circuit empty result."""
    if not ids_str:
        return None, None, None
    try:
        ids = [clamp_sqlite_int(int(x)) for x in ids_str.split(",") if x.strip()]
    except ValueError:
        return None, None, {"error": "invalid ids"}
    if not ids:
        return None, None, None
    cid = clamp_sqlite_int(int(collection_id_str)) if collection_id_str else None
    return ids, cid, None


def build_check_response(ids: list[int], collection_id: int | None) -> dict[str, Any]:
    key = (tuple(sorted(ids)), collection_id)
    return _check_cache.get_or_compute(
        key,
        lambda: {"favorites": check_favorites(ids, collection_id=collection_id)},
    )


def parse_check_collections_args(file_id_str: str) -> tuple[int | None, dict | None]:
    """Return (file_id, error_payload). file_id=None means short-circuit empty result."""
    if not file_id_str:
        return None, None
    try:
        return clamp_sqlite_int(int(file_id_str)), None
    except ValueError:
        return None, {"error": "invalid file_id"}


def build_check_collections_response(file_id: int) -> dict[str, Any]:
    return {"collections": check_collections_for_file(file_id)}


def build_list_response(collection_id: int | None) -> dict[str, Any]:
    return {"ids": list_favorites(collection_id=collection_id)}

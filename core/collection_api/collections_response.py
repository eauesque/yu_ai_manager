"""High-level response builders for the collections endpoints.

Routes stay thin — they handle auth, async/heavy-io dispatch, and Response
construction. Validation, domain calls, and cache invalidation live here.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from core.collection_api import list_cache
from core.collection_api.favorites_response import (
    invalidate_favorites_check_cache,
)

_fav_mod = import_module("extensions.builtin_favorites_manager.core_impl")
batch_add_to_collection = _fav_mod.batch_add_to_collection
batch_remove_favorites = _fav_mod.batch_remove_favorites
create_collection = _fav_mod.create_collection
delete_collection = _fav_mod.delete_collection
list_collections = _fav_mod.list_collections
reorder_collections = _fav_mod.reorder_collections
update_collection = _fav_mod.update_collection

BATCH_ADD_MAX = 500


def build_list_response() -> dict[str, Any]:
    """Return cached or freshly-loaded collections list payload."""
    cached = list_cache.peek_list()
    if cached is not None:
        return {"collections": cached}
    collections = list_collections()
    list_cache.put_list(collections)
    return {"collections": collections}


def build_create_response(data: dict | None) -> tuple[dict, int]:
    if not isinstance(data, dict):
        return {"error": "JSON object required"}, 400
    name = (data.get("name") or "").strip()
    if not name:
        return {"error": "name required"}, 400
    query_json = data.get("query_json")
    result = create_collection(name, query_json=query_json)
    list_cache.invalidate_list()
    return result, 201


def build_update_response(collection_id: int, data: dict | None) -> tuple[dict, int]:
    if not isinstance(data, dict):
        return {"error": "JSON object required"}, 400
    name = (data.get("name") or "").strip()
    if not name:
        return {"error": "name required"}, 400
    result = update_collection(collection_id, name)
    list_cache.invalidate_list()
    return result, 200


def build_delete_response(collection_id: int) -> tuple[dict, int]:
    try:
        deleted_id = delete_collection(collection_id)
    except ValueError:
        return {"error": "Collection could not be deleted"}, 400
    list_cache.invalidate_list()
    invalidate_favorites_check_cache()
    return {"deleted": deleted_id}, 200


def build_reorder_response(data: dict | None) -> tuple[dict, int]:
    if not isinstance(data, dict):
        return {"error": "JSON object required"}, 400
    ids = data.get("ids", [])
    if not ids or not isinstance(ids, list):
        return {"error": "ids list required"}, 400
    reorder_collections(ids)
    list_cache.invalidate_list()
    return {"ok": True}, 200


def validate_batch_payload(data: dict | None):
    """Return (file_ids, None) on success, or (None, (body, status, code)) on error."""
    if not isinstance(data, dict):
        return None, ({"error": "JSON object required"}, 400, "invalid_json")
    file_ids = data.get("file_ids")
    if not isinstance(file_ids, list) or len(file_ids) == 0:
        return None, ({"error": "file_ids array required"}, 400, "batch_empty")
    if len(file_ids) > BATCH_ADD_MAX:
        return None, (
            {"error": f"Batch size {len(file_ids)} exceeds maximum of {BATCH_ADD_MAX}"},
            400,
            "batch_too_large",
        )
    return file_ids, None


def run_batch_add(file_ids: list[int], collection_id: int) -> dict:
    result = batch_add_to_collection(file_ids, collection_id)
    invalidate_favorites_check_cache()
    return result


def run_batch_remove(file_ids: list[int], collection_id: int) -> dict:
    result = batch_remove_favorites(file_ids, collection_id=collection_id)
    invalidate_favorites_check_cache()
    return result

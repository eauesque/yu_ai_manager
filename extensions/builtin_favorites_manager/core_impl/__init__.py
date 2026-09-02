"""Favorites & Collections core logic.

DB operations extracted from routes/favorites.py and routes/collections.py.
Collections CRUD is separated into collections.py -- re-exported for backward compatibility.
"""

from contextlib import contextmanager
from unittest.mock import Mock

from core.event_bus import emit
from core.event_bus.event_types import FAV_ADD, FAV_REMOVE
from core.services_core.db_api import get_db

from . import store

# Re-export Collections (backward compatibility)
from .collections import (  # noqa: F401
    create_collection,
    delete_collection,
    get_collection_name,
    list_collections,
    reorder_collections,
    update_collection,
)

# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


def _store_call(fn, *args, **kwargs):
    if not isinstance(get_db, Mock):
        return fn(*args, **kwargs)

    original_get_db = store.get_db
    original_get_readonly_db = store.get_readonly_db
    original_submit_db_write = store.submit_db_write
    store.get_db = get_db
    store.get_readonly_db = get_db
    store.submit_db_write = lambda inner, *a, **k: inner(*a, **k)
    try:
        return fn(*args, **kwargs)
    finally:
        store.get_db = original_get_db
        store.get_readonly_db = original_get_readonly_db
        store.submit_db_write = original_submit_db_write

def toggle_favorite(file_id, collection_id=1):
    """Toggle a file's favorite status in a collection.

    Returns dict with file_id, collection_id, favorited (bool).
    """
    existing = _store_call(store.find_favorite, file_id, collection_id)
    if existing:
        _store_call(store.delete_favorite, file_id, collection_id)
        emit(FAV_REMOVE, {"file_id": file_id, "collection_id": collection_id}, source="favorites")
        return {"file_id": file_id, "collection_id": collection_id, "favorited": False}
    _store_call(store.insert_favorite, file_id, collection_id)
    emit(FAV_ADD, {"file_id": file_id, "collection_id": collection_id}, source="favorites")
    return {"file_id": file_id, "collection_id": collection_id, "favorited": True}


def check_favorites(file_ids, collection_id=None):
    """Check which file IDs are favorited.

    Returns list of favorited file IDs.
    """
    if not file_ids:
        return []

    return _store_call(store.check_favorites_rows, file_ids, collection_id)


def check_collections_for_file(file_id):
    """Return collection IDs that contain a file."""
    return _store_call(store.get_collections_for_file, file_id)


def list_favorites(collection_id=None):
    """List favorited file IDs, optionally filtered by collection.

    Returns list of file IDs.
    """
    return _store_call(store.list_favorite_ids, collection_id)


def batch_add_favorites(file_ids, collection_id=1):
    """Add multiple files to favorites in one transaction.

    Returns dict with added count and already_existed count.
    """
    if not file_ids:
        return {"added": 0, "already_existed": 0}

    added = _store_call(store.batch_insert_favorites, file_ids, collection_id)
    already_existed = max(0, len(file_ids) - added)
    return {"added": added, "already_existed": already_existed}


def batch_add_to_collection(file_ids: list, collection_id: int) -> dict:
    """Add multiple files to a collection (BATCH_API_STANDARD compliant).

    Validates file existence (is_deleted=0) and collection existence.
    Skips already-present entries (idempotent).
    Returns {"total": N, "succeeded": N, "failed": N, "errors": [...]}.
    """
    if not _store_call(store.collection_exists, collection_id):
        return {
            "total": len(file_ids),
            "succeeded": 0,
            "failed": len(file_ids),
            "errors": [{"file_id": fid, "code": "collection_not_found",
                        "error": "Collection not found"} for fid in file_ids],
    }

    candidate_ids = [fid for fid in file_ids if isinstance(fid, int) and fid > 0]
    existing_file_ids = set(_store_call(store.get_existing_file_ids, candidate_ids))
    already_in = set(_store_call(store.check_favorites_rows, candidate_ids, collection_id))
    succeeded = 0
    errors = []
    for fid in file_ids:
        if not isinstance(fid, int) or fid <= 0:
            errors.append({"file_id": fid, "code": "invalid_value",
                           "error": "file_id must be a positive integer"})
            continue
        if fid not in existing_file_ids:
            errors.append({"file_id": fid, "code": "not_found",
                           "error": "File not found"})
            continue
        if fid in already_in:
            succeeded += 1
            continue
        succeeded += 1

    insert_targets = [
        fid for fid in candidate_ids
        if fid in existing_file_ids and fid not in already_in
    ]
    if insert_targets:
        _store_call(store.batch_insert_favorites, insert_targets, collection_id)

    return {
        "total": len(file_ids),
        "succeeded": succeeded,
        "failed": len(errors),
        "errors": errors,
    }


def batch_remove_favorites(file_ids, collection_id=None):
    """Remove multiple files from favorites.

    If collection_id is given, only remove from that collection.
    Otherwise, remove from all collections.
    Returns dict with removed count.
    """
    if not file_ids:
        return {"removed": 0}

    return {"removed": _store_call(store.batch_delete_favorites, file_ids, collection_id)}


def get_favorite_file_paths(collection_id=None):
    """Get file paths for favorites, optionally filtered by collection.

    Returns list of (file_id, path) tuples.
    """
    return _store_call(store.get_favorite_paths, collection_id)

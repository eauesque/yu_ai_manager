"""Collections CRUD + reorder logic.

Separated from favorites_core/__init__.py.
"""

from unittest.mock import Mock

from core.event_bus import emit
from core.event_bus.event_types import COLL_CREATE, COLL_DELETE
from core.services_core.db_api import get_db

from . import store


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


def list_collections():
    """List all collections with favorite counts.

    Returns list of dicts with id, name, sort_order, created_at, count,
    and query_json (non-null for smart collections).
    """
    return _store_call(store.list_collections_rows)


def create_collection(name, query_json=None):
    """Create a new collection.

    If query_json is provided, the collection is a smart (saved-search) collection.
    Returns dict with id, name, and is_smart flag.
    """
    coll_id = _store_call(store.insert_collection, name, query_json=query_json)
    emit(COLL_CREATE, {"id": coll_id, "name": name, "is_smart": query_json is not None}, source="collections")
    return {"id": coll_id, "name": name, "is_smart": query_json is not None}


def update_collection(collection_id, name):
    """Update a collection's name.

    Returns dict with id and name.
    """
    _store_call(store.update_collection_name, collection_id, name)
    return {"id": collection_id, "name": name}


def delete_collection(collection_id):
    """Delete a collection and its favorites.

    Returns collection_id that was deleted.
    Raises ValueError if trying to delete default collection (id=1).
    """
    if collection_id == 1:
        raise ValueError("cannot delete default collection")

    _store_call(store.delete_collection_rows, collection_id)
    emit(COLL_DELETE, {"id": collection_id}, source="collections")
    return collection_id


def reorder_collections(ids):
    """Reorder collections by the given ID list.

    Returns True on success.
    """
    _store_call(store.reorder_collections_rows, ids)
    return True


def get_collection_name(collection_id):
    """Get a collection's name by ID. Returns None if not found."""
    return _store_call(store.get_collection_name_row, collection_id)

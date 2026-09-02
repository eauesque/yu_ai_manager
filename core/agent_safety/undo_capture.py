"""Undo Capture Handlers — before-state capture for each reversible tool.

Each handler inspects current DB state before a tool executes,
and returns a dict of undo parameters that can later reverse the operation.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)
_IN_CHUNK_SIZE = 500


def _chunks(items: list, size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _get_db() -> sqlite3.Connection:
    """Get DB connection via ServiceRegistry."""
    from core.extensions_core.service_registry import ServiceRegistry
    get_db_fn = ServiceRegistry.get("db")
    if callable(get_db_fn):
        return get_db_fn()
    return get_db_fn


def capture_rate_images(params: dict) -> dict | None:
    """rate_images: capture original ratings before overwrite."""
    items = params.get("items", [])
    if not items:
        return None

    file_ids = [it.get("file_id") for it in items if it.get("file_id")]
    if not file_ids:
        return None

    db = _get_db()
    original_ratings = {}
    for chunk in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in chunk)
        cursor = db.execute(
            f"SELECT file_id, rating FROM file_ratings WHERE file_id IN ({placeholders})",
            chunk,
        )
        original_ratings.update({int(r[0]): r[1] for r in cursor})

    # Record files without rating as 0
    restore_items = []
    for item in items:
        fid = item.get("file_id")
        if fid:
            restore_items.append({
                "file_id": fid,
                "rating": original_ratings.get(fid, 0),
            })

    return {"action": "restore_ratings", "items": restore_items}


def capture_set_tags(params: dict) -> dict | None:
    """set_tags: invert add/remove to produce undo parameters."""
    items = params.get("items", [])
    if not items:
        return None

    # Invert: add -> remove, remove -> add
    reverse_items = []
    for item in items:
        fid = item.get("file_id")
        add_tags = item.get("add", [])
        remove_tags = item.get("remove", [])
        if fid and (add_tags or remove_tags):
            reverse_items.append({
                "file_id": fid,
                "add": list(remove_tags),  # Restore removed tags
                "remove": list(add_tags),  # Remove added tags
            })

    if not reverse_items:
        return None

    return {"action": "restore_tags", "items": reverse_items}


def capture_set_annotations(params: dict) -> dict | None:
    """set_annotations: capture existing annotation values before overwrite."""
    items = params.get("items", [])
    if not items:
        return None

    db = _get_db()
    restore_items = []
    delete_items = []

    for item in items:
        fid = item.get("file_id")
        source = item.get("source", "")
        key = item.get("key", "")
        if not (fid and source and key):
            continue

        row = db.execute(
            "SELECT value, confidence FROM file_annotations WHERE file_id=? AND source=? AND key=?",
            (fid, source, key),
        ).fetchone()

        if row:
            # Record existing value for restoration
            restore_items.append({
                "file_id": fid, "source": source, "key": key,
                "value": row[0], "confidence": row[1],
            })
        else:
            # Will be newly created, so delete on undo
            delete_items.append({
                "file_id": fid, "source": source, "key": key,
            })

    return {
        "action": "restore_annotations",
        "restore": restore_items,
        "delete": delete_items,
    }


def capture_add_to_collection(params: dict) -> dict | None:
    """add_to_collection: capture which file IDs will be newly added."""
    collection_id = params.get("collection_id")
    file_ids = params.get("file_ids", [])
    if not (collection_id and file_ids):
        return None

    # Exclude files already in collection (only newly added files are undo targets)
    db = _get_db()
    existing = set()
    for chunk in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in chunk)
        cursor = db.execute(
            f"SELECT file_id FROM favorites WHERE file_id IN ({placeholders}) AND collection_id=?",
            [*chunk, collection_id],
        )
        existing.update(int(r[0]) for r in cursor)
    new_file_ids = [fid for fid in file_ids if fid not in existing]
    if not new_file_ids:
        return None

    return {
        "action": "remove_from_collection",
        "collection_id": collection_id,
        "file_ids": new_file_ids,
    }


def capture_remove_from_collection(params: dict) -> dict | None:
    """remove_from_collection: capture file IDs being removed."""
    collection_id = params.get("collection_id")
    file_ids = params.get("file_ids", [])
    if not (collection_id and file_ids):
        return None

    return {
        "action": "add_to_collection",
        "collection_id": collection_id,
        "file_ids": list(file_ids),
    }


# Mapping of tool name -> capture handler function
CAPTURE_HANDLERS: dict[str, Any] = {
    "rate_images": capture_rate_images,
    "set_tags": capture_set_tags,
    "set_annotations": capture_set_annotations,
    "add_to_collection": capture_add_to_collection,
    "remove_from_collection": capture_remove_from_collection,
}

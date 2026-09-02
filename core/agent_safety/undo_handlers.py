"""Undo Execution Handlers — reverse operations for each undo action.

Each handler receives undo_params (previously captured) and performs
the actual DB operations to reverse the original tool action.
"""

from __future__ import annotations

import logging
from typing import Any

from core.services_core.db_cipher import sqlite3

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


def undo_restore_ratings(undo_params: dict) -> dict:
    """Restore ratings to their original values."""
    items = undo_params.get("items", [])
    db = _get_db()
    restored = 0

    for item in items:
        fid = item.get("file_id")
        rating = item.get("rating", 0)
        if not fid:
            continue

        if rating == 0:
            db.execute("DELETE FROM file_ratings WHERE file_id=?", (fid,))
        else:
            db.execute(
                """INSERT INTO file_ratings (file_id, rating, rated_at, updated_at)
                   VALUES (?, ?, strftime('%s','now'), strftime('%s','now'))
                   ON CONFLICT(file_id) DO UPDATE
                   SET rating=excluded.rating, updated_at=strftime('%s','now')""",
                (fid, rating),
            )
        restored += 1

    db.commit()
    return {"restored": restored}


def undo_restore_tags(undo_params: dict) -> dict:
    """Reverse tag changes (add back removed tags, remove added tags)."""
    items = undo_params.get("items", [])
    db = _get_db()
    restored = 0

    for item in items:
        fid = item.get("file_id")
        add_tags = item.get("add", [])
        remove_tags = item.get("remove", [])

        for tag_name in add_tags:
            # Add tags
            tag_row = db.execute(
                "SELECT id FROM tags WHERE tag=?", (tag_name,)
            ).fetchone()
            if tag_row:
                tag_id = tag_row[0]
            else:
                cursor = db.execute(
                    "INSERT INTO tags (tag) VALUES (?)", (tag_name,)
                )
                tag_id = cursor.lastrowid
            db.execute(
                "INSERT OR IGNORE INTO file_tags (file_id, tag_id, confidence, source) VALUES (?, ?, 1.0, 'user')",
                (fid, tag_id),
            )

        for tag_name in remove_tags:
            tag_row = db.execute(
                "SELECT id FROM tags WHERE tag=?", (tag_name,)
            ).fetchone()
            if tag_row:
                db.execute(
                    "DELETE FROM file_tags WHERE file_id=? AND tag_id=? AND source='user'",
                    (fid, tag_row[0]),
                )
        restored += 1

    db.commit()
    return {"restored": restored}


def undo_restore_annotations(undo_params: dict) -> dict:
    """Restore annotations to their original values or delete newly created ones."""
    restore_items = undo_params.get("restore", [])
    delete_items = undo_params.get("delete", [])
    db = _get_db()
    restored = 0

    for item in restore_items:
        db.execute(
            """INSERT INTO file_annotations (file_id, source, key, value, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(file_id, source, key) DO UPDATE
               SET value=excluded.value, confidence=excluded.confidence""",
            (item["file_id"], item["source"], item["key"],
             item["value"], item.get("confidence")),
        )
        restored += 1

    for item in delete_items:
        db.execute(
            "DELETE FROM file_annotations WHERE file_id=? AND source=? AND key=?",
            (item["file_id"], item["source"], item["key"]),
        )
        restored += 1

    db.commit()
    return {"restored": restored}


def undo_remove_from_collection(undo_params: dict) -> dict:
    """Remove files from collection (undo of add_to_collection)."""
    collection_id = undo_params.get("collection_id")
    file_ids = undo_params.get("file_ids", [])
    db = _get_db()

    if file_ids:
        for chunk in _chunks(list(dict.fromkeys(file_ids))):
            placeholders = ",".join("?" for _ in chunk)
            db.execute(
                f"DELETE FROM favorites WHERE file_id IN ({placeholders}) AND collection_id=?",
                [*chunk, collection_id],
            )
        db.commit()

    return {"removed": len(file_ids)}


def undo_add_to_collection(undo_params: dict) -> dict:
    """Re-add files to collection (undo of remove_from_collection)."""
    collection_id = undo_params.get("collection_id")
    file_ids = undo_params.get("file_ids", [])
    db = _get_db()
    added = 0

    for fid in file_ids:
        db.execute(
            "INSERT OR IGNORE INTO favorites (file_id, collection_id, added_at) VALUES (?, ?, strftime('%s','now'))",
            (fid, collection_id),
        )
        added += 1

    db.commit()
    return {"added": added}


def undo_delete_collection(undo_params: dict) -> dict:
    """Delete a collection (undo of create_collection)."""
    collection_id = undo_params.get("collection_id")
    if not collection_id:
        return {"error": "collection_id missing"}

    db = _get_db()
    # Also delete files within the collection
    db.execute("DELETE FROM favorites WHERE collection_id=?", (collection_id,))
    db.execute("DELETE FROM collections WHERE id=?", (collection_id,))
    db.commit()
    return {"deleted_collection_id": collection_id}


def undo_delete_prompt(undo_params: dict) -> dict:
    """Delete a prompt (undo of create_prompt)."""
    prompt_id = undo_params.get("prompt_id")
    if not prompt_id:
        return {"error": "prompt_id missing"}

    # prompt_library is in a separate DB, so access directly
    try:
        from pathlib import Path

        from core.extensions_core.service_registry import ServiceRegistry
        db_path = ServiceRegistry.get("db_path")
        pl_db_path = Path(db_path).parent / "prompt_library.db"
        if pl_db_path.exists():
            from core.services_core.db_cipher import apply_key as _apply_key
            from core.services_core.db_cipher import sqlite3 as _cipher_sqlite3
            con = _cipher_sqlite3.connect(str(pl_db_path))
            _apply_key(con)
            con.execute("DELETE FROM prompt_library WHERE id=?", (prompt_id,))
            con.commit()
            con.close()
            return {"deleted_prompt_id": prompt_id}
    except Exception as exc:
        return {"error": str(exc)}

    return {"error": "prompt_library.db not accessible"}


# Mapping of undo action name -> handler function
UNDO_HANDLERS: dict[str, Any] = {
    "restore_ratings": undo_restore_ratings,
    "restore_tags": undo_restore_tags,
    "restore_annotations": undo_restore_annotations,
    "remove_from_collection": undo_remove_from_collection,
    "add_to_collection": undo_add_to_collection,
    "delete_collection": undo_delete_collection,
    "delete_prompt": undo_delete_prompt,
}

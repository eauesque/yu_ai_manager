"""Tag batch operations core logic."""

import time as _time

from core.event_bus import emit
from core.event_bus.event_types import TAG_ADD, TAG_REMOVE
from core.models_core.models_tags import insert_file_tag, upsert_tag
from core.services_core.db_api import get_db

_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def set_tags_batch(items: list, source: str = "user") -> dict:
    """Add/remove tags for multiple files in one transaction.

    Each item: {"file_id": int, "add": ["tag1", ...], "remove": ["tag2", ...]}.
    source: Tag origin ('user' or 'meta'). remove can only delete tags with the same source.
    Returns {"total": N, "succeeded": N, "failed": N, "errors": [...]}.
    """
    from core.services_core.db_write import submit_db_write
    return submit_db_write(_set_tags_batch_write, items, source)


def _set_tags_batch_write(items: list, source: str = "user") -> dict:
    con = get_db()
    # Pre-fetch valid file IDs
    candidate_ids = [item.get("file_id") for item in items
                     if isinstance(item.get("file_id"), int) and item.get("file_id") > 0]
    existing_file_ids: set = set()
    if candidate_ids:
        for chunk in _chunks(candidate_ids):
            placeholders = ",".join("?" for _ in chunk)
            cursor = con.execute(
                f"SELECT id FROM files WHERE id IN ({placeholders}) AND is_deleted=0",
                chunk,
            )
            existing_file_ids.update(int(r[0]) for r in cursor)

    succeeded = 0
    errors = []
    tag_id_cache: dict = {}  # BUG-27: reuse tag_id within batch
    for item in items:
        file_id = item.get("file_id")
        add_tags = item.get("add", [])
        remove_tags = item.get("remove", [])

        if not isinstance(file_id, int) or file_id <= 0:
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "file_id must be a positive integer"})
            continue
        if not isinstance(add_tags, list) or not isinstance(remove_tags, list):
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "add and remove must be arrays"})
            continue
        if len(add_tags) == 0 and len(remove_tags) == 0:
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "at least one of add or remove is required"})
            continue
        if file_id not in existing_file_ids:
            errors.append({"file_id": file_id, "code": "not_found",
                           "error": "File not found"})
            continue

        try:
            # Add tags
            for tag_text in add_tags:
                if not isinstance(tag_text, str) or not tag_text.strip():
                    continue
                key = tag_text.strip()
                if key not in tag_id_cache:
                    tag_id_cache[key] = upsert_tag(
                        con, None, key,
                        first_seen_mtime=int(_time.time()),
                    )
                insert_file_tag(con, file_id, tag_id_cache[key], 1.0, source)

            # Remove tags
            for tag_text in remove_tags:
                if not isinstance(tag_text, str) or not tag_text.strip():
                    continue
                row = con.execute(
                    "SELECT id FROM tags WHERE tag=? AND namespace IS NULL",
                    (tag_text.strip(),),
                ).fetchone()
                if row:
                    tag_id = int(row[0])
                    con.execute(
                        "DELETE FROM file_tags WHERE file_id=? AND tag_id=? AND source=?",
                        (file_id, tag_id, source),
                    )
                    # BUG-27 GC: remove orphan tag if no file_tags remain
                    refs = con.execute(
                        "SELECT 1 FROM file_tags WHERE tag_id=? LIMIT 1",
                        (tag_id,),
                    ).fetchone()
                    if not refs:
                        con.execute("DELETE FROM tags WHERE id=?", (tag_id,))
                        tag_id_cache.pop(tag_text.strip(), None)

            succeeded += 1
        except Exception:
            errors.append({"file_id": file_id, "code": "internal_error",
                           "error": "Internal error"})

    con.commit()
    # Emit tag events for webhook/agent consumption
    added_ids = [item["file_id"] for item in items
                 if item.get("add") and item["file_id"] in existing_file_ids]
    removed_ids = [item["file_id"] for item in items
                   if item.get("remove") and item["file_id"] in existing_file_ids]
    if added_ids:
        emit(TAG_ADD, {"file_ids": added_ids, "source": source})
    if removed_ids:
        emit(TAG_REMOVE, {"file_ids": removed_ids, "source": source})
    return {
        "total": len(items),
        "succeeded": succeeded,
        "failed": len(errors),
        "errors": errors,
    }
    # pooled connection: do not close

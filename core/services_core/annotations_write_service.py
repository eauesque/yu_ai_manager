"""Write helpers for annotations persistence."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from core.utils.zstd_blob import compress_text

_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def upsert_annotation_value(
    file_id: int,
    source: str,
    key: str,
    value: str,
    confidence: float | None,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    """UPSERT one annotation row and commit."""
    upsert_annotations_batch_values(
        [{
            "file_id": file_id,
            "source": source,
            "key": key,
            "value": value,
            "confidence": confidence,
        }],
        get_db_fn=get_db_fn,
    )


def upsert_annotations_batch_values(
    items: list[dict[str, Any]],
    *,
    get_db_fn: Callable | None = None,
) -> int:
    """Batch UPSERT multiple annotations and commit."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    count = _upsert_annotations_batch_with_connection(con, items, int(time.time()))
    con.commit()
    return count


def delete_annotation_rows(
    source: str,
    *,
    file_ids: list[int] | None = None,
    key: str | None = None,
    get_db_fn: Callable | None = None,
) -> int:
    """Delete matching annotation rows and commit."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    where = ["source=?"]
    params: list[Any] = [source]
    if key:
        where.append("key=?")
        params.append(key)
    valid_ids = (
        sorted({fid for fid in file_ids if isinstance(fid, int) and fid > 0})
        if file_ids
        else []
    )
    deleted = 0
    if valid_ids:
        for chunk in _chunks(valid_ids):
            placeholders = ",".join("?" for _ in chunk)
            cur = con.execute(
                "DELETE FROM file_annotations WHERE "
                + " AND ".join([*where, f"file_id IN ({placeholders})"]),
                [*params, *chunk],
            )
            deleted += cur.rowcount
    else:
        cur = con.execute(
            "DELETE FROM file_annotations WHERE " + " AND ".join(where), params
        )
        deleted = cur.rowcount
    con.commit()
    return deleted


def _upsert_annotations_batch_with_connection(con, items: list[dict[str, Any]], now: int) -> int:
    count = 0
    for item in items:
        con.execute(
            "INSERT INTO file_annotations (file_id, source, key, value, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(file_id, source, key) DO UPDATE SET "
            "value=excluded.value, confidence=excluded.confidence",
            (
                item["file_id"],
                item["source"],
                item["key"],
                compress_text(item["value"]),
                item.get("confidence"),
                now,
            ),
        )
        count += 1
    return count

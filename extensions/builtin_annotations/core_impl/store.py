"""Annotations data access layer (Store pattern).

Handles SQL only. Validation and event emission are done in __init__.py.
"""

from __future__ import annotations

from typing import Any

from core.services_core.annotations_write_service import (
    delete_annotation_rows,
    upsert_annotation_value,
    upsert_annotations_batch_values,
)
from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write
from core.utils.zstd_blob import decompress_blob


def upsert_annotation(
    file_id: int,
    source: str,
    key: str,
    value: str,
    confidence: float | None,
) -> None:
    """UPSERT an annotation."""
    submit_db_write(
        lambda: upsert_annotation_value(
            file_id,
            source,
            key,
            value,
            confidence,
            get_db_fn=get_db,
        )
    )


def upsert_annotations_batch_commit(items: list[dict[str, Any]]) -> int:
    """Batch UPSERT multiple annotations and commit. Returns success count."""
    return submit_db_write(
        lambda: upsert_annotations_batch_values(items, get_db_fn=get_db)
    )


def get_annotations_rows(
    file_id: int,
    source: str | None = None,
    key: str | None = None,
) -> list[dict[str, Any]]:
    """Get annotations for a file."""
    con = get_readonly_db()
    where = ["file_id=?"]
    params: list = [file_id]
    if source:
        where.append("source=?")
        params.append(source)
    if key:
        where.append("key=?")
        params.append(key)

    rows = con.execute(
        "SELECT id, file_id, source, key, value, confidence, created_at "
        "FROM file_annotations WHERE " + " AND ".join(where)
        + " ORDER BY created_at DESC",
        params,
    )
    return [
        {"id": r[0], "file_id": r[1], "source": r[2], "key": r[3],
         "value": decompress_blob(r[4]), "confidence": r[5], "created_at": r[6]}
        for r in rows
    ]


def search_annotations_rows(
    source: str | None = None,
    key: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Search annotations. Returns (result list, total count)."""
    con = get_readonly_db()
    where: list = []
    params: list = []
    if source:
        where.append("a.source=?")
        params.append(source)
    if key:
        where.append("a.key=?")
        params.append(key)
    if min_confidence is not None:
        where.append("a.confidence >= ?")
        params.append(min_confidence)
    if max_confidence is not None:
        where.append("a.confidence <= ?")
        params.append(max_confidence)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total_row = con.execute(
        "SELECT COUNT(*) FROM file_annotations a" + where_sql, params
    ).fetchone()
    total = total_row[0] if total_row else 0

    rows = con.execute(
        "SELECT a.id, a.file_id, a.source, a.key, a.value, a.confidence, a.created_at "
        "FROM file_annotations a" + where_sql
        + " ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    results = [
        {"id": r[0], "file_id": r[1], "source": r[2], "key": r[3],
         "value": decompress_blob(r[4]), "confidence": r[5], "created_at": r[6]}
        for r in rows
    ]
    return results, total


def get_user_notes(
    q: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return user notes (source='user', key='note') with file path.

    Joins file_annotations with files to include the file path.
    Supports full-text search across both note value and file path.
    Returns (results, total_count).
    """
    con = get_readonly_db()
    base_where = ["a.source='user'", "a.key='note'"]
    params: list = []

    if q:
        # Search only on file path; value is Zstd-compressed binary and
        # cannot be searched with LIKE.
        base_where.append("f.path LIKE ?")
        like = f"%{q}%"
        params.append(like)

    where_sql = " WHERE " + " AND ".join(base_where)
    join_sql = (
        " FROM file_annotations a"
        " LEFT JOIN files f ON a.file_id = f.id"
    )

    total_row = con.execute(
        "SELECT COUNT(*)" + join_sql + where_sql, params
    ).fetchone()
    total = total_row[0] if total_row else 0

    rows = con.execute(
        "SELECT a.id, a.file_id, f.path, a.value, a.created_at"
        + join_sql
        + where_sql
        + " ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )

    results = [
        {
            "id": r[0],
            "file_id": r[1],
            "path": r[2] or "",
            "value": decompress_blob(r[3]),
            "created_at": r[4],
        }
        for r in rows
    ]
    return results, total


def delete_annotations_rows(
    source: str,
    file_ids: list[int] | None = None,
    key: str | None = None,
) -> int:
    """Delete annotations and return the number of deleted rows."""
    return submit_db_write(
        lambda: delete_annotation_rows(
            source,
            file_ids=file_ids,
            key=key,
            get_db_fn=get_db,
        )
    )

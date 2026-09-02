"""Tags data access layer (Store pattern).

Aggregates SQL queries for tag searching and retrieval.
"""

from __future__ import annotations

from typing import Any

from core.services_core.db_state import get_readonly_db


def get_tags_for_file(file_id: int) -> list[dict[str, Any]]:
    """Tags associated with a fileretrieve."""
    con = get_readonly_db()
    rows = con.execute(
        "SELECT t.id, t.tag, t.namespace, ft.weight, ft.source "
        "FROM file_tags ft "
        "JOIN tags t ON t.id = ft.tag_id "
        "WHERE ft.file_id = ? "
        "ORDER BY ft.weight DESC, t.tag",
        (file_id,),
    )
    return [
        {"id": r[0], "tag": r[1], "namespace": r[2], "weight": r[3], "source": r[4]}
        for r in rows
    ]


def search_tags(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search tags by keyword."""
    con = get_readonly_db()
    rows = con.execute(
        "SELECT t.id, t.tag, t.namespace, COUNT(ft.file_id) AS file_count "
        "FROM tags t "
        "LEFT JOIN file_tags ft ON ft.tag_id = t.id "
        "WHERE t.tag LIKE ? "
        "GROUP BY t.id "
        "ORDER BY file_count DESC "
        "LIMIT ?",
        (f"%{query}%", limit),
    )
    return [
        {"id": r[0], "tag": r[1], "namespace": r[2], "file_count": r[3]}
        for r in rows
    ]


def get_tag_by_name(tag_name: str) -> dict[str, Any] | None:
    """Search by tag name."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT id, tag, namespace FROM tags WHERE tag=? AND namespace IS NULL",
        (tag_name,),
    ).fetchone()
    return {"id": row[0], "tag": row[1], "namespace": row[2]} if row else None


def count_files_with_tag(tag_id: int) -> int:
    """Number of files with the tagreturn."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT COUNT(*) FROM file_tags WHERE tag_id=?", (tag_id,)
    ).fetchone()
    return row[0] if row else 0

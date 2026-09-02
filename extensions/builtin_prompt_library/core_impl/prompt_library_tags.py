"""Prompt Library tag operations: CRUD + assignment."""

from __future__ import annotations

from typing import Any

from core.services_core.db_write import submit_db_write

from .prompt_library_db import get_pl_db, get_pl_read_db


def list_tags() -> list[dict[str, Any]]:
    """Return all tags with usage counts."""
    con = get_pl_read_db()
    rows = con.execute(
        "SELECT t.id, t.name, COUNT(tm.prompt_id) AS count "
        "FROM prompt_library_tags t "
        "LEFT JOIN prompt_library_tag_map tm ON tm.tag_id=t.id "
        "GROUP BY t.id ORDER BY t.name"
    )
    return [{"id": r[0], "name": r[1], "count": r[2]} for r in rows]


def create_tag(name: str) -> dict[str, Any]:
    """Create a tag. Returns the new tag dict. Raises ValueError on duplicate."""
    name = name.strip()
    if not name:
        raise ValueError("Tag name is required")
    def _write() -> int:
        con = get_pl_db()
        existing = con.execute(
            "SELECT id FROM prompt_library_tags WHERE name=?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"Tag '{name}' already exists")
        cur = con.execute(
            "INSERT INTO prompt_library_tags (name) VALUES (?)", (name,)
        )
        con.commit()
        return cur.lastrowid

    tag_id = submit_db_write(_write)
    return {"id": tag_id, "name": name, "count": 0}


def delete_tag(tag_id: int) -> bool:
    """Delete a tag and its mappings. Returns True if deleted."""
    def _write() -> int:
        con = get_pl_db()
        con.execute(
            "DELETE FROM prompt_library_tag_map WHERE tag_id=?", (tag_id,)
        )
        cur = con.execute(
            "DELETE FROM prompt_library_tags WHERE id=?", (tag_id,)
        )
        con.commit()
        return cur.rowcount

    return submit_db_write(_write) > 0


def set_prompt_tags(prompt_id: int, tag_ids: list[int]) -> list[dict[str, Any]]:
    """Replace all tags for a prompt. Returns the new tag list."""
    def _write() -> None:
        con = get_pl_db()
        con.execute(
            "DELETE FROM prompt_library_tag_map WHERE prompt_id=?", (prompt_id,)
        )
        con.executemany(
            "INSERT OR IGNORE INTO prompt_library_tag_map (prompt_id, tag_id) VALUES (?,?)",
            ((prompt_id, tid) for tid in tag_ids),
        )
        con.commit()

    submit_db_write(_write)

    con = get_pl_read_db()
    rows = con.execute(
        "SELECT t.id, t.name FROM prompt_library_tags t "
        "JOIN prompt_library_tag_map tm ON tm.tag_id=t.id "
        "WHERE tm.prompt_id=? ORDER BY t.name",
        (prompt_id,),
    )
    return [{"id": r[0], "name": r[1]} for r in rows]

"""Prompt Library folder operations: CRUD + tree."""

from __future__ import annotations

import time
from typing import Any

from core.services_core.db_write import submit_db_write

from .prompt_library_db import get_pl_db, get_pl_read_db


def list_folders() -> list[dict[str, Any]]:
    """Return flat list of folders with item counts, ordered for tree display."""
    con = get_pl_read_db()
    rows = con.execute(
        "SELECT f.id, f.name, f.parent_id, f.sort_order, f.created_at, "
        "COUNT(fi.prompt_id) AS count "
        "FROM prompt_library_folders f "
        "LEFT JOIN prompt_library_folder_items fi ON fi.folder_id=f.id "
        "GROUP BY f.id "
        "ORDER BY f.sort_order, f.id"
    )
    return [
        {"id": r[0], "name": r[1], "parent_id": r[2],
         "sort_order": r[3], "created_at": r[4], "count": r[5]}
        for r in rows
    ]


def build_folder_tree(folders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert flat folder list into nested tree structure."""
    by_id = {f["id"]: dict(f, children=[]) for f in folders}
    roots: list[dict[str, Any]] = []
    for f in by_id.values():
        pid = f["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["children"].append(f)
        else:
            roots.append(f)
    return roots


def create_folder(name: str, parent_id: int | None = None) -> dict[str, Any]:
    """Create a folder. Returns the new folder dict."""
    now = int(time.time())

    def _write() -> tuple[int, int]:
        con = get_pl_db()
        row = con.execute(
            "SELECT COALESCE(MAX(sort_order),0)+1 FROM prompt_library_folders"
        ).fetchone()
        next_order = row[0] if row else 1
        cur = con.execute(
            "INSERT INTO prompt_library_folders (name, parent_id, sort_order, created_at) "
            "VALUES (?,?,?,?)",
            (name, parent_id, next_order, now),
        )
        con.commit()
        return cur.lastrowid, next_order

    folder_id, next_order = submit_db_write(_write)
    return {"id": folder_id, "name": name, "parent_id": parent_id,
            "sort_order": next_order, "created_at": now, "count": 0}


def update_folder(folder_id: int, *, name: str | None = None,
                  parent_id: object = ...) -> dict[str, Any] | None:
    """Update folder name and/or parent. Returns updated dict or None."""
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name=?")
        params.append(name)
    if parent_id is not ...:
        sets.append("parent_id=?")
        params.append(parent_id)
    if not sets:
        return None

    params.append(folder_id)

    def _write() -> dict[str, Any] | None:
        con = get_pl_db()
        cur = con.execute(
            f"UPDATE prompt_library_folders SET {', '.join(sets)} WHERE id=?",
            params,
        )
        if cur.rowcount == 0:
            return None
        con.commit()
        row = con.execute(
            "SELECT id, name, parent_id, sort_order, created_at "
            "FROM prompt_library_folders WHERE id=?", (folder_id,)
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "parent_id": row[2],
                "sort_order": row[3], "created_at": row[4]}

    return submit_db_write(_write)


def delete_folder(folder_id: int) -> bool:
    """Delete folder. Items become unassigned. Returns True if deleted."""
    def _write() -> int:
        con = get_pl_db()
        parent = con.execute(
            "SELECT parent_id FROM prompt_library_folders WHERE id=?",
            (folder_id,),
        ).fetchone()
        new_parent = parent[0] if parent else None
        con.execute(
            "UPDATE prompt_library_folders SET parent_id=? WHERE parent_id=?",
            (new_parent, folder_id),
        )
        con.execute(
            "DELETE FROM prompt_library_folder_items WHERE folder_id=?",
            (folder_id,),
        )
        cur = con.execute(
            "DELETE FROM prompt_library_folders WHERE id=?", (folder_id,)
        )
        con.commit()
        return cur.rowcount

    return submit_db_write(_write) > 0


def assign_prompt_to_folder(prompt_id: int, folder_id: int) -> bool:
    """Assign a prompt to a folder. Returns True if added."""
    def _write() -> None:
        con = get_pl_db()
        con.execute(
            "INSERT OR IGNORE INTO prompt_library_folder_items "
            "(prompt_id, folder_id, sort_order) VALUES (?,?,0)",
            (prompt_id, folder_id),
        )
        con.commit()

    submit_db_write(_write)
    return True


def remove_prompt_from_folder(prompt_id: int, folder_id: int) -> bool:
    """Remove a prompt from a folder."""
    def _write() -> int:
        con = get_pl_db()
        cur = con.execute(
            "DELETE FROM prompt_library_folder_items WHERE prompt_id=? AND folder_id=?",
            (prompt_id, folder_id),
        )
        con.commit()
        return cur.rowcount

    return submit_db_write(_write) > 0

"""Cross Search store: text_files table management.

Provides CRUD and FTS5 search for .txt files.
Self-initialization pattern: auto-creates tables via ensure_tables().
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any

from core.services_core.cross_search_store_service import (
    add_cross_search_seen_paths,
    ensure_cross_search_seen_temp_table,
    ensure_cross_search_tables,
    get_active_cross_search_file_index,
    mark_missing_cross_search_deleted,
    mark_missing_cross_search_deleted_by_seen_table,
    upsert_cross_search_text_file,
)

_init_lock = threading.Lock()
_initialized = False


def ensure_tables(con: sqlite3.Connection | None = None) -> None:
    """Create text_files + text_files_fts tables (idempotent)."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        ensure_cross_search_tables(con)
        _initialized = True


def upsert_text_file(
    con: sqlite3.Connection,
    path: str,
    mtime: float,
    size: int,
    title: str,
    content: str,
    *,
    commit: bool = True,
) -> int:
    """Insert or update a text file and return the row ID."""
    if commit:
        return upsert_cross_search_text_file(con, path, mtime, size, title, content)
    return upsert_cross_search_text_file(
        con,
        path,
        mtime,
        size,
        title,
        content,
        commit=commit,
    )


def get_active_file_index(con: sqlite3.Connection) -> dict[str, dict[str, float | int]]:
    """Get active text file mtime/size metadata keyed by path."""
    return get_active_cross_search_file_index(con)


def ensure_seen_temp_table(con: sqlite3.Connection) -> None:
    """Create and clear the per-connection scan seen table."""
    ensure_cross_search_seen_temp_table(con)


def add_seen_paths(con: sqlite3.Connection, paths: list[str]) -> None:
    """Add paths seen in the current scan to the temp table."""
    add_cross_search_seen_paths(con, paths)


def get_text_file(con: sqlite3.Connection, file_id: int) -> dict[str, Any] | None:
    """Get a text file by ID (is_deleted=0 only)."""
    row = con.execute(
        "SELECT id, path, mtime, size, title, content, indexed_at "
        "FROM text_files WHERE id = ? AND is_deleted = 0",
        (file_id,),
    ).fetchone()
    if not row:
        return None
    return dict(row) if hasattr(row, "keys") else {
        "id": row[0], "path": row[1], "mtime": row[2], "size": row[3],
        "title": row[4], "content": row[5], "indexed_at": row[6],
    }


def get_text_file_by_path(
    con: sqlite3.Connection, path: str,
) -> dict[str, Any] | None:
    """Get a text file by path."""
    row = con.execute(
        "SELECT id, path, mtime, size, title, indexed_at "
        "FROM text_files WHERE path = ? AND is_deleted = 0",
        (path,),
    ).fetchone()
    if not row:
        return None
    return dict(row) if hasattr(row, "keys") else {
        "id": row[0], "path": row[1], "mtime": row[2],
        "size": row[3], "title": row[4], "indexed_at": row[5],
    }


def mark_missing_deleted(
    con: sqlite3.Connection, found_paths: set,
    *,
    commit: bool = True,
) -> int:
    """Mark active files not in found_paths as is_deleted=1."""
    if commit:
        return mark_missing_cross_search_deleted(con, found_paths)
    return mark_missing_cross_search_deleted(con, found_paths, commit=commit)


def mark_missing_deleted_by_seen_table(
    con: sqlite3.Connection,
    *,
    commit: bool = True,
) -> int:
    """Mark active files not present in the scan temp table as is_deleted=1."""
    return mark_missing_cross_search_deleted_by_seen_table(con, commit=commit)


def count_text_files(con: sqlite3.Connection) -> int:
    """Return the count of active text files."""
    row = con.execute(
        "SELECT COUNT(*) FROM text_files WHERE is_deleted = 0"
    ).fetchone()
    return row[0] if row else 0

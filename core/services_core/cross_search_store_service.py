"""Init/write helpers for cross-search text file persistence."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def ensure_cross_search_tables(
    con: sqlite3.Connection | None = None,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    """Create text_files + text_files_fts tables (idempotent)."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn
    local_con = con if con is not None else get_db_fn()
    local_con.executescript("""
        CREATE TABLE IF NOT EXISTS text_files (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            path       TEXT    NOT NULL UNIQUE,
            mtime      REAL    NOT NULL DEFAULT 0,
            size       INTEGER NOT NULL DEFAULT 0,
            title      TEXT    NOT NULL DEFAULT '',
            content    TEXT    NOT NULL DEFAULT '',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            indexed_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_text_files_path
            ON text_files(path);
        CREATE INDEX IF NOT EXISTS idx_text_files_is_deleted
            ON text_files(is_deleted);
    """)
    try:
        local_con.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS text_files_fts
            USING fts5(
                title, content,
                content=text_files, content_rowid=id
            )
            """
        )
        local_con.executescript("""
            CREATE TRIGGER IF NOT EXISTS text_files_fts_ai
            AFTER INSERT ON text_files BEGIN
                INSERT INTO text_files_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS text_files_fts_au
            AFTER UPDATE ON text_files BEGIN
                INSERT INTO text_files_fts(text_files_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
                INSERT INTO text_files_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS text_files_fts_ad
            AFTER DELETE ON text_files BEGIN
                INSERT INTO text_files_fts(text_files_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
            END;
        """)
    except Exception:
        logger.warning("service step failed", exc_info=True)
    local_con.commit()


def upsert_cross_search_text_file(
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
    now = int(time.time())
    cur = con.execute(
        """
        INSERT INTO text_files (path, mtime, size, title, content, is_deleted, indexed_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(path) DO UPDATE SET
            mtime      = excluded.mtime,
            size       = excluded.size,
            title      = excluded.title,
            content    = excluded.content,
            is_deleted = 0,
            indexed_at = excluded.indexed_at
        """,
        (path, mtime, size, title, content, now),
    )
    if commit:
        con.commit()
    return cur.lastrowid or 0


def get_active_cross_search_file_index(con: sqlite3.Connection) -> dict[str, dict[str, float | int]]:
    """Return active text file metadata keyed by path."""
    rows = con.execute(
        "SELECT path, mtime, size FROM text_files WHERE is_deleted = 0"
    )
    out: dict[str, dict[str, float | int]] = {}
    for row in rows:
        path = row["path"] if hasattr(row, "keys") else row[0]
        mtime = row["mtime"] if hasattr(row, "keys") else row[1]
        size = row["size"] if hasattr(row, "keys") else row[2]
        out[str(path)] = {"mtime": float(mtime), "size": int(size)}
    return out


def ensure_cross_search_seen_temp_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS cross_search_seen_paths (
            path TEXT PRIMARY KEY
        )
        """
    )
    con.execute("DELETE FROM cross_search_seen_paths")


def add_cross_search_seen_paths(
    con: sqlite3.Connection,
    paths: list[str],
) -> None:
    if not paths:
        return
    con.executemany(
        "INSERT OR IGNORE INTO cross_search_seen_paths(path) VALUES (?)",
        [(path,) for path in paths],
    )


def mark_missing_cross_search_deleted_by_seen_table(
    con: sqlite3.Connection,
    *,
    commit: bool = True,
) -> int:
    """Mark active files absent from the current scan temp table as deleted."""
    cur = con.execute(
        """
        UPDATE text_files
        SET is_deleted = 1
        WHERE is_deleted = 0
          AND NOT EXISTS (
              SELECT 1 FROM cross_search_seen_paths s WHERE s.path = text_files.path
          )
        """
    )
    if commit:
        con.commit()
    return int(cur.rowcount or 0)


def mark_missing_cross_search_deleted(
    con: sqlite3.Connection,
    found_paths: set,
    *,
    commit: bool = True,
) -> int:
    """Mark active files not in found_paths as deleted."""
    cursor = con.execute(
        "SELECT id, path FROM text_files WHERE is_deleted = 0"
    )
    missing_ids = []
    for row in cursor:
        path = row["path"] if hasattr(row, "keys") else row[1]
        row_id = row["id"] if hasattr(row, "keys") else row[0]
        if path not in found_paths:
            missing_ids.append(row_id)
    if not missing_ids:
        return 0
    for chunk in _chunks(missing_ids):
        placeholders = ",".join("?" for _ in chunk)
        con.execute(
            f"UPDATE text_files SET is_deleted = 1 WHERE id IN ({placeholders})",
            chunk,
        )
    if commit:
        con.commit()
    return len(missing_ids)

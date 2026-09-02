"""Write/init helpers for MD Viewer persistence."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from importlib import import_module

from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()


def _mark_missing_deleted(local_con: sqlite3.Connection, found_paths: set) -> int:
    store_queries = import_module("extensions.builtin_md_viewer.core_impl.store_queries")
    return store_queries.mark_missing_deleted(local_con, found_paths)


def ensure_md_viewer_tables(
    con: sqlite3.Connection | None = None,
    *,
    get_db_fn: Callable | None = None,
    submit_db_write_fn: Callable | None = None,
) -> None:
    """Create md viewer tables, indexes, and FTS triggers if needed."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn
    if submit_db_write_fn is None:
        submit_db_write_fn = submit_db_write

    with _init_lock:
        def _init() -> None:
            local_con = con if con is not None else get_db_fn()
            local_con.executescript(
                """
                CREATE TABLE IF NOT EXISTS md_files (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    path       TEXT    NOT NULL UNIQUE,
                    mtime      REAL    NOT NULL DEFAULT 0,
                    size       INTEGER NOT NULL DEFAULT 0,
                    title      TEXT    NOT NULL DEFAULT '',
                    content    TEXT    NOT NULL DEFAULT '',
                    lang       TEXT    NOT NULL DEFAULT '',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    indexed_at INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_md_files_path
                    ON md_files(path);
                CREATE INDEX IF NOT EXISTS idx_md_files_is_deleted
                    ON md_files(is_deleted);
                """
            )
            _ensure_lang_column(local_con)
            _ensure_fts_tables(local_con)
            local_con.commit()

        if con is not None:
            _init()
        else:
            submit_db_write_fn(_init)


def upsert_md_file_row(
    path: str,
    mtime: float,
    size: int,
    title: str,
    content: str,
    *,
    lang: str = "",
    con: sqlite3.Connection | None = None,
    get_db_fn: Callable | None = None,
) -> int:
    """Insert or update one markdown file row and return the row id."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    now = int(time.time())
    local_con = con if con is not None else get_db_fn()
    ensure_md_viewer_tables(local_con)
    cur = local_con.execute(
        """
        INSERT INTO md_files (path, mtime, size, title, content, lang, is_deleted, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(path) DO UPDATE SET
            mtime      = excluded.mtime,
            size       = excluded.size,
            title      = excluded.title,
            content    = excluded.content,
            lang       = excluded.lang,
            is_deleted = 0,
            indexed_at = excluded.indexed_at
        """,
        (path, mtime, size, title, content, lang, now),
    )
    local_con.commit()
    return cur.lastrowid or 0


def mark_missing_deleted_rows(
    found_paths: set,
    *,
    con: sqlite3.Connection | None = None,
    get_db_fn: Callable | None = None,
) -> int:
    """Soft-delete md rows that were not found during the latest scan."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    local_con = con if con is not None else get_db_fn()
    ensure_md_viewer_tables(local_con)
    return _mark_missing_deleted(local_con, found_paths)


def _ensure_lang_column(con: sqlite3.Connection) -> None:
    try:
        con.execute("SELECT lang FROM md_files LIMIT 1")
    except Exception:
        try:
            con.execute("ALTER TABLE md_files ADD COLUMN lang TEXT NOT NULL DEFAULT ''")
            con.commit()
        except Exception:
            # Every read of `lang` below assumes this column exists.
            logger.warning("md_files.lang column was not added", exc_info=True)
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_md_files_lang ON md_files(lang)")
        con.commit()
    except Exception:
        logger.warning("md_files lang index was not created", exc_info=True)


def _ensure_fts_tables(con: sqlite3.Connection) -> None:
    try:
        con.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS md_files_fts
            USING fts5(
                title, content,
                content=md_files, content_rowid=id
            )
            """
        )
        con.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS md_files_fts_ai
            AFTER INSERT ON md_files BEGIN
                INSERT INTO md_files_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS md_files_fts_au
            AFTER UPDATE ON md_files BEGIN
                INSERT INTO md_files_fts(md_files_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
                INSERT INTO md_files_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS md_files_fts_ad
            AFTER DELETE ON md_files BEGIN
                INSERT INTO md_files_fts(md_files_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
            END;
            """
        )
    except Exception:
        # Without these triggers the FTS index silently drifts from md_files.
        logger.warning("md_files FTS triggers were not created", exc_info=True)

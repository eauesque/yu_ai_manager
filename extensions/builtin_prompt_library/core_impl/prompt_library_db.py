"""Prompt Library DB schema & initialization.

Self-initializing: tables are created on first access via _ensure_tables().
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False


def _ensure_tables() -> None:
    """Create Prompt Library tables if they don't exist."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        from core.services_core.prompt_library_db_service import (
            initialize_prompt_library_tables,
        )

        initialize_prompt_library_tables()
        _initialized = True


def _migrate_characters_json(con) -> None:
    """Add characters_json column to existing tables (idempotent)."""
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(prompt_library)")}
        if "characters_json" not in cols:
            con.execute(
                "ALTER TABLE prompt_library ADD COLUMN characters_json TEXT NOT NULL DEFAULT ''"
            )
            con.commit()
            logger.info("prompt_library: added characters_json column")
    except Exception as exc:
        logger.warning("prompt_library migration failed: %s", exc)


def _ensure_fts(con) -> None:
    """Create FTS5 virtual table, sync triggers, and rebuild if needed."""
    # FTS5 virtual table
    try:
        con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS prompt_library_fts "
            "USING fts5(title, positive, negative, memo, "
            "content=prompt_library, content_rowid=id)"
        )
    except Exception as exc:
        logger.warning("prompt_library FTS5 unavailable: %s", exc)
        return

    # Check which triggers already exist
    rows = con.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='trigger' AND name LIKE 'prompt_library_fts_%'"
    )
    existing = {r[0] for r in rows}
    required = {"prompt_library_fts_ai", "prompt_library_fts_ad",
                "prompt_library_fts_au"}
    need_rebuild = bool(required - existing)

    # Use executescript for trigger creation -- con.execute() can fail
    # silently on compound trigger bodies containing semicolons.
    if need_rebuild:
        con.executescript("""
            CREATE TRIGGER IF NOT EXISTS prompt_library_fts_ai
            AFTER INSERT ON prompt_library BEGIN
                INSERT INTO prompt_library_fts(rowid, title, positive, negative, memo)
                VALUES (new.id, new.title, new.positive, new.negative, new.memo);
            END;

            CREATE TRIGGER IF NOT EXISTS prompt_library_fts_ad
            AFTER DELETE ON prompt_library BEGIN
                INSERT INTO prompt_library_fts(prompt_library_fts, rowid, title, positive, negative, memo)
                VALUES ('delete', old.id, old.title, old.positive, old.negative, old.memo);
            END;

            CREATE TRIGGER IF NOT EXISTS prompt_library_fts_au
            AFTER UPDATE ON prompt_library BEGIN
                INSERT INTO prompt_library_fts(prompt_library_fts, rowid, title, positive, negative, memo)
                VALUES ('delete', old.id, old.title, old.positive, old.negative, old.memo);
                INSERT INTO prompt_library_fts(rowid, title, positive, negative, memo)
                VALUES (new.id, new.title, new.positive, new.negative, new.memo);
            END;
        """)
        # Rebuild FTS index to catch data inserted before triggers existed
        con.execute(
            "INSERT INTO prompt_library_fts(prompt_library_fts) VALUES('rebuild')"
        )
        con.commit()
        logger.info("prompt_library FTS triggers created + index rebuilt")


def get_pl_db():
    """Return a DB connection with Prompt Library tables guaranteed to exist."""
    _ensure_tables()
    from core.services_core.prompt_library_db_service import get_prompt_library_db

    return get_prompt_library_db()


def get_pl_read_db():
    """Return a read-only DB connection with Prompt Library tables guaranteed to exist."""
    _ensure_tables()
    from core.services_core.prompt_library_db_service import get_prompt_library_read_db

    return get_prompt_library_read_db()

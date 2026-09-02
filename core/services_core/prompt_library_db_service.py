"""DB initialization helpers for Prompt Library."""

from __future__ import annotations

import logging

from core.services_core.db_api import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)


def initialize_prompt_library_tables() -> None:
    """Create Prompt Library tables if they don't exist."""

    def _init() -> None:
        con = get_db()
        con.executescript("""
            CREATE TABLE IF NOT EXISTS prompt_library (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL DEFAULT '',
                positive    TEXT    NOT NULL DEFAULT '',
                negative    TEXT    NOT NULL DEFAULT '',
                seed        TEXT    NOT NULL DEFAULT '',
                steps       TEXT    NOT NULL DEFAULT '',
                sampler     TEXT    NOT NULL DEFAULT '',
                cfg_scale   TEXT    NOT NULL DEFAULT '',
                model_name  TEXT    NOT NULL DEFAULT '',
                memo        TEXT    NOT NULL DEFAULT '',
                source_file_id INTEGER,
                characters_json TEXT NOT NULL DEFAULT '',
                created_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prompt_library_folders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                parent_id   INTEGER,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  INTEGER NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES prompt_library_folders(id)
            );

            CREATE TABLE IF NOT EXISTS prompt_library_folder_items (
                prompt_id   INTEGER NOT NULL,
                folder_id   INTEGER NOT NULL,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (prompt_id, folder_id),
                FOREIGN KEY (prompt_id) REFERENCES prompt_library(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES prompt_library_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS prompt_library_tags (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS prompt_library_tag_map (
                prompt_id INTEGER NOT NULL,
                tag_id    INTEGER NOT NULL,
                PRIMARY KEY (prompt_id, tag_id),
                FOREIGN KEY (prompt_id) REFERENCES prompt_library(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id)    REFERENCES prompt_library_tags(id) ON DELETE CASCADE
            );
        """)
        migrate_prompt_library_characters_json(con)
        ensure_prompt_library_fts(con)

    submit_db_write(_init)


def migrate_prompt_library_characters_json(con) -> None:
    """Add characters_json column to existing tables (idempotent)."""
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(prompt_library)").fetchall()}
        if "characters_json" not in cols:
            con.execute(
                "ALTER TABLE prompt_library ADD COLUMN characters_json TEXT NOT NULL DEFAULT ''"
            )
            con.commit()
            logger.info("prompt_library: added characters_json column")
    except Exception as exc:
        logger.warning("prompt_library migration failed: %s", exc)


def ensure_prompt_library_fts(con) -> None:
    """Create FTS5 virtual table, sync triggers, and rebuild if needed."""
    try:
        con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS prompt_library_fts "
            "USING fts5(title, positive, negative, memo, "
            "content=prompt_library, content_rowid=id)"
        )
    except Exception as exc:
        logger.warning("prompt_library FTS5 unavailable: %s", exc)
        return

    rows = con.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='trigger' AND name LIKE 'prompt_library_fts_%'"
    ).fetchall()
    existing = {r[0] for r in rows}
    required = {"prompt_library_fts_ai", "prompt_library_fts_ad", "prompt_library_fts_au"}
    need_rebuild = bool(required - existing)

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
        con.execute(
            "INSERT INTO prompt_library_fts(prompt_library_fts) VALUES('rebuild')"
        )
        con.commit()
        logger.info("prompt_library FTS triggers created + index rebuilt")


def get_prompt_library_db():
    return get_db()


def get_prompt_library_read_db():
    return get_readonly_db()

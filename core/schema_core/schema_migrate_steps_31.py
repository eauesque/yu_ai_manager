"""Schema migration 31: md_files table + FTS5 virtual table + sync triggers."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_31(con: sqlite3.Connection) -> None:
    """Create tables for the MD viewer."""
    logger.info("  -> Migration 31: Creating md_files table with FTS5")

    con.execute("""
        CREATE TABLE IF NOT EXISTS md_files (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            path       TEXT    NOT NULL UNIQUE,
            mtime      REAL    NOT NULL DEFAULT 0,
            size       INTEGER NOT NULL DEFAULT 0,
            title      TEXT    NOT NULL DEFAULT '',
            content    TEXT    NOT NULL DEFAULT '',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            indexed_at INTEGER NOT NULL DEFAULT 0
        )
    """)

    con.execute("CREATE INDEX IF NOT EXISTS idx_md_files_path ON md_files(path)")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_md_files_is_deleted "
        "ON md_files(is_deleted)"
    )

    # FTS5 virtual table (content-sync)
    con.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS md_files_fts
        USING fts5(
            title, content,
            content=md_files, content_rowid=id
        )
    """)

    # Sync triggers: INSERT / UPDATE / DELETE
    con.executescript("""
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
    """)

    set_schema_version(con, 31, "md_files table with FTS5 for MD viewer")

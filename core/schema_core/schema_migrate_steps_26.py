"""Schema migration 26: Add file_keyframes table for per-keyframe results."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_26(con: sqlite3.Connection) -> None:
    """Create file_keyframes table for per-keyframe analysis storage."""
    logger.info("  -> Migration 26: Adding file_keyframes table")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS file_keyframes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id      INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            keyframe_idx INTEGER NOT NULL,
            timestamp_ms INTEGER NOT NULL DEFAULT 0,
            vector       BLOB,
            wd_tags_json TEXT,
            model        TEXT NOT NULL DEFAULT '',
            created_at   INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(file_id, keyframe_idx, model)
        );
        CREATE INDEX IF NOT EXISTS idx_file_keyframes_file
            ON file_keyframes(file_id);
    """)
    set_schema_version(con, 26, "Add file_keyframes table")

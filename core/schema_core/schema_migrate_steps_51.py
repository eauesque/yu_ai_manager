"""Schema migration 51: file_hailo_tags table for Hailo Remote Tagger."""

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_51(con: sqlite3.Connection) -> None:
    """Create file_hailo_tags table for Hailo Remote Tagger."""
    logger.info("  -> Migration 51: Adding file_hailo_tags table")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS file_hailo_tags (
            id         INTEGER PRIMARY KEY,
            file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            tag_name   TEXT NOT NULL,
            confidence REAL NOT NULL,
            source     TEXT NOT NULL DEFAULT 'hailo_remote',
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            UNIQUE(file_id, tag_name)
        );
        CREATE INDEX IF NOT EXISTS idx_fht_file ON file_hailo_tags(file_id);
        CREATE INDEX IF NOT EXISTS idx_fht_tag  ON file_hailo_tags(tag_name);
    """)
    set_schema_version(con, 51, "Add file_hailo_tags table for Hailo Remote Tagger")

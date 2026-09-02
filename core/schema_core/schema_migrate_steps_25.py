"""Schema migration 25: Add file_vectors table for semantic search."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_25(con: sqlite3.Connection) -> None:
    """Create file_vectors table for CLIP/SigLIP embedding storage."""
    logger.info("  -> Migration 25: Adding file_vectors table for semantic search")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS file_vectors (
            file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
            model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
            vector      BLOB NOT NULL,
            created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_file_vectors_model
            ON file_vectors(model);
    """)
    set_schema_version(con, 25, "Add file_vectors table for semantic search")

"""Schema migration 41: Performance optimization -- path search FTS5 + composite indexes.

Search performance improvements for 1.5M file scale:
- files_path_fts: FTS5 table for path search (avoid full-table LIKE '%...%' scans)
- Composite indexes: covering indexes for frequent query patterns
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_41(con: sqlite3.Connection) -> None:
    """Add path search FTS5 + composite indexes."""
    logger.info("  -> Migration 41: performance indexes + files_path_fts")

    # --- 1. FTS5 table for path search ---
    # unicode61 tokenizer auto-tokenizes on path separators (/, \),
    # enabling fast partial matching on directory/file names.
    # tokenchars keeps '_' inside tokens (don't split snake_case names)
    # '.' is excluded so extensions become independent tokens ("png" etc.)
    try:
        con.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS files_path_fts
            USING fts5(
                path,
                content='files',
                content_rowid='id',
                tokenize="unicode61 tokenchars '_'"
            )
        """)

        # Triggers: sync with files table
        con.execute("""
            CREATE TRIGGER IF NOT EXISTS files_path_fts_ai
            AFTER INSERT ON files BEGIN
                INSERT INTO files_path_fts(rowid, path) VALUES (new.id, new.path);
            END
        """)
        con.execute("""
            CREATE TRIGGER IF NOT EXISTS files_path_fts_ad
            AFTER DELETE ON files BEGIN
                INSERT INTO files_path_fts(files_path_fts, rowid, path)
                VALUES ('delete', old.id, old.path);
            END
        """)
        con.execute("""
            CREATE TRIGGER IF NOT EXISTS files_path_fts_au
            AFTER UPDATE OF path ON files BEGIN
                INSERT INTO files_path_fts(files_path_fts, rowid, path)
                VALUES ('delete', old.id, old.path);
                INSERT INTO files_path_fts(rowid, path) VALUES (new.id, new.path);
            END
        """)

        # Populate FTS with existing data
        existing = con.execute(
            "SELECT COUNT(*) FROM files_path_fts"
        ).fetchone()[0]
        if existing == 0:
            con.execute("""
                INSERT INTO files_path_fts(rowid, path)
                SELECT id, path FROM files WHERE is_deleted=0
            """)
            populated = con.execute(
                "SELECT COUNT(*) FROM files_path_fts"
            ).fetchone()[0]
            logger.info("  -> files_path_fts populated: %d entries", populated)
    except Exception as exc:
        logger.warning("  -> files_path_fts creation skipped: %s", exc)

    # --- 2. Add composite indexes ---
    # Speed up tag search + date sort: file_tags(tag_id, file_id) covering
    _safe_index(con, """
        CREATE INDEX IF NOT EXISTS idx_file_tags_tagid_fileid
        ON file_tags(tag_id, file_id)
    """)

    # Speed up templates file_id reverse lookup (LEFT JOIN templates ON file_id)
    _safe_index(con, """
        CREATE INDEX IF NOT EXISTS idx_templates_file_id
        ON templates(file_id)
    """)

    # file_ratings file_id reverse lookup
    _safe_index(con, """
        CREATE INDEX IF NOT EXISTS idx_file_ratings_file_id
        ON file_ratings(file_id)
    """)

    # favorites(collection_id, file_id) covering -- speed up collection display
    _safe_index(con, """
        CREATE INDEX IF NOT EXISTS idx_favorites_coll_file
        ON favorites(collection_id, file_id)
    """)

    # files(is_deleted, path) -- base index for path LIKE search
    _safe_index(con, """
        CREATE INDEX IF NOT EXISTS idx_files_deleted_path
        ON files(is_deleted, path)
    """)

    set_schema_version(con, 41, "performance indexes + files_path_fts")


def _safe_index(con: sqlite3.Connection, sql: str) -> None:
    """Safely execute CREATE INDEX (skip if already exists)."""
    try:
        con.execute(sql)
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            logger.warning("  -> Index creation skipped: %s", exc)

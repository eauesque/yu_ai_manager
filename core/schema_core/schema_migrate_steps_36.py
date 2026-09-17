"""Schema migration 36: tags.first_seen_mtime (speed up new_tags query)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def apply_migration_36(con: sqlite3.Connection) -> None:
    """Add first_seen_mtime column to tags table and backfill existing data."""
    logger.info("  -> Migration 36: tags.first_seen_mtime column")

    if not _column_exists(con, "tags", "first_seen_mtime"):
        con.execute(
            "ALTER TABLE tags ADD COLUMN first_seen_mtime INTEGER"
        )

    # Backfill: temp table GROUP BY -> JOIN UPDATE (orders of magnitude faster than correlated subquery)
    # Skip if files.mtime or files.is_deleted don't exist (very old DB; no data to backfill)
    if _column_exists(con, "files", "mtime") and _column_exists(con, "files", "is_deleted"):
        logger.info("     Backfilling first_seen_mtime from file_tags (batch) ...")
        con.execute("""
            CREATE TEMP TABLE _tag_min_mtime AS
            SELECT ft.tag_id, MIN(f.mtime) AS min_mtime
            FROM file_tags ft
            JOIN files f ON f.id = ft.file_id
            WHERE f.is_deleted = 0
            GROUP BY ft.tag_id
        """)
        con.execute("""
            UPDATE tags SET first_seen_mtime = (
                SELECT min_mtime FROM _tag_min_mtime WHERE _tag_min_mtime.tag_id = tags.id
            )
            WHERE first_seen_mtime IS NULL
              AND id IN (SELECT tag_id FROM _tag_min_mtime)
        """)
        con.execute("DROP TABLE IF EXISTS _tag_min_mtime")
    else:
        logger.info("     Skipping backfill: files.mtime/is_deleted not yet present")

    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_tags_first_seen_mtime "
        "ON tags(first_seen_mtime) WHERE first_seen_mtime IS NOT NULL"
    )

    set_schema_version(con, 36, "tags.first_seen_mtime for new_tags speedup")

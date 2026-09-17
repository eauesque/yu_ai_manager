"""Schema migration 50: file_ext column for fast format filtering.

Replaces expensive LIKE chains (lower(f.path) LIKE '%.png' OR ...)
with a single indexed column lookup: f.file_ext IN ('.png', '.jpg', ...).

SQLite does not allow ALTER TABLE ADD COLUMN with STORED generated columns,
so we use a regular column + triggers to keep it in sync.
For fresh databases, schema_sql.py defines it as a STORED generated column
directly in CREATE TABLE (which does support it).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version

# SQL expression to compute file_ext from path
_EXT_EXPR = """
    CASE
        WHEN path LIKE '%.png' THEN '.png'
        WHEN path LIKE '%.jpg' THEN '.jpg'
        WHEN path LIKE '%.jpeg' THEN '.jpeg'
        WHEN path LIKE '%.webp' THEN '.webp'
        WHEN path LIKE '%.gif' THEN '.gif'
        WHEN path LIKE '%.bmp' THEN '.bmp'
        WHEN path LIKE '%.tif' THEN '.tif'
        WHEN path LIKE '%.tiff' THEN '.tiff'
        WHEN path LIKE '%.avif' THEN '.avif'
        WHEN path LIKE '%.heif' THEN '.heif'
        WHEN path LIKE '%.heic' THEN '.heic'
        WHEN path LIKE '%.jxl' THEN '.jxl'
        WHEN path LIKE '%.svg' THEN '.svg'
        WHEN path LIKE '%.webm' THEN '.webm'
        WHEN path LIKE '%.mp4' THEN '.mp4'
        WHEN path LIKE '%.mov' THEN '.mov'
        WHEN path LIKE '%.m4v' THEN '.m4v'
        WHEN path LIKE '%.avi' THEN '.avi'
        WHEN path LIKE '%.mkv' THEN '.mkv'
        WHEN path LIKE '%.ogv' THEN '.ogv'
        WHEN path LIKE '%.ts' THEN '.ts'
        WHEN path LIKE '%.m2ts' THEN '.m2ts'
        WHEN path LIKE '%.mp3' THEN '.mp3'
        WHEN path LIKE '%.wav' THEN '.wav'
        WHEN path LIKE '%.ogg' THEN '.ogg'
        WHEN path LIKE '%.opus' THEN '.opus'
        WHEN path LIKE '%.m4a' THEN '.m4a'
        WHEN path LIKE '%.aac' THEN '.aac'
        WHEN path LIKE '%.flac' THEN '.flac'
    END
"""


def _is_generated_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column is a GENERATED (virtual/stored) column."""
    return any(row[1] == column and row[6] in (2, 3) for row in con.execute(f"PRAGMA table_xinfo({table})"))


def apply_migration_50(con: sqlite3.Connection) -> None:
    """Add file_ext column with triggers for existing databases."""
    logger.info("  -> Migration 50: file_ext column + triggers + index")

    # Fresh databases already have file_ext as a GENERATED column from schema_sql.py.
    # In that case, skip ALTER/UPDATE/triggers — the column auto-computes itself.
    if _is_generated_column(con, "files", "file_ext"):
        logger.info("  -> file_ext is a generated column, skipping populate + triggers")
        # Still create the index (schema_init.py may not have run it yet)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_files_deleted_ext
            ON files(is_deleted, file_ext) WHERE file_ext IS NOT NULL
        """)
        set_schema_version(con, 50, "file_ext column + triggers + index")
        return

    # Add regular column (ALTER TABLE does not support STORED generated)
    try:
        con.execute("ALTER TABLE files ADD COLUMN file_ext TEXT")
        logger.info("  -> file_ext column added")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("  -> file_ext column already exists")
        else:
            raise

    # Populate existing rows
    con.execute(f"UPDATE files SET file_ext = ({_EXT_EXPR})")
    updated = con.execute("SELECT changes()").fetchone()[0]
    logger.info("  -> Populated file_ext for %d rows", updated)

    # Triggers to keep file_ext in sync on INSERT/UPDATE
    con.execute(f"""
        CREATE TRIGGER IF NOT EXISTS trg_files_ext_insert
        AFTER INSERT ON files
        BEGIN
            UPDATE files SET file_ext = ({_EXT_EXPR})
            WHERE id = NEW.id;
        END
    """)
    con.execute(f"""
        CREATE TRIGGER IF NOT EXISTS trg_files_ext_update
        AFTER UPDATE OF path ON files
        BEGIN
            UPDATE files SET file_ext = ({_EXT_EXPR})
            WHERE id = NEW.id;
        END
    """)

    # Composite index for the common query pattern:
    # WHERE f.is_deleted=0 AND f.file_ext IN (...)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_files_deleted_ext
        ON files(is_deleted, file_ext) WHERE file_ext IS NOT NULL
    """)

    set_schema_version(con, 50, "file_ext column + triggers + index")

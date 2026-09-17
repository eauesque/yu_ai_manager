"""Schema migration 49: startup performance optimizations.

- Add composite index on (is_deleted, parser_version) to eliminate
  full table scan during startup parser-version check.
- Create db_meta table for caching aggregate stats (total_files,
  min_parser_version, etc.) so startup can skip expensive COUNT queries.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_49(con: sqlite3.Connection) -> None:
    """Add startup performance indexes and db_meta table."""
    logger.info("  -> Migration 49: startup performance optimizations")

    # Index for parser_version check at startup
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_files_deleted_parser_version
        ON files(is_deleted, parser_version)
    """)

    # Metadata table for cached aggregate stats
    # Avoids expensive COUNT(*) queries at startup
    con.execute("""
        CREATE TABLE IF NOT EXISTS db_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)

    # Pre-populate db_meta with current stats
    import time
    now = int(time.time())

    total = con.execute(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0"
    ).fetchone()[0]

    from .schema_constants import CURRENT_PARSER_VERSION
    old_parser = con.execute(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND parser_version < ?",
        (CURRENT_PARSER_VERSION,),
    ).fetchone()[0]

    con.execute(
        """
        INSERT INTO db_meta (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        ("total_files", str(total), now),
    )
    con.execute(
        """
        INSERT INTO db_meta (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        ("old_parser_count", str(old_parser), now),
    )

    set_schema_version(con, 49, "startup performance optimizations")

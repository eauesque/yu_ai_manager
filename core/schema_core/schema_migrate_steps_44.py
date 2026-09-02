"""Schema migration 44: Performance index + monthly statistics cache table.

Speed up stats queries at 280K file scale:
- files.mtime index (for timeline / monthly_report range queries)
- monthly_stats_cache table (materialize COUNT(DISTINCT) results)
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_44(con: sqlite3.Connection) -> None:
    """Add performance index + monthly statistics cache table."""
    logger.info("  -> Migration 44: performance index + monthly_stats_cache")

    # files.mtime index (is_deleted=0 only)
    # Used by timeline GROUP BY and monthly_report range queries
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_files_mtime_active
        ON files(mtime) WHERE is_deleted = 0
    """)

    # Monthly stats cache table
    # Pre-compute and store expensive aggregations like COUNT(DISTINCT tag_id)
    con.execute("""
        CREATE TABLE IF NOT EXISTS monthly_stats_cache (
            month TEXT NOT NULL,
            stat_key TEXT NOT NULL,
            stat_value TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (month, stat_key)
        )
    """)

    set_schema_version(con, 44, "performance index + monthly_stats_cache")

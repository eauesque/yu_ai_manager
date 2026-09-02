"""Migration 77: add wd_tag_stats_cache table.

Stores pre-computed WD-Tagger aggregate statistics so that
/api/wd-tagger/stats never pays the 30-40s COUNT(DISTINCT) cost
on the first request after a server restart.  The background refresh
thread writes here after every recompute; the route reads from here
first, falling back to on-demand recompute only when the table is empty.
"""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_77(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 77: add wd_tag_stats_cache table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS wd_tag_stats_cache (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            stats_json  TEXT    NOT NULL DEFAULT '{}',
            computed_at INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Ensure the single row exists with empty stats so reads never fail.
    con.execute(
        "INSERT OR IGNORE INTO wd_tag_stats_cache (id, stats_json, computed_at) VALUES (1, '{}', 0)"
    )

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (77,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 77, "add wd_tag_stats_cache table")

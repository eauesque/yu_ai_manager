"""Schema migration 72: drop redundant idx_file_wd_tags_file_id.

The UNIQUE constraint ``UNIQUE(file_id, tag_name, model)`` on file_wd_tags
already creates ``sqlite_autoindex_file_wd_tags_1`` covering the same
file_id-prefix lookups (verified by EXPLAIN QUERY PLAN — all queries
filtering by ``file_id`` alone pick the autoindex with COVERING status).

Removing the redundant index cuts the per-row write maintenance cost on
``file_wd_tags`` by ~20% (4 indexes instead of 5). Hot path:
``replace_wd_tags_atomic_batch`` was hitting 800-1300ms per batch under
contention, blocking unrelated writes behind it.

Forward-only: the index can be re-created with a single CREATE INDEX
statement if a future query pattern needs it. The migration is idempotent
via ``DROP INDEX IF EXISTS``.
"""

from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _set_schema_version_once(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1",
        (72,),
    ).fetchone()
    if row is None:
        set_schema_version(
            con, 72,
            "drop redundant idx_file_wd_tags_file_id (covered by UNIQUE autoindex)",
        )


def apply_migration_72(con: sqlite3.Connection) -> None:
    """Idempotent: DROP INDEX IF EXISTS is safe on fresh schemas too."""
    logger.info("  -> Migration 72: drop redundant idx_file_wd_tags_file_id")

    # Drop both historical index names. v14 created idx_fwt_file; v56
    # introduced idx_file_wd_tags_file_id (rebuild-from-scratch path).
    # Either or both may exist depending on the DB's migration history.
    con.execute("DROP INDEX IF EXISTS idx_file_wd_tags_file_id")
    con.execute("DROP INDEX IF EXISTS idx_fwt_file")

    _set_schema_version_once(con)

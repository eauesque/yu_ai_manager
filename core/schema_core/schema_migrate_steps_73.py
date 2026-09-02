"""Schema migration 73: add (model, file_id) covering index on file_wd_tags.

Without this index, ``SELECT COUNT(DISTINCT file_id) ... GROUP BY model FROM
file_wd_tags`` (and ``SELECT DISTINCT model FROM file_wd_tags``) fall back to
a full-table scan + hash/sort. On production DBs with tens of millions of
file_wd_tags rows this takes 15-78 seconds, which directly drives the
``_list_profiles`` slow path under ``/api/wd-tagger/profiles`` (observed
78253ms in field debug logs).

A composite ``(model, file_id)`` index lets SQLite satisfy both queries
purely by index scan / skip-scan, dropping the worst-case cost to well under
a second.

Forward-only and idempotent: ``CREATE INDEX IF NOT EXISTS`` is safe on fresh
schemas too.
"""

from __future__ import annotations

import logging
import sqlite3

from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _set_schema_version_once(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1",
        (73,),
    ).fetchone()
    if row is None:
        set_schema_version(
            con, 73,
            "add idx_fwt_model_file covering index",
        )


def apply_migration_73(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 73: add idx_fwt_model_file")
    if table_has_column(con, "file_wd_tags", "model"):
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_fwt_model_file "
            "ON file_wd_tags(model, file_id)"
        )
    elif table_has_column(con, "file_wd_tags", "model_id"):
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_fwt_model_file "
            "ON file_wd_tags(model_id, file_id)"
        )
    _set_schema_version_once(con)

"""Schema migration 71: tag_name_normalized column + kv_state table.

spec: docs/superpowers/specs/2026-05-10-tagger-pluggable-models-design.md § 5.6

- Adds `file_wd_tags.tag_name_normalized TEXT` for cross-model search
  matching with NFKC + casefold + underscore-to-space normalization.
- Adds `idx_fwt_tag_normalized` index for index-driven lookup once
  backfill completes.
- Adds `kv_state` table to persist runtime markers (e.g. backfill
  progress: tag_normalized_backfill_v1 = running/completed/disabled).

Forward-only: column is never dropped (§ 5.6.4). Emergency rollback uses
kv_state.tag_normalized_backfill_v1='disabled' to disable the feature.
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
        (71,),
    ).fetchone()
    if row is None:
        set_schema_version(
            con, 71,
            "tag_name_normalized column on file_wd_tags + kv_state table",
        )


def apply_migration_71(con: sqlite3.Connection) -> None:
    """Idempotent: re-running on a partially migrated DB is safe."""
    logger.info("  -> Migration 71: tag_name_normalized + kv_state")

    if (
        table_has_column(con, "file_wd_tags", "tag_name")
        and not table_has_column(con, "file_wd_tags", "tag_name_normalized")
    ):
        con.execute(
            "ALTER TABLE file_wd_tags ADD COLUMN tag_name_normalized TEXT"
        )

    if table_has_column(con, "file_wd_tags", "tag_name_normalized"):
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_fwt_tag_normalized "
            "ON file_wd_tags(tag_name_normalized)"
        )

    con.execute(
        """CREATE TABLE IF NOT EXISTS kv_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )"""
    )

    _set_schema_version_once(con)

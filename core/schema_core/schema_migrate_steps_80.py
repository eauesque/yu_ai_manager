"""Migration 80: drop redundant duplicate index idx_fwt_tag on file_wd_tags.

file_wd_tags carried TWO identical indexes on tag_name: the old-named
`idx_fwt_tag` (created only by the pre-v17 migration path) and the canonical
`idx_file_wd_tags_tag_name` (present in the fresh schema + migration 56). The
duplicate wastes a full index over ~15.5M rows. Dropping `idx_fwt_tag` is
lossless (the canonical index serves every tag_name query) and converges old
migrated DBs to the fresh-schema shape. Fresh DBs never had `idx_fwt_tag`, so
this is a no-op there (DROP INDEX IF EXISTS).

Note: actual file-size reclamation requires a separate VACUUM; this migration
only removes the index definition. Designed to run via apply_pending (which
owns the transaction); does not call con.commit().
"""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_80(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 80: drop redundant idx_fwt_tag on file_wd_tags")
    con.execute("DROP INDEX IF EXISTS idx_fwt_tag")
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (80,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 80, "drop redundant idx_fwt_tag on file_wd_tags")

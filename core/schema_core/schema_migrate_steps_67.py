"""Migration 67: track which files carry Bridge sweep XMP metadata.

Adds ``files.has_sweep`` (0/1 flag, default 0) plus a partial index on
``has_sweep=1`` so the "sweep あり" search filter resolves with an
index scan instead of a full table scan.

The flag is set:

* At Bridge save time, by ``core.bridge_core.bridge_save_batch`` whenever
  a saved item carries ``sweep_meta``.
* For pre-existing files, by the one-shot backfill script
  ``scripts/backfill_has_sweep.py`` which walks the XMP packets and
  flips the flag for every file containing a ``sweep:id`` attribute.

We deliberately do not read XMP at periodic-scan time; that would slow
the regular scan path for a feature that only matters to images
generated through the bundled Bridges.
"""

import logging

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _column_exists(con, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def apply_migration_67(con) -> None:
    logger.info("  -> Migration 67: files.has_sweep + partial index")
    if not _column_exists(con, "files", "has_sweep"):
        con.execute(
            "ALTER TABLE files ADD COLUMN has_sweep INTEGER NOT NULL DEFAULT 0"
        )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_has_sweep "
        "ON files(id) WHERE has_sweep=1"
    )
    set_schema_version(con, 67, "Track Bridge sweep metadata presence on files")

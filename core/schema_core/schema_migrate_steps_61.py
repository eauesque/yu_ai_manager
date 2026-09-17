"""Migration 61: Add UNIQUE INDEX on files.path (legacy schema repair).

Fresh DBs created from `schema_sql.py` have `path TEXT NOT NULL UNIQUE`, but
DBs that were migrated up from very old versions never received this
constraint -- the `files` table was created with just `path TEXT` before the
UNIQUE was introduced, and no prior migration added it retroactively.

Without a UNIQUE constraint or UNIQUE INDEX on `path`, the scan worker's
`INSERT INTO files(...) ON CONFLICT(path) DO UPDATE ...` raises
`OperationalError: ON CONFLICT clause does not match any PRIMARY KEY or
UNIQUE constraint` for every file, and rows never land in the DB. Affected
installs would show "files: 0" and "画像がありません" after scan.

This migration:
  1. Resolves any existing duplicate paths (keeps the row with the highest id,
     deletes older duplicates) -- required before a UNIQUE INDEX can be built.
  2. Creates `uq_files_path` as a UNIQUE INDEX on files(path).

Dropping the pre-existing non-unique `idx_files_path` is not required --
SQLite can use the UNIQUE INDEX for the same lookups, but we keep the old
index to avoid breaking any `INDEXED BY idx_files_path` hints that may exist
elsewhere.
"""

import logging

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_61(con) -> None:
    logger.info("  -> Migration 61: add UNIQUE INDEX on files.path")

    # Detect duplicates before attempting to build the unique index.
    dupe_rows = con.execute(
        "SELECT path, COUNT(*) AS cnt FROM files "
        "GROUP BY path HAVING cnt > 1"
    ).fetchall()

    if dupe_rows:
        total_extra = sum(row[1] - 1 for row in dupe_rows)
        logger.warning(
            "  -> Found %d duplicate path(s) covering %d extra rows -- keeping highest id per path",
            len(dupe_rows), total_extra,
        )
        # Keep the row with the highest id for each duplicate path, delete the rest.
        con.execute(
            """DELETE FROM files
               WHERE id NOT IN (
                   SELECT MAX(id) FROM files GROUP BY path
               )"""
        )

    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_files_path ON files(path)"
    )
    set_schema_version(con, 61, "Add UNIQUE INDEX on files.path (legacy schema repair)")

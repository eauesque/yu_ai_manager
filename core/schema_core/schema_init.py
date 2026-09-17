"""Schema initialization helpers."""

import logging
import sqlite3

from .schema_connect import table_has_column
from .schema_sql import BASE_SCHEMA_SQL, FTS_SCHEMA_SQL

logger = logging.getLogger(__name__)

# Columns that were added to CREATE TABLE definitions without corresponding
# migrations. Very old DBs may lack these; add them before running migrations.
_FILES_BACKFILL_COLS = [
    # Columns added to CREATE TABLE without corresponding migrations.
    # Very old DBs may only have (id, path) as originals.
    ("mtime",       "INTEGER NOT NULL DEFAULT 0"),
    ("size",        "INTEGER NOT NULL DEFAULT 0"),
    ("hash",        "TEXT"),
    ("is_deleted",  "INTEGER NOT NULL DEFAULT 0"),
    ("meta_source", "TEXT"),
]
_TAGS_BACKFILL_COLS = [
    ("namespace", "TEXT"),
]


def init_db(con: sqlite3.Connection, enable_fts: bool) -> None:
    try:
        con.executescript(BASE_SCHEMA_SQL)
    except Exception:
        # Old DB: some columns referenced by indexes don't exist yet.
        # Fall back to statement-by-statement execution, skipping failures.
        # Migrations will add the missing columns and their indexes.
        _exec_schema_resilient(con, BASE_SCHEMA_SQL)

    # Backfill columns that were silently added to CREATE TABLE without migrations.
    # Must run before migrations so they can safely reference these columns.
    for col, coldef in _FILES_BACKFILL_COLS:
        if not table_has_column(con, "files", col):
            logger.info("init_db: backfilling files.%s (very old DB)", col)
            con.execute(f"ALTER TABLE files ADD COLUMN {col} {coldef}")
    for col, coldef in _TAGS_BACKFILL_COLS:
        if not table_has_column(con, "tags", col):
            logger.info("init_db: backfilling tags.%s (very old DB)", col)
            con.execute(f"ALTER TABLE tags ADD COLUMN {col} {coldef}")

    if not table_has_column(con, "files", "not_modified"):
        con.execute("ALTER TABLE files ADD COLUMN not_modified INTEGER NOT NULL DEFAULT 0")

    # file_ext index: only create if the generated column exists
    # (added by CREATE TABLE for fresh DBs, or by migration 50 for existing DBs)
    if _has_column_xinfo(con, "files", "file_ext"):
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_deleted_ext "
            "ON files(is_deleted, file_ext) WHERE file_ext IS NOT NULL"
        )

    if table_has_column(con, "tags", "first_seen_mtime"):
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_tags_first_seen_mtime "
            "ON tags(first_seen_mtime) WHERE first_seen_mtime IS NOT NULL"
        )

    if enable_fts and table_has_column(con, "templates", "char_positive"):
        # Only create FTS triggers if char_positive exists (migration 52).
        # On old DBs, migrations will set up FTS properly.
        con.executescript(FTS_SCHEMA_SQL)

    con.commit()


def _exec_schema_resilient(con: sqlite3.Connection, sql: str) -> None:
    """Execute SQL statements one by one, skipping those that fail.

    Used when an old DB lacks columns referenced by CREATE INDEX statements.
    Migrations are responsible for adding the missing columns and indexes.
    """
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            con.execute(stmt)
            con.commit()
        except Exception as e:
            logger.debug("Schema statement skipped (old DB): %s — %s", stmt[:80], e)


def _has_column_xinfo(con: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if column exists using table_xinfo (includes generated columns)."""
    try:
        rows = con.execute(f"PRAGMA table_xinfo({table})").fetchall()
        return any(r[1] == column for r in rows)
    except Exception:
        return False

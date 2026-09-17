"""Migration 57: Add missing columns to existing tables.

Fresh-DB init (migration 56) created all tables, but ALTER TABLE columns
added by migrations 1-55 were not back-filled into schema_sql.py.
This migration adds them with IF NOT EXISTS semantics (try/except).
"""

import logging

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version

_ALTER_COLUMNS = [
    # (table, column, type_and_default)
    ("files",     "phash",                  "TEXT"),
    ("templates", "prompt_lang",            "TEXT DEFAULT ''"),
    ("templates", "prompt_lang_confidence", "REAL DEFAULT 0.0"),
]


def apply_migration_57(con) -> None:
    """Add columns that were missing from the fresh-DB base schema."""
    logger.info("  -> Migration 57: adding missing columns (fresh-DB gap fix)")
    for table, column, col_def in _ALTER_COLUMNS:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            logger.info("     Added column %s.%s", table, column)
        except Exception:
            logger.warning("step failed", exc_info=True)
    set_schema_version(con, 57, "Add missing columns (fresh-DB init gap fix)")

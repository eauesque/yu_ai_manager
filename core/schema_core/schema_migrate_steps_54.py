"""Migration 54: Add hash chain columns to audit_log.

Adds prev_hash and entry_hash columns to enable tamper detection.
Existing records retain empty strings; the chain starts from the
first record inserted after this migration.
"""

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _table_columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def apply_migration_54(con: sqlite3.Connection) -> None:
    """Add prev_hash and entry_hash columns to audit_log."""
    logger.info("  -> Migration 54: audit_log hash chain columns")

    columns = _table_columns(con, "audit_log")
    if "prev_hash" not in columns:
        con.execute(
            "ALTER TABLE audit_log ADD COLUMN prev_hash TEXT DEFAULT ''"
        )
    if "entry_hash" not in columns:
        con.execute(
            "ALTER TABLE audit_log ADD COLUMN entry_hash TEXT DEFAULT ''"
        )

    set_schema_version(con, 54, "audit_log hash chain: prev_hash + entry_hash")
    logger.info("     audit_log hash chain columns added")

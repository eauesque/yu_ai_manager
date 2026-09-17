"""Migration 75: drop peers.allow_legacy_auth column."""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_75(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 75: drop peers.allow_legacy_auth")
    # Drop allow_legacy_auth column from peers table.
    # ALTER TABLE DROP COLUMN requires SQLite >= 3.35.0 (project runs 3.46.1).
    # No index on allow_legacy_auth exists (verified by grep on schema files).
    # Idempotency: check column existence before attempting DROP.
    cols = {r[1] for r in con.execute("PRAGMA table_info(peers)")}
    if "allow_legacy_auth" in cols:
        con.execute("ALTER TABLE peers DROP COLUMN allow_legacy_auth")

    # Record migration version. Do NOT call con.commit() here —
    # schema_migrate_registry.apply_pending() manages BEGIN IMMEDIATE / SAVEPOINT
    # and issues commit/RELEASE after this function returns.
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (75,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 75, "drop peers.allow_legacy_auth")

"""Migration 83: persist LAN Cowork peer crypto keys."""

from __future__ import annotations

import logging
import sqlite3

from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_83(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 83: add peer crypto key columns")

    if not table_has_column(con, "peers", "pubkey"):
        con.execute("ALTER TABLE peers ADD COLUMN pubkey BLOB")
    if not table_has_column(con, "peers", "x25519_pk"):
        con.execute("ALTER TABLE peers ADD COLUMN x25519_pk BLOB")

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (83,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 83, "persist LAN Cowork peer crypto keys")

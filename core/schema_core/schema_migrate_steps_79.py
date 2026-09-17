"""Migration 79: repair peer_pairing_requests missing crypto-identity columns.

Migration 60 adds pubkey/x25519_pk/commit_hash/sas/source_ip to
peer_pairing_requests via apply_crypto_identity_migration. But the fresh
schema definition (schema_sql_integrations.py) historically created the
table WITHOUT these columns, so any DB whose table was created from the
fresh schema at schema_version >= 60 had migration 60 stamped as applied
while the columns were never added. Pairing then fails with
'table peer_pairing_requests has no column named pubkey'.

This repair is idempotent and NON-destructive: it only ADDs missing
columns, never deleting rows/tokens/identity (unlike migration 60).
It is designed to run via apply_pending, which owns transaction commit;
apply_migration_79 itself does not call con.commit(), matching migration 78.
"""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)

_PAIRING_REPAIR_COLUMNS = (
    ("pubkey", "BLOB"),
    ("x25519_pk", "BLOB"),
    ("commit_hash", "BLOB"),
    ("sas", "TEXT"),
    ("source_ip", "TEXT"),
)


def apply_migration_79(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 79: repair peer_pairing_requests crypto-identity columns")
    from core.schema_core.schema_connect import table_has_column

    has_table = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='peer_pairing_requests' LIMIT 1"
    ).fetchone()
    if has_table:
        for name, coltype in _PAIRING_REPAIR_COLUMNS:
            if not table_has_column(con, "peer_pairing_requests", name):
                con.execute(
                    f"ALTER TABLE peer_pairing_requests ADD COLUMN {name} {coltype}"
                )

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (79,)
    ).fetchone()
    if row is None:
        set_schema_version(
            con, 79, "repair peer_pairing_requests crypto-identity columns"
        )

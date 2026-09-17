"""Migration 60: LAN Cowork identity store."""
import logging

logger = logging.getLogger(__name__)
from .schema_migrate_version import set_schema_version


def apply_migration_60(con) -> None:
    logger.info("  -> Migration 60: lan_cowork_identity")
    con.execute(
        """CREATE TABLE IF NOT EXISTS lan_cowork_identity (
               key   TEXT PRIMARY KEY,
               value BLOB NOT NULL
           )"""
    )
    # LAN Cowork crypto-identity Phase 2a Task 7: after the identity table
    # exists, perform the clean-cut migration for pairing columns and stale IDs.
    from core.services_core.lan_cowork_identity_service import apply_crypto_identity_migration

    apply_crypto_identity_migration(con)
    set_schema_version(con, 60, "LAN Cowork identity store")

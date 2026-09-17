"""Schema migration 40: Add undo columns to agent_action_journal (Agent Safety Phase 4)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_40(con: sqlite3.Connection) -> None:
    """Add reversible/undo_params_json/undone/undone_at columns to agent_action_journal."""
    logger.info("  -> Migration 40: agent_action_journal undo columns")

    # Existing column check (idempotency)
    cols = {
        row[1]
        for row in con.execute("PRAGMA table_info(agent_action_journal)").fetchall()
    }

    if "reversible" not in cols:
        con.execute(
            "ALTER TABLE agent_action_journal ADD COLUMN reversible INTEGER DEFAULT 0"
        )
    if "undo_params_json" not in cols:
        con.execute(
            "ALTER TABLE agent_action_journal ADD COLUMN undo_params_json TEXT"
        )
    if "undone" not in cols:
        con.execute(
            "ALTER TABLE agent_action_journal ADD COLUMN undone INTEGER DEFAULT 0"
        )
    if "undone_at" not in cols:
        con.execute(
            "ALTER TABLE agent_action_journal ADD COLUMN undone_at TEXT"
        )

    set_schema_version(con, 40, "agent_action_journal undo columns")

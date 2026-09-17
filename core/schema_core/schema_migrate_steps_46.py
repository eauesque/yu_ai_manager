"""Schema migration 46: audit_log table for Audit Bureau.

Independent audit log table, separate from agent_action_journal.
Used by the Audit Bureau for tamper-resistant operation recording.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_46(con: sqlite3.Connection) -> None:
    """Create audit_log table for Audit Bureau."""
    logger.info("  -> Migration 46: audit_log table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            target TEXT,
            severity TEXT NOT NULL,
            reported_to TEXT NOT NULL,
            detail_json TEXT,
            user_acknowledged INTEGER DEFAULT 0,
            acknowledged_at TEXT
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_event_type
        ON audit_log (event_type)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_severity
        ON audit_log (severity)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
        ON audit_log (timestamp)
    """)

    set_schema_version(con, 46, "audit_log table for Audit Bureau")

"""Schema migration 39: agent_action_journal table (Agent Safety Gateway Phase 1)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_39(con: sqlite3.Connection) -> None:
    """Create agent_action_journal table for agent operation logging."""
    logger.info("  -> Migration 39: agent_action_journal table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS agent_action_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            params_json TEXT NOT NULL DEFAULT '{}',
            result_summary TEXT,
            status TEXT NOT NULL DEFAULT 'success',
            duration_ms INTEGER DEFAULT 0,
            caller_info TEXT DEFAULT '',
            affected_count INTEGER DEFAULT 0
        )
    """)

    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_journal_session
        ON agent_action_journal(session_id)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_journal_time
        ON agent_action_journal(timestamp)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_journal_tool
        ON agent_action_journal(tool_name)
    """)

    set_schema_version(con, 39, "agent_action_journal table for Agent Safety Gateway")

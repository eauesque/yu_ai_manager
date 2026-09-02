"""Schema migration 34: Chat log extension -- entity, topic, decision tables + AI preprocessing columns."""

import contextlib
import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_34(con: sqlite3.Connection) -> None:
    """Add chat log extension tables and columns."""
    logger.info("  -> Migration 34: Chatlog enhanced tables (entities, topics, decisions)")

    # Entity table
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_entities (
            id              INTEGER PRIMARY KEY,
            conversation_id INTEGER NOT NULL
                REFERENCES chat_conversations(id) ON DELETE CASCADE,
            message_id      INTEGER,
            entity_type     TEXT NOT NULL,
            entity_value    TEXT NOT NULL
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_entities_type_value "
        "ON chat_entities(entity_type, entity_value)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_entities_conv "
        "ON chat_entities(conversation_id)"
    )

    # Topic table
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_topics (
            id              INTEGER PRIMARY KEY,
            conversation_id INTEGER NOT NULL
                REFERENCES chat_conversations(id) ON DELETE CASCADE,
            topic           TEXT NOT NULL
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_topics_topic "
        "ON chat_topics(topic)"
    )

    # Decision table
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_decisions (
            id              INTEGER PRIMARY KEY,
            conversation_id INTEGER NOT NULL
                REFERENCES chat_conversations(id) ON DELETE CASCADE,
            message_id      INTEGER,
            decision_text   TEXT NOT NULL
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_decisions_conv "
        "ON chat_decisions(conversation_id)"
    )

    # Conversations table extension (AI preprocessing columns)
    for col_sql in [
        "ALTER TABLE chat_conversations ADD COLUMN summary TEXT",
        "ALTER TABLE chat_conversations ADD COLUMN ai_processed_at INTEGER",
        "ALTER TABLE chat_conversations ADD COLUMN ai_model TEXT",
    ]:
        with contextlib.suppress(Exception):  # column may already exist
            con.execute(col_sql)

    set_schema_version(con, 34, "Chatlog enhanced: entities, topics, decisions, AI columns")

"""Schema migration 32: chat_conversations + chat_messages + FTS5."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_32(con: sqlite3.Connection) -> None:
    """Create tables for chat log management."""
    logger.info("  -> Migration 32: Creating chat_conversations / chat_messages with FTS5")

    # Conversations table
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source        TEXT    NOT NULL,
            external_id   TEXT,
            title         TEXT    NOT NULL DEFAULT '',
            model         TEXT    NOT NULL DEFAULT '',
            created_at    INTEGER NOT NULL DEFAULT 0,
            updated_at    INTEGER NOT NULL DEFAULT 0,
            message_count INTEGER NOT NULL DEFAULT 0,
            imported_at   INTEGER NOT NULL DEFAULT 0
        )
    """)

    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_conv_source "
        "ON chat_conversations(source)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_conv_external_id "
        "ON chat_conversations(external_id)"
    )
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_conv_source_extid "
        "ON chat_conversations(source, external_id)"
    )

    # Messages table
    con.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id)
                            ON DELETE CASCADE,
            role            TEXT    NOT NULL,
            content         TEXT    NOT NULL DEFAULT '',
            created_at      INTEGER NOT NULL DEFAULT 0,
            seq             INTEGER NOT NULL DEFAULT 0
        )
    """)

    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_msg_conv_id "
        "ON chat_messages(conversation_id)"
    )

    # FTS5 virtual table (content-sync)
    con.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts
        USING fts5(
            content,
            content=chat_messages, content_rowid=id,
            tokenize='unicode61'
        )
    """)

    # Sync triggers: INSERT / UPDATE / DELETE
    con.executescript("""
        CREATE TRIGGER IF NOT EXISTS chat_msg_fts_ai
        AFTER INSERT ON chat_messages BEGIN
            INSERT INTO chat_messages_fts(rowid, content)
            VALUES (new.id, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS chat_msg_fts_au
        AFTER UPDATE ON chat_messages BEGIN
            INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO chat_messages_fts(rowid, content)
            VALUES (new.id, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS chat_msg_fts_ad
        AFTER DELETE ON chat_messages BEGIN
            INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
        END;
    """)

    set_schema_version(con, 32, "chat_conversations + chat_messages with FTS5")

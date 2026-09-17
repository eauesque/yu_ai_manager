"""Initialization helpers for chatlog persistence."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

logger = logging.getLogger(__name__)


def ensure_chatlog_tables(
    con: sqlite3.Connection | None = None,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    """Create chatlog tables and FTS artifacts idempotently."""
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    local_con = con if con is not None else get_db_fn()
    local_con.execute("PRAGMA foreign_keys = ON")

    local_con.executescript("""
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
        );
        CREATE INDEX IF NOT EXISTS idx_chat_conv_source
            ON chat_conversations(source);
        CREATE INDEX IF NOT EXISTS idx_chat_conv_external_id
            ON chat_conversations(external_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_conv_source_extid
            ON chat_conversations(source, external_id);

        CREATE TABLE IF NOT EXISTS chat_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL
                REFERENCES chat_conversations(id) ON DELETE CASCADE,
            role            TEXT    NOT NULL,
            content         TEXT    NOT NULL DEFAULT '',
            created_at      INTEGER NOT NULL DEFAULT 0,
            seq             INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_chat_msg_conv_id
            ON chat_messages(conversation_id);
    """)

    try:
        local_con.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts
            USING fts5(
                content,
                content=chat_messages, content_rowid=id,
                tokenize='unicode61'
            )
        """)
        local_con.executescript("""
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
    except Exception:
        logger.warning("service step failed", exc_info=True)

    local_con.commit()

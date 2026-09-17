"""Chatlog store -- entity CRUD + search.

Handles insertion, search, and related conversation retrieval for the chat_entities table.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def ensure_entity_tables(con: sqlite3.Connection) -> None:
    """Create the chat_entities table idempotently.

    Migration 34 適用後は空振りするが、安全のためにべき等作成を残す。
    """
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


def insert_entities(
    con: sqlite3.Connection,
    conv_id: int,
    entities: list[dict[str, Any]],
) -> int:
    """Batch insert entities. Returns insert count."""
    if not entities:
        return 0
    rows = [
        (conv_id, e.get("message_id"), e["entity_type"], e["entity_value"])
        for e in entities
    ]
    con.executemany(
        """
        INSERT INTO chat_entities (conversation_id, message_id, entity_type, entity_value)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def delete_entities_for_conversation(
    con: sqlite3.Connection, conv_id: int,
) -> int:
    """Delete all entities for a conversation. Returns delete count."""
    cur = con.execute(
        "DELETE FROM chat_entities WHERE conversation_id = ?", (conv_id,),
    )
    return cur.rowcount


def get_entities_for_conversation(
    con: sqlite3.Connection, conv_id: int,
) -> list[dict[str, Any]]:
    """Return the list of entities associated with a conversation."""
    rows = con.execute(
        "SELECT id, conversation_id, message_id, entity_type, entity_value "
        "FROM chat_entities WHERE conversation_id = ? ORDER BY entity_type, entity_value",
        (conv_id,),
    )
    return [_row_to_dict(r) for r in rows]


def find_conversations_by_entity(
    con: sqlite3.Connection,
    entity_type: str,
    entity_value: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search conversations containing the specified entity."""
    sql = """
        SELECT DISTINCT c.id, c.source, c.title, c.model,
               c.created_at, c.updated_at, c.message_count
        FROM chat_entities e
        JOIN chat_conversations c ON c.id = e.conversation_id
        WHERE e.entity_type = ? AND e.entity_value = ?
        ORDER BY c.updated_at DESC
        LIMIT ?
    """
    rows = con.execute(sql, (entity_type, entity_value, limit))
    return [
        {
            "id": r[0], "source": r[1], "title": r[2], "model": r[3],
            "created_at": r[4], "updated_at": r[5], "message_count": r[6],
        }
        for r in rows
    ]


def find_conversations_by_entity_like(
    con: sqlite3.Connection,
    entity_type: str,
    entity_value: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search conversations by partial entity value match."""
    sql = """
        SELECT DISTINCT c.id, c.source, c.title, c.model,
               c.created_at, c.updated_at, c.message_count
        FROM chat_entities e
        JOIN chat_conversations c ON c.id = e.conversation_id
        WHERE e.entity_type = ? AND e.entity_value LIKE ?
        ORDER BY c.updated_at DESC
        LIMIT ?
    """
    rows = con.execute(sql, (entity_type, f"%{entity_value}%", limit))
    return [
        {
            "id": r[0], "source": r[1], "title": r[2], "model": r[3],
            "created_at": r[4], "updated_at": r[5], "message_count": r[6],
        }
        for r in rows
    ]


def get_related_conversations(
    con: sqlite3.Connection,
    conv_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get related conversations sharing the same entity.

    Returns other conversations with the same type+value entities as the target,
    sorted by shared entity count descending.
    """
    sql = """
        SELECT c.id, c.source, c.title, c.model,
               c.created_at, c.updated_at, c.message_count,
               COUNT(DISTINCT e2.entity_type || ':' || e2.entity_value) AS shared_count
        FROM chat_entities e1
        JOIN chat_entities e2
            ON e2.entity_type = e1.entity_type
            AND e2.entity_value = e1.entity_value
            AND e2.conversation_id != e1.conversation_id
        JOIN chat_conversations c ON c.id = e2.conversation_id
        WHERE e1.conversation_id = ?
        GROUP BY c.id
        ORDER BY shared_count DESC
        LIMIT ?
    """
    rows = con.execute(sql, (conv_id, limit))
    return [
        {
            "id": r[0], "source": r[1], "title": r[2], "model": r[3],
            "created_at": r[4], "updated_at": r[5], "message_count": r[6],
            "shared_entity_count": r[7],
        }
        for r in rows
    ]


def _row_to_dict(row) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return dict(row)
    return {
        "id": row[0],
        "conversation_id": row[1],
        "message_id": row[2],
        "entity_type": row[3],
        "entity_value": row[4],
    }

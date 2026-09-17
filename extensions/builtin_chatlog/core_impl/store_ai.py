"""Chatlog store -- AI preprocessing result CRUD.

Operates on chat_conversations.summary / ai_processed_at / ai_model columns
and chat_topics / chat_decisions tables.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any


def save_ai_result(
    con: sqlite3.Connection,
    conv_id: int,
    summary: str,
    topics: list[str],
    decisions: list[str],
    model: str,
) -> None:
    """Save AI preprocessing results.

    Existing topics and decisions are deleted and overwritten.
    """
    now = int(time.time())
    con.execute(
        "UPDATE chat_conversations SET summary = ?, ai_processed_at = ?, ai_model = ? "
        "WHERE id = ?",
        (summary, now, model, conv_id),
    )

    # Update topic
    con.execute("DELETE FROM chat_topics WHERE conversation_id = ?", (conv_id,))
    if topics:
        con.executemany(
            "INSERT INTO chat_topics (conversation_id, topic) VALUES (?, ?)",
            [(conv_id, t) for t in topics],
        )

    # Update decisions
    con.execute("DELETE FROM chat_decisions WHERE conversation_id = ?", (conv_id,))
    if decisions:
        con.executemany(
            "INSERT INTO chat_decisions (conversation_id, decision_text) VALUES (?, ?)",
            [(conv_id, d) for d in decisions],
        )


def get_summary(con: sqlite3.Connection, conv_id: int) -> str | None:
    """Get the summary for a conversation."""
    row = con.execute(
        "SELECT summary FROM chat_conversations WHERE id = ?", (conv_id,),
    ).fetchone()
    if not row:
        return None
    return row[0] if not hasattr(row, "keys") else row["summary"]


def get_topics(con: sqlite3.Connection, conv_id: int) -> list[str]:
    """Get the list of topics for a conversation."""
    rows = con.execute(
        "SELECT topic FROM chat_topics WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    )
    return [r[0] if not hasattr(r, "keys") else r["topic"] for r in rows]


def get_decisions(con: sqlite3.Connection, conv_id: int) -> list[dict[str, Any]]:
    """Get the list of decisions for a conversation."""
    rows = con.execute(
        "SELECT id, conversation_id, message_id, decision_text "
        "FROM chat_decisions WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    )
    return [
        {
            "id": r[0] if not hasattr(r, "keys") else r["id"],
            "conversation_id": r[1] if not hasattr(r, "keys") else r["conversation_id"],
            "message_id": r[2] if not hasattr(r, "keys") else r["message_id"],
            "decision_text": r[3] if not hasattr(r, "keys") else r["decision_text"],
        }
        for r in rows
    ]


def search_by_topic(
    con: sqlite3.Connection,
    topic: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search conversations by topic (partial match)."""
    rows = con.execute(
        """
        SELECT DISTINCT c.id, c.source, c.title, c.model,
               c.created_at, c.updated_at, c.message_count, c.summary,
               t.topic
        FROM chat_topics t
        JOIN chat_conversations c ON c.id = t.conversation_id
        WHERE t.topic LIKE ?
        ORDER BY c.updated_at DESC
        LIMIT ?
        """,
        (f"%{topic}%", limit),
    )
    return [
        {
            "id": r[0], "source": r[1], "title": r[2], "model": r[3],
            "created_at": r[4], "updated_at": r[5], "message_count": r[6],
            "summary": r[7], "matched_topic": r[8],
        }
        for r in rows
    ]


def search_decisions(
    con: sqlite3.Connection,
    query: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Cross-search decisions (partial match)."""
    rows = con.execute(
        """
        SELECT d.id, d.conversation_id, d.message_id, d.decision_text,
               c.title AS conv_title, c.source AS conv_source
        FROM chat_decisions d
        JOIN chat_conversations c ON c.id = d.conversation_id
        WHERE d.decision_text LIKE ?
        ORDER BY d.id DESC
        LIMIT ?
        """,
        (f"%{query}%", limit),
    )
    return [
        {
            "id": r[0], "conversation_id": r[1], "message_id": r[2],
            "decision_text": r[3], "conv_title": r[4], "conv_source": r[5],
        }
        for r in rows
    ]


def get_unprocessed_count(con: sqlite3.Connection) -> int:
    """Return the count of AI-unprocessed conversations."""
    row = con.execute(
        "SELECT COUNT(*) FROM chat_conversations WHERE ai_processed_at IS NULL"
    ).fetchone()
    return row[0] if row else 0


def get_unprocessed_ids(
    con: sqlite3.Connection, limit: int = 100,
) -> list[int]:
    """Return the list of AI-unprocessed conversation IDs."""
    rows = con.execute(
        "SELECT id FROM chat_conversations WHERE ai_processed_at IS NULL "
        "ORDER BY id LIMIT ?",
        (limit,),
    )
    return [r[0] for r in rows]

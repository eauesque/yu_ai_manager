"""Chatlog store: conversation CRUD operations.

Split from store.py to keep each module under 300 lines.
All functions take ``con: sqlite3.Connection`` as the first argument.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

_BASE_CONVERSATION_COLUMNS = [
    "id",
    "source",
    "external_id",
    "title",
    "model",
    "created_at",
    "updated_at",
    "message_count",
    "imported_at",
]
_OPTIONAL_CONVERSATION_COLUMNS = [
    "summary",
    "ai_processed_at",
    "ai_model",
    "language",
    "language_confidence",
]
_MESSAGE_COLUMNS = "id, conversation_id, role, content, created_at, seq"


def _conversation_columns_sql(con: sqlite3.Connection) -> str:
    columns = list(_BASE_CONVERSATION_COLUMNS)
    for column in _OPTIONAL_CONVERSATION_COLUMNS:
        if _has_column(con, "chat_conversations", column):
            columns.append(column)
    return ", ".join(columns)



# -- Conversation insert ------------------------------------------------

def insert_conversation(con: sqlite3.Connection, data: dict[str, Any]) -> int:
    """Insert a conversation record and return the new id."""
    now = int(time.time())
    lang = data.get("language", "")
    lang_conf = data.get("language_confidence", 0.0)

    # Check if language column exists (compat before migration 45)
    has_lang = _has_column(con, "chat_conversations", "language")

    if has_lang and lang:
        cur = con.execute(
            """
            INSERT INTO chat_conversations
                (source, external_id, title, model, created_at, updated_at,
                 message_count, imported_at, language, language_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("source", ""),
                data.get("external_id", ""),
                data.get("title", ""),
                data.get("model", ""),
                data.get("created_at", 0),
                data.get("updated_at", 0),
                data.get("message_count", 0),
                now,
                lang,
                lang_conf,
            ),
        )
    else:
        cur = con.execute(
            """
            INSERT INTO chat_conversations
                (source, external_id, title, model, created_at, updated_at,
                 message_count, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("source", ""),
                data.get("external_id", ""),
                data.get("title", ""),
                data.get("model", ""),
                data.get("created_at", 0),
                data.get("updated_at", 0),
                data.get("message_count", 0),
                now,
            ),
        )
    return cur.lastrowid or 0


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    """Check whether a column exists in the given table."""
    try:
        cols = con.execute(f"PRAGMA table_info({table})").fetchall()
        return any(c[1] == column for c in cols)
    except Exception:
        return False


def insert_messages(
    con: sqlite3.Connection, conv_id: int, messages: list[dict[str, Any]],
) -> int:
    """Bulk-insert messages and return the count of inserted rows."""
    rows = [
        (conv_id, m.get("role", ""), m.get("content", ""),
         m.get("created_at", 0), m.get("seq", i))
        for i, m in enumerate(messages)
    ]
    con.executemany(
        """
        INSERT INTO chat_messages (conversation_id, role, content, created_at, seq)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


# -- Conversation read --------------------------------------------------

def get_conversation(
    con: sqlite3.Connection, conv_id: int, *, source: str | None = None,
) -> dict[str, Any] | None:
    """Retrieve a conversation with all its messages.

    When ``source`` is provided, return None unless the conversation's
    ``source`` matches (used by per-source extensions like hailo-genai to
    avoid returning conversations imported from other sources).
    """
    sql = (
        f"SELECT {_conversation_columns_sql(con)} FROM chat_conversations WHERE id = ?"
    )
    params: list[Any] = [conv_id]
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    row = con.execute(sql, params).fetchone()
    if not row:
        return None
    conv = row_to_dict_conv(row)
    msg_rows = con.execute(
        f"SELECT {_MESSAGE_COLUMNS} FROM chat_messages WHERE conversation_id = ? ORDER BY seq",
        (conv_id,),
    )
    conv["messages"] = [row_to_dict_msg(r) for r in msg_rows]
    return conv


def list_conversations(
    con: sqlite3.Connection,
    source: str = "",
    model: str = "",
    query: str = "",
    date_from: int = 0,
    date_to: int = 0,
    sort: str = "updated_at",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List conversations with optional filters. Delegates to FTS if query is set."""
    if query.strip():
        from .store_search import search_conversations_fts
        return search_conversations_fts(
            con, query, source, model, date_from, date_to, sort, limit, offset,
        )

    sql = f"SELECT {_conversation_columns_sql(con)} FROM chat_conversations WHERE 1=1"
    params: list = []

    if source:
        sql += " AND source = ?"
        params.append(source)
    if model:
        sql += " AND model LIKE ?"
        params.append(f"%{model}%")
    if date_from:
        sql += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND created_at <= ?"
        params.append(date_to)

    allowed_sorts = {"created_at", "updated_at", "title", "message_count"}
    sort_col = sort if sort in allowed_sorts else "updated_at"
    sql += f" ORDER BY {sort_col} DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = con.execute(sql, params)
    return [row_to_dict_conv(r) for r in rows]


def find_by_external_id(
    con: sqlite3.Connection, source: str, ext_id: str,
) -> dict[str, Any] | None:
    """Find a conversation by source + external_id (for dedup)."""
    row = con.execute(
        f"SELECT {_conversation_columns_sql(con)} FROM chat_conversations WHERE source = ? AND external_id = ?",
        (source, ext_id),
    ).fetchone()
    if not row:
        return None
    return row_to_dict_conv(row)


def delete_conversation(
    con: sqlite3.Connection, conv_id: int, *, source: str | None = None,
) -> bool:
    """Delete a conversation. Messages are cascade-deleted.

    When ``source`` is provided, the row is deleted only if its source matches —
    caller must commit the surrounding transaction, including when running
    inside ``submit_db_write``.
    """
    con.execute("PRAGMA foreign_keys = ON")
    if source is None:
        cur = con.execute(
            "DELETE FROM chat_conversations WHERE id = ?", (conv_id,),
        )
    else:
        cur = con.execute(
            "DELETE FROM chat_conversations WHERE id = ? AND source = ?",
            (conv_id, source),
        )
    return cur.rowcount > 0


# -- Live chat helpers (used by extensions that append turns interactively) --

def append_message(
    con: sqlite3.Connection,
    conv_id: int,
    role: str,
    content: str,
    *,
    created_at: int | None = None,
) -> int:
    """Atomically append one message to a conversation.

    Allocates ``seq`` as ``MAX(seq)+1`` within a single INSERT statement so
    concurrent writers cannot collide on seq. Also bumps ``message_count`` and
    ``updated_at`` on the parent conversation row. The caller is expected to
    serialize writes (e.g. via ``submit_db_write``) and to commit / rollback
    the surrounding transaction. Returns the allocated ``seq``.

    Raises ``RuntimeError`` if the INSERT does not produce a row.
    """
    import time as _time

    now = int(_time.time()) if created_at is None else int(created_at)
    cur = con.execute(
        "INSERT INTO chat_messages "
        "(conversation_id, role, content, created_at, seq) "
        "VALUES (?, ?, ?, ?, "
        "  COALESCE("
        "    (SELECT MAX(seq) FROM chat_messages WHERE conversation_id = ?), "
        "    0"
        "  ) + 1)",
        (conv_id, role, content, now, conv_id),
    )
    if not cur.lastrowid:
        raise RuntimeError("append_message: INSERT returned no lastrowid")
    seq_row = con.execute(
        "SELECT seq FROM chat_messages WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    if seq_row is None:
        raise RuntimeError(
            f"append_message: inserted row id={cur.lastrowid} not found",
        )
    con.execute(
        "UPDATE chat_conversations "
        "SET message_count = message_count + 1, updated_at = ? "
        "WHERE id = ?",
        (now, conv_id),
    )
    return int(seq_row[0])


def rename_conversation(
    con: sqlite3.Connection,
    conv_id: int,
    title: str,
    *,
    source: str | None = None,
    only_if_title: str | None = None,
) -> bool:
    """Update a conversation title. The caller commits the transaction.

    ``source``: restrict to rows with this source (defense for multi-tenant DB).
    ``only_if_title``: only rename when the current title equals this value;
    used by auto-title flows that should not overwrite a user-set title.
    """
    sql = "UPDATE chat_conversations SET title = ? WHERE id = ?"
    params: list[Any] = [title, conv_id]
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    if only_if_title is not None:
        sql += " AND title = ?"
        params.append(only_if_title)
    cur = con.execute(sql, params)
    return cur.rowcount > 0


def list_messages_recent(
    con: sqlite3.Connection, conv_id: int, limit: int = 20,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` most recent messages, oldest first.

    Useful for building LLM prompts where the recent window matters but the
    chronological order must be preserved for the model.
    """
    rows = list(
        con.execute(
            "SELECT role, content FROM chat_messages "
            "WHERE conversation_id = ? ORDER BY seq DESC LIMIT ?",
            (conv_id, int(limit)),
        )
    )
    out: list[dict[str, Any]] = []
    for r in reversed(rows):
        role = r["role"] if hasattr(r, "keys") else r[0]
        content = r["content"] if hasattr(r, "keys") else r[1]
        out.append({"role": role, "content": content})
    return out


def get_stats(con: sqlite3.Connection) -> dict[str, Any]:
    """Return per-source counts and total message count."""
    rows = con.execute(
        "SELECT source, COUNT(*) AS cnt FROM chat_conversations GROUP BY source"
    )

    by_source = {}
    total_conv = 0
    for r in rows:
        src = r[0] if not hasattr(r, "keys") else r["source"]
        cnt = r[1] if not hasattr(r, "keys") else r["cnt"]
        by_source[src] = cnt
        total_conv += cnt

    msg_row = con.execute("SELECT COUNT(*) FROM chat_messages").fetchone()
    total_msg = msg_row[0] if msg_row else 0

    return {
        "total_conversations": total_conv,
        "total_messages": total_msg,
        "by_source": by_source,
    }


# -- Row conversion helpers -----------------------------------------------

def row_to_dict_conv(row) -> dict[str, Any]:
    """Convert a chat_conversations row to a dictionary."""
    if hasattr(row, "keys"):
        return dict(row)
    d = {
        "id": row[0], "source": row[1], "external_id": row[2],
        "title": row[3], "model": row[4], "created_at": row[5],
        "updated_at": row[6], "message_count": row[7], "imported_at": row[8],
    }
    # Columns added in migration 34 (only if present)
    if len(row) > 9:
        d["summary"] = row[9]
    if len(row) > 10:
        d["ai_processed_at"] = row[10]
    if len(row) > 11:
        d["ai_model"] = row[11]
    # Language column added in migration 45
    if len(row) > 12:
        d["language"] = row[12]
    if len(row) > 13:
        d["language_confidence"] = row[13]
    return d


def row_to_dict_msg(row) -> dict[str, Any]:
    """Convert a chat_messages row to a dictionary."""
    if hasattr(row, "keys"):
        return dict(row)
    return {
        "id": row[0], "conversation_id": row[1], "role": row[2],
        "content": row[3], "created_at": row[4], "seq": row[5],
    }


def row_to_dict_search(row) -> dict[str, Any]:
    """Convert a search result row to a dictionary."""
    if hasattr(row, "keys"):
        return dict(row)
    return {
        "id": row[0], "conversation_id": row[1], "role": row[2],
        "created_at": row[3], "seq": row[4], "snippet": row[5],
        "conv_title": row[6], "conv_source": row[7],
    }

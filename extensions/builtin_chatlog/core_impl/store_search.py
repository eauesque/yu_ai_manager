"""Chatlog store — FTS5 search + LIKE fallback + count helpers.

Search-related logic separated from store.py.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

# CJK character ranges (kanji, hiragana, katakana, hangul, etc.)
_CJK_RE = re.compile(
    r"[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u309F\u30A0-\u30FF"
    r"\uAC00-\uD7AF\uFF65-\uFF9F]"
)


def _row_to_dict_search(row) -> dict[str, Any]:
    """Map a search-result row (8 cols) to a dict.

    Columns: m.id, m.conversation_id, m.role, m.created_at, m.seq,
    snippet, conv_title, conv_source.
    """
    if hasattr(row, "keys"):
        return dict(row)
    return {
        "id": row[0],
        "conversation_id": row[1],
        "role": row[2],
        "created_at": row[3],
        "seq": row[4],
        "snippet": row[5],
        "conv_title": row[6],
        "conv_source": row[7],
    }


def search_conversations_fts(
    con: sqlite3.Connection,
    query: str,
    source: str,
    model: str,
    date_from: int,
    date_to: int,
    sort: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Search messages via FTS5 and return matching conversations.

    Falls back to LIKE for CJK queries.
    """
    from .store import _row_to_dict_conv

    use_fts = not _CJK_RE.search(query)

    if use_fts:
        sql = """
            SELECT DISTINCT c.*
            FROM chat_messages_fts f
            JOIN chat_messages m ON m.id = f.rowid
            JOIN chat_conversations c ON c.id = m.conversation_id
            WHERE chat_messages_fts MATCH ?
        """
    else:
        sql = """
            SELECT DISTINCT c.*
            FROM chat_messages m
            JOIN chat_conversations c ON c.id = m.conversation_id
            WHERE m.content LIKE ?
        """
    params: list = [query if use_fts else f"%{query}%"]

    if source:
        sql += " AND c.source = ?"
        params.append(source)
    if model:
        sql += " AND c.model LIKE ?"
        params.append(f"%{model}%")
    if date_from:
        sql += " AND c.created_at >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND c.created_at <= ?"
        params.append(date_to)

    sql += " ORDER BY c.updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = con.execute(sql, params)
    return [_row_to_dict_conv(r) for r in rows]


def search_messages(
    con: sqlite3.Connection,
    query: str,
    source: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search messages via FTS5 and return with snippets.

    CJK 文字を含むクエリは unicode61 トークナイザーで正しく分割
    されないため、LIKE フォールバックを使用する。
    """
    if _CJK_RE.search(query):
        return _search_messages_like(con, query, source, limit, offset)

    sql = """
        SELECT m.id, m.conversation_id, m.role, m.created_at, m.seq,
               snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 40) AS snippet,
               c.title AS conv_title, c.source AS conv_source
        FROM chat_messages_fts f
        JOIN chat_messages m ON m.id = f.rowid
        JOIN chat_conversations c ON c.id = m.conversation_id
        WHERE chat_messages_fts MATCH ?
    """
    params: list = [query]

    if source:
        sql += " AND c.source = ?"
        params.append(source)

    sql += " ORDER BY bm25(chat_messages_fts) LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = con.execute(sql, params)
    return [_row_to_dict_search(r) for r in rows]


def _search_messages_like(
    con: sqlite3.Connection,
    query: str,
    source: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """LIKE-based message search (CJK fallback)."""
    sql = """
        SELECT m.id, m.conversation_id, m.role, m.created_at, m.seq,
               m.content AS snippet,
               c.title AS conv_title, c.source AS conv_source
        FROM chat_messages m
        JOIN chat_conversations c ON c.id = m.conversation_id
        WHERE m.content LIKE ?
    """
    params: list = [f"%{query}%"]

    if source:
        sql += " AND c.source = ?"
        params.append(source)

    sql += " ORDER BY m.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = con.execute(sql, params)
    return [_row_to_dict_search(r) for r in rows]


def search_messages_grouped(
    con: sqlite3.Connection,
    query: str,
    source: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Message search grouped by conversation.

    Returns hit count and snippet array for each conversation.
    CJK クエリは LIKE フォールバック。

    Two-stage query: (1) GROUP BY for conversation+hit count -> (2) fetch snippets per conversation.
    Separated because snippet() cannot be used with GROUP BY.
    """
    use_fts = not _CJK_RE.search(query)

    # Step 1: get hit count per conversation
    if use_fts:
        count_sql = """
            SELECT c.id AS conversation_id, c.title, c.updated_at,
                   c.source, COUNT(m.id) AS hit_count
            FROM chat_messages_fts f
            JOIN chat_messages m ON m.id = f.rowid
            JOIN chat_conversations c ON c.id = m.conversation_id
            WHERE chat_messages_fts MATCH ?
        """
    else:
        count_sql = """
            SELECT c.id AS conversation_id, c.title, c.updated_at,
                   c.source, COUNT(m.id) AS hit_count
            FROM chat_messages m
            JOIN chat_conversations c ON c.id = m.conversation_id
            WHERE m.content LIKE ?
        """
    params: list = [query if use_fts else f"%{query}%"]

    if source:
        count_sql += " AND c.source = ?"
        params.append(source)

    count_sql += " GROUP BY c.id ORDER BY hit_count DESC LIMIT ?"
    params.append(limit)

    rows = con.execute(count_sql, params)

    # Step 2: get snippets for each conversation individually
    results = []
    for r in rows:
        conv_id = r[0] if not hasattr(r, "keys") else r["conversation_id"]

        if use_fts:
            snip_sql = """
                SELECT snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 40) AS snip
                FROM chat_messages_fts f
                JOIN chat_messages m ON m.id = f.rowid
                WHERE chat_messages_fts MATCH ? AND m.conversation_id = ?
                LIMIT 5
            """
            snip_rows = con.execute(snip_sql, (query, conv_id))
        else:
            snip_sql = """
                SELECT SUBSTR(m.content, 1, 200) AS snip
                FROM chat_messages m
                WHERE m.content LIKE ? AND m.conversation_id = ?
                LIMIT 5
            """
            snip_rows = con.execute(snip_sql, (f"%{query}%", conv_id))

        snippets = [sr[0] for sr in snip_rows if sr[0]]

        results.append({
            "conversation_id": conv_id,
            "title": r[1] if not hasattr(r, "keys") else r["title"],
            "updated_at": r[2] if not hasattr(r, "keys") else r["updated_at"],
            "source": r[3] if not hasattr(r, "keys") else r["source"],
            "hit_count": r[4] if not hasattr(r, "keys") else r["hit_count"],
            "snippets": snippets,
        })
    return results


def count_conversations(
    con: sqlite3.Connection,
    source: str = "",
    model: str = "",
    query: str = "",
) -> int:
    """Return the count of conversations matching conditions."""
    if query.strip():
        use_fts = not _CJK_RE.search(query)
        if use_fts:
            sql = """
                SELECT COUNT(DISTINCT c.id)
                FROM chat_messages_fts f
                JOIN chat_messages m ON m.id = f.rowid
                JOIN chat_conversations c ON c.id = m.conversation_id
                WHERE chat_messages_fts MATCH ?
            """
            params: list = [query]
        else:
            sql = """
                SELECT COUNT(DISTINCT c.id)
                FROM chat_messages m
                JOIN chat_conversations c ON c.id = m.conversation_id
                WHERE m.content LIKE ?
            """
            params = [f"%{query}%"]
        if source:
            sql += " AND c.source = ?"
            params.append(source)
        if model:
            sql += " AND c.model LIKE ?"
            params.append(f"%{model}%")
        row = con.execute(sql, params).fetchone()
    else:
        sql = "SELECT COUNT(*) FROM chat_conversations WHERE 1=1"
        params = []
        if source:
            sql += " AND source = ?"
            params.append(source)
        if model:
            sql += " AND model LIKE ?"
            params.append(f"%{model}%")
        row = con.execute(sql, params).fetchone()
    return row[0] if row else 0

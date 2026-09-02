"""Cross-source full-text search.

Unified search across md_files_fts + chat_messages_fts + prompt_library_fts
sorted by BM25 score.

Safely skips FTS tables that do not exist.
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


def search_all(
    con: sqlite3.Connection,
    query: str,
    targets: str = "md,chat,prompt",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Execute cross-search and return results sorted by BM25 score.

    Args:
        con: DB コネクション
        query: FTS5 検索クエリ
        targets: カンマ区切りの検索対象 ("md", "chat", "prompt")
        limit: 合計の最大件数
    """
    if not query.strip():
        return []

    target_set = {t.strip() for t in targets.split(",") if t.strip()}
    results: list[dict[str, Any]] = []

    if "md" in target_set:
        results.extend(_search_md(con, query, limit))
    if "chat" in target_set:
        results.extend(_search_chat(con, query, limit))
    if "prompt" in target_set:
        results.extend(_search_prompt(con, query, limit))

    # BM25 score ascending (smaller = more relevant) -> unified sort
    results.sort(key=lambda r: r.get("score", 0))
    return results[:limit]


def _search_md(
    con: sqlite3.Connection, query: str, limit: int,
) -> list[dict[str, Any]]:
    """Search from md_files_fts. Falls back to LIKE for CJK queries."""
    if not _table_exists(con, "md_files_fts"):
        return []
    if not _table_exists(con, "md_files"):
        return []
    use_fts = not _CJK_RE.search(query)
    try:
        if use_fts:
            rows = con.execute(
                """
                SELECT m.id, m.title, m.path,
                       snippet(md_files_fts, 1, '<mark>', '</mark>', '...', 40) AS snippet,
                       bm25(md_files_fts) AS score
                FROM md_files_fts f
                JOIN md_files m ON m.id = f.rowid
                WHERE md_files_fts MATCH ? AND m.is_deleted = 0
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            )
        else:
            rows = con.execute(
                """
                SELECT m.id, m.title, m.path,
                       m.content AS snippet,
                       0.0 AS score
                FROM md_files m
                WHERE (m.title LIKE ? OR m.content LIKE ?)
                  AND m.is_deleted = 0
                ORDER BY m.updated_at DESC
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            )
    except Exception:
        return []

    return [
        {
            "type": "md",
            "id": _col(r, 0, "id"),
            "title": _col(r, 1, "title"),
            "path": _col(r, 2, "path"),
            "snippet": _col(r, 3, "snippet"),
            "score": _col(r, 4, "score"),
        }
        for r in rows
    ]


def _search_chat(
    con: sqlite3.Connection, query: str, limit: int,
) -> list[dict[str, Any]]:
    """Search from chat_messages_fts. Falls back to LIKE for CJK queries."""
    if not _table_exists(con, "chat_messages_fts"):
        return []
    use_fts = not _CJK_RE.search(query)
    try:
        if use_fts:
            rows = con.execute(
                """
                SELECT m.id, m.conversation_id, m.role,
                       snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 40) AS snippet,
                       bm25(chat_messages_fts) AS score,
                       c.title AS conv_title, c.source AS conv_source
                FROM chat_messages_fts f
                JOIN chat_messages m ON m.id = f.rowid
                JOIN chat_conversations c ON c.id = m.conversation_id
                WHERE chat_messages_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            )
        else:
            rows = con.execute(
                """
                SELECT m.id, m.conversation_id, m.role,
                       m.content AS snippet,
                       0.0 AS score,
                       c.title AS conv_title, c.source AS conv_source
                FROM chat_messages m
                JOIN chat_conversations c ON c.id = m.conversation_id
                WHERE m.content LIKE ?
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (f"%{query}%", limit),
            )
    except Exception:
        return []

    return [
        {
            "type": "chat",
            "id": _col(r, 0, "id"),
            "conversation_id": _col(r, 1, "conversation_id"),
            "role": _col(r, 2, "role"),
            "snippet": _col(r, 3, "snippet"),
            "score": _col(r, 4, "score"),
            "title": _col(r, 5, "conv_title"),
            "source": _col(r, 6, "conv_source"),
        }
        for r in rows
    ]


def _search_prompt(
    con: sqlite3.Connection, query: str, limit: int,
) -> list[dict[str, Any]]:
    """Search from prompt_library_fts. Falls back to LIKE for CJK queries."""
    if not _table_exists(con, "prompt_library_fts"):
        return []
    use_fts = not _CJK_RE.search(query)
    try:
        if use_fts:
            rows = con.execute(
                """
                SELECT p.id, p.title,
                       snippet(prompt_library_fts, 1, '<mark>', '</mark>', '...', 40) AS snippet,
                       bm25(prompt_library_fts) AS score
                FROM prompt_library_fts f
                JOIN prompt_library p ON p.id = f.rowid
                WHERE prompt_library_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            )
        else:
            if not _table_exists(con, "prompt_library"):
                return []
            rows = con.execute(
                """
                SELECT p.id, p.title,
                       p.content AS snippet,
                       0.0 AS score
                FROM prompt_library p
                WHERE p.title LIKE ? OR p.content LIKE ?
                ORDER BY p.updated_at DESC
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            )
    except Exception:
        return []

    return [
        {
            "type": "prompt",
            "id": _col(r, 0, "id"),
            "title": _col(r, 1, "title"),
            "snippet": _col(r, 2, "snippet"),
            "score": _col(r, 3, "score"),
        }
        for r in rows
    ]


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    """Check if a table/virtual table exists."""
    row = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (name,),
    ).fetchone()
    return bool(row and row[0])


def _col(row: Any, idx: int, key: str) -> Any:
    """Get a value from sqlite3.Row or tuple."""
    if hasattr(row, "keys"):
        return row[key]
    return row[idx]

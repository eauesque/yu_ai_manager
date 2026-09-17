"""Cross-text full-text search.

Searches md_files_fts + chat_messages_fts + prompt_library_fts + text_files_fts
and merges results by BM25 score.

Tables that do not exist are safely skipped.
Helper functions are in search_helpers.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .search_helpers import (
    col,
    is_cjk_query,
    table_exists,
    truncate_snippet,
)

# Re-export for backward compatibility
from .search_helpers import (  # noqa: F401
    col as _col,
)


def search_all(
    con: sqlite3.Connection,
    query: str,
    targets: str = "md,chat,prompt,txt",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Run cross-search and return results sorted by BM25 score."""
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
    if "txt" in target_set:
        results.extend(_search_txt(con, query, limit))

    results.sort(key=lambda r: r.get("score", 0))
    return results[:limit]


def _search_md(
    con: sqlite3.Connection, query: str, limit: int,
) -> list[dict[str, Any]]:
    """Search md_files_fts."""
    if not table_exists(con, "md_files_fts") or not table_exists(con, "md_files"):
        return []
    use_fts = not is_cjk_query(query)
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
            "id": col(r, 0, "id"),
            "title": col(r, 1, "title"),
            "path": col(r, 2, "path"),
            "snippet": truncate_snippet(col(r, 3, "snippet"), query),
            "score": col(r, 4, "score"),
        }
        for r in rows
    ]


def _search_chat(
    con: sqlite3.Connection, query: str, limit: int,
) -> list[dict[str, Any]]:
    """Search chat_messages_fts."""
    if not table_exists(con, "chat_messages_fts"):
        return []
    use_fts = not is_cjk_query(query)
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
            "id": col(r, 0, "id"),
            "conversation_id": col(r, 1, "conversation_id"),
            "role": col(r, 2, "role"),
            "snippet": truncate_snippet(col(r, 3, "snippet"), query),
            "score": col(r, 4, "score"),
            "title": col(r, 5, "conv_title"),
            "source": col(r, 6, "conv_source"),
        }
        for r in rows
    ]


def _search_prompt(
    con: sqlite3.Connection, query: str, limit: int,
) -> list[dict[str, Any]]:
    """Search prompt_library_fts."""
    if not table_exists(con, "prompt_library_fts"):
        return []
    use_fts = not is_cjk_query(query)
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
            if not table_exists(con, "prompt_library"):
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
            "id": col(r, 0, "id"),
            "title": col(r, 1, "title"),
            "snippet": truncate_snippet(col(r, 2, "snippet"), query),
            "score": col(r, 3, "score"),
        }
        for r in rows
    ]


def _search_txt(
    con: sqlite3.Connection, query: str, limit: int,
) -> list[dict[str, Any]]:
    """Search text_files_fts."""
    if not table_exists(con, "text_files_fts") or not table_exists(con, "text_files"):
        return []
    use_fts = not is_cjk_query(query)
    try:
        if use_fts:
            rows = con.execute(
                """
                SELECT t.id, t.title, t.path,
                       snippet(text_files_fts, 1, '<mark>', '</mark>', '...', 40) AS snippet,
                       bm25(text_files_fts) AS score
                FROM text_files_fts f
                JOIN text_files t ON t.id = f.rowid
                WHERE text_files_fts MATCH ? AND t.is_deleted = 0
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            )
        else:
            rows = con.execute(
                """
                SELECT t.id, t.title, t.path,
                       t.content AS snippet,
                       0.0 AS score
                FROM text_files t
                WHERE (t.title LIKE ? OR t.content LIKE ?)
                  AND t.is_deleted = 0
                ORDER BY t.indexed_at DESC
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            )
    except Exception:
        return []

    return [
        {
            "type": "txt",
            "id": col(r, 0, "id"),
            "title": col(r, 1, "title"),
            "path": col(r, 2, "path"),
            "snippet": truncate_snippet(col(r, 3, "snippet"), query),
            "score": col(r, 4, "score"),
        }
        for r in rows
    ]

"""Search helper functions: snippet truncation, table checks, column access."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

_CJK_RE = re.compile(
    r"[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u309F\u30A0-\u30FF"
    r"\uAC00-\uD7AF\uFF65-\uFF9F]"
)


def is_cjk_query(query: str) -> bool:
    """Return True if the query contains CJK characters."""
    return bool(_CJK_RE.search(query))


def truncate_snippet(snippet: str, query: str) -> str:
    """Trim long snippets from CJK LIKE fallback and highlight matches."""
    if not snippet or len(snippet) <= 300:
        return snippet
    # If <mark> tags present, it is an FTS5 snippet -- return as-is
    if "<mark>" in snippet:
        return snippet
    # LIKE fallback: extract ~150 chars around query position
    q_lower = query.lower()
    idx = snippet.lower().find(q_lower)
    if idx < 0:
        return snippet[:300] + "..."
    start = max(0, idx - 100)
    end = min(len(snippet), idx + len(query) + 200)
    result = snippet[start:end]
    if start > 0:
        result = "..." + result
    if end < len(snippet):
        result = result + "..."
    # Highlight
    import html as html_mod
    safe = html_mod.escape(result)
    safe_q = html_mod.escape(query)
    import re as re_mod
    safe = re_mod.sub(
        re_mod.escape(safe_q),
        lambda m: "<mark>" + m.group(0) + "</mark>",
        safe,
        flags=re_mod.IGNORECASE,
        count=3,
    )
    return safe


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    """Check if a table exists in the database."""
    row = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (name,),
    ).fetchone()
    return bool(row and row[0])


def col(row: Any, idx: int, key: str) -> Any:
    """Access a column value by index or key depending on row type."""
    if hasattr(row, "keys"):
        return row[key]
    return row[idx]

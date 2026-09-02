"""Date/path SQL filter builders for query module."""

import datetime as _dt
import logging
from typing import Any

from core.services_core.db_state import nfkc_lower

logger = logging.getLogger(__name__)

# Cache for files_path_fts table existence (checked once at startup)
_fts_available: bool | None = None


def _is_path_fts_available(con) -> bool:
    """Determine whether the files_path_fts table is available (result is cached)."""
    global _fts_available
    if _fts_available is not None:
        return _fts_available
    if con is None:
        return False
    try:
        con.execute("SELECT 1 FROM files_path_fts LIMIT 0")
        _fts_available = True
    except Exception:
        _fts_available = False
    return _fts_available


def invalidate_fts_available_cache() -> None:
    """Force the next call to re-probe ``files_path_fts``.

    Called by migrations that create or drop the table so a running process
    picks up the change without a restart.
    """
    global _fts_available
    _fts_available = None


def _build_fts_query(term: str) -> str | None:
    """Convert a path search term to an FTS5 MATCH query.

    Escapes FTS5 special characters and adds prefix search (*) to each token.
    Returns None for empty strings or special-character-only input (LIKE fallback).
    """
    # Remove FTS5 special characters
    cleaned = term.replace('"', " ").replace("'", " ").replace("*", " ")
    # Split on the same separators as the unicode61 tokenizer
    # (/, \, ., -, :, space, etc. _ is kept in tokenchars so not split)
    for sep in ["/", "\\", ".", "-", ":", " "]:
        cleaned = cleaned.replace(sep, " ")
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return None
    # Prefix search each token and combine with AND
    parts = [f'"{t}"*' for t in tokens]
    return " AND ".join(parts)


def apply_date_filters(
    where_parts: list[str],
    params: list[Any],
    from_date: str | None,
    to_date: str | None,
    from_ts: int | None,
    to_ts: int | None,
):
    if from_ts is not None:
        where_parts.append("f.mtime>=?")
        params.append(from_ts)
    elif from_date:
        try:
            _dt.date.fromisoformat(from_date)  # validate format
            # Use SQLite strftime to convert local date to UTC epoch.
            # The 'utc' modifier means "input is localtime, convert to UTC",
            # so this uses the OS timezone regardless of Python's TZ setting.
            where_parts.append(
                "f.mtime >= CAST(strftime('%s', ? || ' 00:00:00', 'utc') AS INTEGER)"
            )
            params.append(from_date)
        except ValueError:
            pass

    if to_ts is not None:
        where_parts.append("f.mtime<=?")
        params.append(to_ts)
    elif to_date:
        try:
            _dt.date.fromisoformat(to_date)  # validate format
            # End of day in server-local timezone, converted to UTC epoch.
            where_parts.append(
                "f.mtime <= CAST(strftime('%s', ? || ' 23:59:59', 'utc') AS INTEGER)"
            )
            params.append(to_date)
        except ValueError:
            pass


def apply_path_filter(where_parts: list[str], params: list[Any], in_path: str | None, con=None):
    if not (in_path and in_path.strip()):
        return
    path_term = in_path.strip()

    # Use trigram-accelerated MATCH (idxNum=M0). LIKE-with-ESCAPE forces a
    # full SCAN even on a trigram FTS5 column, so MATCH is strictly better
    # whenever the term is long enough (>= 3 chars) for trigram indexing.
    if _is_path_fts_available(con) and path_term:
        from .fts_like_helpers import path_fts_match_phrase
        phrase = path_fts_match_phrase(path_term)
        if phrase is not None:
            where_parts.append(
                "f.id IN (SELECT rowid FROM files_path_fts WHERE path MATCH ?)"
            )
            params.append(phrase)
            return

    # Fallback: legacy LIKE on raw files.path
    normalized = nfkc_lower(path_term)
    path_fwd = normalized.replace("\\", "/")
    path_bck = path_fwd.replace("/", "\\")
    where_parts.append("(nfkc_lower(f.path) LIKE ? OR nfkc_lower(f.path) LIKE ?)")
    params.append(f"%{path_fwd}%")
    params.append(f"%{path_bck}%")

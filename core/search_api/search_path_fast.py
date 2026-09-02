"""Path-only fast-path helpers for search queries."""

import re

from core.services_core.db_state import nfkc_lower

_PATH_TOKEN_SPLIT_RE = re.compile(r"[^\w_]+", re.UNICODE)


def _matches_path_prefix_query(path: str, path_query: str) -> bool:
    query_tokens = [t for t in _PATH_TOKEN_SPLIT_RE.split(nfkc_lower(path_query)) if t]
    if not query_tokens:
        return False
    path_tokens = [t for t in _PATH_TOKEN_SPLIT_RE.split(nfkc_lower(path)) if t]
    if not path_tokens:
        return False
    return all(any(tok.startswith(query_token) for tok in path_tokens) for query_token in query_tokens)


def _try_recent_path_fast_path(con, path_query: str, limit: int, offset: int):
    """Fast path for broad path-only searches sorted by newest first.

    The regular FTS query must materialize and re-sort a potentially huge match set.
    For broad path-only queries, it is often cheaper to walk the newest files first,
    filter paths in Python, and stop once we have enough exact top-N matches.
    """
    target = offset + limit + 1
    window = max(200, min(max(target * 4, 200), 2000))
    max_window = 32000
    while window <= max_window:
        cursor = con.execute(
            "SELECT id, path, mtime, meta_source "
            "FROM files WHERE is_deleted=0 "
            "ORDER BY mtime DESC, id DESC LIMIT ?",
            (window,),
        )
        row_count = 0
        matched = []
        for row in cursor:
            row_count += 1
            if _matches_path_prefix_query(row["path"], path_query):
                matched.append(row)
        if row_count == 0:
            return [], False
        if len(matched) >= target:
            page_rows = matched[offset: offset + limit]
            results = [
                {
                    "id": row["id"],
                    "path": row["path"],
                    "mtime": row["mtime"],
                    "meta_source": row["meta_source"],
                    "positive": "",
                    "negative": "",
                }
                for row in page_rows
            ]
            return results, len(matched) > offset + limit
        if row_count < window:
            break
        window *= 2
    return None


def _path_fts_has_any_match(con, path_match_phrase: str) -> bool:
    # Trigram FTS5 accelerates `path MATCH ?` (idxNum=M0). The argument is the
    # FTS5 phrase already produced by ``path_fts_match_phrase()`` upstream
    # (e.g. ``'"arn-75w"'``).
    row = con.execute(
        "SELECT rowid FROM files_path_fts WHERE path MATCH ? LIMIT 1",
        (path_match_phrase,),
    ).fetchone()
    return row is not None

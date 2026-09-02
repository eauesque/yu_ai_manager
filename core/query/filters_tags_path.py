
from core.services_core.db_state import nfkc_lower

from .fts_like_helpers import path_fts_match_phrase
from .tag_resolve_cache import path_match_probe_cache

_PATH_MATCH_ESTIMATE_CAP = 1024


def path_search_condition(tag_val: str) -> str:
    """SQL fragment for path search via trigram FTS5 MATCH acceleration.

    Uses ``path MATCH ?`` (idxNum=M0, trigram-optimized) instead of
    ``path LIKE ? ESCAPE '\\'`` because the ESCAPE clause defeats SQLite's
    LIKE-on-trigram optimization and forces a full virtual-table SCAN.
    Callers must guarantee ``path_fts_match_phrase(tag_val) is not None``
    before using this fragment for the FTS path; otherwise fall back to
    the non-FTS legacy ``nfkc_lower`` form.
    """
    if not tag_val.strip() or path_fts_match_phrase(tag_val) is None:
        return "(nfkc_lower(f.path) LIKE ? OR nfkc_lower(f.path) LIKE ?)"
    return "f.id IN (SELECT rowid FROM files_path_fts WHERE path MATCH ?)"


def path_search_params(tag_val: str) -> list[str]:
    phrase = path_fts_match_phrase(tag_val)
    if not tag_val.strip() or phrase is None:
        normalized = nfkc_lower(tag_val)
        fwd = normalized.replace("\\", "/")
        return [f"%{normalized}%", f"%{fwd}%"]
    return [phrase]


def build_path_fts_query(term: str) -> str | None:
    """Legacy helper; retained for callers that still want the FTS5 phrase
    syntax. With the trigram tokenizer this is rarely useful — prefer
    ``path_search_params`` (LIKE) instead."""
    cleaned = term.replace('"', " ").replace("'", " ").replace("*", " ")
    for sep in ["/", "\\", ".", "-", ":", " "]:
        cleaned = cleaned.replace(sep, " ")
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return None
    return " AND ".join(f'"{token}"*' for token in tokens)


def path_search_has_match(con, tag_val: str) -> bool | None:
    estimate = path_search_match_estimate(con, tag_val)
    if estimate is None:
        return None
    return estimate > 0


def path_search_match_estimate(con, tag_val: str) -> int | None:
    if con is None or not tag_val.strip():
        return None
    phrase = path_fts_match_phrase(tag_val)
    if phrase is None:
        # Term too short for trigram. Don't probe (would be a full scan).
        # Treat as "unknown" so callers can decide whether to fall back to
        # the non-FTS LIKE path (which is path_search_condition's else branch).
        return None
    cache_key = ("match", tag_val)
    cached = path_match_probe_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        # MATCH on trigram FTS5 → idxNum=M0 (optimized), unlike LIKE+ESCAPE.
        rows = con.execute(
            f"SELECT rowid FROM files_path_fts WHERE path MATCH ? "  # noqa: S608
            f"LIMIT {_PATH_MATCH_ESTIMATE_CAP}",
            (phrase,),
        ).fetchall()
        match_count = len(rows)
        path_match_probe_cache.put(cache_key, match_count)
        return match_count
    except Exception:
        return None

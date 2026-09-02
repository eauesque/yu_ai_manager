"""Tag dictionary data access layer (Store pattern)."""

from __future__ import annotations

from core.services_core.db_api import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write


def search_tags(query: str, limit: int = 20) -> list[dict]:
    """Search with priority: prefix match -> substring match -> alias match."""
    if not query or limit < 1:
        return []
    con = get_readonly_db()
    results: list[dict] = []
    seen: set[str] = set()

    # 1. Prefix match
    rows = con.execute(
        "SELECT tag_name, category, post_count, aliases "
        "FROM tag_dictionary "
        "WHERE tag_name LIKE ? ESCAPE '\\' "
        "ORDER BY post_count DESC LIMIT ?",
        (_like_escape(query) + "%", limit),
    )
    for r in rows:
        key = r[0].lower()
        if key not in seen:
            seen.add(key)
            results.append(_row_to_dict(r, "prefix"))

    if len(results) >= limit:
        return results[:limit]

    # 2. Partial match
    remain = limit - len(results)
    rows = con.execute(
        "SELECT tag_name, category, post_count, aliases "
        "FROM tag_dictionary "
        "WHERE tag_name LIKE ? ESCAPE '\\' "
        "ORDER BY post_count DESC LIMIT ?",
        ("%" + _like_escape(query) + "%", remain + len(seen)),
    )
    for r in rows:
        key = r[0].lower()
        if key not in seen:
            seen.add(key)
            results.append(_row_to_dict(r, "substring"))
            if len(results) >= limit:
                return results[:limit]

    # 3. Alias match
    remain = limit - len(results)
    rows = con.execute(
        "SELECT tag_name, category, post_count, aliases "
        "FROM tag_dictionary "
        "WHERE aliases LIKE ? ESCAPE '\\' "
        "ORDER BY post_count DESC LIMIT ?",
        ("%" + _like_escape(query) + "%", remain + len(seen)),
    )
    for r in rows:
        key = r[0].lower()
        if key not in seen:
            seen.add(key)
            results.append(_row_to_dict(r, "alias"))
            if len(results) >= limit:
                break

    return results[:limit]


def get_tag_info(tag_name: str) -> dict | None:
    """Return details for a single tag."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT tag_name, category, post_count, aliases "
        "FROM tag_dictionary WHERE tag_name = ? COLLATE NOCASE",
        (tag_name,),
    ).fetchone()
    return _row_to_dict(row, "exact") if row else None


def get_stats() -> dict:
    """Dictionary statistics (total count, per-category counts)."""
    con = get_readonly_db()
    total = con.execute("SELECT COUNT(*) FROM tag_dictionary").fetchone()[0]
    cats = con.execute(
        "SELECT category, COUNT(*) FROM tag_dictionary GROUP BY category"
    )
    cat_map = {int(c[0]): c[1] for c in cats}
    return {"total": total, "categories": cat_map}


def get_tag_count() -> int:
    """Total number of tags in the dictionary."""
    con = get_readonly_db()
    return con.execute("SELECT COUNT(*) FROM tag_dictionary").fetchone()[0]


def clear_all() -> int:
    """Delete all entries and return the count."""
    from core.services_core.tag_dictionary_service import clear_tag_dictionary

    return submit_db_write(lambda: clear_tag_dictionary(get_db_fn=get_db))


def fuzzy_search_tags(query: str, limit: int = 100) -> list[dict]:
    """Return candidates for fuzzy matching (tags with similar length, sorted by post_count)."""
    con = get_readonly_db()
    q_len = len(query)
    rows = con.execute(
        "SELECT tag_name, category, post_count, aliases "
        "FROM tag_dictionary "
        "WHERE LENGTH(tag_name) BETWEEN ? AND ? "
        "ORDER BY post_count DESC LIMIT ?",
        (max(1, q_len - 2), q_len + 2, limit),
    )
    return [_row_to_dict(r, "fuzzy") for r in rows]


def get_all_tag_names(min_post_count: int = 0) -> set[str]:
    """Return all tag names in the dictionary as a set (for tag_splitter)."""
    con = get_readonly_db()
    rows = con.execute(
        "SELECT tag_name FROM tag_dictionary WHERE post_count >= ?",
        (min_post_count,),
    )
    return {r[0].lower().replace(" ", "_") for r in rows}


# ---- helpers ----

def _like_escape(s: str) -> str:
    """Escape special characters for LIKE patterns."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_dict(row, match_type: str) -> dict:
    return {
        "tag_name": row[0],
        "category": row[1],
        "post_count": row[2],
        "aliases": row[3] or "",
        "match_type": match_type,
    }

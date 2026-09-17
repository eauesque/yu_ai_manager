"""File-search service for tools routes."""

from core.services_core.db_api import get_readonly_db
from core.services_core.db_state import nfkc_lower


def file_search_service(q: str, meta_filter: str, limit: int):
    """Return file search results and total count."""
    if not q and meta_filter == "all":
        return {"results": [], "total": 0, "message": "検索語を入力してください"}, 200

    con = get_readonly_db()
    conditions = []
    params = []

    if q:
        conditions.append("nfkc_lower(f.path) LIKE ?")
        params.append(f"%{nfkc_lower(q)}%")

    if meta_filter == "has_meta":
        conditions.append("f.meta_source IS NOT NULL AND f.meta_source != 'unknown'")
    elif meta_filter == "no_meta":
        conditions.append("(f.meta_source IS NULL OR f.meta_source = 'unknown')")
    elif meta_filter == "unknown":
        conditions.append("f.meta_source = 'unknown'")

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
        SELECT f.id, f.path, f.meta_source, f.mtime, f.size, f.is_deleted,
               f.hash AS content_hash, f.parser_version,
               t.raw_prompt, t.format
        FROM files f
        LEFT JOIN templates t ON t.file_id = f.id
        WHERE {where}
        ORDER BY f.path
        LIMIT ?
    """
    params.append(limit)
    rows = con.execute(sql, params)

    count_sql = f"SELECT COUNT(*) FROM files f WHERE {where}"
    total = con.execute(count_sql, params[:-1]).fetchone()[0]

    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "path": r["path"],
            "meta_source": r["meta_source"] or "unknown",
            "mtime": r["mtime"],
            "size": r["size"],
            "is_deleted": bool(r["is_deleted"]),
            "content_hash": r["content_hash"],
            "parser_version": r["parser_version"],
            "has_prompt": bool(r["raw_prompt"]),
            "format": r["format"],
        })

    return {"results": results, "total": total}, 200


from .tag_resolve_cache import tag_cardinality_cache, tag_resolve_cache

_DENSE_TAG_THRESHOLD = 20000


def resolve_tag_ids(con, tag_val: str, case_sensitive: bool) -> list[int] | None:
    if con is None:
        return None
    cached = tag_resolve_cache.get(case_sensitive, tag_val)
    if cached is not None:
        return cached
    try:
        if case_sensitive:
            rows = con.execute("SELECT id FROM tags WHERE tag=?", (tag_val,)).fetchall()
        else:
            rows = con.execute(
                "SELECT id FROM tags WHERE LOWER(tag)=LOWER(?)",
                (tag_val,),
            ).fetchall()
        tag_ids = [r[0] for r in rows] if rows else []
        tag_resolve_cache.put(case_sensitive, tag_val, tag_ids)
        return tag_ids
    except Exception:
        return None


def tag_exists_by_id(tag_ids: list[int]) -> str:
    if len(tag_ids) == 1:
        return "f.id IN (SELECT file_id FROM file_tags WHERE tag_id=?)"
    placeholders = ",".join("?" * len(tag_ids))
    return f"f.id IN (SELECT file_id FROM file_tags WHERE tag_id IN ({placeholders}))"


def tag_candidate_set_sql(tag_ids: list[int]) -> str:
    if len(tag_ids) == 1:
        return "SELECT file_id AS id FROM file_tags WHERE tag_id=?"
    placeholders = ",".join("?" * len(tag_ids))
    return f"SELECT file_id AS id FROM file_tags WHERE tag_id IN ({placeholders})"


def tag_not_exists_by_id(tag_ids: list[int]) -> str:
    if len(tag_ids) == 1:
        return "NOT EXISTS(SELECT 1 FROM file_tags WHERE file_id=f.id AND tag_id=?)"
    placeholders = ",".join("?" * len(tag_ids))
    return f"NOT EXISTS(SELECT 1 FROM file_tags WHERE file_id=f.id AND tag_id IN ({placeholders}))"


def choose_tag_exists_sql(con, tag_ids: list[int]) -> str:
    if len(tag_ids) != 1 or con is None:
        return tag_exists_by_id(tag_ids)
    tag_id = int(tag_ids[0])
    cached = estimate_tag_match_count(con, [tag_id])
    if cached is None:
        return tag_exists_by_id(tag_ids)
    if cached >= _DENSE_TAG_THRESHOLD:
        return "EXISTS(SELECT 1 FROM file_tags WHERE file_id=f.id AND tag_id=?)"
    return tag_exists_by_id(tag_ids)


def estimate_tag_match_count(con, tag_ids: list[int]) -> int | None:
    if len(tag_ids) != 1 or con is None:
        return None
    tag_id = int(tag_ids[0])
    cached = tag_cardinality_cache.get(tag_id)
    if cached is not None:
        return cached
    try:
        probe_count = con.execute(
            f"SELECT COUNT(*) FROM ("
            f"SELECT 1 FROM file_tags WHERE tag_id=? LIMIT {_DENSE_TAG_THRESHOLD + 1}"
            f")",
            (tag_id,),
        ).fetchone()[0]
        if probe_count > _DENSE_TAG_THRESHOLD:
            cached = con.execute(
                "SELECT COUNT(*) FROM file_tags WHERE tag_id=?",
                (tag_id,),
            ).fetchone()[0]
        else:
            cached = int(probe_count)
        tag_cardinality_cache.put(tag_id, cached)
        return cached
    except Exception:
        return None

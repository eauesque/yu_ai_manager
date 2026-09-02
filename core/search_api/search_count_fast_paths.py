"""Fast-path SQL builders for count-only search."""

from __future__ import annotations

from core.prompt import parse_tag_query
from core.query.fts_like_helpers import path_fts_match_phrase
from core.search_api.count_cache import count_cache
from core.search_api.search_count_predicates import (
    can_fast_count_file_format,
    can_use_ai_analyzed_count_fast_path,
    can_use_has_tags_count_fast_path,
    can_use_negative_tag_count_fast_path,
    can_use_path_only_count_fast_path,
    can_use_plain_count_fast_path,
    can_use_single_positive_tag_count_fast_path,
    can_use_tag_candidate_count_fast_path,
    count_file_format_clause,
)
from core.search_api.search_count_tags import (
    resolve_excluded_tag_ids,
    resolve_positive_tag_ids,
    split_tag_ids,
)

ACTIVE_WD_MODEL_ALL_CACHE_KEY = "\0__all__"


def get_search_stat(con, key: str) -> int | None:
    try:
        row = con.execute("SELECT value FROM search_stats WHERE key=?", (key,)).fetchone()
        return int(row[0]) if row is not None else None
    except Exception:
        return None


def _get_active_wd_model_id_for_search() -> str | None:
    from core.services_core import wd_active_model

    return wd_active_model.try_get_active_wd_model_id_for_legacy_schema()


def _active_wd_model_cache_suffix(active_model_id: str | None) -> str:
    return active_model_id if active_model_id is not None else ACTIVE_WD_MODEL_ALL_CACHE_KEY


def try_negative_tag_count_fast_path(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_negative_tag_count_fast_path(p):
        return None
    tag_ids = resolve_excluded_tag_ids(con, p)
    if tag_ids is None:
        return None
    cache_key_sql = "NEGATIVE_TAG_COUNT_FAST_PATH:v1"
    cache_key_params = [p.get("tag_query_case_sensitive", False), *tag_ids]
    cached = count_cache.get(cache_key_sql, cache_key_params)
    if cached is not None:
        return {"status": "ok", "total_count": cached}, 200
    active_total = get_search_stat(con, "active_files")
    if active_total is None:
        active_total = int(con.execute("SELECT COUNT(*) FROM files WHERE is_deleted=0").fetchone()[0])
    if not tag_ids:
        count_cache.put(cache_key_sql, cache_key_params, active_total)
        return {"status": "ok", "total_count": active_total}, 200
    placeholders = ",".join("?" * len(tag_ids))
    excluded = int(con.execute(
        "SELECT COUNT(DISTINCT ft.file_id) "
        "FROM file_tags ft JOIN files f ON f.id=ft.file_id "
        f"WHERE f.is_deleted=0 AND ft.tag_id IN ({placeholders})",
        tag_ids,
    ).fetchone()[0])
    total_count = max(0, active_total - excluded)
    count_cache.put(cache_key_sql, cache_key_params, total_count)
    return {"status": "ok", "total_count": total_count}, 200


def try_tag_candidate_count_fast_path(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_tag_candidate_count_fast_path(p):
        return None
    split = split_tag_ids(con, p)
    if split is None:
        return None
    positive_ids, excluded_ids = split
    tag = next(tag for tag in parse_tag_query(p.get("tag_query") or "") if not tag.startswith("-"))
    path_phrase = path_fts_match_phrase(tag) if p.get("also_path") else None
    if not can_fast_count_file_format(p.get("file_format")):
        return None
    format_clause = count_file_format_clause(p.get("file_format"))
    if format_clause is None:
        return None
    cache_key_sql = "TAG_CANDIDATE_COUNT_FAST_PATH:v1"
    cache_key_params = [
        p.get("tag_query_case_sensitive", False), bool(p.get("also_path")),
        path_phrase or "", p.get("file_format") or "all",
        *positive_ids, "!", *excluded_ids,
    ]
    cached = count_cache.get(cache_key_sql, cache_key_params)
    if cached is not None:
        return {"status": "ok", "total_count": cached}, 200
    if not positive_ids and path_phrase is None:
        count_cache.put(cache_key_sql, cache_key_params, 0)
        return {"status": "ok", "total_count": 0}, 200
    candidate_parts, params = _candidate_parts(positive_ids, path_phrase)
    where_parts = ["f.is_deleted=0"]
    if format_clause:
        where_parts.append(format_clause)
    if excluded_ids:
        placeholders = ",".join("?" * len(excluded_ids))
        where_parts.append(
            "NOT EXISTS(SELECT 1 FROM file_tags "
            f"WHERE file_id=f.id AND tag_id IN ({placeholders}))"
        )
        params.extend(excluded_ids)
    total_count = int(con.execute(
        "SELECT COUNT(*) "
        f"FROM ({' UNION '.join(candidate_parts)}) ids "
        "JOIN files f ON f.id=ids.id "
        f"WHERE {' AND '.join(where_parts)}",
        params,
    ).fetchone()[0])
    count_cache.put(cache_key_sql, cache_key_params, total_count)
    return {"status": "ok", "total_count": total_count}, 200


def _candidate_parts(positive_ids: list[int], path_phrase: str | None) -> tuple[list[str], list]:
    candidate_parts = []
    params: list = []
    if positive_ids:
        placeholders = ",".join("?" * len(positive_ids))
        candidate_parts.append(f"SELECT file_id AS id FROM file_tags WHERE tag_id IN ({placeholders})")
        params.extend(positive_ids)
    if path_phrase is not None:
        candidate_parts.append("SELECT rowid AS id FROM files_path_fts WHERE path MATCH ?")
        params.append(path_phrase)
    return candidate_parts, params


def try_ai_analyzed_count_fast_path(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_ai_analyzed_count_fast_path(p):
        return None
    from core.services_core.wd_dict_resolver import resolve_model_id_readonly

    active_model_id = _get_active_wd_model_id_for_search()
    cache_key_sql = "AI_ANALYZED_COUNT_FAST_PATH:v1"
    cache_key_params: list = [_active_wd_model_cache_suffix(active_model_id)]
    cached = count_cache.get(cache_key_sql, cache_key_params)
    if cached is not None:
        return {"status": "ok", "total_count": cached}, 200
    wd_tags_sql = "SELECT file_id FROM file_wd_tags"
    params: list = []
    if active_model_id is not None:
        active_model_db_id = resolve_model_id_readonly(con, active_model_id)
        if active_model_db_id is None:
            wd_tags_sql += " WHERE 0=1"
        else:
            wd_tags_sql += " WHERE model_id = ?"
            params.append(active_model_db_id)
    total_count = int(con.execute(
        "SELECT COUNT(*) "
        f"FROM (SELECT file_id FROM analysis UNION {wd_tags_sql}) ids "
        "JOIN files f ON f.id=ids.file_id WHERE f.is_deleted=0",
        params,
    ).fetchone()[0])
    count_cache.put(cache_key_sql, cache_key_params, total_count)
    return {"status": "ok", "total_count": total_count}, 200


def try_path_only_count_fast_path(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_path_only_count_fast_path(p):
        return None
    path_phrase = path_fts_match_phrase((p.get("in_path") or "").strip())
    if path_phrase is None:
        return None
    cache_key_sql = "PATH_ONLY_COUNT_FAST_PATH:v1"
    cache_key_params = [path_phrase]
    cached = count_cache.get(cache_key_sql, cache_key_params)
    if cached is not None:
        return {"status": "ok", "total_count": cached}, 200
    try:
        total_count = int(con.execute(
            "SELECT COUNT(*) FROM files_path_fts p JOIN files f ON f.id=p.rowid "
            "WHERE p.path MATCH ? AND f.is_deleted=0",
            (path_phrase,),
        ).fetchone()[0])
    except Exception:
        return None
    count_cache.put(cache_key_sql, cache_key_params, total_count)
    return {"status": "ok", "total_count": total_count}, 200


def try_has_tags_count_fast_path(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_has_tags_count_fast_path(p):
        return None
    total_count = get_search_stat(con, "active_tagged_files")
    if total_count is None:
        return None
    return {"status": "ok", "total_count": total_count}, 200


def try_plain_count_fast_path(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_plain_count_fast_path(p):
        return None
    total_count = get_search_stat(con, "active_files")
    if total_count is None:
        return None
    return {"status": "ok", "total_count": total_count}, 200


def try_single_positive_tag_count_fast_path(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_single_positive_tag_count_fast_path(p):
        return None
    tag_ids = resolve_positive_tag_ids(con, p)
    if tag_ids is None:
        return None
    tag = parse_tag_query(p.get("tag_query") or "")[0]
    path_phrase = path_fts_match_phrase(tag) if p.get("also_path") else None
    cache_key_sql = "SINGLE_POSITIVE_TAG_COUNT_FAST_PATH:v1"
    cache_key_params = [p.get("tag_query_case_sensitive", False), bool(p.get("also_path")), path_phrase or "", *tag_ids]
    cached = count_cache.get(cache_key_sql, cache_key_params)
    if cached is not None:
        return {"status": "ok", "total_count": cached}, 200
    total_count = _count_single_positive(con, tag_ids, path_phrase, cache_key_sql, cache_key_params)
    return {"status": "ok", "total_count": total_count}, 200


def _count_single_positive(con, tag_ids: list[int], path_phrase: str | None, cache_key_sql: str, cache_key_params: list) -> int:
    if not tag_ids and path_phrase is None:
        count_cache.put(cache_key_sql, cache_key_params, 0)
        return 0
    if path_phrase is not None:
        union_parts, params = _candidate_parts(tag_ids, path_phrase)
        total_count = int(con.execute(
            "SELECT COUNT(*) FROM files f "
            f"WHERE f.is_deleted=0 AND f.id IN ({' UNION '.join(union_parts)})",
            params,
        ).fetchone()[0])
    else:
        placeholders = ",".join("?" * len(tag_ids))
        total_count = int(con.execute(
            "SELECT COUNT(DISTINCT ft.file_id) "
            "FROM file_tags ft JOIN files f ON f.id=ft.file_id "
            f"WHERE f.is_deleted=0 AND ft.tag_id IN ({placeholders})",
            tag_ids,
        ).fetchone()[0])
    count_cache.put(cache_key_sql, cache_key_params, total_count)
    return total_count

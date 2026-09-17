"""Count-only search response builder."""

from __future__ import annotations

import logging
import time

from core.query.builder import build_query_sql
from core.search_api.count_cache import count_cache
from core.search_api.file_meta_cache import can_use_cache
from core.search_api.search_cache_query import _try_cache_query
from core.search_api.search_count_fast_paths import (
    try_ai_analyzed_count_fast_path,
    try_has_tags_count_fast_path,
    try_negative_tag_count_fast_path,
    try_path_only_count_fast_path,
    try_plain_count_fast_path,
    try_single_positive_tag_count_fast_path,
    try_tag_candidate_count_fast_path,
)
from core.search_api.search_params import parse_search_args
from core.services_core.db_api import get_readonly_db

logger = logging.getLogger(__name__)


def _try_fast_count_paths(p: dict, con) -> tuple[dict, int] | None:
    for try_fast_path in (
        try_plain_count_fast_path,
        try_negative_tag_count_fast_path,
        try_tag_candidate_count_fast_path,
        try_single_positive_tag_count_fast_path,
        try_ai_analyzed_count_fast_path,
        try_path_only_count_fast_path,
        try_has_tags_count_fast_path,
    ):
        fast_count = try_fast_path(p, con)
        if fast_count is not None:
            return fast_count
    return None


def _try_memory_cache_count(p: dict, con) -> tuple[dict, int] | None:
    if not can_use_cache(p):
        return None
    cache_result = _try_cache_query(p, con, None)
    if cache_result is None:
        return None
    payload, status = cache_result
    if status != 200:
        return None
    return {"status": "ok", "total_count": payload.get("total_count", 0)}, 200


def _build_count_sql(p: dict, con):
    return build_query_sql(
        p["tag_query"],
        p["artist"],
        p["from_date"],
        p["to_date"],
        p["in_prompt"],
        p["file_format"],
        p["format_exts"],
        p["sort_by"],
        p["limit"],
        p["in_prompt_regex"],
        p["tag_query_regex"],
        p["tag_query_case_sensitive"],
        p["model_filter"],
        p["checkpoint_filter"],
        p["in_negative"],
        p["in_char_negative"],
        p["in_char_positive"],
        from_ts=p["from_ts_int"],
        to_ts=p["to_ts_int"],
        offset=0,
        in_path=p["in_path"],
        min_width=p["min_width_int"],
        max_width=p["max_width_int"],
        min_height=p["min_height_int"],
        max_height=p["max_height_int"],
        or_tags=p["or_tags"],
        also_search_path=p["also_path"],
        fav_only=p.get("fav_only", False),
        collection_id=p.get("collection_id", 0),
        min_rating=p.get("min_rating"),
        max_rating=p.get("max_rating"),
        ai_analyzed=p.get("ai_analyzed", False),
        has_tags=p.get("has_tags", False),
        has_annotation=p.get("has_annotation", False),
        has_sweep=p.get("has_sweep", False),
        con=con,
    )


def _dlog_slow_count(p: dict, con, count_sql: str, count_params, total_count: int, elapsed_ms: int) -> None:
    if elapsed_ms < 1000:
        return
    try:
        plan_rows = con.execute("EXPLAIN QUERY PLAN " + count_sql, count_params).fetchall()
        plan_text = " | ".join(f"{r[0]}:{r[1]}:{r[2]} {r[3]}" for r in plan_rows)
    except Exception as exc:
        plan_text = f"<plan-error: {exc}>"
    try:
        from core.infra_core.debug_log import dlog

        dlog(
            "search",
            "slow_count",
            elapsed_ms=elapsed_ms,
            total=total_count,
            tag_q=(p.get("tag_query") or "")[:80],
            in_path=(p.get("in_path") or "")[:80],
            in_prompt=(p.get("in_prompt") or "")[:80],
            also_path=p.get("also_path"),
            sql=count_sql[:800],
            params=str(count_params)[:300],
            plan=plan_text[:800],
        )
    except Exception:
        logger.debug("search step failed", exc_info=True)


def _execute_fallback_count(p: dict, con) -> tuple[dict, int]:
    _, _, count_sql, count_params = _build_count_sql(p, con)
    cached = count_cache.get(count_sql, count_params)
    if cached is not None:
        return {"status": "ok", "total_count": cached}, 200
    t0 = time.perf_counter()
    row = con.execute(count_sql, count_params).fetchone()
    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    total_count = int(row[0]) if row else 0
    count_cache.put(count_sql, count_params, total_count)
    _dlog_slow_count(p, con, count_sql, count_params, total_count, elapsed_ms)
    return {"status": "ok", "total_count": total_count}, 200


def build_search_count_response(args):
    p = parse_search_args(args)
    con = get_readonly_db()

    collection_id = p.get("collection_id", 0)
    if collection_id > 0 and not con.execute("SELECT 1 FROM collections WHERE id=?", (collection_id,)).fetchone():
        return {"status": "error", "message": "Collection not found"}, 404

    fast_count = _try_fast_count_paths(p, con)
    if fast_count is not None:
        return fast_count

    memory_cache_count = _try_memory_cache_count(p, con)
    if memory_cache_count is not None:
        return memory_cache_count

    try:
        return _execute_fallback_count(p, con)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}, 500

"""Search result response builder."""

import logging
import time

from core.search_api.search_count_response import build_search_count_response
from core.search_api.search_page_cache import search_page_cache
from core.search_api.search_params import has_search_conditions
from core.search_api.search_path_fast import (
    _path_fts_has_any_match,
    _try_recent_path_fast_path,
)
from core.search_api.search_prompt_fast import _try_recent_prompt_fast_path
from core.search_api.search_response_cache import try_memory_cache_response
from core.search_api.search_response_flow import (
    build_search_sql_bundle,
    parse_request,
    validate_collection,
)
from core.search_api.search_response_helpers import (
    backfill_prompts,
    build_fast_path_payload,
    build_results_payload,
    build_zero_probe_payload,
    perf_stats,
)
from core.search_api.search_response_logging import dlog_fast_path_slow, dlog_slow_query
from core.search_api.search_rows import build_total_count, rows_to_results
from core.services_core.db_api import get_readonly_db

logger = logging.getLogger(__name__)

__all__ = ["build_search_count_response", "build_search_response"]


def build_search_response(args):
    perf_enabled, defer_count, t0, t_parse, p, keyset_info, error = parse_request(args)
    if error is not None:
        return error

    # Read-only connection: don't block write locks during scans
    con = get_readonly_db()

    collection_error = validate_collection(con, p.get("collection_id", 0))
    if collection_error is not None:
        return collection_error

    cache_result, t_cache_start, t_cache_end = try_memory_cache_response(
        p, con, keyset_info, perf_enabled=perf_enabled, t0=t0, t_parse=t_parse
    )
    if cache_result is not None:
        return cache_result

    # === SQLite fallback ===
    try:
        t_sql_start = time.perf_counter()
        sql, params, count_sql, count_params = build_search_sql_bundle(p, keyset_info, con)
        t_build_end = time.perf_counter()
        use_page_cache = (
            p["offset"] == 0
            and keyset_info is None
            and p["limit"] <= 100
        )
        if use_page_cache:
            cached_payload = search_page_cache.get(sql, params)
            if cached_payload is not None:
                dlog_fast_path_slow(
                    "page_cache",
                    t0,
                    p,
                    build_ms=round((t_build_end - t_sql_start) * 1000),
                    hits=len(cached_payload.get("results", [])) if isinstance(cached_payload, dict) else None,
                )
                if perf_enabled:
                    now = time.perf_counter()
                    cached_payload["perf"] = perf_stats(
                        t0=t0,
                        t_parse=t_parse,
                        t_cache_start=t_cache_start,
                        t_cache_end=now,
                        t_build_end=t_build_end,
                        t_sql_start=t_sql_start,
                        t_sql_end=now,
                        t_rows=now,
                        t_count=now,
                        page_cache_hit=1,
                    )
                return cached_payload, 200
        pure_path_only_query = (
            len(params) == 3
            and isinstance(params[0], str)
            and "f.id IN (SELECT rowid FROM files_path_fts WHERE path MATCH ?)" in sql
            and "EXISTS(SELECT 1 FROM file_tags" not in sql
            and "templates" not in sql
        )
        if pure_path_only_query and not _path_fts_has_any_match(con, params[0]):
            t_sql_end = time.perf_counter()
            dlog_fast_path_slow(
                "zero_probe",
                t0,
                p,
                build_ms=round((t_build_end - t_sql_start) * 1000),
                probe_ms=round((t_sql_end - t_build_end) * 1000),
            )
            if perf_enabled:
                payload = build_zero_probe_payload(
                    p,
                    t0=t0,
                    t_parse=t_parse,
                    t_cache_start=t_cache_start,
                    t_cache_end=t_cache_end,
                    t_build_end=t_build_end,
                    t_sql_start=t_sql_start,
                    t_sql_end=t_sql_end,
                )
            else:
                payload = {
                    "status": "empty",
                    "total": 0,
                    "total_count": 0,
                    "limit": p["limit"],
                    "offset": p["offset"],
                    "has_more": False,
                    "has_conditions": has_search_conditions(p),
                    "path_search_active": True,
                    "count_pending": False,
                    "next_cursor": None,
                    "results": [],
                }
            return payload, 200
        recent_path_fast_path = (
            p["sort_by"] in ("date", "date_new")
            and len(params) == 3
            and isinstance(params[0], str)
            and params[0].startswith('"')
            and params[0].endswith('"')
            and len(params[0]) >= 2
            and "f.id IN (SELECT rowid FROM files_path_fts WHERE path MATCH ?)" in sql
            and "ORDER BY f.mtime DESC, f.id DESC" in sql
            and "templates" not in sql
        )
        if recent_path_fast_path:
            t_recent_start = time.perf_counter()
            path_query = params[0][1:-1].replace('""', '"')
            fast_path = _try_recent_path_fast_path(con, path_query, p["limit"], p["offset"])
            if fast_path is not None:
                results, has_more_fast = fast_path
                t_sql_end = time.perf_counter()
                dlog_fast_path_slow(
                    "recent_path",
                    t0,
                    p,
                    build_ms=round((t_build_end - t_sql_start) * 1000),
                    recent_lookup_ms=round((t_sql_end - t_recent_start) * 1000),
                    hits=len(results),
                )
                payload = build_fast_path_payload(
                    p,
                    results,
                    has_more_fast,
                    count_sql,
                    count_params,
                    con,
                    defer_count=defer_count,
                    t0=t0,
                    t_parse=t_parse,
                    t_cache_start=t_cache_start,
                    t_cache_end=t_cache_end,
                    t_build_end=t_build_end,
                    t_sql_start=t_sql_start,
                    t_sql_end=t_sql_end,
                )
                if not perf_enabled:
                    payload.pop("perf", None)
                if use_page_cache and payload["status"] in ("ok", "partial"):
                    search_page_cache.put(sql, params, payload)
                return payload, 200
        recent_prompt_fast_path = _try_recent_prompt_fast_path(con, p, keyset_info)
        if recent_prompt_fast_path is not None:
            results, has_more_fast = recent_prompt_fast_path
            t_sql_end = time.perf_counter()
            dlog_fast_path_slow(
                "recent_prompt",
                t0,
                p,
                build_ms=round((t_build_end - t_sql_start) * 1000),
                recent_lookup_ms=round((t_sql_end - t_build_end) * 1000),
                hits=len(results),
            )
            payload = build_fast_path_payload(
                p,
                results,
                has_more_fast,
                count_sql,
                count_params,
                con,
                defer_count=defer_count,
                t0=t0,
                t_parse=t_parse,
                t_cache_start=t_cache_start,
                t_cache_end=t_cache_end,
                t_build_end=t_build_end,
                t_sql_start=t_sql_start,
                t_sql_end=t_sql_end,
                path_search_active=False,
            )
            if not perf_enabled:
                payload.pop("perf", None)
            if use_page_cache and payload["status"] in ("ok", "partial"):
                search_page_cache.put(sql, params, payload)
            return payload, 200
        rows = con.execute(sql, params).fetchall()
        t_sql_end = time.perf_counter()
    except Exception as e:
        return {
            "status": "error",
            "total": 0,
            "results": [],
            "message": str(e),
        }, 500

    results = rows_to_results(rows)
    t_rows = time.perf_counter()
    backfill_prompts(results, con)
    count_pending = False
    if defer_count and p["offset"] == 0 and keyset_info is None and len(results) >= p["limit"]:
        total_count = p["offset"] + len(results) + p["limit"]
        count_pending = True
        t_count = time.perf_counter()
    elif defer_count and keyset_info is not None:
        total_count = p["offset"] + len(results)
        count_pending = True
        t_count = time.perf_counter()
    else:
        total_count = build_total_count(con, count_sql, count_params, p["limit"], p["offset"], len(results))
        t_count = time.perf_counter()

    payload = build_results_payload(
        p,
        results,
        rows,
        total_count,
        count_pending,
        t0=t0,
        t_parse=t_parse,
        t_cache_start=t_cache_start,
        t_cache_end=t_cache_end,
        t_build_end=t_build_end,
        t_sql_start=t_sql_start,
        t_sql_end=t_sql_end,
        t_rows=t_rows,
        t_count=t_count,
    )
    if not perf_enabled:
        payload.pop("perf", None)
    if (
        p["offset"] == 0
        and keyset_info is None
        and p["limit"] <= 100
        and payload["status"] in ("ok", "partial")
    ):
        search_page_cache.put(sql, params, payload)
    total_ms = dlog_slow_query(
        con,
        sql=sql,
        params=params,
        p=p,
        results=results,
        t0=t0,
        t_build_end=t_build_end,
        t_sql_end=t_sql_end,
        t_rows=t_rows,
        t_count=t_count,
    )
    if total_ms >= 50:
        logger.debug(
            "search q=%r total=%dms query=%dms rows=%dms count=%dms hits=%d",
            (p.get("tag_query") or "")[:40],
            total_ms,
            round((t_sql_end - t_build_end) * 1000),
            round((t_rows - t_sql_end) * 1000),
            round((t_count - t_rows) * 1000),
            len(results),
        )
    return payload, 200

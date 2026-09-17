"""Helper routines for search response assembly."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

from core.prompt import parse_a1111_prompt
from core.search_api.search_cursor import encode_cursor
from core.search_api.search_params import has_search_conditions
from core.search_api.search_rows import build_total_count

_PROMPT_PARSE_CACHE_MAX = 2048
_prompt_parse_cache: OrderedDict[tuple[str, str], tuple[str, str]] = OrderedDict()
_prompt_parse_cache_lock = threading.Lock()
_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def backfill_prompts(results: list, con) -> None:
    """Backfill positive/negative prompts for cache-served results."""
    if not results:
        return
    ids = [r["id"] for r in results if not r.get("positive")]
    if not ids:
        return
    prompt_map = {}
    for chunk in _chunks(list(dict.fromkeys(ids))):
        placeholders = ",".join("?" for _ in chunk)
        rows = con.execute(
            f"SELECT file_id, raw_prompt, raw_negative"
            f" FROM templates WHERE file_id IN ({placeholders})",
            chunk,
        )
        for row in rows:
            fid = row[0]
            raw_prompt = row[1] or ""
            raw_negative = row[2] or ""
            prompt_map[fid] = _normalize_prompt(raw_prompt, raw_negative)
    for result in results:
        if result["id"] in prompt_map:
            result["positive"], result["negative"] = prompt_map[result["id"]]


def _normalize_prompt(raw_prompt: str, raw_negative: str) -> tuple[str, str]:
    key = (raw_prompt, raw_negative)
    with _prompt_parse_cache_lock:
        cached = _prompt_parse_cache.get(key)
        if cached is not None:
            _prompt_parse_cache.move_to_end(key)
            return cached

    positive = raw_prompt
    negative = raw_negative
    if raw_prompt and ("Steps:" in raw_prompt or "Negative prompt:" in raw_prompt):
        parsed = parse_a1111_prompt(raw_prompt)
        positive = parsed["positive"]
        if not negative and parsed["negative"]:
            negative = parsed["negative"]
    normalized = (positive, negative)
    with _prompt_parse_cache_lock:
        _prompt_parse_cache[key] = normalized
        if len(_prompt_parse_cache) > _PROMPT_PARSE_CACHE_MAX:
            _prompt_parse_cache.popitem(last=False)
    return normalized


def perf_stats(
    *,
    t0: float,
    t_parse: float,
    t_cache_start: float,
    t_cache_end: float,
    t_build_end: float,
    t_sql_start: float,
    t_sql_end: float,
    t_rows: float,
    t_count: float,
    cache_hit: int = 0,
    page_cache_hit: int = 0,
    path_fast_path: int = 0,
    path_zero_probe_hit: int = 0,
) -> dict:
    return {
        "parse_ms": round((t_parse - t0) * 1000),
        "cache_ms": round((t_cache_end - t_cache_start) * 1000),
        "build_ms": round((t_build_end - t_sql_start) * 1000),
        "sql_ms": round((t_sql_end - t_cache_end) * 1000),
        "query_ms": round((t_sql_end - t_build_end) * 1000),
        "rows_ms": round((t_rows - t_sql_end) * 1000),
        "count_ms": round((t_count - t_rows) * 1000),
        "total_ms": round((t_count - t0) * 1000),
        "cache_hit": cache_hit,
        "page_cache_hit": page_cache_hit,
        "path_fast_path": path_fast_path,
        "path_zero_probe_hit": path_zero_probe_hit,
    }


def build_zero_probe_payload(p: dict, *, t0: float, t_parse: float, t_cache_start: float, t_cache_end: float, t_build_end: float, t_sql_start: float, t_sql_end: float) -> dict:
    t_rows = t_sql_end
    t_count = t_rows
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
    payload["perf"] = perf_stats(
        t0=t0,
        t_parse=t_parse,
        t_cache_start=t_cache_start,
        t_cache_end=t_cache_end,
        t_build_end=t_build_end,
        t_sql_start=t_sql_start,
        t_sql_end=t_sql_end,
        t_rows=t_rows,
        t_count=t_count,
        path_zero_probe_hit=1,
    )
    return payload


def build_fast_path_payload(
    p: dict,
    results: list,
    has_more_fast: bool,
    count_sql,
    count_params,
    con,
    *,
    defer_count: bool,
    t0: float,
    t_parse: float,
    t_cache_start: float,
    t_cache_end: float,
    t_build_end: float,
    t_sql_start: float,
    t_sql_end: float,
    path_search_active: bool = True,
) -> dict:
    t_rows = t_sql_end
    status = "empty" if len(results) == 0 else "partial" if has_more_fast else "ok"
    count_pending = False
    if defer_count and p["offset"] == 0 and len(results) >= p["limit"]:
        total_count = p["offset"] + len(results) + p["limit"]
        count_pending = True
        t_count = time.perf_counter()
    else:
        total_count = build_total_count(con, count_sql, count_params, p["limit"], p["offset"], len(results))
        t_count = time.perf_counter()
    next_cursor = None
    if has_more_fast and results:
        last = results[-1]
        next_cursor = encode_cursor(
            p["sort_by"],
            {"mtime": last["mtime"], "id": last["id"], "path": last.get("path", "")},
            p["offset"] + p["limit"],
        )
    payload = {
        "status": status,
        "total": len(results),
        "total_count": total_count,
        "limit": p["limit"],
        "offset": p["offset"],
        "has_more": has_more_fast,
        "has_conditions": has_search_conditions(p),
        "path_search_active": path_search_active,
        "count_pending": count_pending,
        "next_cursor": next_cursor,
        "results": results,
    }
    payload["perf"] = perf_stats(
        t0=t0,
        t_parse=t_parse,
        t_cache_start=t_cache_start,
        t_cache_end=t_cache_end,
        t_build_end=t_build_end,
        t_sql_start=t_sql_start,
        t_sql_end=t_sql_end,
        t_rows=t_rows,
        t_count=t_count,
        path_fast_path=1,
    )
    return payload


def build_results_payload(p: dict, results: list, rows, total_count: int, count_pending: bool, *, t0: float, t_parse: float, t_cache_start: float, t_cache_end: float, t_build_end: float, t_sql_start: float, t_sql_end: float, t_rows: float, t_count: float) -> dict:
    status = "empty" if len(results) == 0 else "partial" if len(results) >= p["limit"] else "ok"
    next_cursor = None
    if len(results) >= p["limit"] and results and p["sort_by"] != "random":
        last = results[-1]
        last_row = {"mtime": last["mtime"], "id": last["id"], "path": last.get("path", "")}
        if p["sort_by"] in ("rating_desc", "rating_asc") and rows:
            last_db_row = rows[-1]
            try:
                last_row["rating"] = last_db_row["_sort_rating"]
            except (IndexError, KeyError):
                last_row["rating"] = None
        next_cursor = encode_cursor(p["sort_by"], last_row, p["offset"] + p["limit"])

    path_search_active = (
        p["also_path"]
        and bool(p["tag_query"] and p["tag_query"].strip())
        and not p["tag_query_regex"]
        and not (p["in_path"] and p["in_path"].strip())
    )
    payload = {
        "status": status,
        "total": len(results),
        "total_count": total_count,
        "limit": p["limit"],
        "offset": p["offset"],
        "has_more": len(results) >= p["limit"],
        "has_conditions": has_search_conditions(p),
        "path_search_active": path_search_active,
        "count_pending": count_pending,
        "next_cursor": next_cursor,
        "results": results,
    }
    payload["perf"] = perf_stats(
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
    return payload

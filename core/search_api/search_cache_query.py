"""In-memory file_meta_cache query handler for search."""

import threading
import time

from core.search_api.file_meta_cache import file_meta_cache
from core.search_api.search_cursor import encode_cursor
from core.search_api.search_params import has_search_conditions

# Per-thread timing record (see file_meta_cache_query._QR_TLS for rationale).
_TLS = threading.local()


def _timing() -> dict[str, int]:
    timing = getattr(_TLS, "data", None)
    if timing is None:
        timing = {"ensure_ms": 0, "query_ms": 0, "build_resp_ms": 0}
        _TLS.data = timing
    return timing


def get_last_timing() -> dict[str, int]:
    """Return per-step timing of the most recent _try_cache_query() call.

    Used by build_search_response to enrich fast_path_slow events with a
    breakdown of where the in-memory cache time was spent.
    """
    return dict(_timing())


def _try_cache_query(p: dict, con, keyset_info) -> object:
    """Try to serve search from in-memory cache.

    Returns response tuple or None if cache miss.
    """
    t0 = time.perf_counter()
    if not file_meta_cache.ensure_built(con):
        _timing()["ensure_ms"] = round((time.perf_counter() - t0) * 1000)
        _timing()["query_ms"] = 0
        _timing()["build_resp_ms"] = 0
        return None
    t_ensure = time.perf_counter()

    # Extract cursor info for keyset pagination
    cursor_mtime = None
    cursor_id = None
    cursor_direction = "desc"
    if keyset_info and keyset_info.get("type") == "date":
        cursor_mtime = keyset_info.get("mtime")
        cursor_id = keyset_info.get("id")
        cursor_direction = keyset_info.get("direction", "desc")

    _timing()["ensure_ms"] = round((t_ensure - t0) * 1000)
    results, total_count, has_more = file_meta_cache.query(
        sort_by=p["sort_by"],
        file_format=p["file_format"],
        format_exts=p["format_exts"],
        from_ts=p["from_ts_int"],
        to_ts=p["to_ts_int"],
        in_path=p["in_path"],
        min_width=p["min_width_int"],
        max_width=p["max_width_int"],
        min_height=p["min_height_int"],
        max_height=p["max_height_int"],
        model_filter=p["model_filter"],
        limit=p["limit"],
        offset=p["offset"],
        cursor_mtime=cursor_mtime,
        cursor_id=cursor_id,
        cursor_direction=cursor_direction,
    )
    t_query = time.perf_counter()
    _timing()["query_ms"] = round((t_query - t_ensure) * 1000)

    has_conditions = has_search_conditions(p)
    status = "empty" if len(results) == 0 else "partial" if has_more else "ok"

    # Build next_cursor
    next_cursor = None
    if has_more and results and p["sort_by"] != "random":
        last = results[-1]
        next_cursor = encode_cursor(
            p["sort_by"],
            {"mtime": last["mtime"], "id": last["id"], "path": last.get("path", "")},
            p["offset"] + len(results),
        )

    response = {
        "status": status,
        "total": len(results),
        "total_count": total_count,
        "limit": p["limit"],
        "offset": p["offset"],
        "has_more": has_more,
        "has_conditions": has_conditions,
        "path_search_active": False,
        "next_cursor": next_cursor,
        "results": results,
    }, 200
    _timing()["build_resp_ms"] = round((time.perf_counter() - t_query) * 1000)
    return response

"""Grouped search: run search query, intersect with groups index, return groups."""

import json
import logging
import time

logger = logging.getLogger(__name__)

from core.files_core.groups_index import (
    get_groups_index_with_meta,
    schedule_background_rebuild,
    try_get_groups_index_fast,
)
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.query.builder import build_query_sql
from core.search_api.grouped_ids_cache import grouped_ids_cache
from core.search_api.search_params import has_search_conditions, parse_search_args
from core.services_core.db_api import get_readonly_db

_GROUP_RETURN_LIMIT = 2000

# Route-level TTL cache for /api/search-grouped/warm responses. Warm is a
# best-effort fire-and-forget call from the client, but it can occupy a DB
# read worker for 10+ seconds on cold CJK FTS-fallback searches. Caching the
# completion lets repeat warms (pagination, minor edits, re-renders) return
# instantly without re-entering the executor.
_WARM_RESPONSE_CACHE = SimpleTTLCache(ttl_seconds=30, max_entries=64)


def _load_matching_ids(con, p):
    has_conds = has_search_conditions(p)
    if not has_conds:
        return None, False

    cache_key = grouped_ids_cache.make_key(p)
    cached_hit, cached_ids = grouped_ids_cache.get(cache_key)
    if cached_hit:
        return cached_ids, True

    # 100K rows was overkill: groups index rarely contains more than ~30K
    # matchable IDs in practice, and the previous ceiling let a slow
    # LIKE fallback occupy a DB worker for tens of seconds.
    _GROUP_SEARCH_LIMIT = 30_000
    sql, params, _, _ = build_query_sql(
        p["tag_query"],
        p["artist"],
        p["from_date"],
        p["to_date"],
        p["in_prompt"],
        p["file_format"],
        p["format_exts"],
        p["sort_by"],
        _GROUP_SEARCH_LIMIT,
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
    id_sql = "SELECT f.id FROM files f" + sql.split("FROM files f", 1)[1]
    rows = con.execute(id_sql, params).fetchall()
    matching_ids = set(row[0] for row in rows)
    grouped_ids_cache.put(cache_key, matching_ids)
    return matching_ids, False


def _warm_cache_key(args: dict) -> str:
    """Stable key for the warm response cache.

    Mirrors the field set used by ``GroupedIdsCache.make_key`` plus the
    ``group_mode`` so distinct grouping requests don't collide.
    """
    p = parse_search_args(args)
    payload = {
        "ids": grouped_ids_cache.make_key(p),
        "group_mode": (args.get("group_mode") or "folder").strip(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def warm_response_cache_peek(args: dict):
    """Return cached warm response tuple ``(payload, status)`` if fresh."""
    return _WARM_RESPONSE_CACHE.peek(_warm_cache_key(args))


def warm_response_cache_invalidate() -> None:
    _WARM_RESPONSE_CACHE.invalidate()


def build_grouped_search_warm_response(args):
    """Warm grouped-search dependencies for the current search conditions."""
    t0 = time.perf_counter()
    cache_key = _warm_cache_key(args)
    cached = _WARM_RESPONSE_CACHE.peek(cache_key)
    if cached is not None:
        return cached
    t_key = time.perf_counter()
    p = parse_search_args(args)
    t_parse = time.perf_counter()
    con = get_readonly_db()
    t_con = time.perf_counter()
    try:
        _load_matching_ids(con, p)
        t_ids = time.perf_counter()
        # Non-blocking probe: only return groups index if memory or disk
        # cache is fresh. A full rebuild scan over the files table can take
        # 5-10 seconds on large libraries (200K+ rows) and used to occupy
        # a DB executor slot for the full duration. Now we hand the rebuild
        # off to a daemon thread and respond 202 immediately so the client
        # (and other DB requests) don't stall.
        fast = try_get_groups_index_fast(con)
        t_index = time.perf_counter()
        if fast is None:
            scheduled = schedule_background_rebuild()
            total_ms = int((t_index - t0) * 1000)
            try:
                from core.infra_core.debug_log import dlog
                dlog(
                    "search",
                    "grouped_warm.bg_rebuild",
                    ids_ms=int((t_ids - t_con) * 1000),
                    probe_ms=int((t_index - t_ids) * 1000),
                    total_ms=total_ms,
                    scheduled=scheduled,
                )
            except Exception:
                logger.debug("search step failed", exc_info=True)
            # Do NOT cache the 202 — we want the next warm to retry the
            # fast-path probe and pick up the rebuilt index.
            return {"status": "rebuilding"}, 202
        index_source = fast[1]
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    result = ({"status": "ok"}, 200)
    _WARM_RESPONSE_CACHE.put(cache_key, result)
    total_ms = int((t_index - t0) * 1000)
    if total_ms >= 1000:
        try:
            from core.infra_core.debug_log import dlog
            dlog(
                "search",
                "grouped_warm.slow",
                key_ms=int((t_key - t0) * 1000),
                parse_ms=int((t_parse - t_key) * 1000),
                con_ms=int((t_con - t_parse) * 1000),
                ids_ms=int((t_ids - t_con) * 1000),
                index_ms=int((t_index - t_ids) * 1000),
                index_source=index_source,
                total_ms=total_ms,
                has_conds=has_search_conditions(p),
            )
        except Exception:
            logger.debug("search step failed", exc_info=True)
    return result


def build_grouped_search_response(args):
    """Return folder/ZIP groups that intersect with search results.

    Runs the search query without LIMIT (ID-only) and intersects the
    resulting IDs with the pre-computed groups index.  Returns a list
    of group summaries suitable for rendering as container cards.
    """
    perf_enabled = str(args.get("perf") or "").strip() == "1"
    t0 = time.perf_counter()
    p = parse_search_args(args)
    t_parse = time.perf_counter()
    group_mode = (args.get("group_mode") or "folder").strip()
    if group_mode not in ("folder", "zip", "archive"):
        group_mode = "folder"
    # "zip" is kept as alias for backward compatibility
    if group_mode == "zip":
        group_mode = "archive"

    con = get_readonly_db()
    try:
        matching_ids, ids_cache_hit = _load_matching_ids(con, p)
        t_search = time.perf_counter()

        index, index_source = get_groups_index_with_meta(con)
        t_index = time.perf_counter()
    except Exception as e:
        return {
            "status": "error",
            "groups": [],
            "total_files": 0,
            "total_groups": 0,
            "message": str(e),
        }, 500

    source_groups = index.get("folders" if group_mode == "folder" else "zips", {})
    # Also check "archives" key for forward compat
    if group_mode == "archive" and not source_groups:
        source_groups = index.get("archives", {})
    result_groups = []

    for key, entry in source_groups.items():
        all_ids = entry.get("ids", [])
        filtered = [fid for fid in all_ids if fid in matching_ids] if matching_ids is not None else all_ids

        if not filtered:
            continue
        # For folders, require 2+ matching members
        if group_mode == "folder" and len(filtered) < 2:
            continue

        # Use filtered IDs for representative thumbnails so the card
        # previews match the images that will open in the modal.
        reps = filtered[:8]

        result_groups.append({
            "key": key,
            "type": "archive" if key.startswith(("zip:", "archive:")) else "folder",
            "label": entry.get("label", ""),
            "count": len(all_ids),
            "matchCount": len(filtered),
            "reps": reps,
            "memberIds": filtered,
            "max_mtime": entry.get("max_mtime", 0),
        })
    t_filter = time.perf_counter()

    # Sort groups by newest first (mtime descending)
    result_groups.sort(key=lambda g: g.get("max_mtime", 0), reverse=True)
    t_sort = time.perf_counter()

    total_files = sum(g["matchCount"] for g in result_groups)
    total_groups = len(result_groups)
    limited = total_groups > _GROUP_RETURN_LIMIT
    if limited:
        result_groups = result_groups[:_GROUP_RETURN_LIMIT]
    t_limit = time.perf_counter()

    payload = {
        "status": "ok",
        "groups": result_groups,
        "total_files": total_files,
        "total_groups": total_groups,
        "returned_groups": len(result_groups),
        "limited": limited,
        "group_mode": group_mode,
    }
    total_ms = round((t_limit - t0) * 1000)
    if perf_enabled:
        payload["perf"] = {
            "parse_ms": round((t_parse - t0) * 1000),
            "search_ids_ms": round((t_search - t_parse) * 1000),
            "index_ms": round((t_index - t_search) * 1000),
            "filter_ms": round((t_filter - t_index) * 1000),
            "sort_ms": round((t_sort - t_filter) * 1000),
            "limit_ms": round((t_limit - t_sort) * 1000),
            "total_ms": total_ms,
            "ids_cache_hit": 1 if ids_cache_hit else 0,
            "no_conditions": 1 if matching_ids is None else 0,
            "index_source": index_source,
        }
    if total_ms >= 50:
        logger.debug(
            "grouped q=%r total=%dms ids=%dms filter=%dms groups=%d files=%d cache=%s",
            (p.get("tag_query") or "")[:40],
            total_ms,
            round((t_search - t_parse) * 1000),
            round((t_filter - t_index) * 1000),
            total_groups,
            total_files,
            "hit" if ids_cache_hit else "miss",
        )
    return payload, 200

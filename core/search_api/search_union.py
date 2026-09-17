"""UNION search: merge results from multiple collections (smart + manual)."""

import json
import logging
import random
from typing import Any

from core.extensions_core.service_registry import ServiceRegistry
from core.infra_core.api_params import clamp_sqlite_int
from core.query.builder import build_query_sql
from core.search_api.search_params import parse_search_args
from core.search_api.search_rows import rows_to_results
from core.services_core.db_api import get_readonly_db

logger = logging.getLogger(__name__)

_SQLITE_PARAM_CHUNK = 900


def _chunks(items: list[int], size: int | None = None):
    size = _SQLITE_PARAM_CHUNK if size is None else size
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _collect_smart_ids(con, query_json: str) -> set[int]:
    """Run a smart collection's saved query and return matching file IDs."""
    try:
        raw = json.loads(query_json)
    except (json.JSONDecodeError, TypeError):
        return set()

    p = parse_search_args(raw)
    sql, params, _, _ = build_query_sql(
        p["tag_query"],
        p["artist"],
        p["from_date"],
        p["to_date"],
        p["in_prompt"],
        p["file_format"],
        p["format_exts"],
        p["sort_by"],
        50000,
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
        ai_analyzed=p.get("ai_analyzed", False),
        has_tags=p.get("has_tags", False),
        has_annotation=p.get("has_annotation", False),
        has_sweep=p.get("has_sweep", False),
        con=con,
    )
    # Rewrite to ID-only query for efficiency
    id_sql = "SELECT f.id FROM files f" + sql.split("FROM files f", 1)[1]
    id_sql = id_sql.rsplit("LIMIT", 1)[0]
    id_params = params[:-2]
    rows = con.execute(id_sql, id_params).fetchall()
    return {row[0] for row in rows}


def _collect_manual_ids(con, collection_id: int) -> set[int]:
    """Return file IDs belonging to a manual (favorites) collection."""
    rows = con.execute(
        "SELECT fav.file_id FROM favorites fav "
        "JOIN files f ON f.id=fav.file_id AND f.is_deleted=0 "
        "WHERE fav.collection_id=?",
        (collection_id,),
    ).fetchall()
    return {row[0] for row in rows}


def _folder_sort_key(path: str, roots: list[dict[str, Any]]) -> tuple[int, str]:
    norm = (path or "").replace("\\", "/")
    for i, root in enumerate(roots):
        root_path = str(root.get("path", "")).replace("\\", "/")
        if root_path and norm.startswith(root_path):
            return i, norm
    return 9999, norm


def _load_sort_keys(con, ids: set[int], sort_by: str) -> list[dict[str, Any]]:
    """Load only columns needed for sorting, chunked to avoid huge IN clauses."""
    id_list = list(ids)
    rows: list[dict[str, Any]] = []
    needs_rating = sort_by in ("rating_desc", "rating_asc")
    select_rating = ", rt.rating AS rating" if needs_rating else ", NULL AS rating"
    rating_join = "LEFT JOIN file_ratings rt ON rt.file_id=f.id " if needs_rating else ""

    for chunk in _chunks(id_list):
        placeholders = ",".join("?" * len(chunk))
        chunk_rows = con.execute(
            "SELECT f.id, f.path, f.mtime "
            f"{select_rating} "
            "FROM files f "
            f"{rating_join}"
            f"WHERE f.id IN ({placeholders}) AND f.is_deleted=0",
            chunk,
        ).fetchall()
        rows.extend(dict(row) for row in chunk_rows)
    return rows


def _sort_union_ids(rows: list[dict[str, Any]], sort_by: str) -> list[int]:
    if sort_by == "random":
        shuffled = list(rows)
        random.shuffle(shuffled)
        return [int(row["id"]) for row in shuffled]
    if sort_by == "date_old":
        rows.sort(key=lambda row: (row["mtime"] or 0, row["id"] or 0))
    elif sort_by == "path":
        rows.sort(key=lambda row: (row["path"] or "", row["id"] or 0))
    elif sort_by == "folder":
        import tagdb_tool

        roots = tagdb_tool.load_config_json(None).get("scan_roots", [])
        rows.sort(key=lambda row: (*_folder_sort_key(row["path"] or "", roots), row["id"] or 0))
    elif sort_by == "rating_asc":
        rows.sort(key=lambda row: (row["rating"] is None, row["rating"] if row["rating"] is not None else 0, -(row["mtime"] or 0), -(row["id"] or 0)))
    elif sort_by == "rating_desc":
        rows.sort(key=lambda row: (row["rating"] is None, -(row["rating"] if row["rating"] is not None else 0), -(row["mtime"] or 0), -(row["id"] or 0)))
    else:
        rows.sort(key=lambda row: (-(row["mtime"] or 0), -(row["id"] or 0)))
    return [int(row["id"]) for row in rows]


def _load_result_rows(con, page_ids: list[int]) -> list[dict[str, Any]]:
    if not page_ids:
        return []
    by_id: dict[int, dict[str, Any]] = {}
    for chunk in _chunks(page_ids):
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            "SELECT f.id, f.path, f.mtime, f.meta_source, "
            "tm.raw_prompt, tm.raw_negative "
            "FROM files f "
            "LEFT JOIN templates tm ON tm.file_id=f.id "
            f"WHERE f.id IN ({placeholders}) AND f.is_deleted=0",
            chunk,
        ).fetchall()
        by_id.update({int(row["id"]): dict(row) for row in rows})
    return [by_id[file_id] for file_id in page_ids if file_id in by_id]


def build_union_search_response(data: dict) -> tuple[dict[str, Any], int]:
    """Merge results from multiple collections via two-pass ID aggregation.

    Input: { collection_ids: [int], sort: str, limit: int, offset: int }
    """
    collection_ids = data.get("collection_ids", [])
    if not isinstance(collection_ids, list) or not collection_ids:
        return {"status": "error", "message": "collection_ids list required"}, 400

    sort_by = data.get("sort", "date")
    limit = min(int(data.get("limit", 200)), 5000)
    offset = max(int(data.get("offset", 0)), 0)

    con = get_readonly_db()
    try:
        # Load collection metadata (ServiceRegistry fallback)
        _list_collections = ServiceRegistry.get("favorites.list_collections")
        if _list_collections is None:
            return {"status": "error", "message": "favorites extension not available"}, 503
        all_colls = _list_collections()
        coll_map = {c["id"]: c for c in all_colls}

        # Pass 1: collect IDs from each collection
        merged_ids: set[int] = set()
        for cid in collection_ids:
            cid = clamp_sqlite_int(int(cid))
            coll = coll_map.get(cid)
            if not coll:
                continue
            if coll["is_smart"] and coll["query_json"]:
                merged_ids |= _collect_smart_ids(con, coll["query_json"])
            else:
                merged_ids |= _collect_manual_ids(con, cid)

        if not merged_ids:
            return {
                "status": "ok",
                "total": 0,
                "total_count": 0,
                "results": [],
                "has_more": False,
            }, 200

        # Pass 2: sort IDs using chunked key queries, then load full rows only
        # for the requested page. This avoids giant ``WHERE id IN (...)`` SQL
        # and SQLite variable-limit failures on large UNION collections.
        sort_rows = _load_sort_keys(con, merged_ids, sort_by)
        sorted_ids = _sort_union_ids(sort_rows, sort_by)
        page_ids = sorted_ids[offset:offset + limit]
        rows = _load_result_rows(con, page_ids)
    except Exception as e:
        logger.exception("UNION search failed")
        return {"status": "error", "message": str(e)}, 500

    results = rows_to_results(rows)
    total_count = len(merged_ids)

    return {
        "status": "ok",
        "total": len(results),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(results)) < total_count,
        "results": results,
    }, 200

"""Request parsing and SQL assembly helpers for search responses."""

from __future__ import annotations

import datetime as _dt
import time

from core.query.builder import build_query_sql
from core.search_api.search_cursor import cursor_to_keyset, cursor_to_offset, decode_cursor
from core.search_api.search_fts_strategies import (
    _build_char_fts_first_sql,
    _build_prompt_fts_first_sql,
    _can_use_char_fts_first_path,
    _can_use_prompt_fts_first_path,
)
from core.search_api.search_params import parse_search_args


def parse_request(args):
    """Parse request args, decode cursor, and validate date strings."""
    perf_enabled = str(args.get("perf") or "").strip() == "1"
    defer_count = str(args.get("defer_count") or "1").strip() != "0"
    t0 = time.perf_counter()
    p = parse_search_args(args)
    t_parse = time.perf_counter()

    cursor_str = p.get("cursor", "")
    cursor_data_raw = decode_cursor(cursor_str) if cursor_str else None
    keyset_info = None
    if cursor_data_raw:
        if cursor_data_raw.get("s") != p["sort_by"]:
            cursor_data_raw = None
        else:
            keyset_info = cursor_to_keyset(cursor_data_raw)
            p["offset"] = 0 if keyset_info else cursor_to_offset(cursor_data_raw)

    date_errors = []
    for label, val in [("from_date", p["from_date"]), ("to_date", p["to_date"])]:
        if val:
            try:
                _dt.date.fromisoformat(val)
            except ValueError:
                date_errors.append(f"Invalid {label}: {val}")
    if date_errors:
        payload = {
            "status": "error",
            "total": 0,
            "total_count": 0,
            "results": [],
            "message": "; ".join(date_errors),
        }
        return perf_enabled, defer_count, t0, t_parse, p, keyset_info, (payload, 400)
    return perf_enabled, defer_count, t0, t_parse, p, keyset_info, None


def validate_collection(con, collection_id: int):
    """Validate collection existence for search routes."""
    if collection_id > 0 and not con.execute("SELECT 1 FROM collections WHERE id=?", (collection_id,)).fetchone():
        return {
            "status": "error",
            "total": 0,
            "total_count": 0,
            "results": [],
            "message": "Collection not found",
        }, 404
    return None


def build_search_sql_bundle(p: dict, keyset_info, con):
    """Build the SQL tuple for the current search path."""
    if _can_use_prompt_fts_first_path(p, keyset_info):
        return _build_prompt_fts_first_sql(p, con)
    if _can_use_char_fts_first_path(p, keyset_info, con):
        return _build_char_fts_first_sql(p, con)
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
        offset=p["offset"],
        in_path=p["in_path"],
        min_width=p["min_width_int"],
        max_width=p["max_width_int"],
        min_height=p["min_height_int"],
        max_height=p["max_height_int"],
        or_tags=p["or_tags"],
        wd_model=p.get("wd_model"),
        also_search_path=p["also_path"],
        fav_only=p.get("fav_only", False),
        collection_id=p.get("collection_id", 0),
        min_rating=p.get("min_rating"),
        max_rating=p.get("max_rating"),
        ai_analyzed=p.get("ai_analyzed", False),
        has_tags=p.get("has_tags", False),
        has_annotation=p.get("has_annotation", False),
        has_sweep=p.get("has_sweep", False),
        cursor_data=keyset_info,
        con=con,
    )

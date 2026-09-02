"""In-memory cache path for search responses."""

from __future__ import annotations

import time
from typing import Any

from core.search_api.file_meta_cache import can_use_cache, get_last_ensure_timing
from core.search_api.file_meta_cache_query import get_last_qr_timing
from core.search_api.file_meta_cache_rules import get_last_filter_timing
from core.search_api.search_cache_query import _try_cache_query, get_last_timing
from core.search_api.search_response_helpers import backfill_prompts, perf_stats
from core.search_api.search_response_logging import dlog_fast_path_slow


def try_memory_cache_response(
    p: dict[str, Any],
    con: Any,
    keyset_info: dict[str, Any] | None,
    *,
    perf_enabled: bool,
    t0: float,
    t_parse: float,
) -> tuple[tuple[dict[str, Any], int] | None, float, float]:
    if not can_use_cache(p):
        return None, t_parse, t_parse

    t_cache_start = time.perf_counter()
    cache_result = _try_cache_query(p, con, keyset_info)
    if cache_result is None:
        return None, t_cache_start, time.perf_counter()

    payload, status = cache_result
    t_after_cache_lookup = time.perf_counter()
    if status == 200:
        backfill_prompts(payload["results"], con)
    t_after_backfill = time.perf_counter()
    _log_memory_cache_path(
        p,
        payload,
        status,
        t0=t0,
        t_cache_start=t_cache_start,
        t_after_cache_lookup=t_after_cache_lookup,
        t_after_backfill=t_after_backfill,
    )
    if perf_enabled and status == 200:
        now = time.perf_counter()
        payload["perf"] = perf_stats(
            t0=t0,
            t_parse=t_parse,
            t_cache_start=t_cache_start,
            t_cache_end=now,
            t_build_end=now,
            t_sql_start=now,
            t_sql_end=now,
            t_rows=now,
            t_count=now,
            cache_hit=1,
        )
    return cache_result, t_cache_start, t_after_backfill


def _log_memory_cache_path(
    p: dict[str, Any],
    payload: dict[str, Any],
    status: int,
    *,
    t0: float,
    t_cache_start: float,
    t_after_cache_lookup: float,
    t_after_backfill: float,
) -> None:
    ensure = get_last_ensure_timing()
    cache_t = get_last_timing()
    qr = get_last_qr_timing()
    ft = get_last_filter_timing()
    dlog_fast_path_slow(
        "memory_cache",
        t0,
        p,
        cache_lookup_ms=round((t_after_cache_lookup - t_cache_start) * 1000),
        backfill_ms=round((t_after_backfill - t_after_cache_lookup) * 1000),
        ensure_sig_ms=ensure["sig_ms"],
        ensure_lock_ms=ensure["lock_ms"],
        ensure_build_ms=ensure["build_ms"],
        cache_query_ms=cache_t["query_ms"],
        cache_build_resp_ms=cache_t["build_resp_ms"],
        qr_source_ms=qr["source_ms"],
        qr_filter_ms=qr["filter_ms"],
        qr_sort_ms=qr["sort_ms"],
        qr_slice_ms=qr["slice_ms"],
        qr_dict_ms=qr["dict_build_ms"],
        qr_size=qr["source_size"],
        qr_needs_filter=qr["needs_filter"],
        qr_file_format=qr["file_format"],
        qr_format_exts=qr["format_exts"],
        ft_model_ms=ft["model_ms"],
        ft_ts_ms=ft["ts_ms"],
        ft_path_ms=ft["path_ms"],
        ft_wh_ms=ft["wh_ms"],
        ft_model_active=ft["model_active"],
        ft_ts_active=ft["ts_active"],
        ft_path_active=ft["path_active"],
        ft_wh_active=ft["wh_active"],
        ft_model_value=ft["model_filter_value"],
        ft_input=ft["input_size"],
        ft_after_model=ft["after_model"],
        ft_after_ts=ft["after_ts"],
        ft_after_path=ft["after_path"],
        ft_after_wh=ft["after_wh"],
        status=status,
        hits=len(payload.get("results", [])) if isinstance(payload, dict) else None,
    )

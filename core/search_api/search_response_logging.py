"""Debug logging helpers for search responses."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def dlog_fast_path_slow(path_kind: str, t0: float, p: dict[str, Any], **extra: Any) -> None:
    total_ms = round((time.perf_counter() - t0) * 1000)
    if total_ms < 300:
        return
    try:
        from core.infra_core.debug_log import dlog

        dlog(
            "search",
            "fast_path_slow",
            path_kind=path_kind,
            total_ms=total_ms,
            tag_q=(p.get("tag_query") or "")[:80],
            in_path=(p.get("in_path") or "")[:80],
            in_prompt=(p.get("in_prompt") or "")[:80],
            also_path=p.get("also_path"),
            sort=p.get("sort_by"),
            offset=p.get("offset"),
            limit=p.get("limit"),
            **{k: v for k, v in extra.items() if v is not None},
        )
    except Exception:
        logger.debug("search step failed", exc_info=True)


def dlog_slow_query(
    con: Any,
    *,
    sql: str,
    params: list[Any],
    p: dict[str, Any],
    results: list[dict[str, Any]],
    t0: float,
    t_build_end: float,
    t_sql_end: float,
    t_rows: float,
    t_count: float,
) -> int:
    total_ms = round((time.perf_counter() - t0) * 1000)
    if total_ms < 300:
        return total_ms
    try:
        plan_rows = con.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        plan_text = " | ".join(f"{r[0]}:{r[1]}:{r[2]} {r[3]}" for r in plan_rows)
    except Exception as exc:
        plan_text = f"<plan-error: {exc}>"
    try:
        from core.infra_core.debug_log import dlog

        dlog(
            "search",
            "slow_query",
            total_ms=total_ms,
            query_ms=round((t_sql_end - t_build_end) * 1000),
            rows_ms=round((t_rows - t_sql_end) * 1000),
            count_ms=round((t_count - t_rows) * 1000),
            hits=len(results),
            tag_q=(p.get("tag_query") or "")[:80],
            in_path=(p.get("in_path") or "")[:80],
            in_prompt=(p.get("in_prompt") or "")[:80],
            also_path=p.get("also_path"),
            sort=p.get("sort_by"),
            sql=sql[:800],
            params=str(params)[:300],
            plan=plan_text[:800],
        )
    except Exception:
        logger.debug("search step failed", exc_info=True)
    return total_ms

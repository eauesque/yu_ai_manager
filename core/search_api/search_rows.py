"""Search API row/result conversion helpers."""

import logging

from core.prompt import parse_a1111_prompt
from core.search_api.count_cache import count_cache

logger = logging.getLogger(__name__)


def rows_to_results(rows):
    results = []
    for row in rows:
        raw_prompt = row["raw_prompt"]
        raw_negative = row["raw_negative"]

        # Fast path: if templates JOIN was skipped (NULL), avoid parsing
        if raw_prompt is None:
            results.append({
                "id": row["id"],
                "path": row["path"],
                "mtime": row["mtime"],
                "meta_source": row["meta_source"],
                "positive": "",
                "negative": "",
            })
            continue

        raw_prompt = raw_prompt or ""
        raw_negative = raw_negative or ""
        positive_only = raw_prompt
        if raw_prompt and ("Steps:" in raw_prompt or "Negative prompt:" in raw_prompt):
            parsed = parse_a1111_prompt(raw_prompt)
            positive_only = parsed["positive"]
            if not raw_negative and parsed["negative"]:
                raw_negative = parsed["negative"]
        results.append(
            {
                "id": row["id"],
                "path": row["path"],
                "mtime": row["mtime"],
                "meta_source": row["meta_source"],
                "positive": positive_only,
                "negative": raw_negative,
            }
        )
    return results


_APPROX_COUNT_THRESHOLD = 100_000  # Use approximate COUNT above this threshold


def build_total_count(
    con, count_sql: str, count_params, limit: int, offset: int, result_count: int,
) -> int:
    """Compute total matching rows using the pre-built COUNT query.

    BUG-28: The count_sql/count_params are built *before* cursor injection
    so that total_count is stable across all pages.

    Large dataset optimization:
    - Return immediately on cache hit.
    - For unfiltered (simple total COUNT) queries, retrieve approximate value from sqlite_stat1.
    - For filtered queries, execute an exact COUNT and cache the result.
    """
    total_count = result_count + offset
    has_more = result_count >= limit
    if has_more:
        cached = count_cache.get(count_sql, count_params)
        if cached is not None:
            return cached
        try:
            # If the only filter is is_deleted=0, get approximate count from sqlite_stat1
            if _is_simple_count(count_sql, count_params):
                approx = _approx_count_from_stat1(con)
                if approx is not None and approx > _APPROX_COUNT_THRESHOLD:
                    count_cache.put(count_sql, count_params, approx)
                    return approx

            # 280K files optimization: execute filtered COUNT with timeout
            # LIMIT-based estimation: result_count rows definitely exist, so
            # guarantee at least offset + limit * 2 while attempting exact COUNT
            row = con.execute(count_sql, count_params).fetchone()
            if row:
                total_count = row[0]
                count_cache.put(count_sql, count_params, total_count)
        except Exception as exc:
            logger.debug("Failed to compute total_count: %s", exc)
            # Return estimated value on COUNT failure (UI shows "N+ results")
            total_count = result_count + offset + limit
    return total_count


def _is_simple_count(sql: str, params) -> bool:
    """Determine if the filter condition is a simple COUNT with only is_deleted=0."""
    # No parameters in WHERE clause, only is_deleted=0
    return not params and "is_deleted=0" in sql and sql.count("AND") == 0


def _approx_count_from_stat1(con) -> int | None:
    """Retrieve approximate row count for the files table from sqlite_stat1.

    If ANALYZE has been run, estimates the row count from idx_files_deleted_mtime stat.
    """
    try:
        row = con.execute(
            "SELECT stat FROM sqlite_stat1 WHERE tbl='files' AND idx='idx_files_deleted_mtime' LIMIT 1"
        ).fetchone()
        if row and row[0]:
            # stat format: "total_rows avg_rows/distinct_values" (e.g. "900000 450000")
            parts = row[0].split()
            if parts:
                return int(parts[0])
    except Exception:
        logger.debug("search step failed", exc_info=True)
    return None

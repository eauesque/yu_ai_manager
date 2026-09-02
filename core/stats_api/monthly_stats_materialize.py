"""Materialized cache for monthly statistics.

Pre-computes expensive aggregations like COUNT(DISTINCT tag_id) for 280K file
environments and stores them in the monthly_stats_cache table.

Usage:
- story.py: replacement for _monthly_unique_tags()
- monthly_report.py: replacement for unique_tags
- basic.py: replacement for COUNT(DISTINCT ft.tag_id)
"""

import json
import logging
import time

from core.stats_api.filters import ai_image_where
from core.timezone_core.tz_helper import tz_sqlite_modifier

logger = logging.getLogger(__name__)


def refresh_monthly_stats(con) -> int:
    """Recalculate statistics for all months and save to monthly_stats_cache.

    Returns:
        Number of months updated.
    """
    where = ai_image_where("f")
    now_ts = int(time.time())
    count = 0

    # Calculate monthly file counts + unique tag counts in bulk
    # File counts (lightweight)
    file_rows = con.execute(
        f"""SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as month,
                   COUNT(*) as cnt
            FROM files f WHERE {where}
            GROUP BY month ORDER BY month"""
    )

    for r in file_rows:
        if not r[0]:
            continue
        _upsert(con, r[0], "file_count", str(r[1]), now_ts)
        count += 1

    # Unique tag counts (expensive -- this is why caching matters)
    tag_rows = con.execute(
        f"""SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as month,
                   COUNT(DISTINCT ft.tag_id) as cnt
            FROM files f
            JOIN file_tags ft ON ft.file_id = f.id
            WHERE {where}
            GROUP BY month ORDER BY month"""
    )

    for r in tag_rows:
        if not r[0]:
            continue
        _upsert(con, r[0], "unique_tags", str(r[1]), now_ts)

    # Source distribution
    src_rows = con.execute(
        f"""SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as month,
                   COALESCE(f.meta_source, 'other') as src,
                   COUNT(*) as cnt
            FROM files f WHERE {where}
            GROUP BY month, src ORDER BY month"""
    )

    src_data: dict[str, dict[str, int]] = {}
    for r in src_rows:
        if not r[0]:
            continue
        src_data.setdefault(r[0], {})[r[1]] = r[2]

    for month, sources in src_data.items():
        _upsert(con, month, "sources", json.dumps(sources), now_ts)

    # Total unique tag count (for basic stats)
    total_tag_count = con.execute(
        f"""SELECT COUNT(DISTINCT ft.tag_id)
            FROM file_tags ft
            JOIN files f ON f.id=ft.file_id
            WHERE {where}"""
    ).fetchone()[0]
    _upsert(con, "_total", "unique_tag_count", str(total_tag_count), now_ts)

    con.commit()
    logger.info("monthly_stats_cache refreshed: %d months", count)
    return count


def get_cached_monthly_stat(con, month: str, stat_key: str) -> str | None:
    """Retrieve a monthly statistics value from cache."""
    try:
        row = con.execute(
            "SELECT stat_value FROM monthly_stats_cache WHERE month=? AND stat_key=?",
            (month, stat_key),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def get_cached_total_tag_count(con) -> int | None:
    """Retrieve the total unique tag count from cache."""
    val = get_cached_monthly_stat(con, "_total", "unique_tag_count")
    return int(val) if val is not None else None


def is_cache_fresh(con, max_age_seconds: int = 3600) -> bool:
    """Check whether the cache is fresh (default: 1 hour)."""
    try:
        row = con.execute(
            "SELECT MAX(updated_at) FROM monthly_stats_cache"
        ).fetchone()
        if row and row[0]:
            return (int(time.time()) - row[0]) < max_age_seconds
    except Exception:
        logger.debug("stats step failed", exc_info=True)
    return False


def _upsert(con, month: str, stat_key: str, stat_value: str, now_ts: int) -> None:
    """Update the cache using conflict-aware upsert."""
    con.execute(
        """INSERT INTO monthly_stats_cache
           (month, stat_key, stat_value, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(month, stat_key) DO UPDATE SET
             stat_value=excluded.stat_value,
             updated_at=excluded.updated_at""",
        (month, stat_key, stat_value, now_ts),
    )

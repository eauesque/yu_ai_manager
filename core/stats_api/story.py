"""Story stats builder."""

import datetime as _dt
import logging
from importlib import import_module

# Import from relocated stats extension
_stats_insights = import_module("extensions.builtin_stats.core_impl.stats_insights")
detect_story_events = _stats_insights.detect_story_events
from core.stats_api.filters import ai_image_where
from core.timezone_core.tz_helper import configured_now, local_date_range_unix, tz_sqlite_modifier

logger = logging.getLogger(__name__)


def _on_this_day(con, where: str):
    """Return the number of images created on this day one year ago."""
    now = configured_now()
    try:
        one_year_ago = now.date().replace(year=now.year - 1)
    except ValueError:
        # 2/29 → 2/28
        one_year_ago = now.date().replace(year=now.year - 1, day=28)
    day_start, day_end = local_date_range_unix(one_year_ago)
    row = con.execute(
        f"SELECT COUNT(*) FROM files f WHERE {where} AND f.mtime >= ? AND f.mtime <= ?",
        (day_start, day_end),
    ).fetchone()
    return {
        "date": one_year_ago.strftime("%Y-%m-%d"),
        "count": row[0] if row else 0,
    }


def _streak_days(con, where: str):
    """Calculate the recent consecutive usage streak in days."""
    today = configured_now().date()
    rows = con.execute(
        f"""SELECT DISTINCT date(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r}) as d
            FROM files f WHERE {where}
            ORDER BY d DESC LIMIT 400"""
    )
    dates = set()
    for r in rows:
        try:
            dates.add(_dt.date.fromisoformat(r[0]))
        except (ValueError, TypeError):
            continue
    if not dates:
        return 0
    streak = 0
    check = today
    while check in dates:
        streak += 1
        check -= _dt.timedelta(days=1)
    # If no images today, count from yesterday
    if streak == 0:
        check = today - _dt.timedelta(days=1)
        while check in dates:
            streak += 1
            check -= _dt.timedelta(days=1)
    return streak


def _monthly_file_counts(con, where: str):
    """Return monthly file counts. {month: count}"""
    rows = con.execute(
        f"""SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as month,
                   COUNT(*) as cnt
            FROM files f WHERE {where}
            GROUP BY month ORDER BY month"""
    )
    return {r[0]: r[1] for r in rows if r[0]}


def _monthly_unique_tags(con, where: str):
    """Return monthly unique tag counts. {month: count}

    280K optimization: reads from monthly_stats_cache first, falls back to full query if unavailable.
    """
    from core.stats_api.monthly_stats_materialize import is_cache_fresh
    if is_cache_fresh(con, max_age_seconds=7200):
        try:
            rows = con.execute(
                "SELECT month, stat_value FROM monthly_stats_cache WHERE stat_key='unique_tags'"
            )
            cached = {r[0]: int(r[1]) for r in rows}
            if cached:
                return cached
        except Exception:
            logger.debug("stats step failed", exc_info=True)

    rows = con.execute(
        f"""SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as month,
                   COUNT(DISTINCT ft.tag_id) as cnt
            FROM files f
            JOIN file_tags ft ON ft.file_id = f.id
            WHERE {where}
            GROUP BY month ORDER BY month"""
    )
    return {r[0]: r[1] for r in rows if r[0]}


def _monthly_sources(con, where: str):
    """Return monthly meta_source distribution. {month: {source: count}}"""
    rows = con.execute(
        f"""SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as month,
                   COALESCE(f.meta_source, 'other') as src,
                   COUNT(*) as cnt
            FROM files f WHERE {where}
            GROUP BY month, src ORDER BY month"""
    )
    result = {}
    for r in rows:
        if not r[0]:
            continue
        result.setdefault(r[0], {})[r[1]] = r[2]
    return result


def build_story_stats(con):
    where = ai_image_where("f")

    monthly_counts = _monthly_file_counts(con, where)
    monthly_tags = _monthly_unique_tags(con, where)
    monthly_sources = _monthly_sources(con, where)

    # Build timeline dict for backward compatibility and event detection
    timeline = {}
    for month, count in monthly_counts.items():
        timeline[month] = {
            "count": count,
            "unique_tags": monthly_tags.get(month, 0),
            "sources": monthly_sources.get(month, {}),
        }

    on_this_day = _on_this_day(con, where)
    streak = _streak_days(con, where)

    return {
        "timeline": timeline,
        "story": detect_story_events(timeline),
        "on_this_day": on_this_day,
        "streak_days": streak,
    }

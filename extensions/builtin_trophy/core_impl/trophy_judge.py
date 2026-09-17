"""Trophy judgement logic -- evaluates achievement conditions for all categories."""

import logging
import sqlite3

from .trophy_definitions import (
    DIVERSITY_DEFS,
    HIDDEN_DEFS,
    MILESTONE_DEFS,
    SOURCE_DEFS,
    STREAK_DEFS,
)
from .trophy_store import award_trophy, is_achieved

logger = logging.getLogger(__name__)

# Primary values of meta_source (excluding unknown)
_KNOWN_SOURCES = {"a1111_png", "a1111_webp", "novelai_v4_png", "novelai_v4_webp",
                   "comfy_png", "comfy_webm"}


def judge_all(
    con: sqlite3.Connection,
    month_str: str,
    cumul_before: int,
    cumul_after: int,
    daily_counts: list[dict],
    sources: dict[str, int],
    *,
    unique_tags_cumul: int | None = None,
) -> list[dict]:
    """Judge trophies for all categories and record new achievements in DB.

    Returns:
        List of achieved trophies (is_new=True: newly achieved this time).
    """
    results: list[dict] = []

    # --- Milestones ---
    for d in MILESTONE_DEFS:
        threshold = _milestone_threshold(d.trophy_type)
        if threshold is None:
            continue
        already = is_achieved(con, d.trophy_type)
        if not already and cumul_before < threshold <= cumul_after:
            award_trophy(con, d.trophy_type, achieved_month=month_str)
            results.append(_trophy_dict(d, month_str, is_new=True))
        elif already:
            results.append(_trophy_dict(d, month_str, is_new=False))

    # --- Streaks ---
    max_streak = _calc_max_streak(daily_counts)
    for d in STREAK_DEFS:
        threshold = _streak_threshold(d.trophy_type)
        if threshold is None:
            continue
        already = is_achieved(con, d.trophy_type)
        if not already and max_streak >= threshold:
            award_trophy(con, d.trophy_type, achieved_month=month_str,
                         metadata={"streak_days": max_streak})
            results.append(_trophy_dict(d, month_str, is_new=True))
        elif already:
            results.append(_trophy_dict(d, month_str, is_new=False))

    # --- Tag diversity ---
    if unique_tags_cumul is None:
        unique_tags_cumul = _count_unique_tags(con)
    for d in DIVERSITY_DEFS:
        threshold = _diversity_threshold(d.trophy_type)
        if threshold is None:
            continue
        already = is_achieved(con, d.trophy_type)
        if not already and unique_tags_cumul >= threshold:
            award_trophy(con, d.trophy_type, achieved_month=month_str,
                         metadata={"unique_tags": unique_tags_cumul})
            results.append(_trophy_dict(d, month_str, is_new=True))
        elif already:
            results.append(_trophy_dict(d, month_str, is_new=False))

    # --- Sources ---
    for d in SOURCE_DEFS:
        already = is_achieved(con, d.trophy_type)
        if not already:
            used_sources = {s for s in sources if s in _KNOWN_SOURCES}
            if used_sources and used_sources == _KNOWN_SOURCES:
                award_trophy(con, d.trophy_type, achieved_month=month_str,
                             metadata={"sources": sorted(used_sources)})
                results.append(_trophy_dict(d, month_str, is_new=True))
        elif already:
            results.append(_trophy_dict(d, month_str, is_new=False))

    # --- Hidden trophies ---
    _judge_hidden(con, month_str, daily_counts, results)

    return results


# ------------------------------------------------------------------ helpers


def _trophy_dict(d, month_str: str, *, is_new: bool) -> dict:
    return {
        "type": d.trophy_type,
        "title": d.title,
        "tier": d.tier,
        "category": d.category,
        "is_new": is_new,
    }


def _milestone_threshold(trophy_type: str) -> int | None:
    mapping = {
        "milestone_100": 100, "milestone_500": 500,
        "milestone_1k": 1000, "milestone_5k": 5000,
        "milestone_10k": 10000, "milestone_50k": 50000,
        "milestone_100k": 100000,
    }
    return mapping.get(trophy_type)


def _streak_threshold(trophy_type: str) -> int | None:
    mapping = {"streak_7": 7, "streak_30": 30, "streak_365": 365}
    return mapping.get(trophy_type)


def _diversity_threshold(trophy_type: str) -> int | None:
    mapping = {"tags_100": 100, "tags_500": 500, "tags_1000": 1000}
    return mapping.get(trophy_type)


def _calc_max_streak(daily_counts: list[dict]) -> int:
    """Calculate max consecutive days from daily_counts (ascending date order)."""
    if not daily_counts:
        return 0
    import datetime
    dates: list[datetime.date] = []
    for dc in daily_counts:
        try:
            dates.append(datetime.date.fromisoformat(dc["date"]))
        except (ValueError, KeyError):
            continue
    if not dates:
        return 0
    dates.sort()
    max_s = cur_s = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            cur_s += 1
            if cur_s > max_s:
                max_s = cur_s
        else:
            cur_s = 1
    return max_s


def _count_unique_tags(con: sqlite3.Connection) -> int:
    """Return the number of unique tags in the entire DB."""
    row = con.execute(
        "SELECT COUNT(DISTINCT t.tag) FROM tags t "
        "JOIN file_tags ft ON ft.tag_id = t.id "
        "JOIN files f ON f.id = ft.file_id WHERE f.is_deleted=0"
    ).fetchone()
    return row[0] if row else 0


def _judge_hidden(
    con: sqlite3.Connection,
    month_str: str,
    daily_counts: list[dict],
    results: list[dict],
) -> None:
    """Judge hidden trophies."""
    # Night Owl: files exist at 3 AM
    if not is_achieved(con, "night_owl"):
        row = con.execute(
            "SELECT 1 FROM files WHERE is_deleted=0 "
            "AND CAST(strftime('%H', datetime(mtime, 'unixepoch', 'localtime')) AS INTEGER) = 3 "
            "LIMIT 1"
        ).fetchone()
        if row:
            d = next(h for h in HIDDEN_DEFS if h.trophy_type == "night_owl")
            award_trophy(con, "night_owl", achieved_month=month_str)
            results.append(_trophy_dict(d, month_str, is_new=True))

    # Centurion: 100+ files in a single day
    if not is_achieved(con, "centurion"):
        for dc in daily_counts:
            if dc.get("count", 0) >= 100:
                d = next(h for h in HIDDEN_DEFS if h.trophy_type == "centurion")
                award_trophy(con, "centurion", achieved_month=month_str,
                             metadata={"date": dc["date"], "count": dc["count"]})
                results.append(_trophy_dict(d, month_str, is_new=True))
                break

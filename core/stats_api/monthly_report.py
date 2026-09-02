"""Monthly report data builder.

Generates statistics for the specified month:
- File count + month-over-month comparison
- Top 20 tags (with previous month rank comparison)
- New tags (first appeared in the current month)
- Source distribution
- Most active day + daily counts
- Trophy evaluation
- Available months list
"""

from core.extensions_core.service_registry import ServiceRegistry
from core.stats_api.filters import ai_image_where
from core.timezone_core.tz_helper import month_range_unix, tz_sqlite_modifier


def _month_range_unix(month_str: str) -> tuple[int, int]:
    """Convert 'YYYY-MM' to configured-timezone start/end Unix epoch."""
    return month_range_unix(month_str)


def _prev_month_str(month_str: str) -> str:
    """'2026-02' -> '2026-01'"""
    parts = month_str.split("-")
    year, mon = int(parts[0]), int(parts[1])
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def _top_tags_for_month(con, where: str, mstart: int, mend: int, limit: int = 20):
    """Retrieve top tags for the month. [(tag_id, tag, namespace, count), ...]

    Aggregates by tag_id (not tag name) to avoid merging same-name tags from
    different namespaces (e.g. general:hair vs artist:hair).
    Follows the 2-step pattern from basic.py: aggregate on file_tags first,
    resolve names after to avoid costly 3-way JOINs.
    """
    rows = con.execute(
        f"""SELECT ft.tag_id, COUNT(*) as cnt
            FROM file_tags ft
            JOIN files f ON f.id = ft.file_id
            WHERE {where} AND f.mtime >= ? AND f.mtime <= ?
            GROUP BY ft.tag_id
            ORDER BY cnt DESC
            LIMIT ?""",
        (mstart, mend, limit),
    ).fetchall()
    if not rows:
        return []
    ids = [r[0] for r in rows]
    placeholders = ",".join("?" * len(ids))
    name_map = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            f"SELECT id, tag, namespace FROM tags WHERE id IN ({placeholders})", ids
        )
    }
    return [
        (tid, name_map[tid][0], name_map[tid][1], cnt)
        for tid, cnt in rows
        if tid in name_map
    ]


def _new_tags_for_month(con, where: str, mstart: int, mend: int, limit: int = 20) -> list[str]:
    """Retrieve tags that first appeared in the current month.

    Narrows candidates using the tags.first_seen_mtime index,
    then verifies actual usage via file_tags JOIN and returns in descending count order.
    """
    # Step 1: Get tag_id candidates first seen this month via first_seen_mtime (fast index lookup)
    tag_ids: list[int] = []
    tag_map: dict[int, str] = {}
    for tag_id, tag in con.execute(
        "SELECT id, tag FROM tags "
        "WHERE first_seen_mtime >= ? AND first_seen_mtime <= ?",
        (mstart, mend),
    ):
        tag_ids.append(tag_id)
        tag_map[tag_id] = tag
    if not tag_ids:
        return []

    # Step 2: Verify candidate tag_ids are actually linked to AI image files this month + count
    placeholders = ",".join("?" for _ in tag_ids)

    rows = con.execute(
        f"""SELECT ft.tag_id, COUNT(*) as cnt
            FROM file_tags ft
            JOIN files f ON f.id = ft.file_id
            WHERE ft.tag_id IN ({placeholders})
              AND {where}
              AND f.mtime >= ? AND f.mtime <= ?
            GROUP BY ft.tag_id
            ORDER BY cnt DESC
            LIMIT ?""",
        (*tag_ids, mstart, mend, limit),
    )
    return [tag_map[r[0]] for r in rows if r[0] in tag_map]


def _available_months(con, where: str) -> list[str]:
    """Return all months in the DB in descending order."""
    rows = con.execute(
        f"""SELECT DISTINCT strftime('%Y-%m',
                datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as month
            FROM files f WHERE {where}
            ORDER BY month DESC"""
    )
    return [r[0] for r in rows if r[0]]


def build_monthly_report(con, month_str: str, *, include_trophies: bool = True) -> dict:
    """Build report data for the specified month."""
    where = ai_image_where("f")

    mstart, mend = _month_range_unix(month_str)
    prev_month = _prev_month_str(month_str)
    pstart, pend = _month_range_unix(prev_month)

    # --- File count (280K optimization: merge 2 COUNTs into 1 query) ---
    count_row = con.execute(
        f"""SELECT
            SUM(CASE WHEN f.mtime >= ? AND f.mtime <= ? THEN 1 ELSE 0 END),
            SUM(CASE WHEN f.mtime >= ? AND f.mtime <= ? THEN 1 ELSE 0 END)
        FROM files f WHERE {where}""",
        (mstart, mend, pstart, pend),
    ).fetchone()
    file_count = count_row[0] or 0
    prev_count = count_row[1] or 0

    # None when there is no previous month baseline (first month or gap after
    # a month with 0 files). The frontend renders None as "-- vs prev" via the
    # neutral branch, which is more accurate than "+0.0% vs prev".
    mom_pct: float | None = (
        round((file_count - prev_count) / prev_count * 100, 1) if prev_count > 0 else None
    )

    # --- Unique tag count (280K optimization: leverage cache) ---
    from core.stats_api.monthly_stats_materialize import get_cached_monthly_stat
    cached_tags = get_cached_monthly_stat(con, month_str, "unique_tags")
    if cached_tags is not None:
        unique_tags = int(cached_tags)
    else:
        unique_tags = con.execute(
            f"""SELECT COUNT(DISTINCT ft.tag_id)
                FROM file_tags ft
                JOIN files f ON f.id = ft.file_id
                WHERE {where} AND f.mtime >= ? AND f.mtime <= ?""",
            (mstart, mend),
        ).fetchone()[0]

    # --- Top tags + previous month rank ---
    # Both cur_tags and prev_tags are [(tag_id, tag, namespace, count), ...]
    # Keyed by tag_id to avoid merging same-name tags across namespaces.
    cur_tags = _top_tags_for_month(con, where, mstart, mend, 20)
    prev_tags = _top_tags_for_month(con, where, pstart, pend, 50)
    prev_rank_map = {row[0]: i + 1 for i, row in enumerate(prev_tags)}

    top_tags = []
    for rank, row in enumerate(cur_tags, 1):
        tid, tag, cnt = row[0], row[1], row[3]
        prev_rank = prev_rank_map.get(tid)
        rank_change = (prev_rank - rank) if prev_rank else None
        top_tags.append({
            "tag": tag, "count": cnt, "rank": rank,
            "prev_rank": prev_rank, "rank_change": rank_change,
        })

    # --- New tags (first appeared this month) ---
    new_tags = _new_tags_for_month(con, where, mstart, mend, 20)

    # --- Source distribution ---
    src_rows = con.execute(
        f"""SELECT COALESCE(f.meta_source, 'unknown') as src, COUNT(*) as cnt
            FROM files f WHERE {where} AND f.mtime >= ? AND f.mtime <= ?
            GROUP BY src ORDER BY cnt DESC""",
        (mstart, mend),
    )
    sources = {r[0]: r[1] for r in src_rows}

    # --- Most active day + daily counts ---
    daily_rows = con.execute(
        f"""SELECT date(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r}) as day, COUNT(*) as cnt
            FROM files f WHERE {where} AND f.mtime >= ? AND f.mtime <= ?
            GROUP BY day ORDER BY day""",
        (mstart, mend),
    )
    daily_counts = [{"date": r[0], "count": r[1]} for r in daily_rows]

    most_active_day = None
    if daily_counts:
        best = max(daily_counts, key=lambda d: d["count"])
        most_active_day = {"date": best["date"], "count": best["count"]}

    # --- Trophies (ServiceRegistry fallback) ---
    trophies = []
    _judge_trophies = ServiceRegistry.get("trophies.judge_all") if include_trophies else None
    if _judge_trophies is not None:
        cumul_before = con.execute(
            f"SELECT COUNT(*) FROM files f WHERE {where} AND f.mtime < ?",
            (mstart,),
        ).fetchone()[0]
        cumul_after = cumul_before + file_count
        # Trophy evaluation requires writes (INSERT), so use a writable connection
        try:
            from core.services_core.db_api import get_db
            from core.services_core.db_write import submit_db_write

            def _write_trophies():
                write_con = get_db()
                trophies_local = _judge_trophies(
                    write_con, month_str, cumul_before, cumul_after,
                    daily_counts, sources, unique_tags_cumul=unique_tags,
                )
                if any(t.get("is_new") for t in trophies_local):
                    write_con.commit()
                return trophies_local

            trophies = submit_db_write(_write_trophies)
        except Exception:
            # If writable connection fails, skip with read-only fallback
            trophies = []

    # --- Available months ---
    months = _available_months(con, where)

    return {
        "month": month_str,
        "file_count": file_count,
        "prev_month_count": prev_count,
        "mom_change_pct": mom_pct,
        "unique_tags": unique_tags,
        "new_tags": new_tags,
        "top_tags": top_tags,
        "sources": sources,
        "most_active_day": most_active_day,
        "daily_counts": daily_counts,
        "trophies": trophies,
        "available_months": months,
    }

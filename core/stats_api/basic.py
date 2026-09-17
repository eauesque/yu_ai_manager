"""Basic/hourly stats builders."""

from importlib import import_module

# Import from relocated stats extension
_stats_insights = import_module("extensions.builtin_stats.core_impl.stats_insights")
analyze_personality = _stats_insights.analyze_personality
from core.stats_api.filters import ai_image_where
from core.timezone_core.tz_helper import tz_sqlite_modifier


def build_basic_stats(con):
    where = ai_image_where("f")
    file_count = con.execute(f"SELECT COUNT(*) FROM files f WHERE {where}").fetchone()[0]
    # 280K optimization: get from materialized cache, fallback if unavailable
    from core.stats_api.monthly_stats_materialize import get_cached_total_tag_count
    tag_count = get_cached_total_tag_count(con)
    if tag_count is None:
        tag_count = con.execute(
            f"""SELECT COUNT(DISTINCT ft.tag_id)
                FROM file_tags ft
                JOIN files f ON f.id=ft.file_id
                WHERE {where}"""
        ).fetchone()[0]
    sources = con.execute(
        f"SELECT f.meta_source, COUNT(*) FROM files f WHERE {where} GROUP BY f.meta_source"
    )
    source_stats = {(row[0] or "unknown"): row[1] for row in sources}
    # 2-step top tags: aggregate on file_tags first, resolve names after.
    # Avoids 3-way JOIN with 7M+ file_tags rows (14s → 2.6s on 1.5M DB).
    top_tag_ids = [
        (row[0], row[1])
        for row in con.execute(
        f"""SELECT ft.tag_id, COUNT(*) as cnt
           FROM file_tags ft
           WHERE ft.file_id IN (
               SELECT f.id FROM files f WHERE {where}
           )
           GROUP BY ft.tag_id
           ORDER BY cnt DESC, ft.tag_id DESC
           LIMIT 20"""
        )
    ]
    if top_tag_ids:
        placeholders = ",".join("?" * len(top_tag_ids))
        tag_rows = con.execute(
            f"SELECT id, tag, namespace FROM tags WHERE id IN ({placeholders})",
            [r[0] for r in top_tag_ids],
        )
        name_map = {r[0]: (r[1], r[2]) for r in tag_rows}
        top_tags = [
            (name_map[tid][0], name_map[tid][1], cnt)
            for tid, cnt in top_tag_ids
            if tid in name_map
        ]
    else:
        top_tags = []
    total_files = con.execute("SELECT COUNT(*) FROM files WHERE is_deleted=0").fetchone()[0]
    excluded_files = total_files - file_count
    return {
        "file_count": file_count,
        "total_files": total_files,
        "excluded_files": excluded_files,
        "tag_count": tag_count,
        "sources": source_stats,
        "top_tags": [{"tag": row[0], "namespace": row[1] or "", "count": row[2]} for row in top_tags],
    }


def build_hourly_stats(con):
    where = ai_image_where("f")
    # 280K optimization: use CTE to call strftime only once
    # Previously strftime was redundantly called 7 times inside CASE
    tz = tz_sqlite_modifier()
    hourly = list(con.execute(
        f"""WITH hourly AS (
                SELECT CAST(strftime('%H', datetime(f.mtime, 'unixepoch', {tz!r})) AS INTEGER) as hour
                FROM files f
                WHERE {where}
            )
            SELECT hour, COUNT(*) as count
            FROM hourly
            GROUP BY hour
            ORDER BY hour"""
    ))
    # Build period and heatmap simultaneously from CTE results (single DB query)
    period_data = {"night": 0, "dawn": 0, "day": 0, "evening": 0}
    for row in hourly:
        h, cnt = row[0], row[1]
        if h >= 21 or h < 3:
            period_data["night"] += cnt
        elif h < 9:
            period_data["dawn"] += cnt
        elif h < 15:
            period_data["day"] += cnt
        else:
            period_data["evening"] += cnt
    total = sum(period_data.values())
    heatmap = [0] * 24
    for row in hourly:
        heatmap[row[0]] = row[1]
    return {
        "periods": {
            "night": {
                "label_key": "stats.period.night",
                "count": period_data.get("night", 0),
                "percentage": round(period_data.get("night", 0) / total * 100, 1) if total > 0 else 0,
            },
            "dawn": {
                "label_key": "stats.period.dawn",
                "count": period_data.get("dawn", 0),
                "percentage": round(period_data.get("dawn", 0) / total * 100, 1) if total > 0 else 0,
            },
            "day": {
                "label_key": "stats.period.day",
                "count": period_data.get("day", 0),
                "percentage": round(period_data.get("day", 0) / total * 100, 1) if total > 0 else 0,
            },
            "evening": {
                "label_key": "stats.period.evening",
                "count": period_data.get("evening", 0),
                "percentage": round(period_data.get("evening", 0) / total * 100, 1) if total > 0 else 0,
            },
        },
        "heatmap": heatmap,
        "personality": analyze_personality(period_data, total),
    }

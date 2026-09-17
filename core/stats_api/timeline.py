"""Timeline stats builders."""

from core.stats_api.filters import ai_image_where
from core.timezone_core.tz_helper import tz_sqlite_modifier


def build_timeline_stats(con, granularity: str = "month"):
    if granularity == "day":
        format_str = "%Y-%m-%d"
    elif granularity == "week":
        format_str = "%Y-%W"
    elif granularity == "year":
        format_str = "%Y"
    else:
        format_str = "%Y-%m"
    where = ai_image_where("f")
    timeline = con.execute(
        f"""SELECT
            strftime('{format_str}', datetime(f.mtime, 'unixepoch', {tz_sqlite_modifier()!r})) as period,
            COUNT(*) as count
        FROM files f
        WHERE {where}
        GROUP BY period
        ORDER BY period"""
    )
    return [{"period": row[0], "count": row[1]} for row in timeline]

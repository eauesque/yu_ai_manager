"""SQL for model/resolution stats."""

from collections.abc import Iterator

from core.stats_api.filters import ai_image_where
from core.timezone_core.tz_helper import tz_sqlite_modifier


def get_model_stats_rows(con) -> Iterator:
    """Fetch model stats using 2-query split (INNER JOIN + NOT EXISTS).

    A single LEFT JOIN on 283K files × templates takes 60s+.
    Split approach: INNER JOIN for known models + NOT EXISTS for
    Unknown/NAI fallback — total ~2.6s.
    """
    tz = tz_sqlite_modifier()
    _AI_WHERE = ai_image_where("f")

    # Files WITH a template model name
    def _iter_rows() -> Iterator:
        yield from con.execute(f"""SELECT
    strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz!r})) as month,
    tm.model_name as model,
    COUNT(*) as count
FROM files f
INNER JOIN templates tm ON tm.file_id = f.id
WHERE {_AI_WHERE}
  AND tm.model_name IS NOT NULL
GROUP BY month, model""")

        # Files WITHOUT a template model name
        yield from con.execute(f"""SELECT
    strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz!r})) as month,
    CASE
        WHEN f.meta_source IN ('novelai_v4_webp','novelai_v4_png','novelai_v4')
        THEN 'NovelAI Diffusion V4.5'
        ELSE 'Unknown'
    END as model,
    COUNT(*) as count
FROM files f
WHERE {_AI_WHERE}
  AND NOT EXISTS (
      SELECT 1 FROM templates tm
      WHERE tm.file_id = f.id AND tm.model_name IS NOT NULL
  )
GROUP BY month, model""")

    return _iter_rows()


def get_resolution_stats_sql() -> str:
    tz = tz_sqlite_modifier()
    _where = ai_image_where("f")
    return f"""SELECT
    strftime('%Y-%m', datetime(f.mtime, 'unixepoch', {tz!r})) as month,
    CASE
        WHEN f.width > 0 AND f.height > 0
        THEN (f.width || 'x' || f.height)
        ELSE NULL
    END as resolution,
    COUNT(*) as count
FROM files f
WHERE {_where}
GROUP BY month, resolution
HAVING resolution IS NOT NULL
ORDER BY month, count DESC"""

"""Count validation implementation for health debug tools."""


from .client import YuManagerClient
from .debug_helpers import _check, _g, _json, _sql, _summarize

_AI_WHERE = """(
    f.is_deleted=0
    AND (
        lower(f.path) LIKE '%.png'
        OR lower(f.path) LIKE '%.jpg'
        OR lower(f.path) LIKE '%.jpeg'
        OR lower(f.path) LIKE '%.webp'
        OR lower(f.path) LIKE '%.gif'
        OR lower(f.path) LIKE '%.bmp'
        OR lower(f.path) LIKE '%.tif'
        OR lower(f.path) LIKE '%.tiff'
        OR lower(f.path) LIKE '%.avif'
        OR lower(f.path) LIKE '%.jxl'
        OR lower(f.path) LIKE '%.heif'
        OR lower(f.path) LIKE '%.heic'
    )
    AND COALESCE(f.meta_source, '') NOT IN ('', 'unknown', 'not_modified')
    AND COALESCE(f.meta_source, '') NOT LIKE 'media_%'
)"""
_AI_IMAGE_COUNT_SQL = f"SELECT COUNT(*) as cnt FROM files f WHERE {_AI_WHERE}"
_AI_TAG_COUNT_SQL = f"""SELECT COUNT(DISTINCT ft.tag_id) as cnt
    FROM file_tags ft
    JOIN files f ON f.id=ft.file_id
    WHERE {_AI_WHERE}"""


def validate_counts(client: YuManagerClient) -> str:
    checks: list[dict] = []
    stats = client.get("/api/stats/all")
    basic = _g(_g(stats, "data", stats), "basic", {})

    for name, sql, api_key in [
        ("total_files", "SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0", "total_files"),
        ("file_count", _AI_IMAGE_COUNT_SQL, "file_count"),
        ("tag_count", _AI_TAG_COUNT_SQL, "tag_count"),
    ]:
        res = _sql(client, sql)
        if res.get("rows"):
            db_cnt = res["rows"][0]["cnt"]
            api_cnt = basic.get(api_key)
            checks.append(_check(name, "pass" if db_cnt == api_cnt else "fail", db=db_cnt, api=api_cnt))

    for name, sql in [
        ("orphan_file_tags", "SELECT COUNT(*) as cnt FROM file_tags ft LEFT JOIN files f ON ft.file_id=f.id WHERE f.id IS NULL"),
        ("orphan_annotations", "SELECT COUNT(*) as cnt FROM file_annotations fa LEFT JOIN files f ON fa.file_id=f.id WHERE f.id IS NULL"),
    ]:
        res = _sql(client, sql)
        if res.get("rows"):
            cnt = res["rows"][0]["cnt"]
            checks.append(_check(name, "pass" if cnt == 0 else "warn", count=cnt))

    res = _sql(client, "SELECT rating, COUNT(*) as cnt FROM file_ratings GROUP BY rating ORDER BY rating")
    if res.get("rows"):
        checks.append(_check("rating_distribution", "pass", distribution={row["rating"]: row["cnt"] for row in res["rows"]}))
    return _json(_summarize(checks))

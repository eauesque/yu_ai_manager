"""Annotation validator implementation."""


from .client import YuManagerClient
from .debug_helpers import _check, _json, _sql, _summarize


def validate_annotations(client: YuManagerClient) -> str:
    checks: list[dict] = []

    res = _sql(client, "SELECT COUNT(*) as cnt FROM file_annotations fa LEFT JOIN files f ON fa.file_id=f.id WHERE f.id IS NULL")
    if res.get("rows"):
        cnt = res["rows"][0]["cnt"]
        checks.append(_check("orphan_annotations", "pass" if cnt == 0 else "warn", count=cnt))

    res = _sql(client, "SELECT COUNT(*) as cnt FROM file_annotations WHERE confidence IS NOT NULL AND (confidence < 0.0 OR confidence > 1.0)")
    if res.get("rows"):
        cnt = res["rows"][0]["cnt"]
        checks.append(_check("confidence_range", "pass" if cnt == 0 else "fail", out_of_range=cnt))

    res = _sql(client, "SELECT source, COUNT(*) as cnt FROM file_annotations GROUP BY source ORDER BY cnt DESC")
    if res.get("rows"):
        checks.append(_check("source_distribution", "pass", sources={r["source"]: r["cnt"] for r in res["rows"]}))
    else:
        checks.append(_check("source_distribution", "skip", detail="no annotations"))

    res = _sql(client, "SELECT key, COUNT(*) as cnt FROM file_annotations GROUP BY key ORDER BY cnt DESC LIMIT 20")
    if res.get("rows"):
        checks.append(_check("key_distribution", "pass", keys={r["key"]: r["cnt"] for r in res["rows"]}))
    return _json(_summarize(checks))

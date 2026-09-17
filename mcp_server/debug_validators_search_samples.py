"""Sampling helper for validator debug tools."""

from typing import Any

from .client import YuManagerClient
from .debug_helpers import _json, _sql


def sample_files(client: YuManagerClient, n: int, fields: str) -> str:
    n = max(1, min(n, 500))
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else ["meta_source", "width", "height"]
    allowed = {"meta_source", "width", "height", "path", "mtime", "size", "parser_version", "is_deleted", "phash", "content_hash", "is_zip_member"}
    safe_fields = [f"f.{field}" for field in field_list if field in allowed] or ["f.meta_source"]
    res = _sql(client, f"SELECT f.id, {', '.join(safe_fields)} FROM files f WHERE f.is_deleted=0 ORDER BY RANDOM() LIMIT {n}", limit=n)
    rows = res.get("rows", [])
    stats: dict[str, Any] = {}
    for field in field_list:
        if field not in allowed:
            continue
        values = [row.get(field) for row in rows]
        null_count = sum(1 for value in values if value is None or value == "")
        freq: dict[str, int] = {}
        for value in [v for v in values if v is not None and v != ""]:
            key = str(value)[:80]
            freq[key] = freq.get(key, 0) + 1
        stats[field] = {
            "null_rate": round(null_count / len(rows), 3) if rows else 0,
            "null_count": null_count,
            "total": len(rows),
            "top_values": dict(sorted(freq.items(), key=lambda item: -item[1])[:5]),
        }
    return _json({"sample_size": len(rows), "field_stats": stats})

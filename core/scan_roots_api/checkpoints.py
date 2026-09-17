"""Checkpoint listing helpers for scan roots routes."""

import re as _re
import time as _time

from core.services_core.db_api import get_readonly_db

# Simple in-memory cache (checkpoints change rarely)
_cache: dict | None = None
_cache_ts: float = 0
_CACHE_TTL = 300  # 5 minutes


def fetch_checkpoints_payload():
    """Build checkpoint listing payload for /api/checkpoints."""
    global _cache, _cache_ts
    now = _time.monotonic()
    if _cache is not None and now - _cache_ts < _CACHE_TTL:
        return _cache

    con = get_readonly_db()

    rows = con.execute(
        """
        SELECT model_name, model_hash, COUNT(*) as count
        FROM templates
        WHERE model_name IS NOT NULL AND model_name != ''
        GROUP BY model_name, model_hash
        ORDER BY count DESC
        LIMIT 100
        """
    )

    results = []
    for row in rows:
        results.append({
            "name": row["model_name"],
            "hash": row["model_hash"],
            "count": row["count"],
        })
    if results:
        payload = {"checkpoints": results}
        _cache = payload
        _cache_ts = _time.monotonic()
        return payload

    model_rows = con.execute(
        """
        SELECT raw_prompt FROM templates
        WHERE raw_prompt LIKE '%Model:%'
        LIMIT 50000
        """
    )

    model_counts = {}
    for row in model_rows:
        match = _re.search(r"Model:\\s*([^,\\n]+)", row[0] or "")
        if match:
            name = match.group(1).strip()
            model_counts[name] = model_counts.get(name, 0) + 1

    for name, count in sorted(model_counts.items(), key=lambda item: -item[1])[:100]:
        results.append({"name": name, "hash": None, "count": count})

    payload = {"checkpoints": results}
    _cache = payload
    _cache_ts = _time.monotonic()
    return payload

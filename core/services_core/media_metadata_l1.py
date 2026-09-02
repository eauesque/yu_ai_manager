"""In-memory L1 cache for read-only media metadata resolution."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from core.services_core.db_api import get_config

_LOCK = threading.RLock()
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_TOTAL_BYTES = 0

_DEFAULT_MAX_ITEMS = 20000
_DEFAULT_MAX_MB = 512
_BYTES_PER_MB = 1024 * 1024

# ------------------------------------------------------------------
# Cache _limits() result with 60s TTL to avoid frequent get_config() calls
# ------------------------------------------------------------------
_LIMITS_TTL = 60  # seconds
_cached_limits: tuple[int, int] | None = None
_cached_limits_ts: float = 0.0


def _to_int(v: Any, fallback: int) -> int:
    try:
        return int(v)
    except Exception:
        return fallback


def _limits() -> tuple[int, int]:
    global _cached_limits, _cached_limits_ts
    now = time.monotonic()
    if _cached_limits is not None and (now - _cached_limits_ts) < _LIMITS_TTL:
        return _cached_limits
    cfg = get_config() or {}
    media_cfg = cfg.get("media_cache", {}) if isinstance(cfg, dict) else {}
    max_items = max(1, _to_int(media_cfg.get("l1_max_items"), _DEFAULT_MAX_ITEMS))
    max_mb = max(1, _to_int(media_cfg.get("l1_max_mb"), _DEFAULT_MAX_MB))
    _cached_limits = (max_items, max_mb * _BYTES_PER_MB)
    _cached_limits_ts = now
    return _cached_limits


def _cache_key(
    file_id: int,
    *,
    meta_source: str,
    mtime: int,
    size: int,
    content_hash: str | None,
    raw_meta_json: str | None,
) -> str:
    # Cache key component, not a security primitive.
    digest = hashlib.md5(
        (raw_meta_json or "").encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return f"{file_id}:{meta_source}:{mtime}:{size}:{content_hash or ''}:{digest}"


def _estimate_bytes(value: dict[str, Any]) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except Exception:
        return 1024


def _evict_if_needed(max_items: int, max_bytes: int) -> None:
    global _TOTAL_BYTES
    while _CACHE and (len(_CACHE) > max_items or max_bytes < _TOTAL_BYTES):
        _, evicted = _CACHE.popitem(last=False)
        _TOTAL_BYTES = max(0, _TOTAL_BYTES - int(evicted.get("_bytes", 0)))


def resolve_with_l1_cache(
    *,
    file_id: int,
    meta_source: str,
    mtime: int,
    size: int,
    content_hash: str | None,
    raw_meta_json: str | None,
    resolver: Callable[[str, str | None], dict[str, Any]],
) -> dict[str, Any]:
    global _TOTAL_BYTES
    key = _cache_key(
        int(file_id),
        meta_source=str(meta_source or ""),
        mtime=int(mtime),
        size=int(size),
        content_hash=content_hash,
        raw_meta_json=raw_meta_json,
    )
    with _LOCK:
        existing = _CACHE.get(key)
        if existing is not None:
            _CACHE.move_to_end(key, last=True)
            return dict(existing["value"])

    resolved = resolver(meta_source, raw_meta_json)
    value = {
        "metadata": resolved.get("metadata"),
        "normalized_json": resolved.get("normalized_json"),
        "schedule_reextract": bool(resolved.get("schedule_reextract")),
    }
    entry_bytes = _estimate_bytes(value)
    max_items, max_bytes = _limits()
    with _LOCK:
        prior = _CACHE.get(key)
        if prior is not None:
            _TOTAL_BYTES = max(0, _TOTAL_BYTES - int(prior.get("_bytes", 0)))
            _CACHE.pop(key, None)
        _CACHE[key] = {"value": value, "_bytes": entry_bytes}
        _TOTAL_BYTES += entry_bytes
        _evict_if_needed(max_items, max_bytes)
    return dict(value)


def _test_only_reset() -> None:
    global _TOTAL_BYTES, _cached_limits, _cached_limits_ts
    with _LOCK:
        _CACHE.clear()
        _TOTAL_BYTES = 0
    _cached_limits = None
    _cached_limits_ts = 0.0

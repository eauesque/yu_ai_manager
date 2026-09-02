"""Short-lived cache for first-page search responses."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Sequence
from typing import Any

_TTL = 20  # seconds
_MAX_ENTRIES = 64


class SearchPageCache:
    __slots__ = ("_cache", "_lock")

    def __init__(self) -> None:
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(sql: str, params: Sequence[Any]) -> str:
        raw = sql + "\0" + json.dumps(params, default=str, separators=(",", ":"))
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    def get(self, sql: str, params: Sequence[Any]) -> dict[str, Any] | None:
        key = self._make_key(sql, params)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            payload, expire_at = entry
            if time.time() > expire_at:
                del self._cache[key]
                return None
            return _copy_payload(payload)

    def put(self, sql: str, params: Sequence[Any], payload: dict[str, Any]) -> None:
        key = self._make_key(sql, params)
        expire_at = time.time() + _TTL
        with self._lock:
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_expired()
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_oldest()
            self._cache[key] = (_copy_payload(payload), expire_at)

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]

    def _evict_oldest(self) -> None:
        if not self._cache:
            return
        oldest = min(self._cache, key=lambda k: self._cache[k][1])
        del self._cache[oldest]


search_page_cache = SearchPageCache()


def _copy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    copied = dict(payload)
    results = payload.get("results")
    if isinstance(results, list):
        copied["results"] = [
            dict(item) if isinstance(item, dict) else item
            for item in results
        ]
    perf = payload.get("perf")
    if isinstance(perf, dict):
        copied["perf"] = dict(perf)
    return copied

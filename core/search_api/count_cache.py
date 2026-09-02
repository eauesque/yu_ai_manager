"""In-memory COUNT cache with TTL.

Caches COUNT(*) query results keyed by SQL+params hash for 30 seconds,
avoiding duplicate counts during pagination. Thread-safe.
"""

import hashlib
import json
import threading
import time
from collections.abc import Sequence
from typing import Any

_TTL = 120  # seconds (was 30s; extended for 150K+ file databases)
_MAX_ENTRIES = 200


class CountCache:
    __slots__ = ("_cache", "_lock")

    def __init__(self) -> None:
        # key -> (count, expire_at)
        self._cache: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(sql: str, params: Sequence[Any]) -> str:
        raw = sql + "\0" + json.dumps(params, default=str, separators=(",", ":"))
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    def get(self, sql: str, params: Sequence[Any]) -> int | None:
        key = self._make_key(sql, params)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            count, expire_at = entry
            if time.time() > expire_at:
                del self._cache[key]
                return None
            return count

    def put(self, sql: str, params: Sequence[Any], count: int) -> None:
        key = self._make_key(sql, params)
        expire_at = time.time() + _TTL
        with self._lock:
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_expired()
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_oldest()
            self._cache[key] = (count, expire_at)

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


count_cache = CountCache()

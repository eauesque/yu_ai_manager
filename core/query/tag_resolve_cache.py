"""Short-lived cache for tag-id resolution during search query building."""

from __future__ import annotations

import threading
import time

_TTL = 120
_MAX_ENTRIES = 512


class TagResolveCache:
    __slots__ = ("_cache", "_lock")

    def __init__(self) -> None:
        self._cache: dict[tuple[bool, str], tuple[list[int], float]] = {}
        self._lock = threading.Lock()

    def get(self, case_sensitive: bool, tag_val: str) -> list[int] | None:
        key = (case_sensitive, tag_val)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                del self._cache[key]
                return None
            return list(value)

    def put(self, case_sensitive: bool, tag_val: str, tag_ids: list[int]) -> None:
        key = (case_sensitive, tag_val)
        expire_at = time.time() + _TTL
        with self._lock:
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_expired()
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_oldest()
            self._cache[key] = (list(tag_ids), expire_at)

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


tag_resolve_cache = TagResolveCache()


class TagCardinalityCache:
    __slots__ = ("_cache", "_lock")

    def __init__(self) -> None:
        self._cache: dict[int, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def get(self, tag_id: int) -> int | None:
        with self._lock:
            entry = self._cache.get(tag_id)
            if entry is None:
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                del self._cache[tag_id]
                return None
            return value

    def put(self, tag_id: int, count: int) -> None:
        expire_at = time.time() + _TTL
        with self._lock:
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_expired()
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_oldest()
            self._cache[tag_id] = (count, expire_at)

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


tag_cardinality_cache = TagCardinalityCache()


class PathMatchProbeCache:
    __slots__ = ("_cache", "_lock")

    def __init__(self) -> None:
        self._cache: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def get(self, fts_query: str) -> int | None:
        with self._lock:
            entry = self._cache.get(fts_query)
            if entry is None:
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                del self._cache[fts_query]
                return None
            return value

    def put(self, fts_query: str, match_count: int) -> None:
        expire_at = time.time() + _TTL
        with self._lock:
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_expired()
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_oldest()
            self._cache[fts_query] = (match_count, expire_at)

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


path_match_probe_cache = PathMatchProbeCache()

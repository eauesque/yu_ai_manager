"""Thread-safe per-key TTL cache for memoizing slow status/count lookups.

Designed for short-TTL caching of expensive read-only queries that get
hammered by polling or duplicate UI fetches. Not intended for large hot
datasets — use a domain-specific cache for those.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

# NOTE: this cache is intentionally untyped over its value type. The PEP 695
# `class SimpleTTLCache[T]` syntax is the right fit but the project still
# targets Python 3.11 at runtime, and the legacy `Generic[T]` form trips
# UP046 under py312 lint target. Callers that want stronger guarantees can
# wrap with their own typed shim.


class SimpleTTLCache:
    __slots__ = ("_store", "_lock", "_ttl", "_max_entries")

    def __init__(self, ttl_seconds: float, max_entries: int = 256) -> None:
        self._store: dict[Hashable, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._ttl = float(ttl_seconds)
        self._max_entries = int(max_entries)

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is not None and entry[1] > now:
                return entry[0]
        value = compute()
        self.put(key, value)
        return value

    def peek(self, key: Hashable) -> Any | None:
        """Return the cached value if fresh, else None.

        Use this in async contexts where ``compute`` would itself need to be
        awaited; pair with ``put`` after the slow op completes.
        """
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None or entry[1] <= now:
                return None
            return entry[0]

    def put(self, key: Hashable, value: Any) -> None:
        now = time.time()
        with self._lock:
            if len(self._store) >= self._max_entries:
                self._evict_one(now)
            self._store[key] = (value, now + self._ttl)

    def invalidate(self, key: Hashable | None = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)

    def _evict_one(self, now: float) -> None:
        # Drop one expired entry if any; otherwise drop the soonest-to-expire.
        for k, (_, exp) in self._store.items():
            if exp <= now:
                del self._store[k]
                return
        if self._store:
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]


def memoize_ttl(ttl_seconds: float) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: memoize a pure-args function with TTL. Args must be hashable."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        cache: SimpleTTLCache[Any] = SimpleTTLCache(ttl_seconds)

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            key = (args, tuple(sorted(kwargs.items())))
            return cache.get_or_compute(key, lambda: fn(*args, **kwargs))

        wrapped.cache_invalidate = cache.invalidate  # type: ignore[attr-defined]
        return wrapped

    return decorator

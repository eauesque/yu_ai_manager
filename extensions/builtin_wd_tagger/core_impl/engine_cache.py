"""LRU + thread-safe cache for TaggerAdapter instances.

Spec § 3.1 / § 4.1.

Cache keys are (model_id, threshold_hash) tuples - the same model with
different threshold settings is a distinct entry. Default max=1 to bound
GPU/RAM consumption; users with sufficient memory can raise via
`config.wd_tagger.engine_cache_size`.

All methods are thread-safe via a single internal RLock. Concurrent get()
calls for the same key build the adapter exactly once (the second caller
waits for the first builder to finish).
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class EngineCache:
    """LRU cache for TaggerAdapter instances, keyed by (model_id, thresholds_hash)."""

    def __init__(self, max_size: int = 1):
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size}")
        self._max_size = max_size
        self._entries: OrderedDict[tuple, Any] = OrderedDict()
        self._lock = threading.RLock()
        # Per-key build locks prevent two threads from racing to build
        # the same key simultaneously.
        self._build_locks: dict[tuple, threading.Lock] = {}

    def get(
        self,
        key: tuple,
        builder: Callable[[], Any],
    ) -> Any:
        """Get an adapter for `key`, building if not present.

        On a cache hit, the entry is moved to MRU position.
        On a miss, `builder()` is called exactly once even under concurrent
        access for the same key.
        """
        # Fast path: cache hit
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
            # Acquire (or create) a per-key build lock under the main lock.
            build_lock = self._build_locks.setdefault(key, threading.Lock())

        # Build outside the main lock so other keys remain accessible.
        with build_lock:
            # Re-check after acquiring the build lock - another thread may
            # have built the entry in the meantime.
            with self._lock:
                if key in self._entries:
                    self._entries.move_to_end(key)
                    return self._entries[key]

            logger.info("EngineCache miss; building adapter for key=%r", key)
            try:
                adapter = builder()
            except Exception:
                # On builder failure, drop the per-key build lock so the
                # next caller for the same key can retry with a fresh
                # build. Without this, the lock object would leak in
                # _build_locks indefinitely (until clear()).
                with self._lock:
                    self._build_locks.pop(key, None)
                raise

            with self._lock:
                self._entries[key] = adapter
                self._entries.move_to_end(key)
                self._evict_if_over_capacity()
                # Cleanup: build succeeded, drop the build lock.
                self._build_locks.pop(key, None)

            return adapter

    def evict_by_model_id(self, model_id: str) -> int:
        """Evict all entries whose key starts with `model_id`.

        Returns the number of entries removed. Used by
        `TaggerRegistry.invalidate(model_id)` to keep cache and registry
        in sync (spec § 3.1).
        """
        with self._lock:
            removed = [k for k in self._entries if k[0] == model_id]
            for k in removed:
                self._entries.pop(k, None)
                # Symmetrize with clear(): build_lock for evicted key is
                # also dropped so a re-build can start fresh.
                self._build_locks.pop(k, None)
            if removed:
                logger.info(
                    "EngineCache evicted %d entries for model_id=%r",
                    len(removed),
                    model_id,
                )
            return len(removed)

    def clear(self) -> None:
        """Drop all entries."""
        with self._lock:
            n = len(self._entries)
            self._entries.clear()
            self._build_locks.clear()
            if n:
                logger.info("EngineCache cleared (%d entries dropped)", n)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _evict_if_over_capacity(self) -> None:
        """Caller must hold self._lock."""
        while len(self._entries) > self._max_size:
            # popitem(last=False) drops the least-recently-used.
            evicted_key, _evicted_adapter = self._entries.popitem(last=False)
            logger.info("EngineCache evicted LRU entry: %r", evicted_key)

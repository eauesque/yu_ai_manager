"""Short-lived in-memory cache for grouped-search matching ID sets."""

from __future__ import annotations

import json
import threading
import time

_TTL = 45  # seconds
_MAX_ENTRIES = 12

_KEY_FIELDS = (
    "tag_query",
    "artist",
    "from_date",
    "to_date",
    "in_prompt",
    "in_negative",
    "in_char_negative",
    "in_char_positive",
    "file_format",
    "format_exts",
    "tag_query_regex",
    "in_prompt_regex",
    "tag_query_case_sensitive",
    "model_filter",
    "checkpoint_filter",
    "in_path",
    "or_tags",
    "min_width_int",
    "max_width_int",
    "min_height_int",
    "max_height_int",
    "from_ts_int",
    "to_ts_int",
    "also_path",
    "fav_only",
    "ai_analyzed",
    "has_tags",
    "has_annotation",
    "has_sweep",
    "collection_id",
    "min_rating",
    "max_rating",
)


class GroupedIdsCache:
    __slots__ = ("_cache", "_lock")

    def __init__(self) -> None:
        self._cache: dict[str, tuple[frozenset[int] | None, float]] = {}
        self._lock = threading.Lock()

    def make_key(self, params: dict) -> str:
        payload = {name: params.get(name) for name in _KEY_FIELDS}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def get(self, key: str) -> tuple[bool, frozenset[int] | None]:
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return False, None
            value, expire_at = entry
            if now > expire_at:
                del self._cache[key]
                return False, None
            return True, value

    def put(self, key: str, ids: set[int] | frozenset[int] | None) -> None:
        expire_at = time.time() + _TTL
        value = frozenset(ids) if ids is not None else None
        with self._lock:
            if len(self._cache) >= _MAX_ENTRIES:
                self._evict_one()
            if len(self._cache) >= _MAX_ENTRIES:
                return
            self._cache[key] = (value, expire_at)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _evict_one(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for key in expired:
            del self._cache[key]
        if not self._cache:
            return
        oldest = min(self._cache, key=lambda k: self._cache[k][1])
        del self._cache[oldest]


grouped_ids_cache = GroupedIdsCache()

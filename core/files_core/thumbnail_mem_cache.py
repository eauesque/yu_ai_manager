"""In-memory thumbnail cache helpers."""

from collections import OrderedDict
from threading import Lock

_MEM_CACHE_MAX_ENTRIES = int(__import__("os").environ.get("YU_THUMB_MEM_CACHE_MAX", "4000"))
_MEM_CACHE_MAX_BYTES = int(__import__("os").environ.get("YU_THUMB_MEM_CACHE_MB", "80")) * 1024 * 1024
_mem_cache: OrderedDict[str, tuple[bytes, str, str, int]] = OrderedDict()
_mem_cache_bytes = 0
_mem_lock = Lock()


def mem_get(cache_key: str) -> tuple[bytes, str, str] | None:
    with _mem_lock:
        entry = _mem_cache.get(cache_key)
        if entry is None:
            return None
        _mem_cache.move_to_end(cache_key)
        return entry[0], entry[1], entry[2]


def mem_put(cache_key: str, data: bytes, mime: str, etag: str) -> None:
    global _mem_cache_bytes
    size = len(data)
    if size > _MEM_CACHE_MAX_BYTES // 4:
        return
    with _mem_lock:
        old = _mem_cache.pop(cache_key, None)
        if old:
            _mem_cache_bytes -= old[3]
        while (_mem_cache_bytes + size > _MEM_CACHE_MAX_BYTES or len(_mem_cache) >= _MEM_CACHE_MAX_ENTRIES):
            if not _mem_cache:
                break
            _, evicted = _mem_cache.popitem(last=False)
            _mem_cache_bytes -= evicted[3]
        _mem_cache[cache_key] = (data, mime, etag, size)
        _mem_cache_bytes += size


def invalidate_mem_cache(cache_key: str) -> None:
    global _mem_cache_bytes
    with _mem_lock:
        old = _mem_cache.pop(cache_key, None)
        if old:
            _mem_cache_bytes -= old[3]


def clear_mem_cache() -> int:
    global _mem_cache_bytes
    with _mem_lock:
        count = len(_mem_cache)
        _mem_cache.clear()
        _mem_cache_bytes = 0
    return count

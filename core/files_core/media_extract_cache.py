"""Temporary cache for video/audio inside archives.

Extracts video/audio files inside archives (ZIP/7z/RAR) to disk on first access,
enabling Range (206) delivery via send_file thereafter.

Cache directory: cache/media_extract/
Cache key: MD5(archive_path + "!" + inner_path + ":" + archive_mtime)
LRU capacity limit: MAX_CACHE_BYTES (default 2GB)
"""

import contextlib
import hashlib
import logging
import os
import threading
from pathlib import Path
from shutil import copyfileobj

from .media_types import guess_media_mime

logger = logging.getLogger(__name__)

MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
_cache_dir_ensured = False
_eviction_lock = threading.Lock()


def _ensure_cache_dir() -> Path:
    from core.paths import cache_path
    global _cache_dir_ensured
    cache_dir = cache_path("media_extract")
    if not _cache_dir_ensured:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_dir_ensured = True
    return cache_dir


def is_streamable_media(path_str: str) -> bool:
    """Determine if the target file is video/audio requiring Range delivery."""
    mime = guess_media_mime(path_str)
    return mime is not None and (mime.startswith("video/") or mime.startswith("audio/"))


def _cache_key(archive_path: str, inner_path: str) -> str:
    """Generate cache key from archive path, inner path, and archive mtime."""
    try:
        mtime = os.path.getmtime(archive_path)
    except OSError:
        mtime = 0
    raw = f"{archive_path}!{inner_path}:{mtime}"
    # Cache key, not a security primitive.
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def _suffix_from_path(path_str: str) -> str:
    """Get file extension from file path."""
    ext = os.path.splitext(path_str)[1].lower()
    return ext if ext else ".bin"


def get_cached_path(archive_path: str, inner_path: str) -> Path | None:
    """Return cached file path if it exists, otherwise None."""
    cache_dir = _ensure_cache_dir()
    key = _cache_key(archive_path, inner_path)
    suffix = _suffix_from_path(inner_path)
    cached = cache_dir / f"{key}{suffix}"
    if cached.exists() and cached.stat().st_size > 0:
        # Update atime for LRU timestamp
        with contextlib.suppress(OSError):
            cached.touch()
        return cached
    return None


def _cache_destination(archive_path: str, inner_path: str) -> Path:
    """Return the stable cache destination path for an archive member."""
    cache_dir = _ensure_cache_dir()
    key = _cache_key(archive_path, inner_path)
    suffix = _suffix_from_path(inner_path)
    return cache_dir / f"{key}{suffix}"


def _finalize_cached_file(cached: Path) -> Path:
    """Apply post-processing and background eviction after a cache write."""
    try:
        from .mp4_faststart import ensure_faststart
        ensure_faststart(cached)
    except Exception:
        logger.debug("faststart skipped for %s", cached.name)
    threading.Thread(target=_evict_if_needed, daemon=True).start()
    return cached


def store_to_cache(archive_path: str, inner_path: str, data: bytes) -> Path:
    """Write bytes to cache and return the path.

    For MP4/MOV files, applies faststart (moov atom relocation) synchronously.
    This ensures moov is at the front from the first response, allowing
    browsers to begin streaming playback immediately.
    """
    cached = _cache_destination(archive_path, inner_path)
    # Atomic write: write to temp file then rename
    tmp = cached.with_suffix(cached.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(cached)
    except OSError:
        # Clean up leftover tmp file
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
    return _finalize_cached_file(cached)


def store_fileobj_to_cache(archive_path: str, inner_path: str, src) -> Path:
    """Stream a file-like object into cache and return the final cached path."""
    cached = _cache_destination(archive_path, inner_path)
    tmp = cached.with_suffix(cached.suffix + ".tmp")
    try:
        with open(tmp, "wb") as dst:
            copyfileobj(src, dst, length=1024 * 1024)
        tmp.replace(cached)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
    return _finalize_cached_file(cached)


def _evict_if_needed() -> None:
    """Delete oldest files when cache capacity exceeds the limit."""
    if not _eviction_lock.acquire(blocking=False):
        return  # Another thread is performing eviction
    try:
        cache_dir = _ensure_cache_dir()
        entries: list[tuple[Path, float, int]] = []
        total = 0
        for f in cache_dir.iterdir():
            if f.suffix == ".tmp" or not f.is_file():
                continue
            try:
                st = f.stat()
                entries.append((f, st.st_atime, st.st_size))
                total += st.st_size
            except OSError:
                continue
        if total <= MAX_CACHE_BYTES:
            return
        # Sort by atime ascending (delete oldest first)
        entries.sort(key=lambda x: x[1])
        for path, _, size in entries:
            if total <= MAX_CACHE_BYTES * 0.8:  # Reduce to 80%
                break
            try:
                path.unlink()
                total -= size
                logger.debug("media cache evicted: %s (%d bytes)", path.name, size)
            except OSError:
                continue
    finally:
        _eviction_lock.release()

"""MP4 faststart cache for plain (on-disk) files.

When an MP4/MOV file's moov atom is at the end, browsers cannot
start playback until the entire file is downloaded.
Caches and serves faststarted copies without modifying the original files.

Cache directory: cache/faststart/
Cache key: MD5(file_path + ":" + mtime + ":" + size)
LRU capacity limit: MAX_CACHE_BYTES (default 4GB)
Size limit: MAX_FILE_BYTES (files over 500MB are skipped)
"""

import contextlib
import hashlib
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_CACHE_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB
MAX_FILE_BYTES = 500 * 1024 * 1024  # 500 MB (larger files served via Range from original)
_FASTSTART_EXTS = frozenset({".mp4", ".m4v", ".mov", ".m4a"})
_cache_dir_ensured = False
_eviction_lock = threading.Lock()


def _ensure_cache_dir() -> Path:
    from core.paths import cache_path
    global _cache_dir_ensured
    cache_dir = cache_path("faststart")
    if not _cache_dir_ensured:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_dir_ensured = True
    return cache_dir


def _cache_key(file_path: str, mtime: float, size: int) -> str:
    raw = f"{file_path}:{mtime}:{size}"
    # Cache key, not a security primitive.
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def get_faststarted_path(file_path: Path) -> Path | None:
    """Retrieve faststarted cache for a plain file.

    - Non-MP4/MOV -> None (not needed)
    - moov at the front -> None (already faststarted)
    - Over 500MB -> None (copy cost too high; serve original via Range)
    - No ffmpeg -> None
    - Cache hit -> cached path
    - Cache miss -> apply faststart and cache -> cached path
    """
    suffix = file_path.suffix.lower()
    if suffix not in _FASTSTART_EXTS:
        return None

    try:
        st = file_path.stat()
    except OSError:
        return None

    if st.st_size > MAX_FILE_BYTES:
        return None

    # Check cache hit
    cache_dir = _ensure_cache_dir()
    key = _cache_key(str(file_path), st.st_mtime, st.st_size)
    cached = cache_dir / f"{key}{suffix}"

    if cached.exists() and cached.stat().st_size > 0:
        with contextlib.suppress(OSError):
            cached.touch()  # Update LRU atime
        return cached

    # Determine if faststart is needed (moov after mdat)
    from .mp4_faststart import _FFMPEG_PATH, _needs_faststart

    if not _FFMPEG_PATH:
        return None
    if not _needs_faststart(file_path):
        return None  # Already faststarted

    # Apply faststart (create cached copy of original file)
    logger.info("plain faststart キャッシュ作成: %s (%d MB)",
                file_path.name, st.st_size // (1024 * 1024))
    import subprocess
    import tempfile

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=str(cache_dir))
    os.close(tmp_fd)
    try:
        result = subprocess.run(
            [
                _FFMPEG_PATH,
                "-i", str(file_path),
                "-c", "copy",
                "-movflags", "+faststart",
                "-y",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=60,  # Sufficient for -c copy even at 500MB
        )
        if result.returncode != 0:
            logger.warning("plain faststart 失敗: %s", result.stderr[:200])
            _cleanup_tmp(tmp_path)
            return None

        os.replace(tmp_path, str(cached))
        logger.info("plain faststart 完了: %s", file_path.name)

        # Check capacity in background
        threading.Thread(target=_evict_if_needed, daemon=True).start()
        return cached
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("plain faststart エラー: %s", e)
        _cleanup_tmp(tmp_path)
        return None


def _cleanup_tmp(tmp_path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(tmp_path)


def _evict_if_needed() -> None:
    """Evict oldest files when cache capacity exceeds the limit."""
    if not _eviction_lock.acquire(blocking=False):
        return
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
        entries.sort(key=lambda x: x[1])
        for path, _, size in entries:
            if total <= MAX_CACHE_BYTES * 0.8:
                break
            try:
                path.unlink()
                total -= size
                logger.debug("faststart cache evicted: %s (%d bytes)", path.name, size)
            except OSError:
                continue
    finally:
        _eviction_lock.release()

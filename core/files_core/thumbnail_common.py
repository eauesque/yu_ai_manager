"""Common helpers for thumbnail generation.

Thumbnail generation backends:
1. pyvips (libvips) -- shrink-on-load reduces during JPEG decode. Fastest.
2. Pillow-SIMD -- NEON/AVX2 optimized Pillow fork. Drop-in replacement.
3. Pillow -- standard fallback.

Cache layout (v2 sharded):
  cache/thumbnails/{hash[0:2]}/{hash[2:4]}/{hash}.webp
Legacy flat layout is auto-detected on cache hit for backward compat.
"""

import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import ImageFile

logger = logging.getLogger(__name__)

# Continue thumbnail generation even for images with truncated data
ImageFile.LOAD_TRUNCATED_IMAGES = True


THUMBNAIL_SIZE = (280, 280)
_THUMBNAIL_WIDTH = 280
_QUALITY = 78

# -- WebP support detection --
try:
    from PIL import features as _pil_features
    _USE_WEBP = bool(_pil_features.check("webp"))
except Exception:
    _USE_WEBP = False

if _USE_WEBP:
    _THUMB_EXT = ".webp"
    _THUMB_FORMAT = "WEBP"
    _THUMB_MIME = "image/webp"
    logger.info("WebP サポート検出 — サムネイルを WebP で生成 (JPEG 比 30-40%% 削減)")
else:
    _THUMB_EXT = ".jpg"
    _THUMB_FORMAT = "JPEG"
    _THUMB_MIME = "image/jpeg"
    logger.info("WebP 未サポート — サムネイルは JPEG フォールバック")

# Backward compatibility: constant referenced by existing code
_JPEG_QUALITY = _QUALITY

# -- pyvips backend detection --
try:
    import pyvips

    _USE_VIPS = True
    # Tame libvips internal resource usage:
    # - Reduce operation cache to limit lingering GObject refs
    # - Cap open file handles (default 100 is excessive for thumbnails)
    # - VIPS_CONCURRENCY env var controls internal thread pool size
    pyvips.cache_set_max(50)
    pyvips.cache_set_max_files(20)
    os.environ.setdefault("VIPS_CONCURRENCY", "2")
    logger.info(
        "pyvips %s.%s.%s 検出 — サムネイル生成に libvips を使用 (cache=%d, files=%d)",
        pyvips.version(0), pyvips.version(1), pyvips.version(2),
        pyvips.cache_get_max(), pyvips.cache_get_max_files(),
    )
except ImportError:
    _USE_VIPS = False

# Limit concurrent pyvips calls to avoid segfault on ARM64 (Pi 5).
# libvips uses its own internal thread pool; flooding it from many Python
# threads simultaneously crashes the process on ARM64.
# Default: min(cpu_count, 4) on x86_64, but capped to 2 on ARM64 for safety.
_cpu = os.cpu_count() or 2
import platform as _platform

_is_arm = _platform.machine().lower() in ("aarch64", "arm64", "armv7l")
_VIPS_MAX_CONCURRENT = int(os.environ.get(
    "YU_VIPS_CONCURRENCY",
    str(2 if _is_arm else min(_cpu, 4)),
))
_vips_semaphore = threading.Semaphore(_VIPS_MAX_CONCURRENT)

# -- Pillow-SIMD detection (logging only) --
try:
    import PIL

    _pillow_ver = PIL.__version__
    # Pillow-SIMD has suffixes like .post1
    _IS_PILLOW_SIMD = "post" in _pillow_ver
    if _IS_PILLOW_SIMD:
        logger.info("Pillow-SIMD %s 検出 — SIMD 最適化有効", _pillow_ver)
    else:
        logger.info("Pillow %s (標準)", _pillow_ver)
except Exception:
    _IS_PILLOW_SIMD = False

_cache_dir_ensured = False

# ---------------------------------------------------------------------------
# file_id → (path, mtime) source cache
# Eliminates a DB roundtrip on every thumbnail request (including mem_hit).
# ---------------------------------------------------------------------------
_source_cache: OrderedDict[int, tuple[str, object, float]] = OrderedDict()
_source_cache_lock = threading.Lock()
_SOURCE_CACHE_TTL = 60.0   # seconds
_SOURCE_CACHE_MAX = 10_000


def invalidate_thumbnail_source_cache() -> None:
    """Mark all cached entries as expiring in ~5 s instead of clearing immediately.

    Calling .clear() on a cache shared by 16 run_in_heavy_io threads causes a
    burst reconnect: every thread sees a cache miss simultaneously, launches a
    get_readonly_db() call, and 16 parallel PBKDF2 key derivations (~180 ms
    each) compete for CPU → each takes 2-3 s. Staggering expiry to 5 s from
    now means reconnects are spread over multiple request cycles instead of
    all hitting at once.  Data freshness is preserved: any file whose path/
    mtime actually changed will get a DB refresh within 5 s of the scan.
    """
    stale_ts = time.monotonic() - (_SOURCE_CACHE_TTL - 5.0)
    with _source_cache_lock:
        for k, (path, mtime, _ts) in list(_source_cache.items()):
            _source_cache[k] = (path, mtime, stale_ts)


def ensure_thumbnail_cache_dir() -> Path:
    """Create the cache directory (first call only)."""
    from core.paths import cache_path
    global _cache_dir_ensured
    cache_dir = cache_path("thumbnails")
    if not _cache_dir_ensured:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_dir_ensured = True
    return cache_dir


def lookup_thumbnail_source(file_id: int):
    now = time.monotonic()
    with _source_cache_lock:
        entry = _source_cache.get(file_id)
        if entry is not None:
            path, mtime, ts = entry
            if now - ts < _SOURCE_CACHE_TTL:
                _source_cache.move_to_end(file_id)
                return path, mtime

    from core.services_core.db_api import get_readonly_db

    con = get_readonly_db()
    row = con.execute("SELECT path, mtime FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return None
    path, mtime = row["path"], row["mtime"]
    with _source_cache_lock:
        if len(_source_cache) >= _SOURCE_CACHE_MAX:
            _source_cache.popitem(last=False)
        _source_cache[file_id] = (path, mtime, time.monotonic())
        _source_cache.move_to_end(file_id)
    return path, mtime


# ---------------------------------------------------------------------------
# Cache key computation (blake2b -- faster than MD5 and no openssl dep)
# ---------------------------------------------------------------------------

def _cache_key(file_path_str: str, file_mtime) -> str:
    """Compute cache key hash using blake2b (16-byte digest = 32 hex chars)."""
    return hashlib.blake2b(
        f"{file_path_str}:{file_mtime}".encode(), digest_size=16,
    ).hexdigest()


# ---------------------------------------------------------------------------
# Sharded cache path: cache/thumbnails/{h[0:2]}/{h[2:4]}/{h}{ext}
# ---------------------------------------------------------------------------

def _sharded_path(cache_dir: Path, hex_key: str, ext: str) -> Path:
    """Build 2-level sharded path for a cache key."""
    return cache_dir / hex_key[:2] / hex_key[2:4] / f"{hex_key}{ext}"


def _ensure_shard_dir(path: Path) -> None:
    """Create shard subdirectory if missing."""
    path.parent.mkdir(parents=True, exist_ok=True)


def cache_path_for_source(cache_dir: Path, file_path_str: str, file_mtime) -> Path:
    """Resolve cache file path with sharding and legacy fallback.

    Lookup order:
    1. Sharded WebP  (cache/thumbnails/ab/cd/abcd....webp)
    2. Sharded JPEG  (cache/thumbnails/ab/cd/abcd....jpg)  -- legacy format
    3. Flat WebP     (cache/thumbnails/abcd....webp)       -- pre-sharding
    4. Flat JPEG     (cache/thumbnails/abcd....jpg)         -- pre-sharding
    5. New sharded path (for generation)
    """
    hex_key = _cache_key(file_path_str, file_mtime)

    # Sharded path (current format)
    sharded = _sharded_path(cache_dir, hex_key, _THUMB_EXT)
    if sharded.exists():
        return sharded

    # Sharded JPEG (WebP upgrade path)
    if _USE_WEBP:
        sharded_jpg = _sharded_path(cache_dir, hex_key, ".jpg")
        if sharded_jpg.exists():
            return sharded_jpg

    # Legacy flat path (pre-sharding migration)
    flat = cache_dir / f"{hex_key}{_THUMB_EXT}"
    if flat.exists():
        return flat

    if _USE_WEBP:
        flat_jpg = cache_dir / f"{hex_key}.jpg"
        if flat_jpg.exists():
            return flat_jpg

    # New file: create sharded path
    _ensure_shard_dir(sharded)
    return sharded


# ---------------------------------------------------------------------------
# CacheStat: single stat() result carried through the pipeline
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CacheStat:
    """Pre-fetched stat result to avoid redundant stat() syscalls."""
    size: int
    mtime: int
    etag: str

    @staticmethod
    def from_path(p: Path) -> Optional["CacheStat"]:
        try:
            st = p.stat()
            return CacheStat(
                size=st.st_size,
                mtime=int(st.st_mtime),
                etag=f'"{st.st_size:x}-{int(st.st_mtime):x}"',
            )
        except OSError:
            return None


def save_image_thumbnail(img, cache_path: Path, image_module):
    """Generate and save a thumbnail from a PIL.Image using Pillow (WebP preferred, JPEG fallback)."""
    img.thumbnail(THUMBNAIL_SIZE, image_module.Resampling.BILINEAR)
    img.convert("RGB").save(cache_path, _THUMB_FORMAT, quality=_QUALITY)


# -- pyvips fast path --

def _vips_save(img, cache_path: Path) -> None:
    """Save in optimal format (WebP/JPEG) via pyvips."""
    if _USE_WEBP:
        img.webpsave(str(cache_path), Q=_QUALITY)
    else:
        img.jpegsave(str(cache_path), Q=_QUALITY)


def vips_thumbnail_from_path(file_path: str, cache_path: Path) -> bool:
    """Generate a thumbnail directly from a file path via pyvips.

    Significantly faster than Pillow for JPEG thanks to shrink-on-load.
    Returns True on success, False on failure (caller falls back to Pillow).
    """
    if not _USE_VIPS:
        return False
    if not _vips_semaphore.acquire(timeout=8.0):
        logger.debug("vips semaphore timeout (busy)")
        return False
    try:
        img = pyvips.Image.thumbnail(file_path, _THUMBNAIL_WIDTH)
        _vips_save(img, cache_path)
        return True
    except Exception as exc:
        logger.debug("vips thumbnail_from_path failed: %s", exc)
        return False
    finally:
        _vips_semaphore.release()


def vips_thumbnail_from_buffer(data: bytes, cache_path: Path) -> bool:
    """Generate a thumbnail from bytes via pyvips (for files inside ZIP/7z).

    Returns True on success, False on failure.
    """
    if not _USE_VIPS:
        return False
    if not _vips_semaphore.acquire(timeout=8.0):
        logger.debug("vips semaphore timeout (busy)")
        return False
    try:
        img = pyvips.Image.thumbnail_buffer(data, _THUMBNAIL_WIDTH)
        _vips_save(img, cache_path)
        return True
    except Exception as exc:
        logger.debug("vips thumbnail_from_buffer failed: %s", exc)
        return False
    finally:
        _vips_semaphore.release()


def get_thumbnail_backend_info() -> dict:
    """Return current thumbnail backend information."""
    info = {"backend": "pillow", "pillow_simd": _IS_PILLOW_SIMD, "format": _THUMB_FORMAT.lower(), "webp": _USE_WEBP}
    if _USE_VIPS:
        info["backend"] = "pyvips"
        info["vips_version"] = f"{pyvips.version(0)}.{pyvips.version(1)}.{pyvips.version(2)}"
    if _IS_PILLOW_SIMD:
        info["pillow_version"] = _pillow_ver
    return info

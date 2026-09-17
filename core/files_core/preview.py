"""Preview (intermediate resolution) image generation service.

Returns 1200px intermediate resolution instead of full size (4K, etc.)
in the detail modal. Reuses via disk cache to improve transfer size and display speed.
"""

import contextlib
import hashlib
import logging
import os
import time
from collections import OrderedDict
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import Lock

from .original import serve_original
from .response_types import FileBytes, FileError, FilePath, FileResult

logger = logging.getLogger(__name__)

_PREVIEW_MAX_DIM = 1200
_PREVIEW_QUALITY = 82
_cache_dir_ensured = False

# Small memory cache for previews (100 entries / 50 MB).
# Preview disk reads are fast but SQLCipher reconnects still hurt on the
# initial lookup_thumbnail_source call; the mem cache skips both the DB
# query AND the disk read for the most-recently-viewed files.
_PREVIEW_MEM_MAX = int(os.environ.get("YU_PREVIEW_MEM_MAX", "100"))
_PREVIEW_MEM_BYTES = int(os.environ.get("YU_PREVIEW_MEM_MB", "50")) * 1024 * 1024
_preview_mem: OrderedDict[str, tuple[bytes, str, str, int]] = OrderedDict()
_preview_mem_bytes = 0
_preview_mem_lock = Lock()
_inflight_preview_lock = Lock()
_inflight_preview: dict[str, "Future[FileResult]"] = {}


def _preview_mem_get(key: str) -> tuple[bytes, str, str] | None:
    with _preview_mem_lock:
        entry = _preview_mem.get(key)
        if entry is None:
            return None
        _preview_mem.move_to_end(key)
        return entry[0], entry[1], entry[2]


def _preview_mem_put(key: str, data: bytes, mime: str, etag: str) -> None:
    global _preview_mem_bytes
    size = len(data)
    if size > _PREVIEW_MEM_BYTES // 4:
        return
    with _preview_mem_lock:
        old = _preview_mem.pop(key, None)
        if old:
            _preview_mem_bytes -= old[3]
        while _preview_mem_bytes + size > _PREVIEW_MEM_BYTES or len(_preview_mem) >= _PREVIEW_MEM_MAX:
            if not _preview_mem:
                break
            _, evicted = _preview_mem.popitem(last=False)
            _preview_mem_bytes -= evicted[3]
        _preview_mem[key] = (data, mime, etag, size)
        _preview_mem_bytes += size


def _run_singleflight_preview(cache_key: str, generate_fn, *, timeout_sec: float = 10.0) -> FileResult:
    with _inflight_preview_lock:
        if cache_key in _inflight_preview:
            fut = _inflight_preview[cache_key]
            leader = False
        else:
            fut: Future[FileResult] = Future()
            _inflight_preview[cache_key] = fut
            leader = True

    if leader:
        try:
            result = generate_fn()
            fut.set_result(result)
        except Exception as exc:
            fut.set_exception(exc)
        finally:
            with _inflight_preview_lock:
                if _inflight_preview.get(cache_key) is fut:
                    del _inflight_preview[cache_key]
        return fut.result()

    try:
        return fut.result(timeout=timeout_sec)
    except FutureTimeoutError:
        return FileError("Preview generation timed out", 504)


def _ensure_preview_cache_dir() -> Path:
    from core.paths import cache_path
    global _cache_dir_ensured
    cache_dir = cache_path("previews")
    if not _cache_dir_ensured:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_dir_ensured = True
    return cache_dir


def serve_preview(file_id: int) -> FileResult:
    """Return an intermediate-resolution preview for file_id.

    Returns the original as-is if the longest side is within _PREVIEW_MAX_DIM.
    Falls back to the original for video/audio/PDF files.
    """
    from core.infra_core.debug_log import dlog

    from .thumbnail_common import _USE_WEBP, lookup_thumbnail_source

    t0 = time.perf_counter()
    source = lookup_thumbnail_source(file_id)
    t_lookup = time.perf_counter()
    if not source:
        return FileError("Not found", 404)

    file_path_str: str = source[0]
    file_mtime = source[1]

    # Video/audio/PDF are not resized for preview — return original
    from .media_types import is_audio_file, is_video_file
    check_path = file_path_str.split("!")[-1] if "!" in file_path_str else file_path_str
    if is_video_file(check_path) or is_audio_file(check_path) or check_path.lower().endswith(".pdf"):
        return serve_original(file_id)

    cache_dir = _ensure_preview_cache_dir()
    ext = ".webp" if _USE_WEBP else ".jpg"
    cache_key = hashlib.sha256(f"preview:{file_path_str}:{file_mtime}".encode()).hexdigest()[:32]
    cache_path = cache_dir / f"{cache_key}{ext}"

    # Memory cache hit — skip disk read entirely
    mem_hit = _preview_mem_get(cache_key)
    if mem_hit:
        data, mime, etag = mem_hit
        dlog("files", "preview.mem_hit", file_id=file_id,
             lookup_ms=int((t_lookup - t0) * 1000))
        return FileBytes(data=data, mime_type=mime, etag=etag,
                         cache_control="public, max-age=86400, stale-while-revalidate=604800")

    # Also check legacy cache format
    if _USE_WEBP and not cache_path.exists():
        old_jpg = cache_dir / f"{cache_key}.jpg"
        if old_jpg.exists():
            cache_path = old_jpg

    if cache_path.exists():
        try:
            stat = cache_path.stat()
            etag = f'"{stat.st_size:x}-{int(stat.st_mtime):x}"'
            mime = "image/webp" if cache_path.suffix == ".webp" else "image/jpeg"
            data = cache_path.read_bytes()
            _preview_mem_put(cache_key, data, mime, etag)
            dlog("files", "preview.disk_hit", file_id=file_id,
                 lookup_ms=int((t_lookup - t0) * 1000),
                 disk_read_ms=int((time.perf_counter() - t_lookup) * 1000))
            return FileBytes(data=data, mime_type=mime, etag=etag,
                             cache_control="public, max-age=86400, stale-while-revalidate=604800")
        except OSError:
            pass

    # Generate preview from original — singleflight to coalesce concurrent requests
    def _do_generate() -> FileResult:
        original = serve_original(file_id)
        if isinstance(original, FileError):
            return original

        try:
            if isinstance(original, FilePath):
                try:
                    fsize = original.path.stat().st_size
                    if fsize < 200 * 1024:
                        return original
                except OSError:
                    pass
                result = _generate_preview_from_path(original.path, cache_path, _USE_WEBP, original)
            elif isinstance(original, FileBytes):
                if len(original.data) < 200 * 1024:
                    return original
                result = _generate_preview_from_bytes(original.data, cache_path, _USE_WEBP, original)
            else:
                return original

            if cache_path.exists():
                try:
                    data = cache_path.read_bytes()
                    mime = "image/webp" if cache_path.suffix == ".webp" else "image/jpeg"
                    stat = cache_path.stat()
                    etag = f'"{stat.st_size:x}-{int(stat.st_mtime):x}"'
                    _preview_mem_put(cache_key, data, mime, etag)
                except OSError:
                    pass
            return result
        except Exception as exc:
            logger.debug("Preview generation failed, falling back to original: %s", exc)
            with contextlib.suppress(OSError):
                cache_path.unlink(missing_ok=True)
            return original

    tg0 = time.perf_counter()
    result = _run_singleflight_preview(cache_key, _do_generate)
    dlog("files", "preview.generated", file_id=file_id,
         lookup_ms=int((t_lookup - t0) * 1000),
         generate_ms=int((time.perf_counter() - tg0) * 1000))
    return result


def _resize_and_save(img, cache_path: Path, use_webp: bool, original: FileResult) -> FileResult:
    """Common resize + encode path. Caller has already opened the PIL image
    and (optionally) called ``draft()`` for JPEG to reduce decode cost."""
    from PIL import Image

    w, h = img.size
    if max(w, h) <= _PREVIEW_MAX_DIM:
        return original

    ratio = _PREVIEW_MAX_DIM / max(w, h)
    new_w = max(1, int(w * ratio))
    new_h = max(1, int(h * ratio))
    # BICUBIC is 2-3x faster than LANCZOS and visually indistinguishable for
    # the 4K -> 1200px downscale range that this preview targets.
    img = img.resize((new_w, new_h), Image.Resampling.BICUBIC)

    fmt = "WEBP" if use_webp else "JPEG"
    img.convert("RGB").save(cache_path, fmt, quality=_PREVIEW_QUALITY)

    stat = cache_path.stat()
    etag = f'"{stat.st_size:x}-{int(stat.st_mtime):x}"'
    mime = "image/webp" if use_webp else "image/jpeg"
    return FilePath(path=cache_path, mime_type=mime, etag=etag,
                    cache_control="public, max-age=86400, stale-while-revalidate=604800")


def _generate_preview_from_path(src_path: Path, cache_path: Path, use_webp: bool, original: FileResult) -> FileResult:
    from PIL import Image

    img = Image.open(src_path)
    # JPEG draft() decodes at a reduced resolution (1/2, 1/4, 1/8 of the
    # original). For the 4K -> 1200px target this single call cuts decode
    # time from ~500 ms to ~80 ms on typical photos.
    if (img.format or "").upper() == "JPEG":
        img.draft("RGB", (_PREVIEW_MAX_DIM * 2, _PREVIEW_MAX_DIM * 2))
    return _resize_and_save(img, cache_path, use_webp, original)


def _generate_preview_from_bytes(img_data: bytes, cache_path: Path, use_webp: bool, original: FileResult) -> FileResult:
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(img_data))
    if (img.format or "").upper() == "JPEG":
        img.draft("RGB", (_PREVIEW_MAX_DIM * 2, _PREVIEW_MAX_DIM * 2))
    return _resize_and_save(img, cache_path, use_webp, original)

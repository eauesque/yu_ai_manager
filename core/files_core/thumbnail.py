"""Thumbnail service used by routes/files.py."""

import logging
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import Lock

from core.files_core.thumbnail_mem_cache import (
    mem_get,
    mem_put,
)
from core.files_core.thumbnail_touch_queue import queue_touch
from core.infra_core.debug_log import dlog

from .media import audio_placeholder, is_audio_file, send_cached_image
from .response_types import FileError, FileResult
from .thumbnail_common import CacheStat, cache_path_for_source, ensure_thumbnail_cache_dir, lookup_thumbnail_source
from .thumbnail_plain import serve_plain_thumbnail
from .thumbnail_rar import serve_rar_thumbnail
from .thumbnail_sevenz import serve_7z_thumbnail
from .thumbnail_zip import serve_zip_thumbnail

logger = logging.getLogger(__name__)

_inflight_lock = Lock()
_inflight_thumb: dict[str, Future[FileResult]] = {}


def _wait_for_warmup_cache(file_path_str: str, cache_path: Path) -> bool:
    from core.helpers_core.helpers_text_path import split_archive_path

    from .thumbnail_batch_warmup import _archive_done_cv_lock, _archive_done_cvs

    archive_path, _ = split_archive_path(file_path_str)
    with _archive_done_cv_lock:
        cv = _archive_done_cvs.get(archive_path)
    if cv is None:
        return False
    with cv:
        cv.wait_for(lambda: cache_path.exists(), timeout=2.0)
    return cache_path.exists()


def _release_inflight(cache_key: str, fut: Future[FileResult]) -> None:
    with _inflight_lock:
        cur = _inflight_thumb.get(cache_key)
        if cur is fut:
            _inflight_thumb.pop(cache_key, None)


def _run_singleflight_thumb(cache_key: str, submit_fn, *, timeout_sec: float) -> FileResult:
    created = False
    with _inflight_lock:
        fut = _inflight_thumb.get(cache_key)
        if fut is None or fut.done():
            fut = submit_fn()
            _inflight_thumb[cache_key] = fut
            created = True
    if created:
        fut.add_done_callback(lambda done: _release_inflight(cache_key, done))
    return fut.result(timeout=timeout_sec)


def serve_thumbnail(file_id: int) -> FileResult:
    from PIL import Image, UnidentifiedImageError

    t0 = time.perf_counter()
    cache_dir = ensure_thumbnail_cache_dir()
    source = lookup_thumbnail_source(file_id)
    t_lookup = time.perf_counter()
    if not source:
        dlog("files", "thumbnail.not_found", file_id=file_id)
        return FileError("Not found", 404)

    file_path_str, file_mtime = source
    cache_path = cache_path_for_source(cache_dir, file_path_str, file_mtime)
    cache_key = cache_path.name

    t_mem0 = time.perf_counter()
    mem_hit = mem_get(cache_key)
    t_mem1 = time.perf_counter()
    if mem_hit:
        data, mime, etag = mem_hit
        queue_touch(file_id, cache_path)
        t_serve = time.perf_counter()
        dlog("files", "thumbnail.mem_hit", file_id=file_id,
             lookup_ms=int((t_lookup - t0) * 1000),
             cache_ms=int((t_mem1 - t_mem0) * 1000),
             touch_ms=int((t_serve - t_mem1) * 1000),
             total_ms=int((t_serve - t0) * 1000))
        from .response_types import FileBytes
        return FileBytes(data=data, mime_type=mime, etag=etag, cache_control="public, max-age=86400, immutable, stale-while-revalidate=604800")

    t_stat0 = time.perf_counter()
    cs = CacheStat.from_path(cache_path)
    t_stat1 = time.perf_counter()
    if cs is not None:
        t_disk0 = time.perf_counter()
        try:
            data = cache_path.read_bytes()
            t_read1 = time.perf_counter()
            from .media_placeholders import _mime_for_cached
            mime = _mime_for_cached(cache_path)
            mem_put(cache_key, data, mime, cs.etag)
        except OSError:
            t_read1 = time.perf_counter()
            pass
        t_done = time.perf_counter()
        dlog("files", "thumbnail.disk_hit", file_id=file_id,
             lookup_ms=int((t_lookup - t0) * 1000),
             stat_ms=int((t_stat1 - t_stat0) * 1000),
             read_ms=int((t_read1 - t_disk0) * 1000),
             process_ms=int((t_done - t_read1) * 1000),
             total_ms=int((t_done - t0) * 1000))
        queue_touch(file_id, cache_path)
        return send_cached_image(cache_path, cs=cs)

    from core.infra_core.thread_pool import submit as _pool_submit

    def _generate() -> FileResult:
        from core.helpers_core.helpers_text_path import (
            archive_part as _ap,
        )
        from core.helpers_core.helpers_text_path import (
            is_archive_member,
            split_archive_path,
        )

        tg0 = time.perf_counter()
        is_archive = is_archive_member(file_path_str)
        dlog("files", "thumbnail.request", file_id=file_id, zip_mode=is_archive, path=file_path_str)
        if not is_archive:
            result = serve_plain_thumbnail(file_path_str, cache_path, Image, UnidentifiedImageError)
            dlog("files", "thumbnail.generated_plain", file_id=file_id,
                 generate_ms=int((time.perf_counter() - tg0) * 1000))
            return result

        # Quick path: warmup may have already produced this cache entry.
        if _wait_for_warmup_cache(file_path_str, cache_path):
            dlog("files", "thumbnail.warmup_cache_hit", file_id=file_id,
                 wait_ms=int((time.perf_counter() - tg0) * 1000))
            return send_cached_image(cache_path)

        # Coalesce concurrent requests for the same archive through the
        # per-archive lock used by warmup. Without this, opening a
        # container view kicks off N parallel ZIP opens of the SAME file
        # (one per visible thumbnail) which thrashes the disk and is the
        # main reason "アーカイブを開くと重い" persists even with warmup.
        from .thumbnail_batch_warmup_core import _get_archive_lock

        archive_path_str, _ignored = split_archive_path(file_path_str)
        lock = _get_archive_lock(archive_path_str)
        tlock = time.perf_counter()
        acquired = lock.acquire(timeout=3.0)
        lock_wait_ms = int((time.perf_counter() - tlock) * 1000)
        if not acquired:
            from .media_placeholders import _transient_error_placeholder_bytes
            return _transient_error_placeholder_bytes()
        try:
            if cache_path.exists():
                # Peer thread (or warmup) produced our cache while we waited.
                dlog("files", "thumbnail.lock_peer_cache_hit", file_id=file_id,
                     lock_wait_ms=lock_wait_ms)
                return send_cached_image(cache_path)
            ext = _ap(file_path_str).lower()
            if ext.endswith(".7z"):
                result = serve_7z_thumbnail(file_id, file_path_str, cache_path, Image, UnidentifiedImageError)
            elif ext.endswith(".rar"):
                result = serve_rar_thumbnail(file_id, file_path_str, cache_path, Image, UnidentifiedImageError)
            else:
                result = serve_zip_thumbnail(file_id, file_path_str, cache_path, Image, UnidentifiedImageError)
            dlog("files", "thumbnail.generated_archive", file_id=file_id,
                 lock_wait_ms=lock_wait_ms,
                 generate_ms=int((time.perf_counter() - tg0) * 1000) - lock_wait_ms)
            return result
        finally:
            if acquired:
                lock.release()

    try:
        response = _run_singleflight_thumb(cache_key, lambda: _pool_submit(_generate), timeout_sec=5)
    except FutureTimeoutError:
        logger.warning("サムネイル生成タイムアウト: file_id=%d", file_id)
        dlog("files", "thumbnail.timeout", file_id=file_id)
        return FileError("Thumbnail generation timeout", 504)
    except Exception as e:
        logger.error("Thumbnail error: %s", e, exc_info=True)
        dlog("files", "thumbnail.error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        if "!" not in file_path_str:
            file_path = Path(file_path_str)
            if file_path.exists() and is_audio_file(file_path_str):
                return audio_placeholder(cache_path, file_path.name)
        # Do NOT persist a placeholder to cache_path here. A transient error
        # (ImportError, OSError, brief lock contention, ...) would otherwise
        # overwrite a perfectly recoverable archive entry with a "FILE ERROR"
        # JPEG that sticks forever — that bug polluted hundreds of cache
        # entries when v4.119.14 shipped with a broken `_get_archive_lock`
        # import. Return placeholder bytes from memory instead.
        from .media_placeholders import _transient_error_placeholder_bytes
        return _transient_error_placeholder_bytes()

    if cache_path.exists():
        try:
            data = cache_path.read_bytes()
            from .media_placeholders import _mime_for_cached
            mime = _mime_for_cached(cache_path)
            new_cs = CacheStat.from_path(cache_path)
            if new_cs:
                mem_put(cache_key, data, mime, new_cs.etag)
        except OSError:
            pass
        queue_touch(file_id, cache_path)
    return response

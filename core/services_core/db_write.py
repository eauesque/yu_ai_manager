"""Single-writer execution helpers for SQLite write serialization.

SQLite is fundamentally single-writer. This module makes that constraint
explicit by funnelling high-contention write workloads through one dedicated
writer thread.
"""

from __future__ import annotations

import asyncio
import functools
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from typing import Any, TypeVar

T = TypeVar("T")

_WRITER_PREFIX = "db-writer"
_db_writer_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=_WRITER_PREFIX)
_SLOW_LOG_MS = max(1, int((os.environ.get("TAGDB_DB_SLOW_MS") or "250").strip()))

# Rate-limit read-connection invalidation so burst writes (e.g. retag batch of
# 2000+) don't hammer the staggered-reconnect window in get_readonly_db().
# 2.0 s ≈ one full stagger window (_READONLY_RECONNECT_STAGGER = 3.5 s), so
# a second invalidation burst arriving before all threads finish reconnecting
# is collapsed into a single new wave rather than restarting individual timers.
# The writer thread is single-threaded so no lock is needed here.
_INVALIDATION_MIN_INTERVAL = 2.0  # seconds (was 0.2)
_last_invalidation_ts: float = 0.0


def _describe_fn(fn: Callable[..., Any]) -> str:
    return (
        getattr(fn, "__qualname__", None)
        or getattr(fn, "__name__", None)
        or repr(fn)
    )


def _capture_request_meta() -> dict[str, Any]:
    try:
        from quart import g, request

        return {
            "request_id": getattr(g, "request_id", None),
            "path": getattr(request, "path", None),
            "method": getattr(request, "method", None),
        }
    except Exception:
        return {}


def _log_slow_db_write(
    *,
    fn_name: str,
    queue_wait_ms: int,
    exec_ms: int,
    request_meta: dict[str, Any],
    wait_mode: str,
) -> None:
    if queue_wait_ms < _SLOW_LOG_MS and exec_ms < _SLOW_LOG_MS:
        return
    from core.infra_core.debug_log import dlog

    dlog(
        "db",
        "submit_db_write.slow",
        fn=fn_name,
        wait_mode=wait_mode,
        queue_wait_ms=queue_wait_ms,
        exec_ms=exec_ms,
        total_ms=queue_wait_ms + exec_ms,
        request_id=request_meta.get("request_id"),
        method=request_meta.get("method"),
        path=request_meta.get("path"),
    )


def _invalidate_readonly_after_write() -> None:
    global _last_invalidation_ts
    now = time.perf_counter()
    if now - _last_invalidation_ts < _INVALIDATION_MIN_INTERVAL:
        return
    _last_invalidation_ts = now
    with suppress(Exception):
        from core.services_core.db_state_connections import invalidate_readonly_connections

        invalidate_readonly_connections()


def _capture_app_ctx():
    try:
        from quart.globals import _cv_app
        return _cv_app.get(None)
    except (ImportError, LookupError):
        return None


def _run_with_app_ctx(fn: Callable[..., T], *args: Any, _app_ctx=None, **kwargs: Any) -> T:
    token = None
    try:
        if _app_ctx is not None:
            from quart.globals import _cv_app
            token = _cv_app.set(_app_ctx)
        return fn(*args, **kwargs)
    finally:
        if token is not None:
            from quart.globals import _cv_app
            _cv_app.reset(token)
        # NOTE: do NOT close thread-local DB connections here.
        # _db_writer_executor is a single-thread pool whose worker lives for
        # the app lifetime. Closing the writer's connection after every call
        # forces SQLCipher to re-derive its PBKDF2 key + reapply 7 PRAGMAs +
        # set up 1 GiB mmap on the next call (~250-490 ms per open observed
        # in debug_log: _flush_touch_batch._write exec_ms=289-487 even after
        # we moved Path.stat() off the writer in v4.128.23). db_async.run_db_sync
        # made this same fix earlier — the writer side just hadn't followed.
        # The thread-local cache in _get_cached_connection validates path +
        # liveness, so DB-path swaps still work safely without closing here.


def _run_with_timing(
    fn: Callable[..., T],
    *args: Any,
    submitted_at: float,
    fn_name: str,
    request_meta: dict[str, Any],
    wait_mode: str,
    _app_ctx=None,
    **kwargs: Any,
) -> T:
    started_at = time.perf_counter()
    try:
        return _run_with_app_ctx(fn, *args, _app_ctx=_app_ctx, **kwargs)
    finally:
        _invalidate_readonly_after_write()
        exec_ms = int((time.perf_counter() - started_at) * 1000)
        queue_wait_ms = int((started_at - submitted_at) * 1000)
        _log_slow_db_write(
            fn_name=fn_name,
            queue_wait_ms=queue_wait_ms,
            exec_ms=exec_ms,
            request_meta=request_meta,
            wait_mode=wait_mode,
        )


def submit_db_write(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute a write task on the dedicated SQLite writer thread."""
    if threading.current_thread().name.startswith(_WRITER_PREFIX):
        try:
            return fn(*args, **kwargs)
        finally:
            _invalidate_readonly_after_write()

    app_ctx = _capture_app_ctx()
    request_meta = _capture_request_meta()
    submitted_at = time.perf_counter()
    fn_name = _describe_fn(fn)
    future = _db_writer_executor.submit(
        _run_with_timing,
        fn,
        *args,
        submitted_at=submitted_at,
        fn_name=fn_name,
        request_meta=request_meta,
        wait_mode="blocking",
        _app_ctx=app_ctx,
        **kwargs,
    )
    return future.result()


def submit_db_write_no_wait(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Enqueue a write task on the dedicated SQLite writer thread and return immediately."""
    if threading.current_thread().name.startswith(_WRITER_PREFIX):
        try:
            fn(*args, **kwargs)
        finally:
            _invalidate_readonly_after_write()
        return

    app_ctx = _capture_app_ctx()
    request_meta = _capture_request_meta()
    submitted_at = time.perf_counter()
    fn_name = _describe_fn(fn)
    _db_writer_executor.submit(
        _run_with_timing,
        fn,
        *args,
        submitted_at=submitted_at,
        fn_name=fn_name,
        request_meta=request_meta,
        wait_mode="fire_and_forget",
        _app_ctx=app_ctx,
        **kwargs,
    )


async def run_db_write(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Async wrapper for submit_db_write()."""
    if threading.current_thread().name.startswith(_WRITER_PREFIX):
        return fn(*args, **kwargs)

    app_ctx = _capture_app_ctx()
    request_meta = _capture_request_meta()
    submitted_at = time.perf_counter()
    fn_name = _describe_fn(fn)
    loop = asyncio.get_running_loop()
    task = functools.partial(
        _run_with_timing,
        fn,
        *args,
        submitted_at=submitted_at,
        fn_name=fn_name,
        request_meta=request_meta,
        wait_mode="async",
        _app_ctx=app_ctx,
        **kwargs,
    )
    return await loop.run_in_executor(_db_writer_executor, task)

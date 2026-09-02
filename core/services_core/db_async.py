"""Helper for safely executing synchronous DB functions in an asyncio environment.

Used when calling SQLite (synchronous) from Quart async route handlers.
Delegates to a dedicated worker thread pool and cleans up
thread-local DB connections after completion.

The dedicated pool prevents SSE connections from starving DB queries
(the root cause of server hangs under long-running operation).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

# Dedicated thread pool for DB operations.
_db_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="db-pool")
_SLOW_LOG_MS = max(1, int((os.environ.get("TAGDB_DB_SLOW_MS") or "250").strip()))


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


def _log_slow_db_call(
    *,
    fn_name: str,
    queue_wait_ms: int,
    exec_ms: int,
    request_meta: dict[str, Any],
    error: str | None = None,
) -> None:
    if queue_wait_ms < _SLOW_LOG_MS and exec_ms < _SLOW_LOG_MS:
        return
    from core.infra_core.debug_log import dlog

    dlog(
        "db",
        "run_db_sync.slow",
        fn=fn_name,
        queue_wait_ms=queue_wait_ms,
        exec_ms=exec_ms,
        total_ms=queue_wait_ms + exec_ms,
        request_id=request_meta.get("request_id"),
        method=request_meta.get("method"),
        path=request_meta.get("path"),
        error=error,
    )


async def run_db_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute a synchronous DB function in the DB thread pool.

    Uses a dedicated executor to prevent thread starvation.
    Propagates the Quart app context to the worker thread via
    contextvars (Quart's push/pop are async, so we use the
    underlying ContextVar directly).
    """
    # Capture app context on the event loop thread
    _app_ctx = None
    try:
        from quart.globals import _cv_app
        _app_ctx = _cv_app.get(None)
    except (ImportError, LookupError):
        pass
    request_meta = _capture_request_meta()
    submitted_at = time.perf_counter()
    fn_name = _describe_fn(fn)

    def _wrapper() -> T:
        token = None
        started_at = time.perf_counter()
        error: str | None = None
        try:
            if _app_ctx is not None:
                from quart.globals import _cv_app
                token = _cv_app.set(_app_ctx)
            return fn(*args, **kwargs)
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            exec_ms = int((time.perf_counter() - started_at) * 1000)
            queue_wait_ms = int((started_at - submitted_at) * 1000)
            _log_slow_db_call(
                fn_name=fn_name,
                queue_wait_ms=queue_wait_ms,
                exec_ms=exec_ms,
                request_meta=request_meta,
                error=error,
            )
            if token is not None:
                from quart.globals import _cv_app
                _cv_app.reset(token)
            # NOTE: do NOT close thread-local DB connections here.
            # _db_executor uses a fixed 16-worker pool whose threads live for
            # the app lifetime. Closing the readonly conn after every call
            # forces SQLCipher to re-derive its PBKDF2 key on the next call
            # (~180 ms per open), which dominated this function's exec_ms
            # for hot endpoints like /api/favorites/check (300+ ms despite
            # the underlying SELECT taking <1 ms). The thread-local cache
            # in _get_cached_connection already validates path + liveness,
            # so connections survive safely across DB-path swaps.

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_db_executor, _wrapper)

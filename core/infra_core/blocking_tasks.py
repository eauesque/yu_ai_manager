"""Helpers for running non-DB blocking work away from the Quart event loop."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_MAX_WORKERS = max(2, int((os.environ.get("TAGDB_BLOCKING_WORKERS") or "4").strip()))
_LONG_MAX_WORKERS = max(1, int((os.environ.get("TAGDB_LONG_BLOCKING_WORKERS") or "2").strip()))
_SLOW_LOG_MS = max(1, int((os.environ.get("TAGDB_BLOCKING_SLOW_MS") or "500").strip()))
# Long-pool tasks (NAI/SD/ComfyUI generate, model inference, media conversion)
# are *expected* to take several seconds — that's why they live in a separate
# pool. A 500ms threshold floods debug logs with NAI's normal ~5s response
# time, and even 10s still catches typical SD WebUI / ComfyUI generates
# (~30-60s). Default to 30s so only genuinely anomalous waits (queue
# starvation in the long pool or a stuck inference) surface as `.slow`.
# Override via TAGDB_LONG_BLOCKING_SLOW_MS for power users who want
# verbose timing.
_LONG_SLOW_LOG_MS = max(
    1, int((os.environ.get("TAGDB_LONG_BLOCKING_SLOW_MS") or "30000").strip())
)
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="blocking")
_long_executor = ThreadPoolExecutor(max_workers=_LONG_MAX_WORKERS, thread_name_prefix="blocking-long")


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


def _log_slow_call(
    *,
    fn_name: str,
    queue_wait_ms: int,
    exec_ms: int,
    request_meta: dict[str, Any],
    error: str | None = None,
    pool: str = "shared",
) -> None:
    threshold = _LONG_SLOW_LOG_MS if pool == "long" else _SLOW_LOG_MS
    if queue_wait_ms < threshold and exec_ms < threshold:
        return
    from core.infra_core.debug_log import dlog

    # The event name distinguishes the two pools so perf reviews can tell
    # apart "shared pool starvation" (real concern) from "long-running work in
    # its dedicated pool" (expected — does not block status/thumbnail handlers).
    event = "run_long_blocking_sync.slow" if pool == "long" else "run_blocking_sync.slow"
    dlog(
        "blocking",
        event,
        fn=fn_name,
        pool=pool,
        queue_wait_ms=queue_wait_ms,
        exec_ms=exec_ms,
        total_ms=queue_wait_ms + exec_ms,
        request_id=request_meta.get("request_id"),
        method=request_meta.get("method"),
        path=request_meta.get("path"),
        error=error,
    )


async def run_blocking_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute blocking non-DB work in a small shared executor.

    Use this for model/provider detection and short status checks from Quart
    handlers. Long inference or media conversion should use
    ``run_long_blocking_sync``. SQLite-heavy work should continue to use
    ``core.services_core.db_async.run_db_sync``.
    """
    request_meta = _capture_request_meta()
    submitted_at = time.perf_counter()
    fn_name = _describe_fn(fn)

    def _wrapper() -> T:
        started_at = time.perf_counter()
        error: str | None = None
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            exec_ms = int((time.perf_counter() - started_at) * 1000)
            queue_wait_ms = int((started_at - submitted_at) * 1000)
            _log_slow_call(
                fn_name=fn_name,
                queue_wait_ms=queue_wait_ms,
                exec_ms=exec_ms,
                request_meta=request_meta,
                error=error,
            )
            try:
                from core.services_core.db_state import close_thread_connections
                close_thread_connections()
            except Exception:
                logger.warning("infrastructure step failed", exc_info=True)

    loop = asyncio.get_running_loop()
    # Propagate contextvars (Quart app/request context, etc.) into the worker
    # thread so handlers that touch `current_app`, `g`, or `request` keep
    # working — `loop.run_in_executor` does NOT copy contextvars on its own,
    # while `asyncio.to_thread` does. Without this, swapping a `to_thread`
    # call to `run_blocking_sync` silently breaks Quart-context-dependent code.
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(_executor, functools.partial(ctx.run, _wrapper))


async def run_long_blocking_sync(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute long-running non-DB work without occupying status/check workers."""
    request_meta = _capture_request_meta()
    submitted_at = time.perf_counter()
    fn_name = _describe_fn(fn)

    def _wrapper() -> T:
        started_at = time.perf_counter()
        error: str | None = None
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            exec_ms = int((time.perf_counter() - started_at) * 1000)
            queue_wait_ms = int((started_at - submitted_at) * 1000)
            _log_slow_call(
                fn_name=fn_name,
                queue_wait_ms=queue_wait_ms,
                exec_ms=exec_ms,
                request_meta=request_meta,
                error=error,
                pool="long",
            )
            try:
                from core.services_core.db_state import close_thread_connections
                close_thread_connections()
            except Exception:
                logger.warning("infrastructure step failed", exc_info=True)

    loop = asyncio.get_running_loop()
    # See note in run_blocking_sync: copy contextvars so Quart context
    # (current_app / g / request) propagates into the worker thread.
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(_long_executor, functools.partial(ctx.run, _wrapper))

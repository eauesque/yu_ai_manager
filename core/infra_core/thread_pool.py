"""Application-shared thread pool.

Separates heavy synchronous operations (thumbnail generation, CLI calls, etc.)
from request threads to prevent Quart thread pool exhaustion.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_SLOW_LOG_MS = max(1, int((os.environ.get("TAGDB_HEAVY_IO_SLOW_MS") or "500").strip()))

# Worker count: based on CPU cores.
# At 200K+ files, cache-miss bursts need headroom for concurrent ZIP
# decompression + PIL encoding.  The vips semaphore separately caps
# the CPU-heavy image encoding, so extra workers mainly help I/O overlap.
# ARM64 (Pi 5): capped at 8 to avoid memory pressure on 8GB devices.
# x86_64: up to 16 for high-throughput cache-miss recovery.
import platform as _platform

_is_arm = _platform.machine().lower() in ("aarch64", "arm64", "armv7l")
_MAX_WORKERS = int(os.environ.get(
    "YU_HEAVY_IO_WORKERS",
    str(min(max((os.cpu_count() or 2) * 2, 4), 8 if _is_arm else 16)),
))

_pool: ThreadPoolExecutor | None = None


def get_pool() -> ThreadPoolExecutor:
    """Return the shared ThreadPoolExecutor (lazily created)."""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS,
            thread_name_prefix="heavy-io",
        )
        logger.info("ThreadPoolExecutor 起動: max_workers=%d", _MAX_WORKERS)
    return _pool


def submit(fn: Callable[..., T], *args, **kwargs) -> Future[T]:
    """Submit a task to the thread pool."""
    return get_pool().submit(fn, *args, **kwargs)


async def run_in_heavy_io(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Async wrapper: run a sync callable on the heavy-io pool.

    Use for thumbnail / preview / original media routes so disk-IO + PIL work
    does not occupy DB executor slots. The inner code may still issue tiny DB
    lookups (path resolution); that's fine because the connection pool is
    thread-local and short queries don't pin the DB executor.
    """
    submitted_at = time.perf_counter()

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
            if exec_ms >= _SLOW_LOG_MS or queue_wait_ms >= _SLOW_LOG_MS:
                try:
                    from core.infra_core.debug_log import dlog
                    fn_name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None) or repr(fn)
                    dlog(
                        "heavy_io",
                        "run_in_heavy_io.slow",
                        fn=fn_name,
                        queue_wait_ms=queue_wait_ms,
                        exec_ms=exec_ms,
                        total_ms=queue_wait_ms + exec_ms,
                        error=error,
                    )
                except Exception:
                    logger.warning("infrastructure step failed", exc_info=True)
            # NOTE: do NOT close thread-local DB connections here.
            # heavy_io workers also do small DB lookups (e.g. path resolution
            # in serve_thumbnail). Closing on every call forces SQLCipher to
            # re-derive its PBKDF2 key (~180 ms per open). The fixed-size
            # heavy-io pool keeps thread-local conns valid for the worker
            # lifetime, and _get_cached_connection re-validates path/liveness.

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_pool(), _wrapper)


def shutdown() -> None:
    """Shut down the thread pool."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False)
        _pool = None

"""Background asyncio event loop for MCP client sessions.

Flask is synchronous; MCP SDK is async.  This module bridges the gap
by running a single daemon-thread event loop that MCP coroutines are
submitted to via ``run_async()``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Lazily start the background event loop (once)."""
    global _loop, _thread
    if _loop is not None and _loop.is_running():
        return _loop
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop
        _loop = asyncio.new_event_loop()
        _thread = threading.Thread(target=_run_loop, args=(_loop,), daemon=True)
        _thread.start()
        logger.debug("MCP client async bridge started")
        return _loop


def run_async(coro: Coroutine[Any, Any, T], *, timeout: float = 30.0) -> T:
    """Submit *coro* to the background loop and block until done.

    Raises ``TimeoutError`` if the coroutine does not complete within
    *timeout* seconds. The future is cancelled on timeout to prevent
    background coroutine leaks.
    """
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        raise


def shutdown_loop() -> None:
    """Stop the background loop gracefully."""
    global _loop, _thread
    with _lock:
        if _loop is None:
            return
        _loop.call_soon_threadsafe(_loop.stop)
        if _thread is not None:
            _thread.join(timeout=5.0)
        _loop = None
        _thread = None
        logger.debug("MCP client async bridge stopped")

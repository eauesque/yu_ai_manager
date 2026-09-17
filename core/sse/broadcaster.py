"""SSE fan-out broadcaster.

Subscribes to the global event bus and pushes events to all
connected SSE clients via per-client queues.

The async stream uses asyncio.Queue (no thread pool consumption) so that
SSE connections do not exhaust the default executor and starve DB queries.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import queue
import threading
import time
from collections.abc import AsyncGenerator, Generator

from core.event_bus import event_bus
from core.event_bus.event_types import Event

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30
# Max queued events per client before dropping
CLIENT_QUEUE_MAX = 256
# Max connection age in seconds.
# On Windows, TCP send buffering can hide client disconnections for hours.
# Force-closing after this period ensures zombie connections are cleaned up.
# 900s = 15 min: covers typical long scans without cutting SSE mid-progress.
MAX_STREAM_AGE = 900


class SSEBroadcaster:
    """Manages connected SSE clients and fans out events.

    Maintains two separate client lists:
    - ``_sync_clients``: blocking queue.Queue for sync generators
    - ``_async_clients``: asyncio.Queue for async generators (zero thread usage)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sync_clients: list[queue.Queue] = []
        self._async_clients: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribed = False

    def _ensure_subscribed(self) -> None:
        """Lazily subscribe to event bus on first client connect."""
        if self._subscribed:
            return
        with self._lock:
            if self._subscribed:
                return
            event_bus.subscribe(None, self._on_event)
            self._subscribed = True

    def _on_event(self, event: Event) -> None:
        """Push event to all client queues (sync + async)."""
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        msg = ("event", event.type, payload)
        with self._lock:
            # Sync clients
            dead_sync: list[queue.Queue] = []
            for q in self._sync_clients:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead_sync.append(q)
            for q in dead_sync:
                with contextlib.suppress(ValueError):
                    self._sync_clients.remove(q)
            # Async clients: schedule put on event loop thread
            if self._async_clients and self._loop:
                loop = self._loop
                async_clients = list(self._async_clients)
                with contextlib.suppress(RuntimeError):  # loop may be closed
                    loop.call_soon_threadsafe(
                        self._dispatch_async, async_clients, msg,
                    )

    def _dispatch_async(self, clients: list[asyncio.Queue], msg: tuple) -> None:
        """Put event into async queues (must run on event loop thread)."""
        dead: list[asyncio.Queue] = []
        for aq in clients:
            try:
                aq.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(aq)
        if dead:
            with self._lock:
                for aq in dead:
                    with contextlib.suppress(ValueError):
                        self._async_clients.remove(aq)

    def stream(self, type_filter: set[str] | None = None) -> Generator[str, None, None]:
        """Yield SSE formatted strings for a single client (sync)."""
        self._ensure_subscribed()
        client_q: queue.Queue = queue.Queue(maxsize=CLIENT_QUEUE_MAX)
        with self._lock:
            self._sync_clients.append(client_q)
        start = time.monotonic()
        try:
            while True:
                remaining = MAX_STREAM_AGE - (time.monotonic() - start)
                if remaining <= 0:
                    return
                timeout = min(HEARTBEAT_INTERVAL, remaining)
                try:
                    msg = client_q.get(timeout=timeout)
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    continue
                kind, event_type, data = msg
                if type_filter and event_type not in type_filter:
                    continue
                yield f"event: {event_type}\ndata: {data}\n\n"
        except GeneratorExit:
            pass
        finally:
            with self._lock, contextlib.suppress(ValueError):
                self._sync_clients.remove(client_q)

    async def astream(self, type_filter: set[str] | None = None) -> AsyncGenerator[str, None]:
        """Yield SSE formatted strings asynchronously (for Quart).

        Uses asyncio.Queue instead of threading queue + asyncio.to_thread().
        This means SSE connections consume ZERO threads from the default
        executor, preventing thread pool starvation that caused the server
        to become unresponsive after long operation.
        """
        self._ensure_subscribed()
        client_q: asyncio.Queue = asyncio.Queue(maxsize=CLIENT_QUEUE_MAX)
        with self._lock:
            self._async_clients.append(client_q)
            if self._loop is None:
                self._loop = asyncio.get_event_loop()
        start = time.monotonic()
        try:
            while True:
                remaining = MAX_STREAM_AGE - (time.monotonic() - start)
                if remaining <= 0:
                    return
                timeout = min(HEARTBEAT_INTERVAL, remaining)
                try:
                    msg = await asyncio.wait_for(client_q.get(), timeout=timeout)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                kind, event_type, data = msg
                if type_filter and event_type not in type_filter:
                    continue
                yield f"event: {event_type}\ndata: {data}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            with self._lock, contextlib.suppress(ValueError):
                self._async_clients.remove(client_q)

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._sync_clients) + len(self._async_clients)

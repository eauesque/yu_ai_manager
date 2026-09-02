"""Forward Python event_bus events to the Rust SSE hub via /_internal/sse-emit."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import queue
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.event_bus.event_types import Event

logger = logging.getLogger(__name__)

_QUEUE_MAX = 256  # drop oldest when Rust is unreachable for a sustained period


class SseForwarder:
    """Subscribe to all events on the global event_bus and POST them to Rust.

    _forward() enqueues the event and returns immediately so the event_bus
    callback chain is never blocked by network I/O.  A single daemon worker
    thread drains the queue and performs the actual HTTP POST.
    """

    def __init__(self, emit_url: str) -> None:
        self._emit_url = emit_url
        self._session: object | None = None  # requests.Session, lazy
        self._queue: queue.Queue[str] = queue.Queue(maxsize=_QUEUE_MAX)

    def _get_session(self) -> object:
        if self._session is None:
            import requests

            s = requests.Session()
            s.headers.update({"Content-Type": "application/json"})
            self._session = s
        return self._session

    def _forward(self, event: Event) -> None:
        payload = json.dumps([event.to_dict()])
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            # Queue is full (Rust unreachable); drop the oldest entry and retry.
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(payload)

    def _worker(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                session = self._get_session()
                session.post(self._emit_url, data=payload, timeout=1)  # type: ignore[union-attr]
            except Exception:
                logger.warning("step failed", exc_info=True)
            finally:
                self._queue.task_done()

    def start(self) -> None:
        from core.event_bus import event_bus

        t = threading.Thread(target=self._worker, name="sse-forwarder-worker", daemon=True)
        t.start()
        event_bus.subscribe(None, self._forward)
        logger.debug("[SSE] Forwarder → %s", self._emit_url)


def _resolve_emit_url() -> str:
    url = os.environ.get("YU_SERVER_EMIT_URL")
    if url:
        return url
    port = os.environ.get("YU_SERVER_PORT", "5000")
    return f"http://127.0.0.1:{port}/_internal/sse-emit"


def start_sse_forwarder() -> None:
    """Start the SseForwarder in a daemon thread so startup is non-blocking."""

    def _start() -> None:
        try:
            forwarder = SseForwarder(_resolve_emit_url())
            forwarder.start()
        except Exception as exc:
            logger.debug("[SSE] Forwarder start skipped: %s", exc)

    t = threading.Thread(target=_start, name="sse-forwarder-init", daemon=True)
    t.start()

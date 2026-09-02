"""Thread-safe in-process event bus (pub/sub)."""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable

from .event_types import Event

logger = logging.getLogger(__name__)

Callback = Callable[[Event], None]


class EventBus:
    """Simple pub/sub event bus.

    Subscribers receive events synchronously on the emitting thread.
    Use short non-blocking callbacks; heavy work should be dispatched
    to a thread pool by the subscriber itself.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # event_type -> list of callbacks
        self._subscribers: dict[str, list[Callback]] = {}
        # wildcard subscribers (receive all events)
        self._wildcard: list[Callback] = []

    def subscribe(self, event_type: str | None, callback: Callback) -> None:
        """Subscribe to a specific event type, or all events (type=None)."""
        with self._lock:
            if event_type is None:
                self._wildcard.append(callback)
            else:
                self._subscribers.setdefault(event_type, []).append(callback)

    def subscribe_many(self, event_types: set[str], callback: Callback) -> None:
        """Subscribe to multiple event types with one callback."""
        for et in event_types:
            self.subscribe(et, callback)

    def unsubscribe(self, event_type: str | None, callback: Callback) -> None:
        """Remove a subscription."""
        with self._lock:
            if event_type is None:
                with contextlib.suppress(ValueError):
                    self._wildcard.remove(callback)
            else:
                subs = self._subscribers.get(event_type)
                if subs:
                    with contextlib.suppress(ValueError):
                        subs.remove(callback)

    def emit(self, event: Event) -> None:
        """Emit an event to all matching subscribers."""
        with self._lock:
            targets = list(self._wildcard)
            specific = self._subscribers.get(event.type)
            if specific:
                targets.extend(specific)
        for cb in targets:
            try:
                cb(event)
            except Exception:
                logger.exception("Event subscriber error for %s", event.type)

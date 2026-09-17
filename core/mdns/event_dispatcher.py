"""Async event dispatcher between the mDNS worker thread and subscribers.

The worker thread pushes :class:`PeerEvent` objects into an ``asyncio.Queue``
via ``loop.call_soon_threadsafe``. A single consumer task drains the queue
and invokes every registered subscriber. Subscriber exceptions are logged
and isolated so that one broken subscriber cannot block others.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.mdns.peer_info import PeerInfo

logger = logging.getLogger("core.mdns.event_dispatcher")


PeerAddedCb = Callable[[PeerInfo], Awaitable[None]]
PeerUpdatedCb = Callable[[PeerInfo], Awaitable[None]]
PeerRemovedCb = Callable[[str], Awaitable[None]]


@dataclass
class PeerEvent:
    kind: str  # "added" | "updated" | "removed"
    peer: PeerInfo | None = None
    node_id: str | None = None  # set for "removed"


@dataclass
class _Subscription:
    on_peer_added: PeerAddedCb | None = None
    on_peer_updated: PeerUpdatedCb | None = None
    on_peer_removed: PeerRemovedCb | None = None


class SubscriptionHandle:
    def __init__(self, dispatcher: EventDispatcher, sub: _Subscription) -> None:
        self._dispatcher = dispatcher
        self._sub = sub

    def unsubscribe(self) -> None:
        with contextlib.suppress(ValueError):
            self._dispatcher._subscriptions.remove(self._sub)


class EventDispatcher:
    """Filters self-events and fans out peer events to every subscriber."""

    def __init__(self, self_node_id: str) -> None:
        self._self_node_id = self_node_id
        self._subscriptions: list[_Subscription] = []

    def subscribe(
        self,
        on_peer_added: PeerAddedCb | None = None,
        on_peer_updated: PeerUpdatedCb | None = None,
        on_peer_removed: PeerRemovedCb | None = None,
    ) -> SubscriptionHandle:
        sub = _Subscription(
            on_peer_added=on_peer_added,
            on_peer_updated=on_peer_updated,
            on_peer_removed=on_peer_removed,
        )
        self._subscriptions.append(sub)
        return SubscriptionHandle(self, sub)

    async def dispatch(self, event: PeerEvent) -> None:
        if self._is_self(event):
            return
        for sub in list(self._subscriptions):
            await self._deliver(sub, event)

    def _is_self(self, event: PeerEvent) -> bool:
        if event.kind == "removed":
            return event.node_id == self._self_node_id
        return event.peer is not None and event.peer.node_id == self._self_node_id

    async def _deliver(self, sub: _Subscription, event: PeerEvent) -> None:
        try:
            if event.kind == "added" and sub.on_peer_added and event.peer is not None:
                await sub.on_peer_added(event.peer)
            elif event.kind == "updated" and sub.on_peer_updated and event.peer is not None:
                await sub.on_peer_updated(event.peer)
            elif event.kind == "removed" and sub.on_peer_removed and event.node_id:
                await sub.on_peer_removed(event.node_id)
        except Exception as exc:
            logger.error(
                "[mdns] subscriber raised during %s event: %s",
                event.kind,
                exc,
                exc_info=True,
            )

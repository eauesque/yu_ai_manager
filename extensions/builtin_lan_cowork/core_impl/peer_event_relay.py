"""extensions/builtin_lan_cowork/core_impl/peer_event_relay.py
Relay local events to connected peers and merge incoming peer events.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from core.event_bus import emit, event_bus
from core.event_bus.event_types import Event

if TYPE_CHECKING:
    from .registry import PeerRegistry
    from .transport import PeerTransport

logger = logging.getLogger(__name__)

RELAY_TYPES: set[str] = {
    "generation.submit", "generation.progress", "generation.complete",
    "generation.error", "generation.cancel",
    "sync.file_changed",
    "peer.status_update",
}


def note_rejected_event(
    window_start: float, rejected: int, now: float,
) -> tuple[float, int, int | None]:
    """Record a rejected event and return its window state and flush count."""
    rejected += 1
    if now - window_start >= 60.0:
        return now, 0, rejected
    return window_start, rejected, None


class PeerEventRelay:
    """Bridges local EventBus <-> remote peers."""

    def __init__(self, registry: PeerRegistry, transport: PeerTransport, local_peer_id: str) -> None:
        self._registry = registry
        self._transport = transport
        self._local_id = local_peer_id
        self._subscribed = False
        self._rejection_window_start = float("-inf")
        self._rejected_events = 0

    def start(self) -> None:
        if self._subscribed:
            return
        event_bus.subscribe(None, self._on_local_event)
        self._subscribed = True
        logger.info("PeerEventRelay started")

    def stop(self) -> None:
        if not self._subscribed:
            return
        event_bus.unsubscribe(None, self._on_local_event)
        self._subscribed = False
        logger.info("PeerEventRelay stopped")

    def _on_local_event(self, event: Event) -> None:
        if event.type not in RELAY_TYPES:
            return
        if event.data.get("_peer_relayed"):
            return
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._relay_to_peers(event))
            else:
                loop.run_until_complete(self._relay_to_peers(event))
        except RuntimeError:
            pass

    async def _relay_to_peers(self, event: Event) -> None:
        peers = self._registry.list_online()
        payload = {
            "event_type": event.type,
            "event_data": event.data,
            "source_peer": self._local_id,
        }
        for peer in peers:
            await self._transport.send(peer, "/api/peer/event", payload)

    def inject_remote_event(self, event_type: str, event_data: dict, source_peer: str) -> bool:
        """Inject a remote event into the local event bus.

        Returns True if the event was accepted, False if rejected.
        Only event types in RELAY_TYPES are allowed from remote peers.
        """
        if event_type not in RELAY_TYPES:
            (
                self._rejection_window_start,
                self._rejected_events,
                rejected,
            ) = note_rejected_event(
                self._rejection_window_start, self._rejected_events, time.monotonic(),
            )
            if rejected is not None:
                logger.warning(
                    "Rejected %d remote event(s); last type %r from peer %s (not in whitelist)",
                    rejected, event_type[:64], source_peer,
                )
            return False
        data = dict(event_data)
        data["_peer_relayed"] = True
        data["peer_id"] = source_peer
        emit(event_type, data, source=f"peer:{source_peer}")
        return True

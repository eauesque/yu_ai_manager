"""extensions/builtin_lan_cowork/core_impl/heartbeat.py
Periodic heartbeat loop — broadcasts status to all peers and checks timeouts.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .discovery import PeerDiscovery
    from .models import PeerInfo
    from .registry import PeerRegistry
    from .transport import PeerTransport

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 10  # seconds


class HeartbeatLoop:
    """Sends periodic heartbeats and checks for timed-out peers."""

    def __init__(
        self,
        local_peer: PeerInfo,
        registry: PeerRegistry,
        transport: PeerTransport,
        discovery: PeerDiscovery,
        loopback_listener: bool = False,
    ) -> None:
        self._local = local_peer
        self._registry = registry
        self._transport = transport
        self._discovery = discovery
        self._loopback_listener = loopback_listener
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info("HeartbeatLoop started (interval=%ds)", HEARTBEAT_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("HeartbeatLoop stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("HeartbeatLoop tick error")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _tick(self) -> None:
        await self._discovery.broadcast_hello()
        info = {
            "generating": self._local.generating,
            "queue_depth": self._local.queue_depth,
            "bridges": list(self._local.bridges),
            "inference_types": list(self._local.inference_types),
        }
        peers = self._registry.list_online()
        # Run per-peer heartbeats in parallel — with offline peers each call
        # blocks for the full 5 s connect timeout, so a serial loop turned
        # one tick into peers x 5 s of stalled DB executor / event loop time.
        async def _one(peer):
            ok = await self._transport.heartbeat(peer, info)
            if ok:
                peer.last_seen = time.time()
            elif not self._loopback_listener:
                await self._transport.send(
                    peer, "/api/peer/register",
                    data={"host": self._local.api_host, "port": self._local.api_port},
                )
        if peers:
            await asyncio.gather(
                *(_one(peer) for peer in peers),
                return_exceptions=True,
            )
        went_offline = self._registry.check_timeouts()
        if went_offline:
            from core.event_bus import emit
            from core.event_bus.event_types import PEER_OFFLINE
            for pid in went_offline:
                emit(PEER_OFFLINE, {"peer_id": pid}, source="lan-cowork")
                logger.info("Peer %s went offline", pid)

# core/mdns/service.py
"""Async facade over the mDNS worker thread.

``MdnsService`` is the only class outside of ``core/mdns`` that callers should
import. It owns the worker, bridges raw queue events onto the running asyncio
loop, and exposes a subscribe API compatible with the event dispatcher.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import queue
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.mdns.browser import RawEvent
from core.mdns.event_dispatcher import (
    EventDispatcher,
    PeerAddedCb,
    PeerEvent,
    PeerRemovedCb,
    PeerUpdatedCb,
    SubscriptionHandle,
)
from core.mdns.peer_info import PeerInfo
from core.mdns.worker import MdnsWorker

logger = logging.getLogger("core.mdns.service")


def _detect_primary_lan_ip() -> str | None:
    """Return the primary LAN IPv4 via UDP routing trick (no packet sent).

    Asks the kernel which source address it would use to reach 8.8.8.8,
    which picks the interface whose default route is used — usually the
    real LAN interface rather than virtual Docker/VPN interfaces.
    Returns None on failure (caller falls back to Zeroconf default).
    """
    import socket as _socket
    try:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return None


@dataclass
class MdnsConfig:
    enabled: bool = True
    service_name: str | None = None
    bind_address: str | None = None


class MdnsService:
    def __init__(
        self,
        *,
        zeroconf_factory: Callable[[], Any] | None = None,
        service_info_cls: Any = None,
        service_browser_cls: Any = None,
    ) -> None:
        self._zeroconf_factory = zeroconf_factory
        self._service_info_cls = service_info_cls
        self._service_browser_cls = service_browser_cls
        self._worker: MdnsWorker | None = None
        self._dispatcher: EventDispatcher | None = None
        self._queue: queue.Queue[RawEvent] = queue.Queue()
        self._drain_task: asyncio.Task | None = None
        self._known_peers: dict[str, PeerInfo] = {}
        self._pending_subscribers: list[tuple[PeerAddedCb | None, PeerUpdatedCb | None, PeerRemovedCb | None]] = []
        self._status: str = "stopped"
        self._config: MdnsConfig | None = None
        self._self_peer: PeerInfo | None = None

    @property
    def status(self) -> str:
        return self._status

    def list_peers(self) -> list[PeerInfo]:
        return list(self._known_peers.values())

    def subscribe(
        self,
        on_peer_added: PeerAddedCb | None = None,
        on_peer_updated: PeerUpdatedCb | None = None,
        on_peer_removed: PeerRemovedCb | None = None,
    ) -> SubscriptionHandle | None:
        if self._dispatcher is not None:
            return self._dispatcher.subscribe(
                on_peer_added=on_peer_added,
                on_peer_updated=on_peer_updated,
                on_peer_removed=on_peer_removed,
            )
        self._pending_subscribers.append(
            (on_peer_added, on_peer_updated, on_peer_removed)
        )
        return None

    async def start(self, config: MdnsConfig, self_peer: PeerInfo) -> None:
        if not config.enabled:
            self._status = "disabled"
            logger.info("[mdns] disabled via config")
            return
        self._config = config
        self._self_peer = self_peer

        self._dispatcher = EventDispatcher(self_node_id=self_peer.node_id)
        for a, u, r in self._pending_subscribers:
            self._dispatcher.subscribe(on_peer_added=a, on_peer_updated=u, on_peer_removed=r)
        self._pending_subscribers.clear()

        zc_factory, si_cls, sb_cls = self._resolve_zeroconf_classes(
            bind_address=config.bind_address,
        )
        self._worker = MdnsWorker(
            zeroconf_factory=zc_factory,
            service_info_cls=si_cls,
            service_browser_cls=sb_cls,
            out_queue=self._queue,
        )

        instance_name = config.service_name or f"yu-ai-{self_peer.node_id[:8]}"
        try:
            self._worker.start(self_peer=self_peer, instance_name=instance_name)
        except Exception as exc:
            logger.warning("[mdns] disabled: %s", exc)
            self._status = "disabled"
            self._worker = None
            return

        self._status = "running"
        self._drain_task = asyncio.create_task(self._drain_loop())

    async def readvertise_self(self, self_peer: PeerInfo) -> bool:
        """Restart the worker so our self-advertisement reflects new state.

        If the new worker fails to start, best-effort rollback to the previous
        self advertisement so a transient refresh error does not silently take
        mDNS offline for the whole process.
        """
        if self._status != "running":
            return False
        if self._config is None:
            raise RuntimeError("MdnsService started without config")
        previous_peer = self._self_peer
        old_worker = self._worker
        if old_worker is not None:
            old_worker.stop()
            self._worker = None
        try:
            zc_factory, si_cls, sb_cls = self._resolve_zeroconf_classes(
                bind_address=self._config.bind_address,
            )
            self._worker = MdnsWorker(
                zeroconf_factory=zc_factory,
                service_info_cls=si_cls,
                service_browser_cls=sb_cls,
                out_queue=self._queue,
            )
            instance_name = self._config.service_name or f"yu-ai-{self_peer.node_id[:8]}"
            self._worker.start(self_peer=self_peer, instance_name=instance_name)
            self._self_peer = self_peer
            return True
        except Exception as exc:
            logger.warning("[mdns] self readvertise failed: %s", exc)
            self._worker = None
            if previous_peer is None:
                self._status = "disabled"
                return False
            try:
                zc_factory, si_cls, sb_cls = self._resolve_zeroconf_classes(
                    bind_address=self._config.bind_address,
                )
                rollback_worker = MdnsWorker(
                    zeroconf_factory=zc_factory,
                    service_info_cls=si_cls,
                    service_browser_cls=sb_cls,
                    out_queue=self._queue,
                )
                rollback_name = self._config.service_name or f"yu-ai-{previous_peer.node_id[:8]}"
                rollback_worker.start(self_peer=previous_peer, instance_name=rollback_name)
                self._worker = rollback_worker
                self._self_peer = previous_peer
                logger.warning("[mdns] restored previous self advertisement after refresh failure")
            except Exception as rollback_exc:
                logger.error("[mdns] failed to restore previous self advertisement: %s", rollback_exc)
                self._status = "disabled"
            return False

    async def stop(self) -> None:
        if self._drain_task is not None:
            # Push a sentinel so the executor thread unblocks from queue.get
            # before we cancel the task. Otherwise the executor thread leaks
            # until another event arrives.
            self._queue.put(None)
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._drain_task
            self._drain_task = None
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        self._status = "stopped"
        self._config = None
        self._self_peer = None

    def _resolve_zeroconf_classes(
        self, bind_address: str | None = None
    ) -> tuple[Callable[[], Any], Any, Any]:
        if self._zeroconf_factory is not None and self._service_info_cls is not None and self._service_browser_cls is not None:
            # Tests inject everything — don't override with bind_address.
            return (
                self._zeroconf_factory,
                self._service_info_cls,
                self._service_browser_cls,
            )
        import zeroconf as _zc  # noqa: WPS433 — deliberate lazy import

        if self._zeroconf_factory is not None:
            factory: Callable[[], Any] = self._zeroconf_factory
        elif bind_address:
            # Pin zeroconf to a single interface. On Windows with
            # WSL / Hyper-V virtual adapters, InterfaceChoice.All (the default)
            # causes multicast reception to be unreliable on the real LAN
            # interface — peers can receive OUR advertisements but we do not
            # receive theirs. Binding explicitly to the LAN IP fixes this.
            def factory() -> Any:
                return _zc.Zeroconf(interfaces=[bind_address])
            logger.info("[mdns] binding zeroconf to interface %s", bind_address)
        else:
            # Auto-detect the primary LAN IP and bind to it.
            # On Linux (and Windows) with Docker / VPN / multiple virtual
            # interfaces, InterfaceChoice.All can route mDNS multicast through
            # the wrong interface, causing peers on the real LAN to be missed.
            # Using the UDP-routing trick (same as advertiser.py) to pick the
            # outbound interface for 8.8.8.8 gives us the primary LAN IP.
            _auto_ip = _detect_primary_lan_ip()
            if _auto_ip:
                def factory() -> Any:
                    return _zc.Zeroconf(interfaces=[_auto_ip])
                logger.info("[mdns] auto-binding zeroconf to LAN interface %s", _auto_ip)
            else:
                factory = _zc.Zeroconf
                logger.info("[mdns] using default zeroconf interfaces")
        return (
            factory,
            self._service_info_cls or _zc.ServiceInfo,
            self._service_browser_cls or _zc.ServiceBrowser,
        )

    async def _drain_loop(self) -> None:
        # Polling-based drain. We deliberately do NOT use
        # ``loop.run_in_executor(None, self._queue.get)`` because the default
        # executor is shared with Quart/Hypercorn sync handlers and can be
        # saturated for many seconds at a time by other parts of the app
        # (e.g. lan_cowork heartbeat handlers). When that happens our
        # blocking ``queue.get`` request sits in the executor backlog and
        # mDNS events never reach the bridge.
        #
        # 50ms polling adds negligible CPU and gives <50ms latency on event
        # delivery, while being completely independent of executor state.
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            if event is None:
                # Sentinel from stop() — exit cleanly.
                return
            peer_event = _to_peer_event(event)
            if peer_event.kind in ("added", "updated") and peer_event.peer is not None:
                self._known_peers[peer_event.peer.node_id] = peer_event.peer
            elif peer_event.kind == "removed" and peer_event.node_id:
                self._known_peers.pop(peer_event.node_id, None)
            assert self._dispatcher is not None
            await self._dispatcher.dispatch(peer_event)


def _to_peer_event(raw: RawEvent) -> PeerEvent:
    return PeerEvent(kind=raw.kind, peer=raw.peer, node_id=raw.node_id)

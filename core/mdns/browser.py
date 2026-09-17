# core/mdns/browser.py
"""ServiceBrowser listener that pushes raw events into a thread-safe queue.

Runs entirely in the mDNS worker thread. Never imports asyncio.
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import logging
import queue
import socket
from dataclasses import dataclass
from typing import Any

from core.mdns.peer_info import PeerInfo
from core.mdns.service_types import OLLAMA_SERVICE_TYPE, YU_SERVICE_TYPE

logger = logging.getLogger("core.mdns.browser")


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RawEvent:
    kind: str  # "added" | "updated" | "removed"
    peer: PeerInfo | None = None
    node_id: str | None = None


class BrowserListener:
    """Implements zeroconf.ServiceListener; converts raw events to PeerInfo."""

    def __init__(self, out_queue: queue.Queue[RawEvent]) -> None:
        self._q = out_queue
        self._by_name: dict[tuple[str, str], str] = {}
        self._local_ipv4s = self._detect_local_ipv4s()
        self._local_hostname = socket.gethostname().rstrip(".").lower()

    def add_service(self, zc: Any, type_: str, name: str) -> None:
        peer = self._resolve(zc, type_, name)
        if peer is None:
            return
        self._by_name[(type_, name)] = peer.node_id
        self._q.put(RawEvent(kind="added", peer=peer))

    def update_service(self, zc: Any, type_: str, name: str) -> None:
        peer = self._resolve(zc, type_, name)
        if peer is None:
            return
        self._by_name[(type_, name)] = peer.node_id
        self._q.put(RawEvent(kind="updated", peer=peer))

    def remove_service(self, zc: Any, type_: str, name: str) -> None:
        node_id = self._by_name.pop((type_, name), None)
        if node_id is None:
            return
        self._q.put(RawEvent(kind="removed", node_id=node_id))

    def _resolve(self, zc: Any, type_: str, name: str) -> PeerInfo | None:
        info = zc.get_service_info(type_, name, timeout=2000)
        if info is None:
            logger.debug("[mdns] unresolved service %s", name)
            return None
        try:
            addresses = tuple(
                socket.inet_ntoa(a) for a in (info.addresses or [])
            )
        except Exception:
            addresses = ()
        hostname = (info.server or "").rstrip(".")
        if type_ == YU_SERVICE_TYPE:
            return PeerInfo.from_txt(
                txt=info.properties or {},
                hostname=hostname,
                addresses=addresses,
                first_seen=_now_iso(),
            )
        if type_ == OLLAMA_SERVICE_TYPE:
            if self._is_local_ollama_service(hostname=hostname, addresses=addresses):
                logger.debug("[mdns] skip self bare ollama service %s", name)
                return None
            addresses = self._prioritize_ollama_addresses(addresses)
            return PeerInfo.from_ollama_service(
                service_name=name,
                hostname=hostname,
                addresses=addresses,
                port=int(getattr(info, "port", 0) or 0),
                first_seen=_now_iso(),
            )
        logger.debug("[mdns] unsupported service type %s for %s", type_, name)
        return None

    def _is_local_ollama_service(
        self,
        *,
        hostname: str,
        addresses: tuple[str, ...],
    ) -> bool:
        host = hostname.lower()
        if host and host == self._local_hostname:
            return True
        return any(addr in self._local_ipv4s for addr in addresses)

    def _prioritize_ollama_addresses(
        self,
        addresses: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Prefer addresses that look reachable from this host's LAN.

        Zeroconf responses on Windows often include extra virtual-adapter
        addresses (for example Docker/WSL 172.* ranges) before the primary
        LAN address. For bare Ollama peers we currently derive llm_base_url
        from the first address, so reorder candidates to prefer:

        1. Same /24 as one of our local IPv4s
        2. RFC1918 addresses, with 192.168/16 preferred over 10/8 over 172.16/12
        3. Everything else, preserving original order within each bucket
        """

        def _bucket(ip: str) -> tuple[int, int]:
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                return (9, 9)
            if addr.version != 4:
                return (8, 8)
            if any(self._same24(ip, local) for local in self._local_ipv4s):
                return (0, 0)
            if addr in ipaddress.ip_network("192.168.0.0/16"):
                return (1, 0)
            if addr in ipaddress.ip_network("10.0.0.0/8"):
                return (2, 0)
            if addr in ipaddress.ip_network("172.16.0.0/12"):
                return (3, 0)
            if addr.is_private:
                return (4, 0)
            return (5, 0)

        indexed = list(enumerate(addresses))
        indexed.sort(key=lambda item: (_bucket(item[1]), item[0]))
        return tuple(addr for _, addr in indexed)

    @staticmethod
    def _same24(a: str, b: str) -> bool:
        try:
            return ".".join(a.split(".")[:3]) == ".".join(b.split(".")[:3])
        except Exception:
            return False

    @staticmethod
    def _detect_local_ipv4s() -> set[str]:
        from core.mdns.advertiser import _detect_local_addresses

        local: set[str] = set()
        for packed in _detect_local_addresses():
            try:
                local.add(socket.inet_ntoa(packed))
            except OSError:
                continue
        return local

"""extensions/builtin_lan_cowork/core_impl/discovery.py
UDP broadcast peer discovery on LAN.

Uses asyncio DatagramProtocol on Linux/macOS (SelectorEventLoop),
and a dedicated listener thread on Windows (ProactorEventLoop does
not support create_datagram_endpoint reliably).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import sys
import threading
from collections.abc import Callable

from core.crypto_identity import (
    ParsedHello,
)
from core.crypto_identity import (
    build_hello_packet as _ci_build_hello,
)
from core.crypto_identity import (
    parse_hello_packet as _ci_parse_hello,
)

from .models import PeerInfo

logger = logging.getLogger(__name__)

MAGIC = b"YUAI"
PROTOCOL_VERSION = 2  # signed HELLO
DEFAULT_PORT = 19850
BROADCAST_ADDR = "<broadcast>"


def _get_broadcast_addrs() -> list[str]:
    """Return LAN broadcast addresses for all active non-loopback interfaces.

    Falls back to "<broadcast>" (255.255.255.255) on error or when no
    interface-specific address is found.  macOS/BSD routes 255.255.255.255
    only when an explicit route exists; per-interface directed-broadcast
    addresses are reliable on all platforms.
    """
    addrs: list[str] = []
    try:
        import ipaddress

        import psutil

        for snic_list in psutil.net_if_addrs().values():
            for snic in snic_list:
                if snic.family != socket.AF_INET or not snic.broadcast:
                    continue
                # A probe: a non-IPv4 address simply is not one of ours.
                with contextlib.suppress(ValueError):
                    if not ipaddress.IPv4Address(snic.address).is_loopback:
                        addrs.append(snic.broadcast)
    except Exception:
        # Falls back to the limited-broadcast address, which works on one
        # subnet -- worth knowing enumeration keeps failing.
        logger.warning("interface enumeration failed", exc_info=True)
    return addrs or [BROADCAST_ADDR]

_IS_WINDOWS = sys.platform == "win32"


def build_hello_packet(peer: PeerInfo, seed: bytes | None = None) -> bytes:
    """Build a signed VERSION=2 discovery packet."""
    return _ci_build_hello(peer, seed)


def parse_hello_packet(data: bytes) -> ParsedHello | None:
    """Parse a VERSION=2 discovery packet. Returns None if invalid."""
    return _ci_parse_hello(data)


class PeerDiscovery:
    """Async UDP broadcast discovery service."""

    def __init__(
        self,
        local_peer: PeerInfo,
        port: int = DEFAULT_PORT,
        on_peer_found: Callable[[ParsedHello, str], None] | None = None,
        seed: bytes | None = None,
    ) -> None:
        self._local = local_peer
        self._port = port
        self._on_peer_found = on_peer_found
        self._seed = seed
        self._sock: socket.socket | None = None
        self._running = False
        # asyncio DatagramProtocol transport (non-Windows)
        self._udp_transport: asyncio.DatagramTransport | None = None
        # Listener thread (Windows)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _socket_usable(self) -> bool:
        sock = self._sock
        if sock is None:
            return False
        try:
            return sock.fileno() >= 0
        except OSError:
            return False

    def _transport_usable(self) -> bool:
        transport = self._udp_transport
        if transport is None:
            return False
        try:
            return not transport.is_closing()
        except (AttributeError, RuntimeError):
            return False

    @property
    def available(self) -> bool:
        """False if bind failed (port already held by another instance)."""
        return self._running

    async def start(self) -> None:
        if self._running:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # nosemgrep: python.lang.security.audit.network.bind.avoid-bind-to-all-interfaces
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # A broadcast listener must bind every interface to receive at
            # all. LAN Cowork is opt-in (`extensions."builtin-lan-cowork".
            # enabled`), so this socket does not exist unless an operator
            # turned discovery on.
            sock.bind(("", self._port))
        except OSError as e:
            sock.close()
            logger.warning(
                "PeerDiscovery: port %d already in use (%s) — "
                "discovery disabled (another instance may be running).",
                self._port, e,
            )
            return

        self._sock = sock
        self._running = True
        self._loop = asyncio.get_event_loop()

        if _IS_WINDOWS:
            # Windows ProactorEventLoop: use a dedicated listener thread
            self._sock.settimeout(1.0)
            self._thread = threading.Thread(
                target=self._listen_thread,
                name="discovery-udp",
                daemon=True,
            )
            self._thread.start()
        else:
            # Linux/macOS: use asyncio DatagramProtocol (zero thread overhead)
            self._sock.setblocking(False)
            self._udp_transport, _ = await self._loop.create_datagram_endpoint(
                lambda: _DiscoveryProtocol(
                    self._local.peer_id, self._on_peer_found,
                ),
                sock=self._sock,
            )

        await self.broadcast_hello()
        logger.info("PeerDiscovery started on port %d", self._port)

    async def stop(self) -> None:
        self._running = False
        if self._udp_transport:
            self._udp_transport.close()
            self._udp_transport = None
        if self._sock:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("PeerDiscovery stopped")

    async def broadcast_hello(self) -> None:
        if not self._running or not self._socket_usable():
            return
        pkt = build_hello_packet(self._local, self._seed)
        targets = _get_broadcast_addrs()
        for addr in targets:
            try:
                if self._transport_usable():
                    self._udp_transport.sendto(pkt, (addr, self._port))
                else:
                    self._sock.sendto(pkt, (addr, self._port))
            except (AttributeError, RuntimeError) as e:
                # SelectorEventLoop may leave a closed datagram transport object
                # behind briefly during shutdown or after fatal socket errors.
                if self._udp_transport is not None:
                    self._udp_transport = None
                logger.warning("broadcast_hello failed: %s", e)
                break
            except OSError as e:
                logger.debug("broadcast_hello to %s failed: %s", addr, e)

    def _listen_thread(self) -> None:
        """Blocking listener thread for Windows."""
        while self._running and self._sock:
            try:
                data, addr = self._sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                if self._running:
                    logger.debug("Discovery socket error, stopping listener")
                break

            parsed = parse_hello_packet(data)
            if parsed is None:
                continue
            if parsed.peer_dict.get("peer_id") == self._local.peer_id:
                continue
            if self._on_peer_found and self._loop:
                self._loop.call_soon_threadsafe(
                    self._on_peer_found, parsed, addr[0],
                )


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Async UDP protocol for peer discovery (non-Windows)."""

    def __init__(self, local_peer_id: str, on_peer_found):
        self._local_peer_id = local_peer_id
        self._on_peer_found = on_peer_found

    def datagram_received(self, data: bytes, addr):
        parsed = parse_hello_packet(data)
        if parsed is None:
            return
        if parsed.peer_dict.get("peer_id") == self._local_peer_id:
            return
        if self._on_peer_found:
            try:
                self._on_peer_found(parsed, addr[0])
            except Exception:
                logger.exception("on_peer_found callback error")

    def error_received(self, exc):
        logger.debug("Discovery UDP error: %s", exc)

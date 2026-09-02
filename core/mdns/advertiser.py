# core/mdns/advertiser.py
"""Owns our self-advertised ServiceInfo lifecycle.

Only the worker thread is allowed to call this class. Do NOT import asyncio
here — this file runs exclusively in the dedicated mDNS thread.
"""
from __future__ import annotations

import logging
import socket
from typing import Any
from urllib.parse import urlsplit

from core.mdns.peer_info import PeerInfo, assert_txt_size
from core.mdns.service_types import OLLAMA_SERVICE_TYPE, SERVICE_TYPE

logger = logging.getLogger("core.mdns.advertiser")


def _detect_local_addresses() -> list[bytes]:
    """Return the routable IPv4 addresses of this host as packed bytes.

    Uses a UDP trick to ask the kernel which address it would use to reach the
    internet — this picks the primary interface in multi-homed setups — then
    falls back to ``gethostbyname_ex`` and finally to ``127.0.0.1``.
    """
    addrs: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            primary = s.getsockname()[0]
            if primary:
                addrs.append(primary)
    except OSError:
        pass
    try:
        _, _, fallback = socket.gethostbyname_ex(socket.gethostname())
        for a in fallback:
            if a not in addrs and not a.startswith("127."):
                addrs.append(a)
    except OSError:
        pass
    if not addrs:
        addrs = ["127.0.0.1"]
    return [socket.inet_aton(a) for a in addrs]


class ZeroconfAdvertiser:
    def __init__(self, service_info_cls: Any) -> None:
        self._service_info_cls = service_info_cls
        self._registered: Any | None = None
        self._registered_ollama: Any | None = None

    def register(self, zc: Any, self_peer: PeerInfo, instance_name: str) -> None:
        txt = self_peer.to_txt()
        assert_txt_size(txt)  # fail-fast on oversized payload

        info = self._service_info_cls(
            SERVICE_TYPE,
            f"{instance_name}.{SERVICE_TYPE}",
            addresses=_detect_local_addresses(),
            port=self_peer.web_port,
            properties=txt,
            server=f"{self_peer.hostname}.",
        )
        zc.register_service(info)
        self._registered = info
        logger.info("[mdns] advertising %s on port %d", info.name, self_peer.web_port)

    def update(self, zc: Any, self_peer: PeerInfo) -> None:
        """Update the primary _yu-ai._tcp advertisement in place."""
        if self._registered is None:
            raise RuntimeError("primary service not registered")
        txt = self_peer.to_txt()
        assert_txt_size(txt)
        info = self._service_info_cls(
            SERVICE_TYPE,
            self._registered.name,
            addresses=_detect_local_addresses(),
            port=self_peer.web_port,
            properties=txt,
            server=f"{self_peer.hostname}.",
        )
        zc.update_service(info)
        self._registered = info
        logger.info("[mdns] updated %s on port %d", info.name, self_peer.web_port)

    def register_ollama(
        self,
        zc: Any,
        *,
        base_url: str,
        instance_name: str,
        hostname: str,
    ) -> None:
        split = urlsplit(base_url)
        port = split.port or 11434
        info = self._service_info_cls(
            OLLAMA_SERVICE_TYPE,
            f"{instance_name}.{OLLAMA_SERVICE_TYPE}",
            addresses=_detect_local_addresses(),
            port=port,
            properties={},
            server=f"{hostname}.",
        )
        zc.register_service(info)
        self._registered_ollama = info
        logger.info("[mdns] advertising %s on port %d", info.name, port)

    def update_ollama(
        self,
        zc: Any,
        *,
        base_url: str,
        hostname: str,
    ) -> None:
        """Update or register the companion _ollama._tcp advertisement."""
        if self._registered_ollama is None:
            instance_name = hostname.rstrip(".")
            self.register_ollama(
                zc,
                base_url=base_url,
                instance_name=f"{instance_name}-ollama",
                hostname=hostname,
            )
            return
        split = urlsplit(base_url)
        port = split.port or 11434
        info = self._service_info_cls(
            OLLAMA_SERVICE_TYPE,
            self._registered_ollama.name,
            addresses=_detect_local_addresses(),
            port=port,
            properties={},
            server=f"{hostname}.",
        )
        zc.update_service(info)
        self._registered_ollama = info
        logger.info("[mdns] updated %s on port %d", info.name, port)

    def unregister(self, zc: Any) -> None:
        if self._registered is None:
            return
        try:
            zc.unregister_service(self._registered)
            logger.info("[mdns] unregistered %s", self._registered.name)
        except Exception as exc:
            logger.warning("[mdns] unregister failed: %s", exc)
        finally:
            self._registered = None
        if self._registered_ollama is None:
            return
        try:
            zc.unregister_service(self._registered_ollama)
            logger.info("[mdns] unregistered %s", self._registered_ollama.name)
        except Exception as exc:
            logger.warning("[mdns] unregister failed: %s", exc)
        finally:
            self._registered_ollama = None

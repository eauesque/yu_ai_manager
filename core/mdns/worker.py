# core/mdns/worker.py
"""Dedicated-thread driver for the synchronous zeroconf API.

This file is the only one in core/mdns that touches the ``zeroconf`` package
(via the factories injected by :class:`MdnsService`). Do NOT import asyncio
here — this thread must never interact with the main event loop directly.
Event delivery is handled by ``MdnsService`` via ``loop.call_soon_threadsafe``.
"""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

from core.mdns.advertiser import ZeroconfAdvertiser
from core.mdns.browser import BrowserListener, RawEvent
from core.mdns.peer_info import PeerInfo
from core.mdns.service_types import BROWSE_SERVICE_TYPES

logger = logging.getLogger("core.mdns.worker")


class MdnsWorker:
    def __init__(
        self,
        *,
        zeroconf_factory: Callable[[], Any],
        service_info_cls: Any,
        service_browser_cls: Any,
        out_queue: queue.Queue[RawEvent],
    ) -> None:
        self._zeroconf_factory = zeroconf_factory
        self._service_info_cls = service_info_cls
        self._service_browser_cls = service_browser_cls
        self._queue = out_queue
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._zc: Any = None
        self._advertiser: ZeroconfAdvertiser | None = None
        self._listener: BrowserListener | None = None
        self._browsers: list[Any] = []
        self._self_peer: PeerInfo | None = None
        self._instance_name: str | None = None
        self._ready_event = threading.Event()
        self._init_error: BaseException | None = None

    def start(self, self_peer: PeerInfo, instance_name: str) -> None:
        self._self_peer = self_peer
        self._instance_name = instance_name
        self._thread = threading.Thread(
            target=self._run,
            name="mdns-worker",
            daemon=True,
        )
        self._thread.start()
        self._ready_event.wait(timeout=5.0)
        if self._init_error is not None:
            raise self._init_error

    def _run(self) -> None:
        try:
            self._zc = self._zeroconf_factory()
            self._advertiser = ZeroconfAdvertiser(self._service_info_cls)
            assert self._self_peer is not None and self._instance_name is not None
            self._advertiser.register(self._zc, self._self_peer, self._instance_name)
            if getattr(self._self_peer, "ollama_advertise_url", ""):
                self._advertiser.register_ollama(
                    self._zc,
                    base_url=self._self_peer.ollama_advertise_url,
                    instance_name=f"{self._instance_name}-ollama",
                    hostname=self._self_peer.hostname,
                )
            self._listener = BrowserListener(self._queue)
            self._browsers = [
                self._service_browser_cls(self._zc, service_type, self._listener)
                for service_type in BROWSE_SERVICE_TYPES
            ]
        except BaseException as exc:  # noqa: BLE001 — propagated to start()
            self._init_error = exc
            self._ready_event.set()
            return
        self._ready_event.set()
        self._stop_event.wait()
        self._teardown()

    def _teardown(self) -> None:
        try:
            for browser in self._browsers:
                try:
                    cancel = getattr(browser, "cancel", None)
                    if callable(cancel):
                        cancel()
                except Exception as exc:
                    logger.warning("[mdns] browser.cancel raised: %s", exc)
            if self._advertiser is not None and self._zc is not None:
                self._advertiser.unregister(self._zc)
            if self._zc is not None:
                try:
                    self._zc.close()
                except Exception as exc:
                    logger.warning("[mdns] zeroconf.close raised: %s", exc)
        finally:
            self._zc = None
            self._browsers = []
            self._listener = None
            self._advertiser = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

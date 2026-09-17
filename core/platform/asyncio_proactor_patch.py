"""Silence harmless ConnectionResetError noise from Windows ProactorEventLoop.

On Windows + Python's ProactorEventLoop, when a remote peer abruptly closes a
TCP connection (RST), the transport's cleanup path calls
``socket.shutdown(SHUT_RDWR)`` on an already-reset socket. This surfaces as
``ConnectionResetError: [WinError 10054]`` logged from
``_ProactorBasePipeTransport._call_connection_lost``. It does not affect
correctness -- the connection is already gone -- but it spams the log.

The fix below is the same approach used by aiohttp, Tornado, and Discord.py:
wrap ``_call_connection_lost`` so the well-known cleanup-time exceptions are
swallowed. No-op on non-Windows platforms.
"""

from __future__ import annotations

import contextlib
import logging
import sys

logger = logging.getLogger(__name__)

_installed = False


def install_proactor_connection_reset_silencer() -> None:
    """Install monkey patch once. Safe to call multiple times."""
    global _installed
    if _installed:
        return
    if sys.platform != "win32":
        _installed = True
        return

    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
    except ImportError:
        return

    original = _ProactorBasePipeTransport._call_connection_lost  # pyright: ignore[reportAttributeAccessIssue]

    def _silenced_call_connection_lost(self, exc):  # type: ignore[no-untyped-def]
        # Peer already gone; shutdown() can race with RST. Harmless.
        with contextlib.suppress(ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            original(self, exc)

    _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost  # pyright: ignore[reportAttributeAccessIssue]
    _installed = True
    logger.debug("Installed ProactorEventLoop ConnectionResetError silencer")

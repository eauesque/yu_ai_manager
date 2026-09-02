"""Graceful shutdown handler for the Quart application.

Three layers of shutdown protection:
  1. ``@app.after_serving`` — Quart's native hook (ideal path)
  2. ``atexit`` — fires when Python interpreter is exiting
  3. ``SIGINT/SIGTERM`` handler — fires on Ctrl+C / kill
  4. Watchdog timer — force ``os._exit()`` after deadline

Cleanup order:
  1. Stream capture threads + pipeline + recorder (OpenCV / FFmpeg)
  2. SSE dedicated server
  3. Hailo device
  4. APScheduler
  5. Webhook dispatcher
"""

from __future__ import annotations

import atexit
import contextlib
import faulthandler
import logging
import os
import signal
import threading

from quart import Quart

logger = logging.getLogger(__name__)

_SHUTDOWN_TIMEOUT = 8  # seconds — force exit after this
_shutdown_done = threading.Event()
_sigint_count = 0  # Track repeated Ctrl-C

# /dev/null file kept open for faulthandler's deferred write (must outlive the timer)
_DEVNULL_FD: object | None = None


def _open_devnull() -> None:
    """Open /dev/null once at signal-handler install time."""
    global _DEVNULL_FD
    try:
        _DEVNULL_FD = open(os.devnull, "w")  # noqa: SIM115 — intentionally long-lived
    except Exception:
        _DEVNULL_FD = None


def register_shutdown(app: Quart) -> None:
    """Register all shutdown hooks on *app*."""

    @app.after_serving
    async def _graceful_shutdown() -> None:
        _run_shutdown("after_serving")

    # Fallback: atexit (runs if after_serving was never called)
    atexit.register(lambda: _run_shutdown("atexit"))

    # Signal handlers: ensure shutdown runs even if Quart doesn't cooperate
    _install_signal_handlers()


def _run_shutdown(source: str) -> None:
    """Execute shutdown sequence exactly once."""
    if _shutdown_done.is_set():
        return
    _shutdown_done.set()

    logger.info("Shutting down subsystems (via %s)...", source)

    # Watchdog: force exit if cleanup hangs
    watchdog = threading.Timer(_SHUTDOWN_TIMEOUT, _force_exit)
    watchdog.daemon = True
    watchdog.start()

    try:
        _shutdown_streams()
        _shutdown_sse()
        _shutdown_hailo()
        _shutdown_scheduler()
        _shutdown_webhooks()
        _shutdown_mdns()
    except Exception as exc:
        logger.warning("Shutdown error (non-fatal): %s", exc)
    finally:
        watchdog.cancel()
        # Cancel C-level faulthandler watchdog — graceful shutdown completed.
        with contextlib.suppress(Exception):
            faulthandler.cancel_dump_traceback_later()

    logger.info("All subsystems stopped.")


def _force_exit() -> None:
    """Watchdog: force-exit if graceful shutdown exceeds the timeout."""
    # Cancel the C-level faulthandler watchdog — we're exiting via Python now.
    with contextlib.suppress(Exception):
        faulthandler.cancel_dump_traceback_later()
    logger.warning(
        "Shutdown timed out after %ds — force exiting", _SHUTDOWN_TIMEOUT,
    )
    os._exit(1)


def _install_signal_handlers() -> None:
    """Install SIGINT/SIGTERM handlers that trigger shutdown + exit."""
    global _sigint_count
    _sigint_count = 0
    _open_devnull()

    def _handler(signum, _frame):
        global _sigint_count
        _sigint_count += 1
        sig_name = signal.Signals(signum).name

        # Second Ctrl-C while shutdown is already in progress: force exit now.
        # At this point the GIL is available (we're in Python code between C calls),
        # so os._exit() is callable.
        if _sigint_count >= 2:
            logger.warning("Second %s received — forcing immediate exit", sig_name)
            os._exit(1)

        logger.info("Received %s — initiating shutdown", sig_name)

        # Install a C-level SIGALRM watchdog via faulthandler as last resort.
        # faulthandler's internal thread uses SIGALRM and calls _exit() directly
        # at the C level — this bypasses the GIL entirely and guarantees process
        # exit even if HailoRT C extensions hold the GIL indefinitely
        # (e.g. VDevice.release() hanging after a device error).
        try:
            kwargs: dict = {"exit": True}
            if _DEVNULL_FD is not None:
                kwargs["file"] = _DEVNULL_FD
            faulthandler.dump_traceback_later(15, **kwargs)
        except Exception:
            logger.warning("web startup step failed", exc_info=True)

        _run_shutdown(sig_name)
        # After cleanup, raise KeyboardInterrupt so Quart/Hypercorn exits
        raise KeyboardInterrupt

    with contextlib.suppress(OSError, ValueError):  # Can't set in non-main thread
        signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        with contextlib.suppress(OSError, ValueError):
            signal.signal(signal.SIGTERM, _handler)


def _shutdown_streams() -> None:
    """Stop YOLO stream capture threads, pipeline, and recorder."""
    import sys
    for mod_name, mod in list(sys.modules.items()):
        if mod_name.endswith(".stream.stream_routes") and "hailo" in mod_name:
            recorder = getattr(mod, "_recorder", None)
            pipeline = getattr(mod, "_pipeline", None)
            manager = getattr(mod, "_manager", None)
            if recorder is not None:
                logger.info("  [SHUTDOWN] Stopping recorder...")
                recorder.stop_all()
            if pipeline is not None:
                logger.info("  [SHUTDOWN] Stopping pipeline...")
                pipeline.stop()
            if manager is not None:
                logger.info("  [SHUTDOWN] Stopping stream sources...")
                manager.stop_all()
            return


def _shutdown_sse() -> None:
    """Stop the dedicated SSE server."""
    try:
        from core.sse.sse_server import stop_sse_server
        logger.info("  [SHUTDOWN] Stopping SSE server...")
        stop_sse_server()
    except Exception as exc:
        logger.debug("SSE shutdown skipped: %s", exc)


def _shutdown_hailo() -> None:
    """Release all Hailo models and the shared VDevice."""
    try:
        from core.hailo_device_core.device_manager import (
            get_active_owners,
            shutdown_all,
        )
        owners = get_active_owners()
        if owners:
            logger.info(
                "  [SHUTDOWN] Releasing Hailo device (models: %s)...",
                ", ".join(owners),
            )
            shutdown_all()
    except Exception as exc:
        logger.debug("Hailo shutdown skipped: %s", exc)


def _shutdown_scheduler() -> None:
    """Shut down APScheduler if running."""
    try:
        from core.scheduler_core import scheduler_manager
        if scheduler_manager._running:
            logger.info("  [SHUTDOWN] Stopping scheduler...")
            scheduler_manager.stop()
    except Exception as exc:
        logger.debug("Scheduler shutdown skipped: %s", exc)


def _shutdown_webhooks() -> None:
    """Stop the webhook dispatcher."""
    try:
        from core.webhook import webhook_dispatcher
        if webhook_dispatcher and hasattr(webhook_dispatcher, "stop"):
            logger.info("  [SHUTDOWN] Stopping webhook dispatcher...")
            webhook_dispatcher.stop()
    except Exception as exc:
        logger.debug("Webhook shutdown skipped: %s", exc)


def _shutdown_mdns() -> None:
    """Stop the mDNS worker thread (unregister + close zeroconf)."""
    try:
        import core.web.runtime_mdns as rs
        svc = getattr(rs, "_MDNS_SERVICE", None)
        if svc is None or svc._worker is None:
            return
        logger.info("  [SHUTDOWN] Stopping mDNS worker...")
        # Use the worker's sync stop() directly. This avoids needing an
        # event loop in atexit/signal shutdown paths; the worker thread's
        # teardown handles advertiser.unregister + zeroconf.close.
        svc._worker.stop()
        rs._MDNS_SERVICE = None
    except Exception as exc:
        logger.debug("mDNS shutdown skipped: %s", exc)

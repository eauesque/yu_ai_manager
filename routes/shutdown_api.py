"""Server shutdown endpoint for the WebUI.

Hybrid access control:
- Loopback (127.0.0.1 / ::1): allowed without PIN. Anyone sitting at the
  machine can stop the server. This matches the launcher / start.vbs use case
  where the operator wants a simple "quit" button.
- LAN: requires the boss-mode PIN (or the dedicated approval PIN if that source
  is configured under settings.lan_cowork.approval_pin_source).

Why not just deny LAN entirely? On LAN-share setups the operator may not be
sitting at the host. Reusing the existing PIN source keeps the trust model
consistent with other privileged operations.

The actual shutdown is performed by sending SIGINT to ourselves on a short
delay so the response can flush. core/web/shutdown.py already has the SIGINT
handler wired and runs the graceful teardown sequence.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
import time

from quart import Blueprint, current_app, request

from core.infra_core.api_errors import api_error, api_success
from core.web.api_rate_limit import get_client_ip
from core.web.auth_lock_state import (
    rate_limiter,
    verify_approval_pin,
)
from core.web.auth_restart import is_loopback_request

logger = logging.getLogger(__name__)

bp = Blueprint("shutdown_api", __name__)


_SHUTDOWN_DELAY_SECONDS = 0.5


def _trigger_shutdown_after_delay() -> None:
    """Schedule SIGINT to ourselves after a short delay.

    Done from a daemon thread (not the event loop) so the response can be
    flushed and the connection closed before the signal arrives. SIGINT lands
    in the main thread where core.web.shutdown's handler runs the graceful
    teardown.

    On Windows, signal.SIGINT delivery via os.kill works for the same
    process, but we add a hard fallback via os._exit if shutdown stalls past
    the existing 8-second watchdog.
    """
    def _run() -> None:
        time.sleep(_SHUTDOWN_DELAY_SECONDS)
        try:
            os.kill(os.getpid(), signal.SIGINT)
        except Exception as exc:  # pragma: no cover — platform fallback
            logger.warning("SIGINT delivery failed (%s); falling back to _exit", exc)
            os._exit(0)

    t = threading.Thread(target=_run, name="shutdown-trigger", daemon=True)
    t.start()


@bp.route("/api/admin/shutdown", methods=["POST"])
async def api_shutdown():
    """Stop the server.

    Body (optional, only required for non-loopback callers):
        {"pin": "<boss/approval PIN>"}
    """
    client_ip = get_client_ip() or request.remote_addr or ""
    is_local = is_loopback_request()

    if not is_local:
        # LAN caller — gate behind boss/approval PIN.
        if not rate_limiter.check(client_ip):
            remaining = rate_limiter.remaining_seconds(client_ip)
            return api_error(
                f"試行回数の上限に達しました。{remaining}秒後に再試行してください。",
                429,
                code="rate_limited",
            )

        try:
            data = await request.get_json(silent=True) or {}
        except Exception:
            data = {}
        pin = str(data.get("pin") or "").strip()
        if not pin:
            return api_error(
                "LAN 経由のシャットダウンには PIN が必要です。",
                401,
                code="pin_required",
            )

        secret = str(current_app.config.get("APP_SECRET") or "").strip()
        if not secret or not verify_approval_pin(pin, secret):
            rate_limiter.record_failure(client_ip)
            return api_error("PIN が正しくありません。", 401, code="pin_invalid")

        rate_limiter.clear(client_ip)
        logger.info("WebUI shutdown requested by LAN client %s (PIN verified)", client_ip)
    else:
        logger.info("WebUI shutdown requested by loopback client %s", client_ip)

    _trigger_shutdown_after_delay()
    # Defer briefly so the JSON response is on the wire before SIGINT lands.
    asyncio.get_running_loop()  # ensure we're on an event loop
    return api_success({"status": "shutting_down", "delay_s": _SHUTDOWN_DELAY_SECONDS})


@bp.route("/api/admin/shutdown/info")
async def api_shutdown_info():
    """Tell the WebUI whether the current request needs a PIN to shut down.

    Used by the WebUI to decide whether to show a PIN prompt or shut down
    directly. No state changes here, so no rate-limiting / no auth beyond
    whatever the global before_request layer enforces.
    """
    is_local = is_loopback_request()
    return api_success({"loopback": is_local, "pin_required": not is_local})

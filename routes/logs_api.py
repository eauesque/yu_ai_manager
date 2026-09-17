"""Log streaming API endpoints.

- GET  /api/logs/recent       -- JSON: recent log entries
- GET  /api/logs/stream       -- SSE: real-time log stream (independent of shared SSE)
- POST /api/internal/log      -- Write a log entry from a subprocess (localhost only)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time

from quart import Blueprint, Response, request

from core.infra_core.api_errors import api_error
from core.infra_core.log_ring_buffer import LogEntry, log_ring
from core.web.api_rate_limit import get_client_ip

bp = Blueprint("logs_api", __name__)

# ---------------------------------------------------------------------------
# Per-IP SSE connection limiter (separate from main SSE)
# ---------------------------------------------------------------------------
_MAX_LOG_SSE_PER_IP = 3
_MAX_STREAM_AGE = 300  # seconds
_CONN_AGE_LIMIT = _MAX_STREAM_AGE + 30
_log_sse_starts: dict[str, list[float]] = {}
_log_sse_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Heartbeat / SSE constants
# ---------------------------------------------------------------------------
_HEARTBEAT_SEC = 15


from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_local as _require_local


@bp.route("/api/internal/log", methods=["POST"])
async def api_internal_log():
    """Accept a log entry from a local subprocess (e.g. MCP) and write to log_ring.

    Restricted to localhost callers only.  No admin auth required because the
    caller is the same machine's MCP subprocess and may not hold a session token.
    """
    err = _require_local("Internal log write")
    if err:
        return err
    try:
        body = await request.get_json(force=True, silent=True) or {}
        level = str(body.get("level", "INFO")).upper()
        message = str(body.get("message", ""))[:2000]
        source = str(body.get("source", "subprocess"))[:64]
        # Append any extra key=value pairs to the message for visibility
        extra_parts = [
            f"{k}={v}"
            for k, v in body.items()
            if k not in {"level", "message", "source"}
        ]
        if extra_parts:
            message = message + " | " + " ".join(extra_parts)
        log_ring.append(LogEntry(
            timestamp=time.time(),
            level=level,
            source=source,
            message=message,
        ))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@bp.route("/api/logs/recent")
async def api_logs_recent():
    """Return recent log entries as JSON."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    limit = request.args.get("limit", 200, type=int)
    limit = max(1, min(limit, 2000))
    level = request.args.get("level", "").strip() or None

    entries = log_ring.recent(limit=limit, level=level)
    return {"ok": True, "data": entries, "count": len(entries)}


@bp.route("/api/logs/stream")
async def api_logs_stream():
    """SSE endpoint for real-time log streaming.

    Independent from the shared ``/api/events/stream`` because log
    events are high-frequency and only needed on the Settings page.

    Query params:
      level  -- minimum log level filter (DEBUG/INFO/WARNING/ERROR)
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    ip = get_client_ip() or "unknown"
    now = time.monotonic()

    with _log_sse_lock:
        starts = _log_sse_starts.get(ip)
        if starts:
            _log_sse_starts[ip] = [
                t for t in starts if now - t < _CONN_AGE_LIMIT
            ]
            if not _log_sse_starts[ip]:
                del _log_sse_starts[ip]

        if len(_log_sse_starts.get(ip, [])) >= _MAX_LOG_SSE_PER_IP:
            return api_error("Too many log SSE connections", 429)
        _log_sse_starts.setdefault(ip, []).append(now)

    conn_start = now
    level = request.args.get("level", "").strip() or None

    async def generate():
        try:
            last_seq = log_ring.last_seq
            start_mono = time.monotonic()
            last_heartbeat = time.monotonic()
            while True:
                if time.monotonic() - start_mono > _MAX_STREAM_AGE:
                    # Clean close: EventSource auto-reconnects after retry ms
                    yield "retry: 1000\n\n"
                    return
                entries = log_ring.get_since(last_seq, level=level)
                if entries:
                    for entry in entries:
                        last_seq = entry["seq"]
                        yield f"event: log.entry\ndata: {json.dumps(entry, ensure_ascii=False)}\n\n"
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= _HEARTBEAT_SEC:
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.monotonic()
                await asyncio.sleep(0.25)
        finally:
            with _log_sse_lock:
                starts = _log_sse_starts.get(ip)
                if starts:
                    with contextlib.suppress(ValueError):
                        starts.remove(conn_start)
                    if not starts:
                        _log_sse_starts.pop(ip, None)

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp

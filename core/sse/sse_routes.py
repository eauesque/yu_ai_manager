"""SSE streaming endpoint.

Redirects via 307 when the dedicated SSE server is running.
Falls back to the traditional Quart Generator approach when not started.
"""

from __future__ import annotations

import contextlib
import threading
import time

from quart import Blueprint, Response, redirect, request

from core.infra_core.api_errors import api_error
from core.sse import sse_broadcaster
from core.sse.auth import get_auth_refresh_deadline, is_configured, issue_sse_token
from core.sse.broadcaster import MAX_STREAM_AGE
from core.web.api_rate_limit import get_client_ip
from core.web.public_host import resolve_public_host

bp = Blueprint("sse_core", __name__)

# Per-IP SSE connection limiter (used in fallback mode).
# Not needed when dedicated SSE server is running, as it handles its own limits.
_MAX_SSE_PER_IP = 100
_CONN_AGE_LIMIT = MAX_STREAM_AGE + 30  # small buffer over stream age
_sse_ip_starts: dict[str, list[float]] = {}
_sse_lock = threading.Lock()


@bp.route("/api/events/stream")
async def api_events_stream():
    """SSE endpoint. Optional ?types=scan.progress,scan.complete filter.

    Redirect via 307 if the dedicated SSE server is running.
    EventSource auto-follows 307, so no frontend changes needed.
    """
    # Redirect to dedicated SSE server
    from core.sse.sse_server import get_sse_port

    sse_port = get_sse_port()
    if sse_port is not None:
        client_ip = get_client_ip()
        types_param = request.args.get("types", "")
        redirect_url = f"http://{resolve_public_host(client_ip)}:{sse_port}/stream"
        if is_configured():
            auth_token, _expires_at = issue_sse_token(client_ip)
            redirect_url += f"?auth={auth_token}"
        if types_param:
            redirect_url += f"{'&' if '?' in redirect_url else '?'}types={types_param}"
        return redirect(redirect_url, code=307)

    # Fallback: legacy Quart Generator approach
    ip = request.remote_addr or "unknown"
    now = time.monotonic()

    with _sse_lock:
        # Prune zombie slots older than _CONN_AGE_LIMIT
        starts = _sse_ip_starts.get(ip)
        if starts:
            _sse_ip_starts[ip] = [t for t in starts if now - t < _CONN_AGE_LIMIT]
            if not _sse_ip_starts[ip]:
                del _sse_ip_starts[ip]

        if len(_sse_ip_starts.get(ip, [])) >= _MAX_SSE_PER_IP:
            return api_error("Too many SSE connections", 429)
        _sse_ip_starts.setdefault(ip, []).append(now)

    conn_start = now
    types_param_val = request.args.get("types", "").strip()
    type_filter = set(types_param_val.split(",")) if types_param_val else None

    async def generate():
        try:
            async for chunk in sse_broadcaster.astream(type_filter=type_filter):
                yield chunk
        finally:
            with _sse_lock:
                starts = _sse_ip_starts.get(ip)
                if starts:
                    with contextlib.suppress(ValueError):
                        starts.remove(conn_start)
                    if not starts:
                        _sse_ip_starts.pop(ip, None)

    resp = Response(generate(), mimetype="text/event-stream")
    resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp


@bp.route("/api/events/info")
async def api_events_info():
    """Return SSE connection info.

    Used when client wants to know the SSE server port in advance.
    Normally the 307 redirect from /api/events/stream handles the
    connection automatically, so calling this endpoint is not required.
    """
    from core.sse.sse_server import get_sse_port

    port = get_sse_port()
    stream_url = None
    expires_at = None
    if port is not None and is_configured():
        client_ip = get_client_ip()
        auth_token, expires_at = issue_sse_token(client_ip)
        stream_url = (
            f"http://{resolve_public_host(client_ip)}:{port}/stream"
            f"?auth={auth_token}"
        )
    return {
        "sse_port": port,
        "dedicated_server": port is not None,
        "stream_url": stream_url,
        "expires_at": expires_at,
        "refresh_after": get_auth_refresh_deadline() if port is not None else None,
    }

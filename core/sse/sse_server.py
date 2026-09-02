"""Dedicated SSE thread server.

Delivers SSE via dedicated threads without occupying Flask request threads.
Listens on a separate port within the same process as the main Flask server.

Architecture:
  [Browser EventSource] ---> [SSE dedicated HTTPServer (separate thread, separate port)]
                                       |
  [Flask event_bus.emit()] ---> [SSEBroadcaster._on_event()] ---> [client queues]

Flask's /api/events/stream redirects to SSE server via 307.
On SSE server startup failure, falls back to the traditional Flask Generator approach.
"""

from __future__ import annotations

import contextlib
import http.server
import logging
import socket
import socketserver
import threading
import time
from urllib.parse import parse_qs, urlparse

from core.sse.auth import is_allowed_sse_origin, validate_sse_token
from core.sse.broadcaster import MAX_STREAM_AGE, SSEBroadcaster

logger = logging.getLogger(__name__)

# Max simultaneous SSE connections per IP (same value as sse_routes.py)
_MAX_SSE_PER_IP = 100
# Grace period before auto-purging zombie connections (seconds)
_CONN_AGE_LIMIT = MAX_STREAM_AGE + 30

# Module-level singleton
_server: SSEServer | None = None
_server_lock = threading.Lock()

# IP-based connection tracking (list of monotonic timestamps)
_sse_ip_starts: dict[str, list[float]] = {}
_ip_lock = threading.Lock()


class SSEHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for processing SSE requests."""

    # Use HTTP/1.1 (for keep-alive)
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        """Suppress werkzeug-style log output, debug level only."""
        logger.debug("SSE: %s", format % args)

    def do_OPTIONS(self):
        """Respond to CORS preflight requests."""
        self._send_cors_headers(204)

    def do_GET(self):
        """Process SSE stream requests."""
        parsed = urlparse(self.path)
        if parsed.path != "/stream":
            self.send_error(404, "Not Found")
            return

        # Parse types parameter
        params = parse_qs(parsed.query)
        auth_token = params.get("auth", [""])[0].strip()
        types_param = params.get("types", [""])[0].strip()
        type_filter: set[str] | None = (
            set(types_param.split(",")) if types_param else None
        )

        ip = self.client_address[0] if self.client_address else "unknown"
        if not validate_sse_token(auth_token, ip):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # IP-based rate limiting
        now = time.monotonic()

        with _ip_lock:
            # Purge zombie slots
            starts = _sse_ip_starts.get(ip)
            if starts:
                _sse_ip_starts[ip] = [
                    t for t in starts if now - t < _CONN_AGE_LIMIT
                ]
                if not _sse_ip_starts[ip]:
                    del _sse_ip_starts[ip]

            if len(_sse_ip_starts.get(ip, [])) >= _MAX_SSE_PER_IP:
                # Must include CORS headers even on error responses,
                # otherwise browser reports CORS error instead of 429
                self._send_cors_headers(429)
                return
            _sse_ip_starts.setdefault(ip, []).append(now)

        conn_start = now

        # Send response headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "keep-alive")
        # Don't use Transfer-Encoding: chunked, write directly
        # Omitting Content-Length enables streaming on HTTP/1.1
        # CORS: Allow origin since clients connect directly to the SSE port
        origin = self.headers.get("Origin", "")
        if origin and is_allowed_sse_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()

        # Send data from SSEBroadcaster.stream() Generator
        server: SSEServer = self.server  # type: ignore[assignment]
        try:
            for chunk in server.broadcaster.stream(type_filter=type_filter):
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Client disconnected
        finally:
            # Clean up IP connection tracking
            with _ip_lock:
                starts = _sse_ip_starts.get(ip)
                if starts:
                    with contextlib.suppress(ValueError):
                        starts.remove(conn_start)
                    if not starts:
                        _sse_ip_starts.pop(ip, None)

    def _send_cors_headers(self, code: int = 200) -> None:
        """Send response with CORS headers."""
        origin = self.headers.get("Origin", "")
        self.send_response(code)
        if origin and is_allowed_sse_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
        self.send_header("Content-Length", "0")
        self.end_headers()


class SSEServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Multi-threaded dedicated SSE server.

    With ThreadingMixIn, each SSE connection is handled by an individual daemon thread.
    These threads are independent from Flask's request thread pool.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, broadcaster: SSEBroadcaster):
        self.broadcaster = broadcaster
        super().__init__((host, port), SSEHandler)

    def handle_error(self, request, client_address):  # type: ignore[override]
        """Suppress ConnectionAbortedError from client disconnections."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return  # Browser just closed the connection, no logging needed
        super().handle_error(request, client_address)


def start_sse_server(
    host: str, flask_port: int, broadcaster: SSEBroadcaster
) -> int | None:
    """Start dedicated SSE server in background thread.

    Args:
        host: Bind host (same as Flask)
        flask_port: Flask port number (SSE searches from flask_port + 1)
        broadcaster: SSEBroadcaster instance

    Returns:
        SSE server port number. None on startup failure.
    """
    global _server
    with _server_lock:
        if _server is not None:
            return _server.server_address[1]

        # Find an available port (try flask_port + 1 through + 9)
        sse_port: int | None = None
        for offset in range(1, 10):
            candidate = flask_port + offset
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((host, candidate))
                sse_port = candidate
                break
            except OSError:
                continue

        if sse_port is None:
            logger.warning(
                "SSE サーバー: ポート %d-%d が全て使用中。"
                "従来の Flask Generator 方式にフォールバック",
                flask_port + 1,
                flask_port + 9,
            )
            return None

        try:
            _server = SSEServer(host, sse_port, broadcaster)
        except OSError as exc:
            logger.warning(
                "SSE サーバー起動失敗 (port %d): %s。フォールバック",
                sse_port,
                exc,
            )
            return None

        thread = threading.Thread(
            target=_server.serve_forever,
            name="sse-server",
            daemon=True,
        )
        thread.start()
        logger.info(
            "SSE 専用サーバー起動: http://%s:%d/stream", host, sse_port
        )
        return sse_port


def get_sse_port() -> int | None:
    """Return SSE server port number. None if not started."""
    if _server is None:
        return None
    return _server.server_address[1]


def stop_sse_server() -> None:
    """Stop the SSE server."""
    global _server
    with _server_lock:
        if _server is not None:
            _server.shutdown()
            _server = None
            logger.info("SSE 専用サーバー停止")

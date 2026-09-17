"""MCP HTTP/SSE endpoint — serves MCP protocol for LAN clients.

Provides FastMCP streamable-http transport within Quart.
localhost: no auth required; LAN IP: API Key required.

Split into three modules:
  - mcp_auth.py:    internal token management + auth checks
  - mcp_handler.py: JSON-RPC dispatch to MCP server
  - mcp_endpoint.py (this file): Blueprint + HTTP routes + session management
"""

import contextlib
import json
import os
import queue
import threading
import uuid

from quart import Blueprint, Response, request

from core.infra_core.api_errors import api_error

# Re-export for backward compatibility
# (auth_routes.py imports get_internal_token from routes.mcp_endpoint)
from core.mcp_api.auth import _check_mcp_auth, get_internal_token  # noqa: F401
from core.mcp_api.handler import SUPPORTED_VERSIONS, _handle_jsonrpc
from core.services_core.db_async import run_db_sync
from core.web.api_rate_limit import get_client_ip

bp = Blueprint("mcp_endpoint", __name__)

# Session management (MCP JSON-RPC over SSE)
_sessions: dict[str, "McpSession"] = {}
_sessions_lock = threading.Lock()
_sessions_per_ip: dict[str, int] = {}

_MAX_SESSIONS = max(1, int(os.environ.get("YU_MCP_MAX_SESSIONS", "1000")))
_MAX_SESSIONS_PER_IP = max(1, int(os.environ.get("YU_MCP_MAX_SESSIONS_PER_IP", "20")))
_QUEUE_MAXSIZE = max(1, int(os.environ.get("YU_MCP_QUEUE_MAXSIZE", "256")))
_MISSING = object()


def _meta_protocol_version(params: object) -> str | None:
    if not isinstance(params, dict):
        return None
    meta = params.get("_meta")
    value = meta.get("io.modelcontextprotocol/protocolVersion") if isinstance(meta, dict) else None
    return value if isinstance(value, str) else None


def classify_protocol_version(headers, params: object) -> dict | None:
    """Return a JSON-RPC transport rejection, if any."""
    header = headers.get("MCP-Protocol-Version")
    meta = _meta_protocol_version(params)
    for version in (header, meta):
        if version is not None and version not in SUPPORTED_VERSIONS:
            return {
                "code": -32022,
                "message": "Unsupported protocol version",
                "data": {"supported": SUPPORTED_VERSIONS, "requested": version},
            }
    if header is not None and meta is not None and header != meta:
        return {
            "code": -32600,
            "message": "Invalid Request",
            "data": {"header": header, "meta": meta},
        }
    return None


def version_reject_response(rejection: dict, msg_id: object = _MISSING) -> Response:
    if msg_id is _MISSING:
        return Response("", status=400)
    return Response(
        json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": rejection}),
        status=400,
        mimetype="application/json",
    )


def declared_2026(headers, method: str, params: object) -> bool:
    return (
        headers.get("MCP-Protocol-Version") == "2026-07-28"
        or _meta_protocol_version(params) == "2026-07-28"
        or (
            method == "initialize"
            and isinstance(params, dict)
            and params.get("protocolVersion") == "2026-07-28"
        )
    )


class McpSession:
    """Represents a single MCP SSE session."""

    def __init__(self, session_id: str, owner_ip: str):
        self.session_id = session_id
        self.owner_ip = owner_ip
        self.message_queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self.alive = True

    def send(self, data: dict):
        if not self.alive:
            return
        try:
            self.message_queue.put_nowait(data)
        except queue.Full:
            # Backpressure safety: avoid unbounded memory growth.
            self.close()

    def close(self):
        self.alive = False
        try:
            self.message_queue.put_nowait(None)  # sentinel
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self.message_queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self.message_queue.put_nowait(None)


@bp.route("/mcp", methods=["GET"])
async def mcp_sse():
    """SSE stream — establish an MCP session."""
    auth_err = _check_mcp_auth()
    if auth_err:
        return auth_err
    if (rejection := classify_protocol_version(request.headers, None)) is not None:
        return version_reject_response(rejection)
    if declared_2026(request.headers, "", None):
        return Response("", status=405)

    remote_ip = (get_client_ip() or "").strip() or "unknown"
    session_id = str(uuid.uuid4())
    session = McpSession(session_id, owner_ip=remote_ip)

    with _sessions_lock:
        if len(_sessions) >= _MAX_SESSIONS:
            return api_error("Too many active MCP sessions", 429)
        active_for_ip = _sessions_per_ip.get(remote_ip, 0)
        if active_for_ip >= _MAX_SESSIONS_PER_IP:
            return api_error("Too many MCP sessions from this IP", 429)
        _sessions[session_id] = session
        _sessions_per_ip[remote_ip] = active_for_ip + 1

    def generate():
        # Send session ID first
        yield f"event: endpoint\ndata: /mcp/message?session_id={session_id}\n\n"

        try:
            while session.alive:
                try:
                    msg = session.message_queue.get(timeout=30)
                    if msg is None:
                        break
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    # keepalive
                    yield ": keepalive\n\n"
        finally:
            with _sessions_lock:
                _sessions.pop(session_id, None)
                cur = _sessions_per_ip.get(remote_ip, 0)
                if cur <= 1:
                    _sessions_per_ip.pop(remote_ip, None)
                else:
                    _sessions_per_ip[remote_ip] = cur - 1

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@bp.route("/mcp/message", methods=["POST"])
async def mcp_message():
    """Receive an MCP message — process JSON-RPC request."""
    auth_err = _check_mcp_auth()
    if auth_err:
        return auth_err

    remote_ip = (get_client_ip() or "").strip() or "unknown"
    session_id = request.args.get("session_id", "")

    with _sessions_lock:
        session = _sessions.get(session_id)

    if not session:
        return api_error("Invalid or expired session", 404)
    if session.owner_ip != remote_ip:
        return api_error("Session owner mismatch", 403)

    try:
        msg = await request.get_json(force=True)
    except Exception:
        return api_error("Invalid JSON", 400)

    if not isinstance(msg, dict):
        return api_error("Expected JSON object", 400)
    if (rejection := classify_protocol_version(request.headers, msg.get("params"))) is not None:
        return version_reject_response(rejection, msg.get("id", _MISSING))

    # JSON-RPC processing
    declared = declared_2026(request.headers, msg.get("method", ""), msg.get("params"))
    response = await run_db_sync(_handle_jsonrpc, session_id, msg, declared)

    if response is not None:
        # Send to SSE stream & also return as HTTP response
        session.send(response)
        return Response(
            json.dumps(response, ensure_ascii=False),
            status=200,
            mimetype="application/json",
        )

    # Notification (no response needed)
    return Response("", status=202)


@bp.route("/mcp", methods=["POST"])
async def mcp_post():
    """POST /mcp — stateless JSON-RPC (single request)."""
    auth_err = _check_mcp_auth()
    if auth_err:
        return auth_err

    try:
        msg = await request.get_json(force=True)
    except Exception:
        return api_error("Invalid JSON", 400)

    if not isinstance(msg, dict):
        return api_error("Expected JSON object", 400)
    if (rejection := classify_protocol_version(request.headers, msg.get("params"))) is not None:
        return version_reject_response(rejection, msg.get("id", _MISSING))

    declared = declared_2026(request.headers, msg.get("method", ""), msg.get("params"))
    response = await run_db_sync(_handle_jsonrpc, "__stateless__", msg, declared)
    if response is None:
        return Response("", status=202)

    return Response(
        json.dumps(response, ensure_ascii=False),
        status=200,
        mimetype="application/json",
    )


@bp.route("/_internal/mcp/dispatch", methods=["POST"])
async def mcp_internal_dispatch():
    """Internal bridge: Rust MCP native handler → Python JSON-RPC dispatch.

    Loopback-only. Uses request.remote_addr directly to avoid XFF pollution.
    This internal bridge is not an HTTP MCP transport entrypoint.
    """
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return api_error("Internal endpoint: loopback only", 403)

    body = await request.get_json(force=True)
    if not isinstance(body, dict):
        return api_error("Expected JSON object", 400)

    session_id = body.get("session_id") or "__stateless__"
    msg = body.get("message", {})
    if not isinstance(msg, dict):
        return api_error("message must be a JSON object", 400)

    try:
        declared = declared_2026(request.headers, msg.get("method", ""), msg.get("params"))
        response = await run_db_sync(_handle_jsonrpc, session_id, msg, declared)
    except Exception as exc:
        return api_error(f"Dispatch error: {exc}", 500)

    return Response(
        json.dumps({"response": response}, ensure_ascii=False),
        status=200,
        mimetype="application/json",
    )

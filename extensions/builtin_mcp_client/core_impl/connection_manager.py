"""Thread-safe synchronous facade for MCP client connections.

``ConnectionManager`` is a singleton that Flask routes call to manage
connections.  It delegates all async I/O to the background loop via
:func:`async_bridge.run_async`.
"""

from __future__ import annotations

import contextlib
import logging
import threading

from . import async_bridge
from . import connection_config as cfg
from .mcp_session import McpConnection, call_tool_on_session, connect_session, disconnect_session

logger = logging.getLogger(__name__)


def _redact_headers(headers: dict | None) -> dict:
    if not isinstance(headers, dict):
        return {}
    return {str(k): "***" for k in headers}


class ConnectionManager:
    """Manage MCP client connections (singleton)."""

    _instance: ConnectionManager | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> ConnectionManager:
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._connections: dict[str, McpConnection] = {}
                    inst._lock = threading.Lock()
                    cls._instance = inst
        return cls._instance

    # ── connection lifecycle ────────────────────────────────────────

    def connect(self, conn_id: str, *, timeout: float = 30.0) -> dict:
        """Connect to an MCP server. Returns status dict."""
        conn = self._get_or_load(conn_id)
        if conn is None:
            return {"ok": False, "error": f"Connection not found: {conn_id}"}
        if conn.status == "connected":
            return {"ok": True, **conn.to_dict()}
        try:
            async_bridge.run_async(connect_session(conn), timeout=timeout)
            return {"ok": True, **conn.to_dict()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300], **conn.to_dict()}

    def disconnect(self, conn_id: str) -> dict:
        """Disconnect from an MCP server."""
        with self._lock:
            conn = self._connections.get(conn_id)
        if conn is None:
            return {"ok": False, "error": f"Connection not found: {conn_id}"}
        try:
            async_bridge.run_async(disconnect_session(conn), timeout=10.0)
        except Exception:
            logger.debug("Disconnect error for %s", conn_id, exc_info=True)
        return {"ok": True, **conn.to_dict()}

    def disconnect_all(self) -> None:
        """Disconnect every active connection."""
        with self._lock:
            ids = list(self._connections)
        for cid in ids:
            with contextlib.suppress(Exception):
                self.disconnect(cid)

    # ── queries ─────────────────────────────────────────────────────

    def list_connections(self) -> list[dict]:
        """Return config + runtime status merged list."""
        saved = cfg.list_connections()
        result = []
        for sc in saved:
            cid = sc.get("id", "")
            with self._lock:
                conn = self._connections.get(cid)
            status_info = conn.to_dict() if conn else {
                "status": "disconnected", "error": "", "tool_count": 0,
                "connected_at": 0.0,
            }
            merged = {**sc, **status_info}
            # mask env secrets
            if "stdio" in merged and "env" in merged.get("stdio", {}):
                merged["stdio"] = {
                    **merged["stdio"],
                    "env": {k: "***" for k in merged["stdio"].get("env", {})},
                }
            if "sse" in merged and "headers" in merged.get("sse", {}):
                merged["sse"] = {
                    **merged["sse"],
                    "headers": _redact_headers(merged["sse"].get("headers")),
                }
            if "streamable_http" in merged and "headers" in merged.get("streamable_http", {}):
                merged["streamable_http"] = {
                    **merged["streamable_http"],
                    "headers": _redact_headers(merged["streamable_http"].get("headers")),
                }
            result.append(merged)
        return result

    def get_tools(self, conn_id: str) -> list[dict]:
        with self._lock:
            conn = self._connections.get(conn_id)
        if conn is None or conn.status != "connected":
            return []
        return list(conn.tools)

    def call_tool(
        self, conn_id: str, tool_name: str, arguments: dict | None = None,
        *, timeout: float = 60.0,
    ) -> dict:
        with self._lock:
            conn = self._connections.get(conn_id)
        if conn is None:
            return {"ok": False, "error": f"Connection not found: {conn_id}"}
        if conn.status != "connected":
            return {"ok": False, "error": f"Not connected (status={conn.status})"}
        try:
            return async_bridge.run_async(
                call_tool_on_session(conn, tool_name, arguments),
                timeout=timeout,
            )
        except TimeoutError:
            return {"ok": False, "error": "Tool call timed out"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}

    # ── config CRUD delegates ───────────────────────────────────────

    def add_connection(self, data: dict) -> tuple[dict | None, str | None]:
        saved, err = cfg.add_connection(data)
        return saved, err

    def update_connection(self, conn_id: str, data: dict) -> tuple[dict | None, str | None]:
        # disconnect first if connected
        with self._lock:
            conn = self._connections.get(conn_id)
        if conn and conn.status == "connected":
            self.disconnect(conn_id)
            with self._lock:
                self._connections.pop(conn_id, None)
        return cfg.update_connection(conn_id, data)

    def delete_connection(self, conn_id: str) -> str | None:
        with self._lock:
            conn = self._connections.get(conn_id)
        if conn and conn.status == "connected":
            self.disconnect(conn_id)
        with self._lock:
            self._connections.pop(conn_id, None)
        return cfg.delete_connection(conn_id)

    def get_connection_config(self, conn_id: str) -> dict | None:
        """Return saved config dict for a connection (no runtime state)."""
        return cfg.get_connection(conn_id)

    # ── auto-connect ────────────────────────────────────────────────

    def auto_connect_all(self) -> None:
        """Connect all connections with ``auto_connect=true``."""
        for sc in cfg.list_connections():
            if sc.get("auto_connect") and sc.get("enabled", True):
                cid = sc["id"]
                logger.info("Auto-connecting MCP: %s (%s)", sc.get("name"), cid)
                result = self.connect(cid)
                if not result.get("ok"):
                    logger.warning("Auto-connect failed for %s: %s",
                                   cid, result.get("error"))

    # ── shutdown ────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Disconnect all and stop the background loop."""
        self.disconnect_all()
        async_bridge.shutdown_loop()
        with self._lock:
            self._connections.clear()

    # ── internal ────────────────────────────────────────────────────

    def _get_or_load(self, conn_id: str) -> McpConnection | None:
        """Get existing runtime connection or create from saved config."""
        with self._lock:
            if conn_id in self._connections:
                return self._connections[conn_id]
        # load from config
        sc = cfg.get_connection(conn_id)
        if sc is None:
            return None
        conn = McpConnection(
            id=sc["id"],
            name=sc.get("name", sc["id"]),
            transport=sc["transport"],
            config=sc,
        )
        with self._lock:
            # double-check: another thread may have created it
            if conn_id in self._connections:
                return self._connections[conn_id]
            self._connections[conn_id] = conn
        return conn

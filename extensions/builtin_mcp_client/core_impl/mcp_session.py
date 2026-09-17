"""Async MCP session wrapper.

Manages the lifecycle of a single MCP client connection using the
official ``mcp`` SDK.  Each connection holds an ``AsyncExitStack`` that
owns the transport context manager and the ``ClientSession``.
"""

from __future__ import annotations

import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


@dataclass
class McpConnection:
    """Runtime state for a single MCP connection."""

    id: str
    name: str
    transport: str
    config: dict
    status: str = "disconnected"        # disconnected | connecting | connected | error
    error: str = ""
    tools: list[dict] = field(default_factory=list)
    connected_at: float = 0.0

    # runtime (not serialised)
    _session: ClientSession | None = field(default=None, repr=False)
    _stack: AsyncExitStack | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """Public-safe dict (no internal refs, no env secrets)."""
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "transport": self.transport,
            "status": self.status,
            "error": self.error,
            "tool_count": len(self.tools),
            "connected_at": self.connected_at,
        }
        return d


# ── connect / disconnect ────────────────────────────────────────────

async def connect_session(conn: McpConnection) -> None:
    """Open transport + initialise ``ClientSession``.

    On success ``conn.status`` is set to ``"connected"`` and
    ``conn.tools`` is populated.
    """
    conn.status = "connecting"
    conn.error = ""
    stack = AsyncExitStack()
    try:
        read_stream, write_stream = await _open_transport(stack, conn)
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        # cache tool list
        tools_result = await session.list_tools()
        conn.tools = [
            {"name": t.name, "description": t.description or "",
             "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {}}
            for t in tools_result.tools
        ]
        conn._session = session
        conn._stack = stack
        conn.status = "connected"
        conn.connected_at = time.time()
        logger.info("MCP connected: %s (%s) - %d tools",
                     conn.name, conn.transport, len(conn.tools))
    except Exception as exc:
        conn.status = "error"
        conn.error = str(exc)[:300]
        await stack.aclose()
        logger.warning("MCP connect failed: %s - %s", conn.name, exc)
        raise


async def disconnect_session(conn: McpConnection) -> None:
    """Gracefully close the session and transport."""
    if conn._stack is not None:
        try:
            await conn._stack.aclose()
        except Exception:
            logger.debug("Error closing MCP stack for %s", conn.name, exc_info=True)
    conn._session = None
    conn._stack = None
    conn.status = "disconnected"
    conn.error = ""
    conn.tools = []
    conn.connected_at = 0.0
    logger.info("MCP disconnected: %s", conn.name)


async def call_tool_on_session(
    conn: McpConnection, tool_name: str, arguments: dict | None = None,
) -> dict:
    """Invoke a tool on the connected session."""
    if conn._session is None or conn.status != "connected":
        return {"ok": False, "error": "Not connected"}
    try:
        result = await conn._session.call_tool(tool_name, arguments or {})
        contents = []
        for item in result.content:
            contents.append({"type": item.type, "text": getattr(item, "text", "")})
        return {"ok": True, "content": contents, "isError": result.isError}
    except Exception as exc:
        conn.status = "error"
        conn.error = str(exc)[:300]
        return {"ok": False, "error": str(exc)[:300]}


# ── transport helpers ───────────────────────────────────────────────

async def _open_transport(stack: AsyncExitStack, conn: McpConnection):
    """Open the appropriate transport and return (read, write) streams."""
    if conn.transport == "stdio":
        cfg = conn.config.get("stdio", {})
        params = StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
            env=cfg.get("env") or None,
            cwd=cfg.get("cwd") or None,
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        return read, write

    if conn.transport == "sse":
        cfg = conn.config.get("sse", {})
        url = cfg["url"]
        headers = cfg.get("headers", {})
        read, write = await stack.enter_async_context(
            sse_client(url, headers=headers)
        )
        return read, write

    if conn.transport == "streamable_http":
        cfg = conn.config.get("streamable_http", {})
        url = cfg["url"]
        headers = cfg.get("headers", {})
        read, write = await stack.enter_async_context(
            streamablehttp_client(url, headers=headers)
        )
        return read, write

    raise ValueError(f"Unknown transport: {conn.transport}")

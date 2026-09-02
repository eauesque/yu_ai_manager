"""MCP JSON-RPC handler — dispatches JSON-RPC methods to the MCP server.

Handles initialize, tools/list, tools/call, resources/list, resources/read,
and notifications/initialized.
"""

import asyncio
import logging

from core.mcp_api.auth import get_internal_token

logger = logging.getLogger(__name__)


def _get_mcp_server():
    """Lazy-import to obtain the MCP server instance."""
    from mcp_server.server import mcp
    return mcp


def _sync_client_for_internal():
    """Configure the MCP client for internal (loopback) requests.

    When invoked via /mcp endpoint, the client needs to call back into the
    same server, so we set base_url and an internal auth token.
    """
    from mcp_server.server import client
    base = _resolve_local_base_url()
    if client.base_url != base:
        client.base_url = base
    # Bypass auth with internal token
    client.api_key = f"internal_{get_internal_token()}"


def _resolve_local_base_url() -> str:
    return f"http://127.0.0.1:{_resolve_local_port()}"


def _resolve_local_port() -> int:
    from core.services_core.db_state import get_config

    config = get_config() or {}
    server = config.get("server") or {}
    try:
        port = int(server.get("port", 5000))
    except (TypeError, ValueError):
        port = 5000
    return port if 1 <= port <= 65535 else 5000


def _handle_jsonrpc(session_id: str, msg: dict) -> dict | None:
    """Dispatch a JSON-RPC message to the MCP server and return a response."""
    _sync_client_for_internal()
    mcp_srv = _get_mcp_server()
    method = msg.get("method", "")
    params = msg.get("params", {})
    msg_id = msg.get("id")

    # initialize
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "yu-ai-manager",
                "version": "1.0.0",
            },
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
            },
        }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    # notifications/initialized -- client notifies initialization complete
    if method == "notifications/initialized":
        return None  # No response needed

    # tools/list
    if method == "tools/list":
        tools = []
        for tool in mcp_srv._tool_manager.list_tools():
            schema = tool.parameters if hasattr(tool, "parameters") else {}
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": schema,
            })
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}

    # tools/call
    if method == "tools/call":
        return _handle_tool_call(mcp_srv, params, msg_id)

    # resources/list
    if method == "resources/list":
        return _handle_resources_list(mcp_srv, msg_id)

    # resources/read
    if method == "resources/read":
        return _handle_resources_read(mcp_srv, params, msg_id)

    # Unknown method
    return {
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _handle_tool_call(mcp_srv, params: dict, msg_id) -> dict:
    """Execute a tools/call JSON-RPC request."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    # Kill Switch check (double-check for safety even though interceptor
    # may have already wrapped call_tool)
    try:
        from mcp_server.interceptor import check_kill_switch
        kill_msg = check_kill_switch(tool_name)
        if kill_msg:
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": kill_msg}]},
            }
    except Exception:
        logger.warning("step failed", exc_info=True)

    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                mcp_srv._tool_manager.call_tool(tool_name, arguments)
            )
        finally:
            loop.close()

        # result is list[TextContent | ...] -- convert to text
        content = []
        if isinstance(result, list):
            for item in result:
                if hasattr(item, "text"):
                    content.append({"type": "text", "text": item.text})
                elif isinstance(item, dict):
                    content.append(item)
                else:
                    content.append({"type": "text", "text": str(item)})
        else:
            content.append({"type": "text", "text": str(result)})

        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}
    except Exception as e:
        logger.warning("MCP tool call error: %s", e)
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32603, "message": "Internal MCP tool error"},
        }


def _handle_resources_list(mcp_srv, msg_id) -> dict:
    """List available MCP resources."""
    resources = []
    for res in mcp_srv._resource_manager.list_resources():
        resources.append({
            "uri": str(res.uri) if hasattr(res, "uri") else str(res),
            "name": res.name if hasattr(res, "name") else "",
            "description": res.description if hasattr(res, "description") else "",
        })
    return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": resources}}


def _handle_resources_read(mcp_srv, params: dict, msg_id) -> dict:
    """Read a specific MCP resource by URI."""
    uri = params.get("uri", "")
    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                mcp_srv._resource_manager.read_resource(uri)
            )
        finally:
            loop.close()
        text = result if isinstance(result, str) else str(result)
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"contents": [{"uri": uri, "text": text}]},
        }
    except Exception as e:
        logger.warning("MCP resource read error: %s", e)
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32603, "message": "Internal MCP resource error"},
        }

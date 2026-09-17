"""MCP tools for server mode and subsystem status."""

import json


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def register_gateway_tools(mcp, client):
    @mcp.tool()
    def server_mode_get() -> str:
        """Get current server mode (full/gateway) and headless state."""
        return _json(client.get("/api/server/mode"))

    @mcp.tool()
    def server_subsystems_status() -> str:
        """List all subsystems and background tasks with their enabled/disabled state."""
        return _json(client.get("/api/server/subsystems"))

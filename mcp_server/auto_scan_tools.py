"""MCP tools for Auto Scan Watcher — filesystem watch and auto-scan."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_auto_scan_tools(mcp: FastMCP, client):
    """Register Auto Scan Watcher MCP tools."""

    @mcp.tool()
    def auto_scan_info() -> str:
        """Get auto-scan watcher status and monitored directories."""
        return _json(client.get("/ext/watcher/info"))

    @mcp.tool()
    def auto_scan_start() -> str:
        """Start the filesystem watcher for auto-scanning new images."""
        return _json(client.post("/ext/watcher/start", {}))

    @mcp.tool()
    def auto_scan_stop() -> str:
        """Stop the filesystem watcher."""
        return _json(client.post("/ext/watcher/stop", {}))

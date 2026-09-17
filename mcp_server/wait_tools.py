"""MCP tools for blocking wait with progress notifications."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .wait_tools_batch import register_wait_batch_tools
from .wait_tools_scan import register_wait_scan_tools


def register_wait_tools(mcp: FastMCP, client: YuManagerClient):
    """Register wait / progress tools on the MCP server."""
    register_wait_scan_tools(mcp, client)
    register_wait_batch_tools(mcp, client)

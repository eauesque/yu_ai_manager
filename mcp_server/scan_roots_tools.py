"""MCP tools for scan root management and directory scanning."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .scan_roots_tools_manage import register_scan_root_manage_tools
from .scan_roots_tools_queue import register_scan_root_queue_tools
from .scan_roots_tools_scan import register_scan_root_scan_tools


def register_scan_roots_tools(mcp: FastMCP, client: YuManagerClient):
    register_scan_root_manage_tools(mcp, client)
    register_scan_root_scan_tools(mcp, client)
    register_scan_root_queue_tools(mcp, client)

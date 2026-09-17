"""MCP tools for SD WebUI Bridge."""

from mcp.server.fastmcp import FastMCP

from .sd_bridge_tools_config import register_sd_bridge_config_tools
from .sd_bridge_tools_generate import register_sd_bridge_generate_tools


def register_sd_bridge_tools(mcp: FastMCP, client):
    """Register SD WebUI Bridge MCP tools."""
    register_sd_bridge_config_tools(mcp, client)
    register_sd_bridge_generate_tools(mcp, client)

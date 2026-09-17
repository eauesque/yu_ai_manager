"""MCP tools for AI Analysis (image description generation)."""

from mcp.server.fastmcp import FastMCP

from .analysis_tools_core import register_analysis_core_tools
from .analysis_tools_media import register_analysis_media_tools
from .analysis_tools_servers import register_analysis_server_tools
from .client import YuManagerClient


def register_analysis_tools(mcp: FastMCP, client: YuManagerClient):
    """Register AI Analysis tools on the MCP server."""
    register_analysis_core_tools(mcp, client)
    register_analysis_server_tools(mcp, client)
    register_analysis_media_tools(mcp, client)

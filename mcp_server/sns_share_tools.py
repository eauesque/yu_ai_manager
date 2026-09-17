"""MCP tools for SNS sharing."""

from mcp.server.fastmcp import FastMCP

from .sns_share_tools_bluesky import register_sns_bluesky_tools
from .sns_share_tools_share import register_sns_share_core_tools


def register_sns_share_tools(mcp: FastMCP, client):
    """Register SNS share MCP tools."""
    register_sns_share_core_tools(mcp, client)
    register_sns_bluesky_tools(mcp, client)

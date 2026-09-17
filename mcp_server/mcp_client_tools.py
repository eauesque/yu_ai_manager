"""MCP tools for querying MCP client connections."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .mcp_client_tools_actions import register_mcp_client_action_tools
from .mcp_client_tools_manage import register_mcp_client_manage_tools


def register_mcp_client_tools(mcp: FastMCP, client: YuManagerClient):
    """Register MCP client introspection tools on the MCP server."""
    register_mcp_client_manage_tools(mcp, client)
    register_mcp_client_action_tools(mcp, client)

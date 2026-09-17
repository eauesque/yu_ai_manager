"""MCP tools for extension management and authoring."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .extension_tools_authoring import register_extension_authoring_tools
from .extension_tools_manage import register_extension_management_tools


def register_extension_tools(mcp: FastMCP, client: YuManagerClient):
    """Register extension management tools on the MCP server."""
    register_extension_management_tools(mcp, client)
    register_extension_authoring_tools(mcp, client)

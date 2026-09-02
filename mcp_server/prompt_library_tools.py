"""MCP tools for the Prompt Library extension."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_manage import register_prompt_library_manage_tools
from .prompt_library_tools_organize import register_prompt_library_organize_tools


def register_prompt_library_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Prompt Library tools on the MCP server."""
    register_prompt_library_manage_tools(mcp, client)
    register_prompt_library_organize_tools(mcp, client)

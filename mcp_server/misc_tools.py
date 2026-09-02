"""Miscellaneous MCP tool registration."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .misc_tools_debug import register_misc_debug_tools
from .misc_tools_files import register_misc_file_tools
from .misc_tools_media import register_misc_media_tools
from .misc_tools_server import register_misc_server_tools


def register_misc_tools(mcp: FastMCP, client: YuManagerClient):
    register_misc_server_tools(mcp, client)
    register_misc_debug_tools(mcp, client)
    register_misc_file_tools(mcp, client)
    register_misc_media_tools(mcp, client)

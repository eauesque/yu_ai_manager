"""MCP tools for the Chatlog extension."""

from mcp.server.fastmcp import FastMCP

from .chatlog_tools_manage import register_chatlog_manage_tools
from .chatlog_tools_search import register_chatlog_search_tools
from .client import YuManagerClient


def register_chatlog_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Chatlog tools on the MCP server."""
    register_chatlog_search_tools(mcp, client)
    register_chatlog_manage_tools(mcp, client)

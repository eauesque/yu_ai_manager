"""MCP tools for Tagger Server Registry."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .tagger_servers_tools_batch import register_tagger_server_batch_tools
from .tagger_servers_tools_store import register_tagger_server_store_tools


def register_tagger_servers_tools(mcp: FastMCP, client: YuManagerClient):
    """Register tagger server MCP tools on the MCP server."""
    register_tagger_server_batch_tools(mcp, client)
    register_tagger_server_store_tools(mcp, client)

"""MCP tools for search, read, and collection operations."""

from .server_tools_search_collections import register_search_collection_tools
from .server_tools_search_query import register_search_query_tools


def register_search_tools(mcp, client) -> None:
    """Register resources, search/read tools, and collection tools."""
    register_search_query_tools(mcp, client)
    register_search_collection_tools(mcp, client)

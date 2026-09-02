"""Search and CRUD registration for Prompt Library."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_manage_crud import register_prompt_library_crud_tools
from .prompt_library_tools_manage_io import register_prompt_library_io_tools
from .prompt_library_tools_manage_search import register_prompt_library_search_tools


def register_prompt_library_manage_tools(mcp: FastMCP, client: YuManagerClient):
    """Register search and CRUD Prompt Library tools."""
    register_prompt_library_search_tools(mcp, client)
    register_prompt_library_crud_tools(mcp, client)
    register_prompt_library_io_tools(mcp, client)

"""Folder, tag, and bulk registration for Prompt Library."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_organize_bulk import register_prompt_library_bulk_tools
from .prompt_library_tools_organize_folders import register_prompt_library_folder_tools
from .prompt_library_tools_organize_tags import register_prompt_library_tag_tools


def register_prompt_library_organize_tools(mcp: FastMCP, client: YuManagerClient):
    """Register organizing Prompt Library tools."""
    register_prompt_library_folder_tools(mcp, client)
    register_prompt_library_tag_tools(mcp, client)
    register_prompt_library_bulk_tools(mcp, client)

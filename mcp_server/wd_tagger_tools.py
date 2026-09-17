"""MCP tools for WD-Tagger image tagging."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .wd_tagger_tools_config import register_wd_tagger_config_tools
from .wd_tagger_tools_profiles import register_wd_tagger_profile_tools
from .wd_tagger_tools_retag import register_wd_tagger_retag_tools
from .wd_tagger_tools_tagging import register_wd_tagger_tagging_tools
from .wd_tagger_tools_vlm import register_wd_tagger_vlm_tools


def register_wd_tagger_tools(mcp: FastMCP, client: YuManagerClient):
    """Register WD-Tagger tools on the MCP server."""
    register_wd_tagger_tagging_tools(mcp, client)
    register_wd_tagger_config_tools(mcp, client)
    register_wd_tagger_profile_tools(mcp, client)
    register_wd_tagger_vlm_tools(mcp, client)
    register_wd_tagger_retag_tools(mcp, client)

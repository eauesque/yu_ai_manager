"""MCP tools for settings management."""

from mcp.server.fastmcp import FastMCP

from .settings_tools_external import register_settings_external_tools
from .settings_tools_legacy import register_settings_legacy_tools
from .settings_tools_secrets import register_settings_secret_tools
from .settings_tools_values import register_settings_value_tools


def register_settings_tools(mcp: FastMCP, client):
    """Register settings management MCP tools."""
    register_settings_value_tools(mcp, client)
    register_settings_secret_tools(mcp, client)
    register_settings_external_tools(mcp, client)
    register_settings_legacy_tools(mcp, client)

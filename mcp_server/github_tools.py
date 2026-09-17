"""MCP tools for GitHub Integration."""

from mcp.server.fastmcp import FastMCP

from .github_tools_queue import register_github_queue_tools
from .github_tools_triage import register_github_triage_tools


def register_github_tools(mcp: FastMCP, client):
    """Register GitHub Integration MCP tools."""
    register_github_triage_tools(mcp, client)
    register_github_queue_tools(mcp, client)

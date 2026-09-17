"""MCP tools for Hailo GenAI extension (LLM/VLM on Hailo-10H)."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .hailo_genai_tools_benchmark import register_hailo_genai_benchmark_tools
from .hailo_genai_tools_manage import register_hailo_genai_manage_tools


def register_hailo_genai_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Hailo GenAI tools on the MCP server."""
    register_hailo_genai_manage_tools(mcp, client)
    register_hailo_genai_benchmark_tools(mcp, client)

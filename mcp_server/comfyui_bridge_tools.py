"""MCP tools for ComfyUI Bridge."""

from mcp.server.fastmcp import FastMCP

from .comfyui_bridge_tools_config import register_comfyui_bridge_config_tools
from .comfyui_bridge_tools_generate import register_comfyui_bridge_generate_tools
from .comfyui_bridge_tools_registry import register_comfyui_bridge_registry_tools


def register_comfyui_bridge_tools(mcp: FastMCP, client):
    """Register ComfyUI Bridge MCP tools."""
    register_comfyui_bridge_config_tools(mcp, client)
    register_comfyui_bridge_generate_tools(mcp, client)
    register_comfyui_bridge_registry_tools(mcp, client)

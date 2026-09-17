"""MCP tools for Agent Safety Gateway."""

from .agent_safety_tools_control import register_agent_safety_control_tools
from .agent_safety_tools_review import register_agent_safety_review_tools
from .agent_safety_tools_scope import register_agent_safety_scope_tools


def register_agent_safety_tools(mcp, client):
    """Register agent safety MCP tools."""
    register_agent_safety_control_tools(mcp, client)
    register_agent_safety_scope_tools(mcp, client)
    register_agent_safety_review_tools(mcp, client)

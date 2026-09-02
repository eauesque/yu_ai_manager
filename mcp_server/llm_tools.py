"""MCP tools for LLM endpoint management and chat delegation."""

from .llm_tools_agent import register_llm_agent_tools
from .llm_tools_endpoints import register_llm_endpoint_tools
from .llm_tools_router import register_llm_router_tools


def register_llm_tools(mcp, client):
    register_llm_endpoint_tools(mcp, client)
    register_llm_agent_tools(mcp, client)
    register_llm_router_tools(mcp, client)

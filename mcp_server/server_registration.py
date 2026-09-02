"""Registration helpers for MCP server assembly."""

from .server_registration_manifest import iter_tool_registrars


def register_all_tools(mcp, client):
    # server_tools (core) must be registered first
    from .server_tools import register_core_tools

    register_core_tools(mcp, client)

    # Register remaining tool hubs in an explicit, reviewable order.
    for registrar in iter_tool_registrars():
        registrar(mcp, client)

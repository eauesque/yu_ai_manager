"""MCP server definition: tools and resources for YU AI Manager."""

import os

from .server_bootstrap import build_server_context
from .server_registration import register_all_tools

mcp, client = build_server_context()
register_all_tools(mcp, client)

DEBUG_MODE = os.environ.get("YU_DEBUG_MODE", "0") == "1"
if DEBUG_MODE:
    from .debug_tools import register_debug_tools
    register_debug_tools(mcp, client)

from .server_interceptor import install_interceptor

install_interceptor(mcp)

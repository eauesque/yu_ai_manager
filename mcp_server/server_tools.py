"""MCP tool and resource definitions for core library operations.

Re-exports from server_tools_search and server_tools_batch for backward compatibility.

Includes: search, image detail, collections, ratings, tags,
annotations, scan, and find-similar.
"""

import json

from .server_tools_batch import register_batch_tools
from .server_tools_search import register_search_tools


def _json(data) -> str:
    """Serialize data to pretty-printed JSON string."""
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_core_tools(mcp, client) -> None:
    """Register resources, search/read tools, batch tools, and scan tools."""
    register_search_tools(mcp, client)
    register_batch_tools(mcp, client)

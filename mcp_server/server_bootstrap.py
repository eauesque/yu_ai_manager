"""Bootstrap helpers for MCP server assembly."""

import os

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def build_server_context():
    base_url = os.environ.get("YU_BASE_URL", "http://localhost:5000")
    api_key = os.environ.get("YU_API_KEY", "")
    mcp = FastMCP(
        "yu-ai-manager",
        instructions=(
            "YU AI Manager - AI-generated image metadata management system. "
            "Search, rate, tag, organize, and annotate images in the library."
        ),
    )
    client = YuManagerClient(base_url, api_key)
    return mcp, client

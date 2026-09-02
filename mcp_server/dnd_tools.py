"""MCP tools for drag & drop file registration.

These tools let an MCP client register a file into the library by absolute
path (headless equivalent of the browser drag & drop endpoint). The path must
already live inside one of the configured scan roots; no upload transport is
involved.
"""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_dnd_tools(mcp: FastMCP, client):
    """Register file registration MCP tools."""

    @mcp.tool()
    def register_file(path: str) -> str:
        """Register an on-disk file into the library by absolute path.

        The path must be an existing file inside one of the configured scan
        roots. Metadata, thumbnail, and tag extraction are performed via the
        normal single-file scan path.

        Args:
            path: Absolute path to the file to register.

        Returns:
            JSON payload with status (``added`` / ``updated`` / ``skipped``)
            and ``file_id`` when the file was ingested.
        """
        return _json(client.post("/api/files/register-path", {"path": path}))

    @mcp.tool()
    def drop_inbox_info() -> str:
        """Return the resolved drop inbox directory used by the web D&D zone."""
        return _json(client.get("/api/dnd-inbox"))

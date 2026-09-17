"""MCP tools for source code browsing (read-only)."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_source_tools(mcp: FastMCP, client: YuManagerClient):
    """Register source code browsing tools on the MCP server."""

    @mcp.tool()
    def source_tree(path: str = "", depth: int = 3) -> str:
        """Browse the project directory tree.

        Shows source files and directories with security filtering
        (secrets, binaries, and build artifacts are excluded).

        Args:
            path: Relative path from project root (default: root)
            depth: Tree depth 1-6 (default: 3)
        """
        return _json(client.get("/api/source/tree", {
            "path": path,
            "depth": str(depth),
        }))

    @mcp.tool()
    def source_read(path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read a source file with line numbers.

        Returns file content with line numbers, respecting size limits
        (max 1MB, 2000 lines per request). Use offset for pagination.

        Args:
            path: Relative file path from project root (required)
            offset: Start line number, 0-based (default: 0)
            limit: Max lines to return (default: 2000)
        """
        if not path:
            return _json({"ok": False, "error": "path is required"})
        return _json(client.get("/api/source/read", {
            "path": path,
            "offset": str(offset),
            "limit": str(limit),
        }))

    @mcp.tool()
    def source_search(query: str, glob: str = "", limit: int = 30) -> str:
        """Search text across project source files.

        Case-insensitive text search with optional file type filtering.
        Returns matching lines with file paths and line numbers.

        Args:
            query: Search text (min 2 characters)
            glob: File name filter (e.g. "*.py", "*.ts")
            limit: Max results 1-50 (default: 30)
        """
        if not query or len(query) < 2:
            return _json({"ok": False, "error": "query must be at least 2 characters"})
        return _json(client.get("/api/source/search", {
            "q": query,
            "glob": glob,
            "limit": str(limit),
        }))

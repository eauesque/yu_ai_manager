"""MCP tools for the Cross Search extension."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import validate_search_limit

_PFX = "/ext/cross-search"


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_cross_search_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Cross Search tools on the MCP server."""

    @mcp.tool()
    def text_search(
        query: str,
        target: str = "md,chat,prompt,txt",
        limit: int = 50,
    ) -> str:
        """Cross-search across MD files, chat logs, prompt library, and text files using FTS5.

        Searches multiple data sources simultaneously and returns results ranked by relevance (BM25).
        Supports CJK characters with automatic LIKE fallback.

        Args:
            query: Full-text search query (FTS5 syntax supported)
            target: Comma-separated search targets: 'md', 'chat', 'prompt', 'txt' (default: all)
            limit: Max results (1-200, default 50)
        """
        if not query.strip():
            return "Error: query must not be empty"
        limit, _ = validate_search_limit(limit)
        return _json(client.get(f"{_PFX}/api/search", {
            "q": query, "target": target, "limit": str(limit),
        }))

    # ── Cross Search scan management ──

    @mcp.tool()
    def cross_search_scan() -> str:
        """Start a cross-search text file scan."""
        return _json(client.post(f"{_PFX}/api/scan", {}))

    @mcp.tool()
    def cross_search_scan_stop() -> str:
        """Stop a running cross-search scan."""
        return _json(client.post(f"{_PFX}/api/scan/stop", {}))

    @mcp.tool()
    def cross_search_scan_status() -> str:
        """Get cross-search scan progress status."""
        return _json(client.get(f"{_PFX}/api/scan/status"))

    @mcp.tool()
    def cross_search_get_txt(file_id: int) -> str:
        """Get text content of a cross-search indexed file.

        Args:
            file_id: Text file ID
        """
        return _json(client.get(f"{_PFX}/api/txt/{file_id}"))

    @mcp.tool()
    def cross_search_open_file(path: str) -> str:
        """Open a file in the system file manager.

        Args:
            path: Absolute file path to open
        """
        if not path.strip():
            return "Error: path must not be empty"
        return _json(client.post(f"{_PFX}/api/open-file", {"path": path}))

    @mcp.tool()
    def cross_search_get_scan_roots() -> str:
        """Get cross-search scan root directories."""
        return _json(client.get(f"{_PFX}/api/scan-roots"))

    @mcp.tool()
    def cross_search_set_scan_roots(roots: list) -> str:
        """Set cross-search scan root directories.

        Args:
            roots: List of directory paths to scan for text files
        """
        if not isinstance(roots, list):
            return "Error: roots must be a list of path strings"
        return _json(client.post(f"{_PFX}/api/scan-roots", {"roots": roots}))

    @mcp.tool()
    def cross_search_delete_scan_root(index: int) -> str:
        """Remove a cross-search scan root by index.

        Args:
            index: Scan root index to remove
        """
        return _json(client.delete(f"{_PFX}/api/scan-roots/{index}"))

    @mcp.tool()
    def cross_search_stats() -> str:
        """Get cross-search statistics (indexed text file count)."""
        return _json(client.get(f"{_PFX}/api/stats"))

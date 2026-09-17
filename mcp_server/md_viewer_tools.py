"""MCP tools for the MD Viewer extension."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import validate_search_limit

_PFX = "/ext/md-viewer"


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_md_viewer_tools(mcp: FastMCP, client: YuManagerClient):
    """Register MD Viewer tools on the MCP server."""

    @mcp.tool()
    def search_md_files(
        query: str = "",
        path_filter: str = "",
        lang: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """Search markdown files using FTS5 full-text search.

        Args:
            query: Full-text search query (FTS5 syntax supported)
            path_filter: Filter by path substring
            lang: Filter by language code (e.g. 'ja', 'en', 'ko', 'zh-cn', 'zh-tw')
            limit: Max results per page (1-200, default 50)
            offset: Skip first N results
        """
        limit, _ = validate_search_limit(limit)
        params = {"limit": str(limit), "offset": str(offset)}
        if query:
            params["query"] = query
        if path_filter:
            params["path_filter"] = path_filter
        if lang:
            params["lang"] = lang
        return _json(client.get(f"{_PFX}/api/files", params))

    @mcp.tool()
    def get_md_scan_roots() -> str:
        """Get the list of MD Viewer scan root directories with existence check.

        Returns directory paths and whether each exists on disk.
        """
        return _json(client.get(f"{_PFX}/api/scan-roots"))

    @mcp.tool()
    def set_md_scan_roots(roots: list[str]) -> str:
        """Set the list of MD Viewer scan root directories.

        Args:
            roots: List of directory paths to scan for markdown files
        """
        if not isinstance(roots, list):
            return "Error: roots must be a list of path strings"
        return _json(client.post(f"{_PFX}/api/scan-roots", {"roots": roots}))

    @mcp.tool()
    def get_md_content(file_id: int) -> str:
        """Get full content of a markdown file by ID.

        Args:
            file_id: The MD file ID to retrieve
        """
        if not isinstance(file_id, int) or file_id < 1:
            return "Error: file_id must be a positive integer"
        return _json(client.get(f"{_PFX}/api/files/{file_id}"))

    @mcp.tool()
    def trigger_md_scan() -> str:
        """Start scanning configured markdown directories."""
        return _json(client.post(f"{_PFX}/api/scan", {}))

    @mcp.tool()
    def get_md_scan_status() -> str:
        """Get markdown scan progress."""
        return _json(client.get(f"{_PFX}/api/scan/status"))

    @mcp.tool()
    def get_md_stats() -> str:
        """Get markdown viewer statistics."""
        return _json(client.get(f"{_PFX}/api/stats"))

    @mcp.tool()
    def remove_md_scan_root(index: int) -> str:
        """Remove a markdown scan root by index.
        Args:
            index: Scan root index to remove
        """
        return _json(client.delete(f"{_PFX}/api/scan-roots/{index}"))

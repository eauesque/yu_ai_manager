"""Debug and maintenance misc tools."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .misc_tools_common import as_json


def register_misc_debug_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def get_debug_log(limit: int = 200, filter: str = "") -> str:
        """Get debug log output (newest entries last).

        Args:
            limit: Maximum number of log lines to return (1–5000, default 200)
            filter: Optional substring filter applied to each line
        """
        params: dict[str, str] = {"limit": str(max(1, min(limit, 5000)))}
        if filter.strip():
            params["filter"] = filter.strip()
        return as_json(client.get("/api/tools/debug-log", params))

    @mcp.tool()
    def clear_debug_log() -> str:
        """Clear the debug log."""
        return as_json(client.post("/api/tools/debug-log/clear", {}))

    @mcp.tool()
    def get_cache_info() -> str:
        """Get cache statistics."""
        return as_json(client.get("/api/tools/cache-info"))

    @mcp.tool()
    def clear_cache() -> str:
        """Clear all caches."""
        return as_json(client.post("/api/tools/clear-cache", {}))

    @mcp.tool()
    def rebuild_groups() -> str:
        """Rebuild directory groups."""
        return as_json(client.post("/api/tools/rebuild-groups", {}))

    @mcp.tool()
    def normalize_tags() -> str:
        """Normalize tags in the database."""
        return as_json(client.get("/api/tools/normalize-tags"))

    @mcp.tool()
    def debug_file_meta(file_id: int) -> str:
        """Get debug metadata for a file. Args: file_id: target file ID"""
        return as_json(client.get(f"/api/debug/file-meta/{file_id}"))

    @mcp.tool()
    def debug_model_check() -> str:
        """Run model availability check."""
        return as_json(client.get("/api/debug/model-check"))

    @mcp.tool()
    def get_scanned_roots() -> str:
        """Get list of scanned root directories."""
        return as_json(client.get("/api/scanned-roots"))

    @mcp.tool()
    def purge_scanned_roots() -> str:
        """Purge all scanned root records."""
        return as_json(client.post("/api/scanned-roots/purge", {}))

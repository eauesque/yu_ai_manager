"""Scan tools for server MCP batch layer."""

from .server_tools_common import as_json


def register_batch_scan_tools(mcp, client) -> None:
    """Register scan tools."""

    @mcp.tool()
    def trigger_scan() -> str:
        """Start a scan of all configured scan roots to find new/updated images."""
        return as_json(client.post("/api/scan-all", {}))

    @mcp.tool()
    def get_scan_status() -> str:
        """Check current scan progress and job status."""
        return as_json(client.get("/api/scan/status"))

    @mcp.tool()
    def get_scan_errors(error_type: str = "", resolved: str = "false", limit: int = 50) -> str:
        """List scan errors (encoding failures, timeouts, filesystem errors).

        Args:
            error_type: Filter by type: "encoding", "timeout", "filesystem", "scan", "archive_scan", "archive_timeout". Empty = all.
            resolved: "true", "false", or "" for all.
            limit: Max results (default 50, max 1000).
        """
        params: dict[str, str | int] = {"limit": min(limit, 1000)}
        if error_type:
            params["error_type"] = error_type
        if resolved:
            params["resolved"] = resolved
        return as_json(client.get("/api/scan-errors", params))

    @mcp.tool()
    def get_scan_history(limit: int = 50) -> str:
        """Get recent scan history records.

        Args:
            limit: Max records to return (default 50)
        """
        return as_json(client.get("/api/scan/history", {"limit": limit}))

    @mcp.tool()
    def clear_scan_history() -> str:
        """Clear all scan history records."""
        return as_json(client.post("/api/scan/history/clear", {}))

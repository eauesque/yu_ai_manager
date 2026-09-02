import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_stats_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def get_stats_timeline(granularity: str = "month") -> str:
        """Get timeline statistics.
        Args: granularity: 'day' | 'week' | 'month' | 'year' (default: 'month')"""
        allowed = {"day", "week", "month", "year"}
        g = granularity if granularity in allowed else "month"
        return _json(client.get("/api/stats/timeline", {"granularity": g}))

    @mcp.tool()
    def get_stats_hourly() -> str:
        """Get hourly activity statistics."""
        return _json(client.get("/api/stats/hourly"))

    @mcp.tool()
    def get_stats_models() -> str:
        """Get model usage statistics."""
        return _json(client.get("/api/stats/models"))

    @mcp.tool()
    def get_stats_resolutions() -> str:
        """Get resolution distribution statistics."""
        return _json(client.get("/api/stats/resolutions"))

    @mcp.tool()
    def get_stats_story() -> str:
        """Generate a story narrative about the library."""
        return _json(client.get("/api/stats/story"))

    @mcp.tool()
    def get_stats_overview() -> str:
        """Get basic library statistics (file count, total size, etc.)."""
        return _json(client.get("/api/stats"))

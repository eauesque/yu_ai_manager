"""Scan queue tools."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .scan_roots_tools_common import as_json


def register_scan_root_queue_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def scan_queue_list() -> str:
        """List pending items in the scan queue."""
        return as_json(client.get("/api/scan/queue"))

    @mcp.tool()
    def scan_queue_remove(queue_id: str) -> str:
        """Remove an item from the scan queue.
        Args:
            queue_id: Queue item ID to remove
        """
        return as_json(client.delete(f"/api/scan/queue/{queue_id}"))

    @mcp.tool()
    def scan_queue_clear() -> str:
        """Clear all items from the scan queue."""
        return as_json(client.post("/api/scan/queue/clear", {}))

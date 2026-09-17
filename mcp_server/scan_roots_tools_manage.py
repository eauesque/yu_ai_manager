"""Scan root CRUD tools."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .scan_roots_tools_common import as_json
from .validators import validate_path


def register_scan_root_manage_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def list_scan_roots() -> str:
        """List all configured scan roots with their enabled/disabled status."""
        return as_json(client.get("/api/scan-roots"))

    @mcp.tool()
    def add_scan_root(path: str) -> str:
        """Add a new directory as a scan root.

        Args:
            path: Absolute directory path to add as a scan root
        """
        err = validate_path(path)
        if err:
            return err
        return as_json(client.post("/api/scan-roots", {"path": path.strip()}))

    @mcp.tool()
    def remove_scan_root(index: int) -> str:
        """Remove a scan root by its index.

        Args:
            index: Zero-based index of the scan root to remove
        """
        if index < 0:
            return as_json({"ok": False, "error": "index must be non-negative"})
        return as_json(client.delete(f"/api/scan-roots/{index}"))

    @mcp.tool()
    def toggle_scan_root(index: int) -> str:
        """Toggle a scan root between enabled and disabled.

        Args:
            index: Zero-based index of the scan root to toggle
        """
        if index < 0:
            return as_json({"ok": False, "error": "index must be non-negative"})
        return as_json(client.post(f"/api/scan-roots/{index}/toggle", {}))

    @mcp.tool()
    def edit_scan_root(index: int, path: str) -> str:
        """Edit a scan root path.
        Args:
            index: Scan root index
            path: New path
        """
        return as_json(client.put(f"/api/scan-roots/{index}", {"path": path.strip()}))

    @mcp.tool()
    def reorder_scan_roots(order: list) -> str:
        """Reorder scan roots.
        Args:
            order: List of indices in desired order
        """
        return as_json(client.post("/api/scan-roots/reorder", {"order": order}))

"""Scan execution tools."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .scan_roots_tools_common import as_json
from .validators import validate_path


def register_scan_root_scan_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def scan_directory(path: str) -> str:
        """Start scanning a specific directory for new/updated images.

        Args:
            path: Directory path to scan
        """
        err = validate_path(path)
        if err:
            return err
        return as_json(client.post("/api/tools/scan", {"path": path.strip()}))

    @mcp.tool()
    def get_scan_interrupted() -> str:
        """Get information about the last interrupted scan, if any."""
        return as_json(client.get("/api/scan/interrupted"))

    @mcp.tool()
    def get_checkpoints() -> str:
        """List available model checkpoints."""
        return as_json(client.get("/api/checkpoints"))

    @mcp.tool()
    def start_scan(path: str = "") -> str:
        """Start scanning a specific path or all roots.
        Args:
            path: Path to scan (empty = all roots)
        """
        body = {}
        if path:
            body["path"] = path.strip()
        return as_json(client.post("/api/scan/start", body))

    @mcp.tool()
    def cancel_scan() -> str:
        """Cancel a running scan."""
        return as_json(client.post("/api/scan/cancel", {}))

    @mcp.tool()
    def resume_scan() -> str:
        """Resume an interrupted scan."""
        return as_json(client.post("/api/scan/resume", {}))

    @mcp.tool()
    def dismiss_interrupted_scan() -> str:
        """Dismiss interrupted scan state without resuming."""
        return as_json(client.post("/api/scan/dismiss", {}))

    @mcp.tool()
    def resolve_scan_error(error_id: int) -> str:
        """Mark a scan error as resolved.
        Args:
            error_id: Error ID to resolve
        """
        return as_json(client.post(f"/api/scan-errors/{error_id}/resolve", {}))

    @mcp.tool()
    def clear_scan_errors() -> str:
        """Clear all resolved scan errors."""
        return as_json(client.post("/api/scan-errors/clear", {}))

    @mcp.tool()
    def start_hash_backfill() -> str:
        """Start computing missing hashes for all files."""
        return as_json(client.post("/api/hash-backfill/start", {}))

    @mcp.tool()
    def cancel_hash_backfill() -> str:
        """Cancel running hash backfill."""
        return as_json(client.post("/api/hash-backfill/cancel", {}))

    @mcp.tool()
    def get_hash_backfill_status() -> str:
        """Get hash backfill progress."""
        return as_json(client.get("/api/hash-backfill/status"))

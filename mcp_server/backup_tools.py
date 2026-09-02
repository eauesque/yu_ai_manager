"""MCP tools for database backup management."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_backup_tools(mcp: FastMCP, client: YuManagerClient):
    """Register backup management tools on the MCP server."""

    @mcp.tool()
    def list_backups() -> str:
        """List all available database backups with filename, size, date, and reason."""
        return _json(client.get("/api/tools/backup/list"))

    @mcp.tool()
    def create_backup() -> str:
        """Create a manual database backup. Returns filename and size."""
        return _json(client.post("/api/tools/backup/create", {}))

    @mcp.tool()
    def restore_backup(filename: str) -> str:
        """Restore the database from a named backup file.

        A pre-restore backup of the current DB is created automatically.

        Args:
            filename: Backup filename to restore from (e.g. "yu_ai_manager_20260301_120000.db")
        """
        if not filename or not filename.strip():
            return _json({"error": "filename is required"})
        return _json(client.post("/api/tools/backup/restore", {"filename": filename.strip()}))

    @mcp.tool()
    def get_backup_status() -> str:
        """Get backup system status: scheduler state, last backup time, config."""
        return _json(client.get("/api/tools/backup/status"))

    @mcp.tool()
    def delete_backup(filename: str) -> str:
        """Delete a backup file.
        Args:
            filename: Backup filename to delete
        """
        return _json(client.post("/api/tools/backup/delete", {"filename": filename.strip()}))

    @mcp.tool()
    def download_latest_backup() -> str:
        """Get the download URL for the current database as a live backup file.

        This endpoint streams the current database as a binary SQLite attachment.
        The MCP client cannot receive binary data directly, so this tool returns
        the full URL to use with a browser or download tool (e.g. curl/wget).
        The endpoint requires local access (localhost only).

        Returns a dict with 'download_url' for direct use.
        """
        download_url = f"{client.base_url}/api/tools/backup-download"
        return _json({"download_url": download_url, "note": "Binary SQLite file — use a browser or curl to download. Requires localhost access and admin auth."})

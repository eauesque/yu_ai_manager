"""MCP tools for system update management."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_update_tools(mcp: FastMCP, client: YuManagerClient):
    """Register system update tools on the MCP server."""

    @mcp.tool()
    def check_for_update() -> str:
        """Check if a new version of YU AI Manager is available on GitHub.
        Compares the current VERSION with the latest GitHub release.
        Returns version info, update availability, and install type."""
        return _json(client.get("/api/system/update/check"))

    @mcp.tool()
    def get_update_status() -> str:
        """Get current installation type (git/tauri/docker/portable) and version."""
        return _json(client.get("/api/system/update/status"))

    @mcp.tool()
    def apply_system_update() -> str:
        """Apply available update for git clone installations.
        Creates a pre-update backup of config.json and tags.db,
        then runs git pull + dependency install + server restart.
        Only works for git clone installs. Docker and Tauri have
        separate update mechanisms."""
        return _json(client.post("/api/system/update/apply", {"confirm": "update"}))

    @mcp.tool()
    def check_unified_updates() -> str:
        """Check update status for system AND all extensions at once.
        Returns system update info, per-extension status (up_to_date /
        update_available / unknown / builtin), and a summary with counts.
        Git-based extensions are compared against their remote HEAD.
        Builtin extensions are shown as 'bundled' (tied to system version)."""
        return _json(client.get("/api/system/update/unified-check", {"force": "1"}))

    @mcp.tool()
    def apply_unified_updates(
        update_system: bool = True,
        update_extensions: bool = True,
        extension_names: list | None = None,
    ) -> str:
        """Apply updates for system and/or extensions in one operation.
        Backs up extension config before updating. Extensions are updated
        first, then the system (which may trigger a server restart).
        Progress is emitted via SSE events (update.progress).

        Args:
            update_system: Whether to update the system (git/portable only)
            update_extensions: Whether to update git-based extensions
            extension_names: Optional list of specific extension names to update.
                             If omitted, all git-based extensions with updates are updated.
        """
        payload = {
            "update_system": update_system,
            "update_extensions": update_extensions,
        }
        if extension_names:
            payload["extension_names"] = extension_names
        return _json(client.post("/api/system/update/unified-apply", payload))

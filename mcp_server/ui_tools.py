"""MCP tools for UI management -- list, switch, install, uninstall."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(msg: str) -> str:
    return _json({"ok": False, "error": msg})


def register_ui_tools(mcp: FastMCP, client: YuManagerClient):
    """Register UI management tools on the MCP server."""

    @mcp.tool()
    def list_uis() -> str:
        """List all installed UIs with their manifest info and active status."""
        return _json(client.get("/api/ui/list"))

    @mcp.tool()
    def switch_ui(name: str) -> str:
        """Switch the active UI. Requires server restart to take effect.

        Args:
            name: UI name (directory name under ui/, e.g. "default", "custom")
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.post("/api/ui/switch", {"name": name}))

    @mcp.tool()
    def install_ui(url: str) -> str:
        """Install a custom UI from a URL (Git repo, ZIP, or 7z archive).

        Args:
            url: HTTPS URL to install from. Git repos are cloned with --depth 1.
                 ZIP and 7z archives are downloaded and extracted.
                 The installed UI must contain a valid manifest.json.
        """
        url = url.strip()
        if not url:
            return _err("url must not be empty")
        return _json(client.post("/api/ui/install", {"url": url}))

    @mcp.tool()
    def uninstall_ui(name: str) -> str:
        """Uninstall a custom UI by name. The default UI cannot be uninstalled.

        Args:
            name: UI name to remove (directory name under ui/)
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        if name == "default":
            return _err("Cannot uninstall the default UI")
        return _json(client.delete(f"/api/ui/{name}/uninstall"))

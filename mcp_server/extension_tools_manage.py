"""Extension management MCP tool registration."""

from __future__ import annotations

import json


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(msg: str) -> str:
    return _json({"ok": False, "error": msg})


def register_extension_management_tools(mcp, client) -> None:
    @mcp.tool()
    def list_extensions() -> str:
        """List all installed extensions with name, version, enabled status, and source."""
        return _json(client.get("/api/extensions"))

    @mcp.tool()
    def get_extension_detail(name: str) -> str:
        """Get detailed information about a specific extension.

        Args:
            name: Extension name (directory name)
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.get(f"/api/extensions/{name}"))

    @mcp.tool()
    def toggle_extension(name: str, enabled: bool) -> str:
        """Enable or disable an extension. Requires server restart to take effect.

        Args:
            name: Extension name
            enabled: True to enable, False to disable
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.post(f"/api/extensions/{name}/toggle", {"enabled": enabled}))

    @mcp.tool()
    def install_extension(url: str) -> str:
        """Install an extension from a Git repository URL. Only available from localhost.

        Args:
            url: HTTPS URL of the Git repository to install from.
                 The repository must contain a valid extension.json manifest.
        """
        url = url.strip()
        if not url:
            return _err("url must not be empty")
        return _json(client.post("/api/extensions/install", {"url": url}))

    @mcp.tool()
    def update_extension(name: str) -> str:
        """Update a git-installed extension to the latest version. Only available from localhost.

        Args:
            name: Extension name to update
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.post(f"/api/extensions/{name}/update", {}))

    @mcp.tool()
    def uninstall_extension(name: str) -> str:
        """Uninstall an extension. Built-in extensions cannot be uninstalled.
        Only available from localhost.

        Args:
            name: Extension name to uninstall
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.delete(f"/api/extensions/{name}/uninstall"))

    @mcp.tool()
    def search_marketplace(query: str = "") -> str:
        """Search the extension marketplace for available extensions.

        Args:
            query: Search query (empty string returns all available extensions)
        """
        params = {}
        if query.strip():
            params["q"] = query.strip()
        return _json(client.get("/api/extensions/marketplace", params))

    @mcp.tool()
    def get_extension_config(name: str) -> str:
        """Get the configuration schema and current values for an extension.

        Args:
            name: Extension name
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.get(f"/api/extensions/{name}/config"))

    @mcp.tool()
    def get_extension_permissions(name: str) -> str:
        """Get permission information and approval status for an extension.

        Args:
            name: Extension name
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.get(f"/api/extensions/{name}/permissions"))

    @mcp.tool()
    def approve_extension_permissions(name: str, granted: list | None = None, denied: list | None = None, action: str = "approve") -> str:
        """Approve or revoke permissions for an extension.

        Args:
            name: Extension name
            granted: List of permission names to grant (for approve action)
            denied: List of permission names to deny (for approve action)
            action: "approve" to grant permissions, "revoke" to revoke
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        payload = {"action": action}
        if action == "approve":
            payload["granted"] = granted or []
            payload["denied"] = denied or []
        return _json(client.post(f"/api/extensions/{name}/permissions", payload))

    @mcp.tool()
    def scan_extension_code(name: str) -> str:
        """Run static analysis on extension code and return security findings.

        Args:
            name: Extension name to scan
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.get(f"/api/extensions/{name}/scan-results"))

    @mcp.tool()
    def get_extension_tokens(name: str) -> str:
        """Get Capability Token status for an extension (Phase 2 sandbox).

        Returns issued token count, permissions, and expiry info.
        Signature is not exposed.

        Args:
            name: Extension name
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.get(f"/api/extensions/{name}/tokens"))

    @mcp.tool()
    def get_extension_integrity(name: str) -> str:
        """Get file integrity and runtime monitoring status for an extension (Phase 3 sandbox).

        Returns file tampering status, denial counts, and revocation tracking info.

        Args:
            name: Extension name
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.get(f"/api/extensions/{name}/integrity"))

    @mcp.tool()
    def get_extension_isolation_status() -> str:
        """Get process isolation status for all extensions (Phase 4 sandbox).

        Returns availability of process isolation on the current platform
        and status of all isolated extension processes (PID, alive state, socket path).
        Linux only - returns available=false on other platforms.
        """
        return _json(client.get("/api/extensions/isolation"))

    @mcp.tool()
    def get_extension_os_isolation_status() -> str:
        """Get OS-level isolation status (Phase D).

        Returns OS isolation availability (AppArmor/sandbox-exec/Restricted Token),
        current configuration, and per-process isolation state.
        Linux: AppArmor profile auto-generation + aa-exec.
        macOS: sandbox-exec (experimental, deprecated).
        Windows: Restricted Token + Job Object.
        """
        return _json(client.get("/api/extensions/os-isolation"))

    @mcp.tool()
    def set_extension_config(name: str, values: dict) -> str:
        """Update configuration values for an extension.

        Args:
            name: Extension name
            values: Dictionary of config key-value pairs to set.
                    Keys must match the extension's config_schema fields.
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.post(f"/api/extensions/{name}/config", {"values": values}))

    @mcp.tool()
    def update_all_extensions() -> str:
        """Update all installed extensions to latest versions."""
        return _json(client.post("/api/extensions/update-all", {}))

    @mcp.tool()
    def rescan_extension(name: str) -> str:
        """Re-scan extension code for security analysis.
        Args:
            name: Extension name
        """
        return _json(client.post(f"/api/extensions/{name}/rescan", {}))

    @mcp.tool()
    def get_extension_hooks() -> str:
        """List all registered extension hooks."""
        return _json(client.get("/api/extensions/hooks"))

    @mcp.tool()
    def refresh_marketplace() -> str:
        """Refresh the extensions marketplace catalog."""
        return _json(client.post("/api/extensions/marketplace/refresh", {}))

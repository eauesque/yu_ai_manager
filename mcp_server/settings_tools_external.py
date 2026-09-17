"""External vault integration tools for settings MCP integration."""

from mcp.server.fastmcp import FastMCP

from .settings_tools_common import as_error, as_json


def register_settings_external_tools(mcp: FastMCP, client):
    """Register external vault tools."""

    @mcp.tool()
    def get_op_status() -> str:
        """Get 1Password CLI integration status."""
        return as_json(client.get("/api/settings/op-status"))

    @mcp.tool()
    def delete_op_mapping(key: str) -> str:
        """Delete a 1Password field mapping.
        Args:
            key: Setting key to unmap
        """
        return as_json(client.delete(f"/api/settings/op-mapping/{key}"))

    @mcp.tool()
    def list_op_vaults() -> str:
        """List available 1Password vaults. Returns vault id and name for each."""
        return as_json(client.get("/api/settings/secrets/op-vaults"))

    @mcp.tool()
    def push_secrets_to_1password(vault: str, item_title: str = "YU AI Manager") -> str:
        """Push all configured secrets to 1Password and auto-link op_secrets mappings.

        Args:
            vault: 1Password vault name (e.g. 'Personal')
            item_title: Item title in 1Password (default: 'YU AI Manager')
        """
        vault = vault.strip()
        if not vault:
            return as_error("vault must not be empty")
        return as_json(client.post("/api/settings/secrets/push-to-op", {"vault": vault, "item_title": item_title}))

    @mcp.tool()
    def get_bw_status() -> str:
        """Get Bitwarden CLI integration status."""
        return as_json(client.get("/api/settings/bw-status"))

    @mcp.tool()
    def list_bw_folders() -> str:
        """List available Bitwarden folders. Returns folder id and name for each."""
        return as_json(client.get("/api/settings/secrets/bw-folders"))

    @mcp.tool()
    def push_secrets_to_bitwarden(item_name: str = "YU AI Manager", folder_id: str = "") -> str:
        """Push all configured secrets to Bitwarden and auto-link bw_secrets mappings.

        Args:
            item_name: Item name in Bitwarden (default: 'YU AI Manager')
            folder_id: Bitwarden folder ID (empty for no folder)
        """
        item_name = item_name.strip()
        if not item_name:
            return as_error("item_name must not be empty")
        body = {"item_name": item_name}
        if folder_id:
            body["folder_id"] = folder_id
        return as_json(client.post("/api/settings/secrets/push-to-bw", body))

    @mcp.tool()
    def delete_bw_mapping(key: str) -> str:
        """Delete a Bitwarden field mapping.
        Args:
            key: Setting key to unmap
        """
        return as_json(client.delete(f"/api/settings/bw-mapping/{key}"))

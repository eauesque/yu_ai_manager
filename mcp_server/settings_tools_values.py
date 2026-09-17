"""Value and schema tools for settings MCP integration."""

from mcp.server.fastmcp import FastMCP

from .settings_tools_common import as_error, as_json


def register_settings_value_tools(mcp: FastMCP, client):
    """Register settings schema and value tools."""

    @mcp.tool()
    def settings_get_schema() -> str:
        """Get the full settings schema with type, description, and category for each key."""
        return as_json(client.get("/api/settings/schema"))

    @mcp.tool()
    def settings_get_all() -> str:
        """Get all settings values (secrets are masked). Includes source info (config/encrypted/1password/default)."""
        return as_json(client.get("/api/settings/all"))

    @mcp.tool()
    def settings_get(key: str) -> str:
        """Get a single setting value by dotted key (e.g. 'server.pin', 'backup.enabled').

        Args:
            key: Dotted setting key (e.g. 'server.pin', 'sns.bluesky.handle')
        """
        key = key.strip()
        if not key:
            return as_error("key must not be empty")
        return as_json(client.get(f"/api/settings/{key}"))

    @mcp.tool()
    def settings_set(key: str, value: str, op_uri: str = "") -> str:
        """Update a setting value. Secrets are auto-encrypted. Optionally set a 1Password URI.

        Args:
            key: Dotted setting key (e.g. 'server.pin', 'backup.max_generations')
            value: New value (will be coerced to the schema type)
            op_uri: Optional 1Password URI (e.g. 'op://Private/YuManager/pin')
        """
        key = key.strip()
        if not key:
            return as_error("key must not be empty")
        body = {"value": value}
        if op_uri:
            body["op_uri"] = op_uri
        return as_json(client.put(f"/api/settings/{key}", body))

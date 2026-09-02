"""Legacy config tools for settings MCP integration."""

from mcp.server.fastmcp import FastMCP

from .settings_tools_common import as_json


def register_settings_legacy_tools(mcp: FastMCP, client):
    """Register legacy config tools."""

    @mcp.tool()
    def get_legacy_config() -> str:
        """Get legacy config.json settings."""
        return as_json(client.get("/api/settings/config"))

    @mcp.tool()
    def save_legacy_config(config: dict) -> str:
        """Save legacy config.json settings.
        Args:
            config: Configuration dict
        """
        return as_json(client.post("/api/settings/config", config))

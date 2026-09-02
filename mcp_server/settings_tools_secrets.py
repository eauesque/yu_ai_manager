"""Secret backend tools for settings MCP integration."""

import json as json_mod

from mcp.server.fastmcp import FastMCP

from .settings_tools_common import as_error, as_json


def register_settings_secret_tools(mcp: FastMCP, client):
    """Register secret backend tools."""

    @mcp.tool()
    def secrets_status() -> str:
        """Get encryption key backend status (passphrase/keychain/file)."""
        return as_json(client.get("/api/settings/secrets/status"))

    @mcp.tool()
    def secrets_export(password: str) -> str:
        """Export encryption key as password-protected JSON for backup/migration.

        Args:
            password: Protection password (minimum 8 characters)
        """
        password = password.strip()
        if not password:
            return as_error("password must not be empty")
        return as_json(client.post("/api/settings/secrets/export", {"password": password}))

    @mcp.tool()
    def secrets_import(export_json: str, password: str) -> str:
        """Import encryption key from password-protected export data.

        Args:
            export_json: JSON string from secrets_export output
            password: Password used during export
        """
        password = password.strip()
        if not password:
            return as_error("password must not be empty")
        try:
            export_data = json_mod.loads(export_json)
        except (ValueError, TypeError):
            return as_error("export_json must be valid JSON")
        return as_json(client.post("/api/settings/secrets/import", {"export_data": export_data, "password": password}))

    @mcp.tool()
    def migrate_secrets_to_keychain() -> str:
        """Migrate secrets from file to OS keychain."""
        return as_json(client.post("/api/settings/secrets/migrate-keychain", {}))

    @mcp.tool()
    def migrate_plaintext_secrets() -> str:
        """Encrypt any plaintext secrets remaining in config.json.
        Safe to run multiple times (idempotent). Returns count of migrated secrets.
        """
        return as_json(client.post("/api/settings/secrets/migrate", {}))

    @mcp.tool()
    def secrets_rotate() -> str:
        """Rotate the encryption key. All stored secrets are re-encrypted with the new key."""
        return as_json(client.post("/api/settings/secrets/rotate", {}))

    @mcp.tool()
    def get_secrets_keyring_info() -> str:
        """Get key ring info: list of key_ids in the ring and the active key_id."""
        return as_json(client.get("/api/settings/secrets/keyring"))

"""MCP tools for LAN share token management."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def register_lan_share_tools(mcp: FastMCP, client):
    """Register LAN share MCP tools."""

    @mcp.tool()
    def create_lan_share(
        collection_id: int,
        expires_hours: int = 24,
    ) -> str:
        """Create a LAN share token for a collection.

        Args:
            collection_id: Collection ID to share (required)
            expires_hours: Token expiration in hours (default 24)
        """
        if collection_id < 1:
            return _err("collection_id must be a positive integer")
        return _json(client.post("/api/lan-share/create", {
            "collection_id": collection_id,
            "expires_hours": expires_hours,
        }))

    @mcp.tool()
    def revoke_lan_share(token: str) -> str:
        """Revoke an active LAN share token.

        Args:
            token: The share token to revoke (required)
        """
        if not token.strip():
            return _err("token is required")
        return _json(client.post("/api/lan-share/revoke", {
            "token": token,
        }))

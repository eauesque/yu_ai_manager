"""Connection management tools for MCP client integration."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .mcp_client_tools_common import as_json


def register_mcp_client_manage_tools(mcp: FastMCP, client: YuManagerClient):
    """Register MCP client connection management tools."""

    @mcp.tool()
    def list_mcp_connections() -> str:
        """List all configured MCP client connections with their status.

        Returns connection name, transport type, status (connected/disconnected/error),
        and number of available tools for each connection.
        """
        return as_json(client.get("/ext/mcp-client/api/connections"))

    @mcp.tool()
    def create_mcp_connection(name: str, transport: str = "stdio", command: str = "", args: list | None = None, env: dict | None = None, url: str = "") -> str:
        """Create a new MCP server connection.
        Args:
            name: Connection display name
            transport: Transport type ('stdio', 'sse', or 'streamable_http')
            command: Command to launch the MCP server (stdio transport)
            args: Command arguments list (stdio transport)
            env: Environment variables dict (stdio transport)
            url: Server URL (sse/streamable_http transport)
        """
        body = {"name": name, "transport": transport}
        if transport == "stdio":
            stdio = {"command": command}
            if args:
                stdio["args"] = args
            if env:
                stdio["env"] = env
            body["stdio"] = stdio
        elif transport in ("sse", "streamable_http"):
            body[transport] = {"url": url}
        return as_json(client.post("/ext/mcp-client/api/connections", body))

    @mcp.tool()
    def update_mcp_connection(connection_id: str, name: str = "", transport: str = "", command: str = "", args: list | None = None, env: dict | None = None, url: str = "") -> str:
        """Update an MCP server connection.
        Args:
            connection_id: Connection ID
            name: New name (empty = no change)
            transport: Transport type (empty = no change)
            command: New command for stdio (empty = no change)
            args: New args for stdio (None = no change)
            env: New env for stdio (None = no change)
            url: New URL for sse/streamable_http (empty = no change)
        """
        body = {}
        if name:
            body["name"] = name
        if transport:
            body["transport"] = transport
            if transport == "stdio":
                stdio = {}
                if command:
                    stdio["command"] = command
                if args is not None:
                    stdio["args"] = args
                if env is not None:
                    stdio["env"] = env
                if stdio:
                    body["stdio"] = stdio
            elif transport in ("sse", "streamable_http") and url:
                body[transport] = {"url": url}
        return as_json(client.put(f"/ext/mcp-client/api/connections/{connection_id}", body))

    @mcp.tool()
    def delete_mcp_connection(connection_id: str) -> str:
        """Delete an MCP server connection.
        Args:
            connection_id: Connection ID to delete
        """
        return as_json(client.delete(f"/ext/mcp-client/api/connections/{connection_id}"))

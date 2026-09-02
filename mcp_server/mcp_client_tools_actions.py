"""Action tools for MCP client integration."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .mcp_client_tools_common import as_json


def register_mcp_client_action_tools(mcp: FastMCP, client: YuManagerClient):
    """Register MCP client action tools."""

    @mcp.tool()
    def get_mcp_connection_tools(connection_id: str) -> str:
        """List tools available on a connected MCP server.

        Args:
            connection_id: The ID of the MCP client connection.
        """
        if not connection_id or not connection_id.strip():
            return as_json({"error": "connection_id is required"})
        return as_json(client.get(f"/ext/mcp-client/api/connections/{connection_id.strip()}/tools"))

    @mcp.tool()
    def connect_mcp_server(connection_id: str) -> str:
        """Connect to an MCP server.
        Args:
            connection_id: Connection ID to connect
        """
        return as_json(client.post(f"/ext/mcp-client/api/connections/{connection_id}/connect", {}))

    @mcp.tool()
    def disconnect_mcp_server(connection_id: str) -> str:
        """Disconnect from an MCP server.
        Args:
            connection_id: Connection ID to disconnect
        """
        return as_json(client.post(f"/ext/mcp-client/api/connections/{connection_id}/disconnect", {}))

    @mcp.tool()
    def call_mcp_tool(connection_id: str, tool_name: str, arguments: dict | None = None) -> str:
        """Call a tool on a connected MCP server.
        Args:
            connection_id: Connection ID
            tool_name: Tool name to call
            arguments: Tool arguments dict
        """
        body = {"tool_name": tool_name}
        if arguments:
            body["arguments"] = arguments
        return as_json(client.post(f"/ext/mcp-client/api/connections/{connection_id}/call-tool", body))

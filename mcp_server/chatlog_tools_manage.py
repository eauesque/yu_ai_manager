"""Import and maintenance Chatlog MCP tools."""

from mcp.server.fastmcp import FastMCP

from .chatlog_tools_common import _PFX, as_json
from .client import YuManagerClient


def register_chatlog_manage_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Chatlog maintenance tools on the MCP server."""

    @mcp.tool()
    def import_chat_log(source: str, json_path: str) -> str:
        """Import a chat log from a local JSON or ZIP file."""
        source = source.strip().lower()
        if source not in ("claude", "chatgpt", "openwebui"):
            return "Error: source must be 'claude', 'chatgpt', or 'openwebui'"
        if not json_path.strip():
            return "Error: json_path must not be empty"
        return as_json(client.post(f"{_PFX}/api/import-path", {"source": source, "json_path": json_path}))

    @mcp.tool()
    def reprocess_chat_logs(target: str = "unprocessed") -> str:
        """Trigger AI reprocessing of chat logs."""
        return as_json(client.post(f"{_PFX}/api/chat/reprocess", {"target": target}))

    @mcp.tool()
    def get_chatlog_import_status() -> str:
        """Get chat log import progress status."""
        return as_json(client.get(f"{_PFX}/api/import/status"))

    @mcp.tool()
    def delete_conversation(conversation_id: int) -> str:
        """Delete a conversation from chat logs."""
        return as_json(client.delete(f"{_PFX}/api/conversations/{conversation_id}"))

    @mcp.tool()
    def get_chatlog_stats() -> str:
        """Get chat log statistics."""
        return as_json(client.get(f"{_PFX}/api/stats"))

    @mcp.tool()
    def chatlog_entity_reindex() -> str:
        """Trigger entity reindex for all chat logs.

        Re-extracts and re-indexes named entities (people, places, concepts, etc.)
        from all conversations.
        """
        return as_json(client.post(f"{_PFX}/api/entities/reindex"))

    @mcp.tool()
    def chatlog_reprocess_status() -> str:
        """Get the current status of chat log AI reprocessing.

        Returns progress information for any running or recently completed
        reprocessing job.
        """
        return as_json(client.get(f"{_PFX}/api/chat/reprocess/status"))

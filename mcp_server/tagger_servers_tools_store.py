"""Store tools for tagger server MCP integration."""

import json

from mcp.server.fastmcp import FastMCP


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_tagger_server_store_tools(mcp: FastMCP, client):
    """Register tagger server storage tools."""

    @mcp.tool()
    def tagger_servers_tags(file_id: int) -> str:
        """Get tagger tags for a file.

        Args:
            file_id: Database file ID
        """
        from core.mesh_inference.tagger_store import get_tagger_tags
        return as_json({"file_id": file_id, "tags": get_tagger_tags(file_id)})

    @mcp.tool()
    def tagger_servers_delete_tags(file_id: int) -> str:
        """Delete tagger tags for a file.

        Args:
            file_id: Database file ID
        """
        from core.mesh_inference.tagger_store import delete_tagger_tags
        return as_json({"file_id": file_id, "deleted": delete_tagger_tags(file_id)})

    @mcp.tool()
    def tagger_servers_stats() -> str:
        """Get tagger statistics (untagged file count)."""
        from core.mesh_inference.tagger_store import count_untagged_files
        return as_json({"untagged_count": count_untagged_files()})

"""Sharing and config tools for SNS MCP integration."""

from mcp.server.fastmcp import FastMCP

from .sns_share_tools_common import as_json
from .validators import validate_file_id


def register_sns_share_core_tools(mcp: FastMCP, client):
    """Register direct sharing and config tools."""

    @mcp.tool()
    def share_to_bluesky(file_id: int, text: str = "", attach_image: bool = True) -> str:
        """Post an image to Bluesky with generated or custom text."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {"file_id": file_id, "attach_image": attach_image}
        if text:
            body["text"] = text
        return as_json(client.post("/api/sns/bluesky/post", body))

    @mcp.tool()
    def get_x_share_url(file_id: int) -> str:
        """Get X Web Intent URL for sharing an image's prompt info."""
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.get("/api/sns/x/intent", {"file_id": str(file_id)}))

    @mcp.tool()
    def get_sns_preview(file_id: int) -> str:
        """Get SNS share preview for an image."""
        return as_json(client.get("/api/sns/preview", {"file_id": str(file_id)}))

    @mcp.tool()
    def test_bluesky_connection() -> str:
        """Test Bluesky API connection."""
        return as_json(client.post("/api/sns/bluesky/test", {}))

    @mcp.tool()
    def get_sns_config() -> str:
        """Get SNS sharing configuration."""
        return as_json(client.get("/api/sns/config"))

    @mcp.tool()
    def save_sns_config(config: dict) -> str:
        """Save SNS sharing configuration."""
        return as_json(client.post("/api/sns/config", config))

"""Tag tools for Prompt Library."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_common import _PFX, as_json


def register_prompt_library_tag_tools(mcp: FastMCP, client: YuManagerClient):
    """Register tag tools."""

    @mcp.tool()
    def list_prompt_tags() -> str:
        """List all prompt library tags."""
        return as_json(client.get(f"{_PFX}/api/tags"))

    @mcp.tool()
    def create_prompt_tag(name: str) -> str:
        """Create a new prompt tag.
        Args:
            name: Tag name
        """
        return as_json(client.post(f"{_PFX}/api/tags", {"name": name}))

    @mcp.tool()
    def delete_prompt_tag(tag_id: int) -> str:
        """Delete a prompt tag.
        Args:
            tag_id: Tag ID to delete
        """
        return as_json(client.delete(f"{_PFX}/api/tags/{tag_id}"))

    @mcp.tool()
    def set_prompt_tags(prompt_id: int, tag_ids: list) -> str:
        """Set tags on a prompt (replaces existing).
        Args:
            prompt_id: Prompt ID
            tag_ids: List of tag IDs to assign
        """
        return as_json(client.post(f"{_PFX}/api/prompts/{prompt_id}/tags", {"tag_ids": tag_ids}))

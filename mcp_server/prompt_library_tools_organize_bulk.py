"""Bulk operations for Prompt Library."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_common import _PFX, as_json


def register_prompt_library_bulk_tools(mcp: FastMCP, client: YuManagerClient):
    """Register bulk tools."""

    @mcp.tool()
    def create_prompt_from_file(file_id: int, title: str = "", memo: str = "") -> str:
        """Create a prompt from an image file's metadata.

        Args:
            file_id: Source image file ID
            title: Optional title override (default: derived from filename)
            memo: Optional memo / description
        """
        body: dict = {"file_id": file_id}
        if title:
            body["title"] = title
        if memo:
            body["memo"] = memo
        return as_json(client.post(f"{_PFX}/api/prompts/from-file", body))

    @mcp.tool()
    def bulk_delete_prompts(prompt_ids: list) -> str:
        """Delete multiple prompts at once.

        Args:
            prompt_ids: List of prompt IDs to delete
        """
        return as_json(client.post(f"{_PFX}/api/prompts/bulk-delete", {"ids": prompt_ids}))

    @mcp.tool()
    def bulk_move_prompts(prompt_ids: list, folder_id: int) -> str:
        """Move multiple prompts to a folder.

        Args:
            prompt_ids: List of prompt IDs
            folder_id: Target folder ID (0 = move to root)
        """
        return as_json(client.post(f"{_PFX}/api/prompts/bulk-move", {"ids": prompt_ids, "folder_id": folder_id}))

    @mcp.tool()
    def bulk_tag_prompts(prompt_ids: list, tag_ids: list) -> str:
        """Add tags to multiple prompts.

        Args:
            prompt_ids: List of prompt IDs
            tag_ids: List of tag IDs to add
        """
        return as_json(client.post(f"{_PFX}/api/prompts/bulk-tag", {"ids": prompt_ids, "tag_ids": tag_ids}))

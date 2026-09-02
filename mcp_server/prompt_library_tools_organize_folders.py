"""Folder tools for Prompt Library."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_common import _PFX, as_json


def register_prompt_library_folder_tools(mcp: FastMCP, client: YuManagerClient):
    """Register folder tools."""

    @mcp.tool()
    def list_prompt_folders() -> str:
        """List all folders in the Prompt Library with item counts."""
        return as_json(client.get(f"{_PFX}/api/folders"))

    @mcp.tool()
    def create_prompt_folder(name: str) -> str:
        """Create a new prompt folder.
        Args:
            name: Folder name
        """
        return as_json(client.post(f"{_PFX}/api/folders", {"name": name}))

    @mcp.tool()
    def update_prompt_folder(folder_id: int, name: str = "", parent_id: int | None = None) -> str:
        """Rename or move a prompt folder.
        Args:
            folder_id: Folder ID
            name: New folder name (omit to keep unchanged)
            parent_id: New parent folder ID, or None to move to root (omit to keep unchanged)
        """
        payload: dict = {}
        if name:
            payload["name"] = name
        if parent_id is not None:
            payload["parent_id"] = parent_id
        return as_json(client.put(f"{_PFX}/api/folders/{folder_id}", payload))

    @mcp.tool()
    def delete_prompt_folder(folder_id: int) -> str:
        """Delete a prompt folder.
        Args:
            folder_id: Folder ID to delete
        """
        return as_json(client.delete(f"{_PFX}/api/folders/{folder_id}"))

    @mcp.tool()
    def move_prompt_to_folder(prompt_id: int, folder_id: int) -> str:
        """Move a prompt into a folder.
        Args:
            prompt_id: Prompt ID
            folder_id: Target folder ID
        """
        return as_json(client.post(f"{_PFX}/api/prompts/{prompt_id}/folder", {"folder_id": folder_id}))

    @mcp.tool()
    def remove_prompt_from_folder(prompt_id: int) -> str:
        """Remove a prompt from its folder (move to root).
        Args:
            prompt_id: Prompt ID
        """
        return as_json(client.delete(f"{_PFX}/api/prompts/{prompt_id}/folder"))

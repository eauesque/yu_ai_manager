"""Tag preset tools for LoRA dataset MCP integration."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .lora_dataset_tools_common import as_json


def register_lora_dataset_preset_tools(mcp: FastMCP, client: YuManagerClient):
    """Register LoRA dataset tag preset tools."""

    @mcp.tool()
    def list_lora_tag_presets() -> str:
        """List all saved tag exclusion presets."""
        return as_json(client.get("/ext/lora-dataset/tag-presets"))

    @mcp.tool()
    def create_lora_tag_preset(name: str, tags: list) -> str:
        """Create a tag exclusion preset.

        Args:
            name: Preset name (e.g. 'character_lora')
            tags: List of tag names to exclude
        """
        return as_json(client.post("/ext/lora-dataset/tag-presets", {"name": name, "tags": tags}))

    @mcp.tool()
    def update_lora_tag_preset(preset_id: int, name: str = "", tags: list | None = None) -> str:
        """Update a tag exclusion preset.

        Args:
            preset_id: Preset ID
            name: New preset name (omit to keep unchanged)
            tags: New list of tag names to exclude (omit to keep unchanged)
        """
        payload: dict = {}
        if name:
            payload["name"] = name
        if tags is not None:
            payload["tags"] = tags
        return as_json(client.put(f"/ext/lora-dataset/tag-presets/{preset_id}", payload))

    @mcp.tool()
    def delete_lora_tag_preset(preset_id: int) -> str:
        """Delete a tag exclusion preset.

        Args:
            preset_id: Preset ID
        """
        return as_json(client.delete(f"/ext/lora-dataset/tag-presets/{preset_id}"))

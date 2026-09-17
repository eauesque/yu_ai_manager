"""Import/export tools for Prompt Library."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_common import _PFX, as_json


def register_prompt_library_io_tools(mcp: FastMCP, client: YuManagerClient):
    """Register import/export tools."""

    @mcp.tool()
    def export_prompts() -> str:
        """Export all prompts as JSON."""
        return as_json(client.get(f"{_PFX}/api/export"))

    @mcp.tool()
    def import_prompts(data: dict) -> str:
        """Import prompts from exported JSON data.
        Args:
            data: Exported prompt data dict
        """
        return as_json(client.post(f"{_PFX}/api/import", data))

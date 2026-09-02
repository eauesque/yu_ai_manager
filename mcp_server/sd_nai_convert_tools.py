"""MCP tools for SD/NAI prompt format conversion."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def register_sd_nai_convert_tools(mcp: FastMCP, client):
    """Register SD/NAI prompt conversion MCP tools."""

    @mcp.tool()
    def convert_sd_to_nai(prompt: str) -> str:
        """Convert SD WebUI prompt syntax to NovelAI format.

        Args:
            prompt: Prompt text in SD WebUI format
        """
        if not prompt.strip():
            return _err("prompt is required")
        return _json(client.post("/ext/convert/sd-to-nai", {"prompt": prompt}))

    @mcp.tool()
    def convert_nai_to_sd(prompt: str) -> str:
        """Convert NovelAI prompt syntax to SD WebUI format.

        Args:
            prompt: Prompt text in NovelAI format
        """
        if not prompt.strip():
            return _err("prompt is required")
        return _json(client.post("/ext/convert/nai-to-sd", {"prompt": prompt}))

    @mcp.tool()
    def convert_prompt_batch(
        items: list,
        direction: str = "sd_to_nai",
    ) -> str:
        """Batch convert prompts between SD and NAI formats.

        Args:
            items: List of prompt text strings to convert
            direction: Conversion direction ('sd_to_nai' or 'nai_to_sd')
        """
        if not items:
            return _err("items list is required")
        return _json(client.post("/ext/convert/batch", {
            "items": items,
            "direction": direction,
        }))

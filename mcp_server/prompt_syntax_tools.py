"""MCP tools for prompt syntax analysis."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def register_prompt_syntax_tools(mcp: FastMCP, client):
    """Register prompt syntax analysis MCP tools."""

    @mcp.tool()
    def analyze_prompt_syntax(
        text: str,
        engine: str = "a1111",
    ) -> str:
        """Analyze prompt syntax and return token information.

        Parses emphasis, LoRA tags, wildcards, and other syntax elements.

        Args:
            text: Prompt text to analyze
            engine: Target engine ('a1111', 'nai', 'comfy', default 'a1111')
        """
        if not text.strip():
            return _err("text is required")
        return _json(client.post("/ext/syntax/analyze", {
            "text": text,
            "engine": engine,
        }))

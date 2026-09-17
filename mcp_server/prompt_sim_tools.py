"""MCP tools for Prompt Simulator — Dynamic Prompts, emphasis, conversion."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def register_prompt_sim_tools(mcp: FastMCP, client):
    """Register Prompt Simulator MCP tools."""

    @mcp.tool()
    def prompt_dp_analyze(text: str) -> str:
        """Analyze Dynamic Prompts syntax ({a|b|c}, __wildcard__, etc).

        Args:
            text: Prompt text containing Dynamic Prompts syntax
        """
        if not text.strip():
            return _err("text is required")
        return _json(client.post("/ext/prompt-sim/dp-analyze", {"text": text}))

    @mcp.tool()
    def prompt_emphasis(
        text: str,
        format: str = "a1111",
    ) -> str:
        """Convert emphasis/attention syntax in prompt text.

        Args:
            text: Prompt text with emphasis markers
            format: Target format ('a1111' or 'nai', default 'a1111')
        """
        if not text.strip():
            return _err("text is required")
        return _json(client.post("/ext/prompt-sim/emphasis", {
            "prompt": text,
            "format": format,
        }))

    @mcp.tool()
    def prompt_convert(
        text: str,
        mode: str = "sd_to_nai",
    ) -> str:
        """Convert prompt between A1111 and NovelAI formats.

        Args:
            text: Prompt text to convert
            mode: Conversion mode ('sd_to_nai', 'nai_to_sd', or 'expand')
        """
        if not text.strip():
            return _err("text is required")
        return _json(client.post("/ext/prompt-sim/convert", {
            "prompt": text,
            "mode": mode,
        }))

    @mcp.tool()
    def prompt_list_wildcards() -> str:
        """List available wildcard files and their contents."""
        return _json(client.get("/ext/prompt-sim/wildcards"))

    @mcp.tool()
    def prompt_set_wildcard_dirs(dirs: list) -> str:
        """Set wildcard search directories.

        Args:
            dirs: List of directory paths to search for wildcard files
        """
        return _json(client.post("/ext/prompt-sim/wildcard-dirs", {"dirs": dirs}))

    @mcp.tool()
    def prompt_danbooru_autocomplete(q: str) -> str:
        """Autocomplete Danbooru tags by prefix.

        Args:
            q: Tag prefix query string
        """
        if not q.strip():
            return _err("q is required")
        return _json(client.get("/ext/prompt-sim/danbooru-ac", {"q": q}))

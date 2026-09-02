"""MCP tools for tag dictionary operations."""

import json


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_tag_dict_tools(mcp, client):
    """Register tag dictionary MCP tools."""

    @mcp.tool()
    def search_tag_dictionary(
        query: str,
        limit: int = 20,
        fuzzy: bool = False,
    ) -> str:
        """Search the local tag dictionary for Danbooru tags.

        Args:
            query: Tag name to search (prefix match, then substring, then alias)
            limit: Max results (1-100, default 20)
            fuzzy: Enable fuzzy matching for typo tolerance
        """
        if not query.strip():
            return "Error: query must not be empty"
        limit = max(1, min(limit, 100))
        params = {
            "q": query,
            "limit": str(limit),
            "fuzzy": "1" if fuzzy else "0",
        }
        return _json(client.get("/api/tag-dict/search", params))

    @mcp.tool()
    def get_tag_dict_stats() -> str:
        """Get tag dictionary statistics (total count, category breakdown)."""
        return _json(client.get("/api/tag-dict/stats"))

    @mcp.tool()
    def split_tags(text: str) -> str:
        """Split concatenated tags into individual tags using the dictionary.

        Args:
            text: Concatenated tag string (e.g. "1girlblueeyeslonghair")
        """
        if not text.strip():
            return "Error: text must not be empty"
        return _json(client.post("/api/tag-dict/split", {"text": text}))

    @mcp.tool()
    def import_tag_dictionary(data: dict) -> str:
        """Import tag dictionary entries.
        Args:
            data: Import data dict
        """
        return _json(client.post("/api/tag-dict/import", data))

    @mcp.tool()
    def clear_tag_dictionary() -> str:
        """Clear all tag dictionary entries."""
        return _json(client.delete("/api/tag-dict/clear"))

    @mcp.tool()
    def get_tag_dict_info(tag: str) -> str:
        """Get detailed info for a single tag from the dictionary.

        Args:
            tag: Tag name to look up (exact match)
        """
        if not tag.strip():
            return "Error: tag must not be empty"
        return _json(client.get("/api/tag-dict/info", {"tag": tag}))

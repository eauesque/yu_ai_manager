"""MCP tools for trophy system."""

import json


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_trophy_tools(mcp, client):
    """Register trophy-related MCP tools."""

    @mcp.tool()
    def list_trophies() -> str:
        """List all trophies (achieved and unachieved silhouettes).

        Returns trophy list with type, title, tier (bronze/silver/gold/platinum),
        category (milestone/streak/diversity/source/hidden), and achievement status.
        Hidden trophies show title as '???' when not yet achieved.
        """
        return _json(client.get("/api/trophies"))

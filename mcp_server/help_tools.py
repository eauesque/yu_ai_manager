"""MCP ツール: ヘルプコンテンツの検索・取得。"""

import json


def register_help_tools(mcp, client):
    """ヘルプ関連 MCP ツールを登録。"""

    @mcp.tool()
    def help_search(query: str, limit: int = 5, lang: str = "ja") -> str:
        """Search the built-in help documentation by keyword.

        Args:
            query: Search keyword
            limit: Max results (1-20, default 5)
            lang: Language code ("ja" or "en", default "ja")
        """
        if not query.strip():
            return "Error: query must not be empty"
        limit = max(1, min(limit, 20))
        if lang not in ("ja", "en"):
            lang = "ja"
        result = client.get("/api/help/search", {
            "q": query,
            "limit": str(limit),
            "lang": lang,
        })
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    def help_get_section(section: str, lang: str = "ja") -> str:
        """Get a specific help section content.

        User guide sections: getting-started, search, scan, bridges,
        settings, troubleshooting

        Developer guide sections: api, api-reference, mcp, extensions,
        plugin-development, custom-ui, events, theming

        Args:
            section: Section slug name
            lang: Language code ("ja" or "en", default "ja")
        """
        section = section.strip()
        if not section:
            return "Error: section must not be empty"
        if lang not in ("ja", "en"):
            lang = "ja"
        result = client.get(f"/api/help/content/{section}", {"lang": lang})
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    def help_toc(lang: str = "ja") -> str:
        """Get help documentation table of contents (categorized).

        Args:
            lang: Language code ("ja" or "en", default "ja")
        """
        if lang not in ("ja", "en"):
            lang = "ja"
        return json.dumps(client.get("/api/help/toc", {"lang": lang}),
                          ensure_ascii=False, indent=2)

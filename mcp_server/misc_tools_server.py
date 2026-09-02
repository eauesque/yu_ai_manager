"""Server, search, and suggestion misc tools."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .misc_tools_common import as_json


def register_misc_server_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def get_server_info() -> str:
        """Get server information."""
        return as_json(client.get("/api/server-info"))

    @mcp.tool()
    def get_inference_info() -> str:
        """Get inference engine information."""
        return as_json(client.get("/api/system/inference-info"))

    @mcp.tool()
    def get_suggestions(q: str, limit: int = 10) -> str:
        """Get tag/prompt suggestions. Args: q: query string, limit: max results"""
        return as_json(client.get("/api/suggest", {"q": q, "limit": str(limit)}))

    @mcp.tool()
    def suggest_lora(q: str = "") -> str:
        """Suggest LoRA names. Args: q: query string"""
        return as_json(client.get("/api/suggest/lora", {"q": q}))

    @mcp.tool()
    def suggest_embedding(q: str = "") -> str:
        """Suggest embedding names. Args: q: query string"""
        return as_json(client.get("/api/suggest/embedding", {"q": q}))

    @mcp.tool()
    def suggest_tags(q: str, limit: int = 10) -> str:
        """Suggest tags. Args: q: query string, limit: max results"""
        return as_json(client.get("/api/tags/suggest", {"q": q, "limit": str(limit)}))

    @mcp.tool()
    def search_images_grouped(
        query: str = "",
        sort: str = "date",
        limit: int = 20,
        from_date: str = "",
        to_date: str = "",
        file_format: str = "all",
        min_rating: str = "",
        max_rating: str = "",
        in_prompt: str = "",
        fav_only: bool = False,
        collection_id: int = 0,
    ) -> str:
        """Search images with directory grouping.

        Args:
            query: Tag query (comma-separated)
            sort: Sort order (date|folder|path|random)
            limit: Max results per page
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            file_format: File type (all|png|webp|jpg|gif)
            min_rating: Minimum star rating (1-5)
            max_rating: Maximum star rating (1-5)
            in_prompt: Full-text search within positive prompt
            fav_only: Only show favorited images
            collection_id: Filter by collection (0=all)
        """
        params: dict = {"query": query, "sort": sort, "limit": str(limit)}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        if file_format and file_format != "all":
            params["format"] = file_format
        if min_rating:
            params["min_rating"] = min_rating
        if max_rating:
            params["max_rating"] = max_rating
        if in_prompt:
            params["in_prompt"] = in_prompt
        if fav_only:
            params["fav_only"] = "true"
        if collection_id:
            params["collection_id"] = str(collection_id)
        return as_json(client.get("/api/search-grouped", params))

    @mcp.tool()
    def search_union(collection_ids: list, sort: str = "date", limit: int = 200, offset: int = 0) -> str:
        """Merge results from multiple collections via union search. Args: collection_ids: list of collection IDs to merge, sort: sort order (date/name), limit: max results, offset: pagination offset"""
        return as_json(client.post("/api/search-union", {"collection_ids": collection_ids, "sort": sort, "limit": limit, "offset": offset}))

    @mcp.tool()
    def get_recent_logs(limit: int = 100) -> str:
        """Get recent application logs. Args: limit: max log entries"""
        return as_json(client.get("/api/logs/recent", {"limit": str(limit)}))

    @mcp.tool()
    def get_market_quotes() -> str:
        """Get stock market quotes."""
        return as_json(client.get("/api/market/quotes"))

    @mcp.tool()
    def get_mdns_identity() -> str:
        """Get this server's mDNS identity (hostname, peer ID)."""
        return as_json(client.get("/api/mdns/identity"))

    @mcp.tool()
    def get_mdns_peers() -> str:
        """Get list of mDNS-discovered peers on the local network."""
        return as_json(client.get("/api/mdns/peers"))

    @mcp.tool()
    def get_shutdown_info() -> str:
        """Get shutdown configuration: whether PIN is required."""
        return as_json(client.get("/api/admin/shutdown/info"))

    @mcp.tool()
    def shutdown_server(pin: str | None = None) -> str:
        """Shutdown the yu_ai_manager server.

        Args:
            pin: Optional shutdown PIN (omit if not required)
        """
        body: dict = {}
        if pin is not None and pin != "":
            body["pin"] = pin
        return as_json(client.post("/api/admin/shutdown", body))

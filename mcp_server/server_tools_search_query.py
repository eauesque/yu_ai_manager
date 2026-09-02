"""Search and read tools for server MCP layer."""

from .server_tools_common import as_json
from .validators import (
    validate_date_range,
    validate_file_format,
    validate_file_id,
    validate_rating_range,
    validate_search_limit,
    validate_sort,
)


def register_search_query_tools(mcp, client) -> None:
    """Register resources and search/read tools."""

    @mcp.resource("library://stats")
    def library_stats() -> str:
        return as_json(client.get("/api/stats/all"))

    @mcp.resource("library://recent")
    def library_recent() -> str:
        return as_json(client.get("/api/search", {"sort": "date", "limit": "20"}))

    @mcp.tool()
    def search_images(
        query: str = "",
        sort: str = "date",
        limit: int = 20,
        cursor: str = "",
        from_date: str = "",
        to_date: str = "",
        file_format: str = "all",
        min_rating: str = "",
        max_rating: str = "",
        in_prompt: str = "",
        fav_only: bool = False,
        collection_id: int = 0,
        also_path: bool = False,
    ) -> str:
        """Search images in the library with various filters.

        Args:
            query: Tag query (comma-separated, e.g. "1girl, blue_eyes")
            sort: Sort order (date|date_new|date_old|folder|path|random|rating_desc|rating_asc)
            limit: Max results per page (1-200, default 20)
            cursor: Pagination cursor from a previous search's next_cursor
            from_date: Start date filter (YYYY-MM-DD, server-local timezone)
            to_date: End date filter (YYYY-MM-DD, server-local timezone)
            file_format: File type (all|png|webp|jpg|gif)
            min_rating: Minimum star rating (1-5)
            max_rating: Maximum star rating (1-5)
            in_prompt: Full-text search within positive prompt
            fav_only: Only show favorited images
            collection_id: Filter by collection (0=all, -1=any favorite)
            also_path: Also match query as path substring (default False, tag-only)
        """
        err = validate_sort(sort)
        if err:
            return err
        err = validate_file_format(file_format)
        if err:
            return err
        limit, _ = validate_search_limit(limit)
        err = validate_rating_range(min_rating, max_rating)
        if err:
            return err
        err = validate_date_range(from_date, to_date)
        if err:
            return err
        params = {
            "q": query,
            "sort": sort,
            "limit": str(limit),
            "cursor": cursor,
            "from": from_date,
            "to": to_date,
            "format": file_format,
            "min_rating": min_rating,
            "max_rating": max_rating,
            "in_prompt": in_prompt,
            "fav_only": "true" if fav_only else "",
            "collection_id": str(collection_id) if collection_id else "",
            "also_path": "true" if also_path else "false",
        }
        result = client.get("/api/search", params)
        if sort == "random":
            data = result.get("data", result)
            if isinstance(data, dict):
                data.pop("next_cursor", None)
                data["has_more"] = False
        return as_json(result)

    @mcp.tool()
    def get_image_detail(file_id: int) -> str:
        """Get full metadata for a single image (path, prompt, tags, etc.).

        Args:
            file_id: The file ID to look up
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.get(f"/api/file/{file_id}"))

    @mcp.tool()
    def get_library_stats() -> str:
        """Get library statistics: file count, tags, sources, timeline, models."""
        return as_json(client.get("/api/stats/all"))

"""File and group misc tools."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .misc_tools_common import as_json


def register_misc_file_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def list_dirs(path: str = "") -> str:
        """List directories. Args: path: root path to list"""
        return as_json(client.get("/api/tools/list-dirs", {"path": path}))

    @mcp.tool()
    def inspect_metadata(file_id: int) -> str:
        """Inspect raw metadata of a file. Args: file_id: target file ID"""
        return as_json(client.post("/api/inspect", {"file_id": file_id}))

    @mcp.tool()
    def get_share_link(file_id: int) -> str:
        """Get a share link for a file. Args: file_id: target file ID"""
        return as_json(client.get(f"/api/share/{file_id}"))

    @mcp.tool()
    def get_file_info(file_id: int) -> str:
        """Get file path and metadata info. Args: file_id: target file ID"""
        return as_json(client.get(f"/api/file-info/{file_id}"))

    @mcp.tool()
    def get_container_members(file_id: int) -> str:
        """Get member list of a ZIP/RAR container. Args: file_id: container file ID"""
        return as_json(client.get(f"/api/container-members/{file_id}"))

    @mcp.tool()
    def extract_from_zip(file_id: int, members: list) -> str:
        """Extract specific members from a ZIP file. Args: file_id: ZIP file ID, members: list of member paths to extract"""
        return as_json(client.post("/api/extract-from-zip", {"file_id": file_id, "members": members}))

    @mcp.tool()
    def get_groups_index() -> str:
        """Get directory groups index."""
        return as_json(client.get("/api/groups-index"))

    @mcp.tool()
    def get_group_members(group: str) -> str:
        """Get members of a directory group. Args: group: group name/path"""
        return as_json(client.get("/api/group-members", {"group": group}))

    @mcp.tool()
    def get_ratings(file_ids: list) -> str:
        """Get ratings for files. Args: file_ids: list of integer file IDs"""
        return as_json(client.post("/api/ratings/batch", {"file_ids": file_ids}))

    @mcp.tool()
    def get_ratings_stats() -> str:
        """Get rating statistics."""
        return as_json(client.get("/api/ratings/stats"))

    @mcp.tool()
    def rate_image(file_id: int, rating: int) -> str:
        """Set a rating for a single file.

        Args:
            file_id: Target file ID
            rating: Rating value (0-5, 0 to clear)
        """
        return as_json(client.post("/api/ratings/set", {"file_id": file_id, "rating": rating}))

    @mcp.tool()
    def get_image_rating(file_id: int) -> str:
        """Get rating for a single file.

        Args:
            file_id: Target file ID
        """
        return as_json(client.get("/api/ratings/get", {"file_id": str(file_id)}))

    @mcp.tool()
    def file_search(query: str, meta_filter: str = "all", limit: int = 100) -> str:
        """Search files by path/name in the database.

        Args:
            query: Search query for file path/name
            meta_filter: Metadata filter - 'all', 'with_meta', 'no_meta'
            limit: Max results (1-500, default 100)
        """
        limit = max(1, min(limit, 500))
        return as_json(client.get("/api/tools/file-search", {"q": query, "meta": meta_filter, "limit": str(limit)}))

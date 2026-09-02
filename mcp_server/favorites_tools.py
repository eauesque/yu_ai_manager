import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_favorites_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def toggle_favorite(file_id: int) -> str:
        """Toggle favorite status for a file. Args: file_id: target file ID"""
        return _json(client.post("/api/favorites/toggle", {"file_id": file_id}))

    @mcp.tool()
    def check_favorite(file_id: int) -> str:
        """Check if a file is favorited. Args: file_id: target file ID"""
        return _json(client.get("/api/favorites/check", {"file_id": str(file_id)}))

    @mcp.tool()
    def check_favorite_collections(file_id: int) -> str:
        """Check which collections a favorited file belongs to. Args: file_id: target file ID"""
        return _json(client.get("/api/favorites/check_collections", {"file_id": str(file_id)}))

    @mcp.tool()
    def list_favorites(limit: int = 50, offset: int = 0) -> str:
        """List favorited files. Args: limit: max results, offset: pagination offset"""
        return _json(client.get("/api/favorites/list", {"limit": str(limit), "offset": str(offset)}))

    # ── Favorites Manager Extension ──

    _FAV_PFX = "/ext/favorites"

    @mcp.tool()
    def fav_batch_add(file_ids: list, collection_id: int = 1) -> str:
        """Add multiple files to favorites at once.

        Args:
            file_ids: List of file IDs to add
            collection_id: Target collection ID (default 1)
        """
        if not file_ids:
            return _json({"ok": False, "error": "file_ids must not be empty"})
        return _json(client.post(f"{_FAV_PFX}/api/batch-add", {
            "file_ids": file_ids, "collection_id": collection_id,
        }))

    @mcp.tool()
    def fav_batch_remove(file_ids: list, collection_id: int = 0) -> str:
        """Remove multiple files from favorites at once.

        Args:
            file_ids: List of file IDs to remove
            collection_id: Collection ID to remove from (0 = all collections)
        """
        if not file_ids:
            return _json({"ok": False, "error": "file_ids must not be empty"})
        body = {"file_ids": file_ids}
        if collection_id:
            body["collection_id"] = collection_id
        return _json(client.post(f"{_FAV_PFX}/api/batch-remove", body))

    @mcp.tool()
    def fav_images(collection_id: int = 0) -> str:
        """List images in a favorites collection.

        Args:
            collection_id: Collection ID to list (0 = default collection)
        """
        params = {}
        if collection_id:
            params["collection_id"] = str(collection_id)
        return _json(client.get(f"{_FAV_PFX}/api/images", params))

    @mcp.tool()
    def fav_export_folder(dest_path: str, collection_id: int = 0) -> str:
        """Export favorites to a folder on the server.

        Args:
            dest_path: Destination directory path on the server
            collection_id: Collection ID to export (0 = default)
        """
        if not dest_path.strip():
            return _json({"ok": False, "error": "dest_path is required"})
        body = {"dest_path": dest_path}
        if collection_id:
            body["collection_id"] = collection_id
        return _json(client.post(f"{_FAV_PFX}/api/export/folder", body))

"""Collection tools for server MCP search layer."""

from .server_tools_common import as_json
from .validators import check_batch_all_failed, validate_batch_size, validate_file_id


def register_search_collection_tools(mcp, client) -> None:
    """Register collection and similarity tools."""

    @mcp.tool()
    def list_collections() -> str:
        """List all collections with their file counts."""
        return as_json(client.get("/api/collections"))

    @mcp.tool()
    def create_collection(name: str) -> str:
        """Create a new collection.

        Args:
            name: Collection name (must not be empty)
        """
        name = name.strip()
        if not name:
            return "Error: name must not be empty"
        return as_json(client.post("/api/collections", {"name": name}))

    @mcp.tool()
    def delete_collection(collection_id: int) -> str:
        """Delete a collection by ID. The default collection (id=1) cannot be deleted.

        Args:
            collection_id: ID of the collection to delete
        """
        err = validate_file_id(collection_id)
        if err:
            return err
        return as_json(client.delete(f"/api/collections/{collection_id}"))

    @mcp.tool()
    def remove_from_collection(collection_id: int, file_ids: list, expected_count: int = 0) -> str:
        """Remove multiple images from a collection.

        Args:
            collection_id: Target collection ID
            file_ids: List of integer file IDs to remove. Max 500.
            expected_count: Number of file_ids you intended to send (truncation guard)
        """
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        return as_json(check_batch_all_failed(client.post(f"/api/collections/{collection_id}/batch-remove", {"file_ids": file_ids})))

    @mcp.tool()
    def rename_collection(collection_id: int, name: str) -> str:
        """Rename a collection.

        Args:
            collection_id: Collection ID to rename
            name: New collection name
        """
        err = validate_file_id(collection_id)
        if err:
            return err
        name = name.strip()
        if not name:
            return "Error: name must not be empty"
        return as_json(client.put(f"/api/collections/{collection_id}", {"name": name}))

    @mcp.tool()
    def reorder_collections(order: list) -> str:
        """Reorder collections.

        Args:
            order: List of collection IDs in desired display order
        """
        return as_json(client.post("/api/collections/reorder", {"order": order}))

    @mcp.tool()
    def find_similar(file_id: int, threshold: int = 5) -> str:
        """Find visually similar images using perceptual hash comparison.

        Args:
            file_id: Reference image file ID
            threshold: Hamming distance (1-20, lower=stricter, default 5)
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.get("/api/tools/find-similar", {"file_id": str(file_id), "threshold": str(threshold)}))

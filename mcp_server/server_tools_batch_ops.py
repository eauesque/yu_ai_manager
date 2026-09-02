"""Batch write operations for server MCP tools."""

from .server_tools_common import as_json
from .validators import check_batch_all_failed, validate_batch_size


def register_batch_operation_tools(mcp, client) -> None:
    """Register batch rating, collection, and tag tools."""

    @mcp.tool()
    def rate_images(items: list, expected_count: int = 0) -> str:
        """Set star ratings for multiple images at once.

        Args:
            items: List of objects with file_id and rating.
                   Example: [{"file_id": 123, "rating": 5}, {"file_id": 456, "rating": 0}]
                   rating 0 clears the rating, 1-5 sets it. Max 500 items.
            expected_count: Number of items you intended to send (truncation guard)
        """
        err = validate_batch_size(items, expected_count)
        if err:
            return err
        return as_json(check_batch_all_failed(client.post("/api/ratings/batch-set", {"items": items})))

    @mcp.tool()
    def add_to_collection(collection_id: int, file_ids: list, expected_count: int = 0) -> str:
        """Add multiple images to a collection (idempotent).

        Args:
            collection_id: Target collection ID
            file_ids: List of integer file IDs to add. Max 500.
            expected_count: Number of file_ids you intended to send (truncation guard)
        """
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        return as_json(check_batch_all_failed(client.post(f"/api/collections/{collection_id}/batch-add", {"file_ids": file_ids})))

    @mcp.tool()
    def set_tags(items: list, expected_count: int = 0) -> str:
        """Add or remove user tags from multiple images.

        Tags are saved with source='user' to distinguish from metadata-extracted tags.
        User tags are preserved across re-scans and can be removed independently.

        Args:
            items: List of objects with file_id, add, and remove arrays.
                   Example: [{"file_id": 123, "add": ["good"], "remove": ["bad"]}]
                   Max 500 items. Only user-source tags can be removed via this API.
            expected_count: Number of items you intended to send (truncation guard)
        """
        err = validate_batch_size(items, expected_count)
        if err:
            return err
        return as_json(check_batch_all_failed(client.post("/api/tags/batch-set", {"items": items})))

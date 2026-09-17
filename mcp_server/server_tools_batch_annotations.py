"""Annotation tools for server MCP batch layer."""


from .server_tools_common import as_json
from .validators import (
    check_batch_all_failed,
    validate_annotation_items,
    validate_batch_size,
    validate_confidence_range,
    validate_file_id,
)


def register_batch_annotation_tools(mcp, client) -> None:
    """Register annotation tools."""

    @mcp.tool()
    def set_annotations(items: list, expected_count: int = 0) -> str:
        """Store AI/agent analysis results as annotations (upserts by file_id+source+key).

        Args:
            items: List of annotation objects. Max 500. Example:
                   [{"file_id": 123, "source": "agent:claude",
                     "key": "quality_score", "value": "0.85", "confidence": 0.85}]
                   source: identifies who created it (e.g. "agent:claude")
                   key: annotation type (e.g. "quality_score", "hand_defect")
                   value: string value (use JSON for structured data)
                   confidence: 0.0-1.0 or null
            expected_count: Number of items you intended to send (truncation guard)
        """
        err = validate_batch_size(items, expected_count)
        if err:
            return err
        err = validate_annotation_items(items)
        if err:
            return err
        return as_json(check_batch_all_failed(client.post("/api/annotations/batch-set", {"items": items})))

    @mcp.tool()
    def get_annotations(file_id: int, source: str = "", key: str = "") -> str:
        """Get annotations for a specific image.

        Args:
            file_id: File ID to get annotations for
            source: Filter by source (e.g. "agent:claude")
            key: Filter by key (e.g. "quality_score")
        """
        err = validate_file_id(file_id)
        if err:
            return err
        params = {}
        if source:
            params["source"] = source
        if key:
            params["key"] = key
        return as_json(client.get(f"/api/annotations/{file_id}", params))

    @mcp.tool()
    def search_annotations(
        source: str = "",
        key: str = "",
        min_confidence: str = "",
        max_confidence: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> str:
        """Search annotations across all files by source, key, or confidence.

        Args:
            source: Filter by source (e.g. "agent:claude")
            key: Filter by key (e.g. "quality_score")
            min_confidence: Minimum confidence threshold (0.0-1.0)
            max_confidence: Maximum confidence threshold (0.0-1.0)
            limit: Max results (1-2000, default 100)
            offset: Skip first N results
        """
        err = validate_confidence_range(min_confidence, max_confidence)
        if err:
            return err
        return as_json(client.get("/api/annotations/search", {
            "source": source,
            "key": key,
            "min_confidence": min_confidence,
            "max_confidence": max_confidence,
            "limit": str(limit),
            "offset": str(offset),
        }))

    @mcp.tool()
    def delete_annotations(source: str, file_ids: list | None = None, key: str = "") -> str:
        """Delete annotations by source. Optionally scope to specific files or keys.

        Args:
            source: Required. Source to delete (e.g. "agent:claude")
            file_ids: Optional list of file IDs to limit deletion scope
            key: Optional key to limit deletion (e.g. "quality_score")
        """
        if file_ids:
            for file_id in file_ids:
                err = validate_file_id(file_id)
                if err:
                    return err
        body = {"source": source}
        if file_ids:
            body["file_ids"] = file_ids
        if key:
            body["key"] = key
        return as_json(client.post("/api/annotations/batch-delete", body))

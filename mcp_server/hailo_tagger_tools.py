"""MCP tools for Hailo Remote Tagger."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import validate_file_id


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_hailo_tagger_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Hailo Remote Tagger tools on the MCP server."""

    @mcp.tool()
    def hailo_tagger_tag_file(file_id: int) -> str:
        """Run Hailo remote tagger on a single image file.

        Args:
            file_id: The file ID to tag
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return _json(client.post(f"/api/hailo-tagger/tag/{file_id}", {}))

    @mcp.tool()
    def hailo_tagger_batch(file_ids: list, expected_count: int = 0) -> str:
        """Run Hailo remote tagger on multiple files. Max 500.

        Args:
            file_ids: List of file IDs to tag
            expected_count: Number of file_ids you intended to send (truncation guard)
        """
        from .validators import check_batch_all_failed, validate_batch_size
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        result = client.post("/api/hailo-tagger/batch", {"file_ids": file_ids})
        return _json(check_batch_all_failed(result))

    @mcp.tool()
    def hailo_tagger_status() -> str:
        """Check Hailo remote tagger connection status."""
        return _json(client.get("/api/hailo-tagger/status"))

    @mcp.tool()
    def hailo_tagger_get_config() -> str:
        """Get Hailo remote tagger configuration."""
        return _json(client.get("/api/hailo-tagger/config"))

    @mcp.tool()
    def hailo_tagger_save_config(config: dict) -> str:
        """Save Hailo remote tagger configuration (endpoint_url, enabled, threshold, timeout).

        Args:
            config: Config dict with keys: endpoint_url, enabled, threshold, timeout
        """
        return _json(client.post("/api/hailo-tagger/config", config))

    @mcp.tool()
    def hailo_tagger_get_tags(file_id: int) -> str:
        """Get Hailo tagger tags for a file.

        Args:
            file_id: The file ID to get tags for
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return _json(client.get(f"/api/hailo-tagger/tags/{file_id}"))

    @mcp.tool()
    def hailo_tagger_delete_tags(file_id: int) -> str:
        """Delete Hailo tagger tags for a file.

        Args:
            file_id: The file ID to delete tags from
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return _json(client.delete(f"/api/hailo-tagger/tags/{file_id}"))

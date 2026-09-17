"""Tagging and batch tools for WD-Tagger."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import check_batch_all_failed, validate_batch_size, validate_file_id
from .wd_tagger_tools_common import as_json


def register_wd_tagger_tagging_tools(mcp: FastMCP, client: YuManagerClient):
    """Register WD-Tagger tagging tools."""

    @mcp.tool()
    def wd_tagger_tag_file(file_id: int) -> str:
        """Run WD-Tagger inference on a single image file.

        Args:
            file_id: The file ID to tag
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.post(f"/api/wd-tagger/tag/{file_id}", {}))

    @mcp.tool()
    def wd_tagger_batch(
        file_ids: list,
        expected_count: int = 0,
        limit: int = 100,
        force: bool = False,
        scan_root: str = "",
    ) -> str:
        """Run WD-Tagger inference on multiple files at once.

        Args:
            file_ids: List of file IDs to tag. Max 500. Pass empty list to use
                scan_root/backfill mode instead.
            expected_count: Number of file_ids you intended to send (truncation guard)
            limit: Max files to process (default 100, max 500). Applies when
                file_ids is empty and scan_root backfill is used.
            force: Re-tag files that already have tags (default False). Only
                applies when file_ids is empty (backfill mode).
            scan_root: Restrict backfill to files under this path (empty = all).
                Only applies when file_ids is empty.
        """
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        body: dict = {"file_ids": file_ids}
        if limit != 100:
            body["limit"] = limit
        if force:
            body["force"] = force
        if scan_root:
            body["scan_root"] = scan_root
        return as_json(check_batch_all_failed(client.post("/api/wd-tagger/batch", body)))

    @mcp.tool()
    def wd_tagger_batch_cancel() -> str:
        """Cancel a running WD-Tagger batch job."""
        return as_json(client.post("/api/wd-tagger/batch/cancel", {}))

    @mcp.tool()
    def wd_tagger_get_tags(file_id: int) -> str:
        """Get WD-Tagger tags for a specific file.

        Args:
            file_id: The file ID to get tags for
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.get(f"/api/wd-tagger/tags/{file_id}"))

    @mcp.tool()
    def wd_tagger_delete_tags(file_id: int) -> str:
        """Delete all WD-Tagger tags for a specific file.

        Args:
            file_id: The file ID to delete tags from
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return as_json(client.delete(f"/api/wd-tagger/tags/{file_id}"))

    @mcp.tool()
    def wd_tagger_delete_tags_batch(file_ids: list, expected_count: int = 0) -> str:
        """Delete WD-Tagger tags for multiple files at once.

        Args:
            file_ids: List of file IDs to delete tags from. Max 500.
            expected_count: Number of file_ids you intended to send (truncation guard)
        """
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        return as_json(client.delete("/api/wd-tagger/tags/batch", {"file_ids": file_ids}))

    @mcp.tool()
    def wd_tagger_stats() -> str:
        """Get WD-Tagger statistics: tagged file count, tag distribution, etc."""
        return as_json(client.get("/api/wd-tagger/stats"))

    @mcp.tool()
    def wd_tagger_untagged(limit: int = 50, offset: int = 0) -> str:
        """List files that have not been tagged by WD-Tagger yet.

        Args:
            limit: Max results (default 50)
            offset: Skip first N results
        """
        return as_json(client.get("/api/wd-tagger/untagged", {"limit": str(limit), "offset": str(offset)}))

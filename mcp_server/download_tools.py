"""MCP tools for batch download."""

import json

from .validators import validate_batch_size


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_download_tools(mcp, client):
    @mcp.tool()
    def batch_download_zip(file_ids: list, expected_count: int = 0) -> str:
        """Download multiple images as a single ZIP file.

        Note: MCP cannot transfer binary data. This tool validates
        the request and returns metadata. Use the REST API directly
        for the actual ZIP download.

        Args:
            file_ids: List of integer file IDs to include. Max 500.
            expected_count: Number of file_ids you intended to send (truncation guard)
        """
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err

        return _json({
            "endpoint": "POST /api/download/batch-zip",
            "body": {"file_ids": file_ids},
            "note": "Use the REST API directly to download the ZIP binary.",
            "file_count": len(file_ids),
        })

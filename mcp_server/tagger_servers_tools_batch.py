"""Batch tools for tagger server MCP integration."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def as_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_tagger_server_batch_tools(mcp: FastMCP, client: YuManagerClient):
    """Register tagger server batch tools."""

    @mcp.tool()
    def tagger_servers_batch(file_ids: list[int] | None = None, limit: int = 500, force: bool = False, threshold: float | None = None) -> str:
        """Start distributed batch tagging across all enabled tagger servers.

        Uses shared-queue work-stealing: faster workers process more files.

        Args:
            file_ids: Specific file IDs to tag (None = auto-select untagged)
            limit: Max files to process when auto-selecting
            force: Re-tag files that already have tags
            threshold: Override confidence threshold
        """
        from core.mesh_inference.dispatch_sync import run_tagger_batch as run_batch
        return as_json(run_batch(file_ids=file_ids, limit=limit, force=force, threshold=threshold))

    @mcp.tool()
    def tagger_servers_batch_cancel() -> str:
        """Cancel a running tagger cluster batch job."""
        return as_json(client.post("/api/tagger-servers/batch/cancel", {}))

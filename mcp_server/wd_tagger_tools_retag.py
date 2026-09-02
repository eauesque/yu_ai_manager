"""Retag job tools for WD-Tagger (Phase 2b)."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .wd_tagger_tools_common import as_json

_MAX_FILE_IDS = 500


def register_wd_tagger_retag_tools(mcp: FastMCP, client: YuManagerClient):
    """Register WD-Tagger retag job tools."""

    @mcp.tool()
    def wd_tagger_retag_single(
        file_id: int,
        model_id: str,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        overwrite_same_model: bool = True,
        set_active: bool = True,
    ) -> str:
        """Retag a single file with a specific WD-Tagger model (synchronous).

        Args:
            file_id: The file ID to retag
            model_id: WD-Tagger model ID to use (e.g. "wd-v1-4-moat-tagger-v2")
            general_threshold: Confidence threshold for general tags (default 0.35)
            character_threshold: Confidence threshold for character tags (default 0.85)
            overwrite_same_model: Overwrite existing tags from the same model (default True)
            set_active: Set the new annotation as active (default True)
        """
        if file_id <= 0:
            return "Error: file_id must be a positive integer"
        if not model_id or not model_id.strip():
            return "Error: model_id must not be empty"
        body = {
            "file_id": file_id,
            "model_id": model_id.strip(),
            "thresholds": {
                "general": general_threshold,
                "character": character_threshold,
            },
            "overwrite_same_model": overwrite_same_model,
            "set_active": set_active,
        }
        return as_json(client.post("/api/wd-tagger/retag/single", body))

    @mcp.tool()
    def wd_tagger_retag_batch(
        file_ids: list,
        model_id: str,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        batch_size: int = 8,
        limit: int = 0,
        set_active: bool = True,
        expected_count: int = 0,
    ) -> str:
        """Start an async retag job for a list of specific files.

        Args:
            file_ids: List of file IDs to retag. Max 500.
            model_id: WD-Tagger model ID to use
            general_threshold: Confidence threshold for general tags (default 0.35)
            character_threshold: Confidence threshold for character tags (default 0.85)
            batch_size: Inference batch size, 1-64 (default 8)
            limit: Max files to process, 0 = no limit (default 0)
            set_active: Set new annotations as active (default True)
            expected_count: Number of file_ids you intended to send (truncation guard)
        """
        if not isinstance(file_ids, list) or len(file_ids) == 0:
            return "Error: file_ids must be a non-empty list"
        if expected_count > 0 and len(file_ids) != expected_count:
            return (
                f"Error: truncation guard - expected {expected_count} file_ids "
                f"but received {len(file_ids)}"
            )
        if len(file_ids) > _MAX_FILE_IDS:
            return f"Error: file_ids max {_MAX_FILE_IDS}"
        if not model_id or not model_id.strip():
            return "Error: model_id must not be empty"
        body = {
            "file_ids": file_ids,
            "model_id": model_id.strip(),
            "thresholds": {
                "general": general_threshold,
                "character": character_threshold,
            },
            "batch_size": batch_size,
            "limit": limit,
            "set_active": set_active,
        }
        return as_json(client.post("/api/wd-tagger/retag/batch", body))

    @mcp.tool()
    def wd_tagger_retag_backfill(
        model_id: str,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        batch_size: int = 8,
        limit: int = 0,
        set_active: bool = True,
        scan_root: str = "",
        force: bool = False,
    ) -> str:
        """Start an async retag job for files missing tags (backfill mode).

        Args:
            model_id: WD-Tagger model ID to use
            general_threshold: Confidence threshold for general tags (default 0.35)
            character_threshold: Confidence threshold for character tags (default 0.85)
            batch_size: Inference batch size, 1-64 (default 8)
            limit: Max files to process, 0 = no limit (default 0)
            set_active: Set new annotations as active (default True)
            scan_root: Restrict backfill to files under this path (empty = all)
            force: Re-tag files that already have tags (default False)
        """
        if not model_id or not model_id.strip():
            return "Error: model_id must not be empty"
        body = {
            "model_id": model_id.strip(),
            "thresholds": {
                "general": general_threshold,
                "character": character_threshold,
            },
            "batch_size": batch_size,
            "limit": limit,
            "set_active": set_active,
            "scan_root": scan_root,
            "force": force,
        }
        return as_json(client.post("/api/wd-tagger/retag/backfill", body))

    @mcp.tool()
    def wd_tagger_retag_query(
        model_id: str,
        query_params: dict,
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        batch_size: int = 8,
        limit: int = 0,
        set_active: bool = True,
    ) -> str:
        """Start an async retag job for files matching a search query.

        Args:
            model_id: WD-Tagger model ID to use
            query_params: Search query parameters (same shape as /api/search body)
            general_threshold: Confidence threshold for general tags (default 0.35)
            character_threshold: Confidence threshold for character tags (default 0.85)
            batch_size: Inference batch size, 1-64 (default 8)
            limit: Max files to process, 0 = no limit (default 0)
            set_active: Set new annotations as active (default True)
        """
        if not model_id or not model_id.strip():
            return "Error: model_id must not be empty"
        if not isinstance(query_params, dict):
            return "Error: query_params must be an object"
        body = {
            "model_id": model_id.strip(),
            "query_params": query_params,
            "thresholds": {
                "general": general_threshold,
                "character": character_threshold,
            },
            "batch_size": batch_size,
            "limit": limit,
            "set_active": set_active,
        }
        return as_json(client.post("/api/wd-tagger/retag/query", body))

    @mcp.tool()
    def wd_tagger_retag_cancel() -> str:
        """Cancel the currently running WD-Tagger retag job."""
        return as_json(client.post("/api/wd-tagger/retag/cancel", {}))

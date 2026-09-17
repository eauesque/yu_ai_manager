"""MCP tools for archive cleanup (duplicate archive detection and removal)."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_archive_cleanup_tools(mcp: FastMCP, client: YuManagerClient):
    """Register archive cleanup tools on the MCP server."""

    @mcp.tool()
    def archive_cleanup_scan(path: str = "") -> str:
        """Scan for archive pairs (ZIP/RAR files with matching extracted folders).

        Args:
            path: Directory path to scan. Empty string scans all scan roots.
        """
        body = {"path": path.strip() if path else ""}
        return _json(client.post("/api/tools/archive-cleanup/scan", body))

    @mcp.tool()
    def archive_cleanup_execute(actions: list, expected_count: int = 0) -> str:
        """Execute cleanup actions on archive pairs.

        Each action specifies what to do: "delete_archive" (remove the archive file),
        "delete_folder" (remove the extracted folder), or "skip" (no action).

        Args:
            actions: List of action objects. Example:
                     [{"action": "delete_archive", "archive_path": "/path/to/file.zip"},
                      {"action": "delete_folder", "folder_path": "/path/to/folder"}]
                     Max 500 actions.
            expected_count: Number of actions you intended to send (truncation guard)
        """
        from .validators import validate_batch_size
        err = validate_batch_size(actions, expected_count)
        if err:
            return err
        return _json(client.post("/api/tools/archive-cleanup/execute", {
            "actions": actions,
        }))

    @mcp.tool()
    def archive_cleanup_llm_verify(file_path: str, action: str) -> str:
        """Verify a single archive cleanup action with LLM.
        Args:
            file_path: Path to the archive file
            action: Proposed action (delete/keep/extract)
        """
        return _json(client.post("/api/tools/archive-cleanup/llm-verify", {"file_path": file_path, "action": action}))

    @mcp.tool()
    def archive_cleanup_llm_verify_batch(items: list) -> str:
        """Verify multiple archive cleanup actions with LLM.
        Args:
            items: List of {file_path, action} objects
        """
        return _json(client.post("/api/tools/archive-cleanup/llm-verify-batch", {"items": items}))

    @mcp.tool()
    def archive_cleanup_get_llm_config() -> str:
        """Get LLM configuration for archive cleanup verification."""
        return _json(client.get("/api/tools/archive-cleanup/llm-config"))

    @mcp.tool()
    def archive_cleanup_save_llm_config(config: dict) -> str:
        """Save LLM configuration for archive cleanup verification.
        Args:
            config: LLM config dict
        """
        return _json(client.post("/api/tools/archive-cleanup/llm-config", config))

    @mcp.tool()
    def archive_cleanup_list_models() -> str:
        """List available LLM models for archive cleanup verification."""
        return _json(client.post("/api/tools/archive-cleanup/list-models", {}))

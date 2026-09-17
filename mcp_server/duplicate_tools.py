"""MCP tools for duplicate file detection and management."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import validate_duplicate_method, validate_hash_type


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_duplicate_tools(mcp: FastMCP, client: YuManagerClient):
    """Register duplicate detection tools on the MCP server."""

    @mcp.tool()
    def find_duplicates(method: str = "hash") -> str:
        """Find duplicate files in the library.

        Args:
            method: Detection method - "hash" (exact MD5 match), "phash" (visual similarity via pHash), or "size" (same file size)
        """
        err = validate_duplicate_method(method)
        if err:
            return err
        return _json(client.get("/api/tools/find-duplicates", {
            "method": method,
        }))

    @mcp.tool()
    def compute_hashes(hash_type: str = "both") -> str:
        """Start a background job to compute file hashes for duplicate detection.

        Args:
            hash_type: Hash type to compute - "md5", "phash", or "both" (default "both")
        """
        err = validate_hash_type(hash_type)
        if err:
            return err
        return _json(client.post("/api/tools/compute-hashes", {
            "type": hash_type,
        }))

    @mcp.tool()
    def delete_duplicates(groups: list, mode: str = "soft") -> str:
        """Delete duplicate files. Each group keeps the first file and deletes the rest.

        Args:
            groups: List of duplicate groups. Each group has a "files" array of file paths.
                    The first path in each group is kept, the rest are deleted.
                    Example: [{"files": ["/keep/this.png", "/delete/this.png"]}]
            mode: "soft" (mark as deleted in DB) or "hard" (also delete from filesystem)
        """
        if not isinstance(groups, list) or len(groups) == 0:
            return _json({"ok": False, "error": "groups array required (non-empty)"})
        return _json(client.post("/api/tools/delete-duplicates", {
            "groups": groups,
            "mode": mode,
        }))

"""MCP tools for CLIP semantic image search."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_semantic_tools(mcp: FastMCP, client: YuManagerClient):
    """Register semantic search tools on the MCP server."""

    @mcp.tool()
    def semantic_search(
        query: str,
        limit: int = 50,
        threshold: float = 0.2,
        format: str = "",
        date_from: str = "",
        date_to: str = "",
        path: str = "",
        favorites: bool | None = None,
        width_min: int = 0,
        width_max: int = 0,
        height_min: int = 0,
        height_max: int = 0,
    ) -> str:
        """Search images by natural language text using CLIP semantic similarity.

        Args:
            query: Natural language search text (e.g. "a cat sitting on a chair")
            limit: Maximum number of results (1-200, default 50)
            threshold: Minimum cosine similarity score (0.0-1.0, default 0.2)
            format: File format filter (e.g. "image", "video", or "" for all)
            date_from: Date range start in YYYY-MM-DD format (e.g. "2024-01-01")
            date_to: Date range end in YYYY-MM-DD format (e.g. "2024-12-31")
            path: Path substring filter (e.g. "/photos/vacation")
            favorites: If True, return only favorited files; None means no filter
            width_min: Minimum image width in pixels (0 = no limit)
            width_max: Maximum image width in pixels (0 = no limit)
            height_min: Minimum image height in pixels (0 = no limit)
            height_max: Maximum image height in pixels (0 = no limit)
        """
        if not query or not query.strip():
            return _json({"error": "query must not be empty"})
        if len(query) > 500:
            return _json({"error": "query too long (max 500 chars)"})
        limit = max(1, min(limit, 200))
        threshold = max(0.0, min(threshold, 1.0))
        params: dict[str, str] = {
            "q": query,
            "limit": str(limit),
            "threshold": str(threshold),
        }
        if format:
            params["format"] = format
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        if path:
            params["in_path"] = path
        if favorites is True:
            params["fav_only"] = "true"
        if width_min > 0:
            params["min_width"] = str(width_min)
        if width_max > 0:
            params["max_width"] = str(width_max)
        if height_min > 0:
            params["min_height"] = str(height_min)
        if height_max > 0:
            params["max_height"] = str(height_max)
        result = client.get(
            "/ext/hailo-semantic/api/search",
            params,
        )
        return _json(result)

    @mcp.tool()
    def semantic_index_start(batch_size: int = 32, backend: str = "auto") -> str:
        """Start building the CLIP semantic search index.

        Processes all unindexed images through the CLIP encoder in batches.

        Args:
            batch_size: Images per batch (1-128, default 32)
            backend: Encoder backend: "auto", "hailo", "coreml", or "onnx"
        """
        batch_size = max(1, min(batch_size, 128))
        result = client.post(
            "/ext/hailo-semantic/api/index/start",
            {"batch_size": batch_size, "backend": backend},
        )
        return _json(result)

    @mcp.tool()
    def semantic_index_status() -> str:
        """Check semantic search index progress and statistics."""
        return _json(client.get("/ext/hailo-semantic/api/index/status"))

    @mcp.tool()
    def semantic_index_stop() -> str:
        """Stop the currently running semantic indexing job."""
        return _json(client.post("/ext/hailo-semantic/api/index/stop", {}))

    @mcp.tool()
    def semantic_backend_info() -> str:
        """Get information about available CLIP encoder backends.

        Returns available backends (Hailo, ONNX), their status,
        and ONNX model download status.
        """
        return _json(client.get("/ext/hailo-semantic/api/backends"))

    @mcp.tool()
    def semantic_status() -> str:
        """Get semantic search extension runtime state."""
        return _json(client.get("/ext/hailo-semantic/api/runtime"))

    @mcp.tool()
    def semantic_index_clear() -> str:
        """Clear all semantic search indexes."""
        return _json(client.post("/ext/hailo-semantic/api/index/clear", {}))

    @mcp.tool()
    def semantic_model_status() -> str:
        """Get CLIP model download/load status."""
        return _json(client.get("/ext/hailo-semantic/api/model/status"))

    @mcp.tool()
    def semantic_model_download() -> str:
        """Download the CLIP model for semantic search."""
        return _json(client.post("/ext/hailo-semantic/api/model/download", {}))

    @mcp.tool()
    def semantic_caption_start(batch_size: int = 50) -> str:
        """Start batch captioning for semantic search indexing.
        Args:
            batch_size: Number of images per batch (default 50)
        """
        return _json(client.post("/ext/hailo-semantic/api/caption/start", {"batch_size": batch_size}))

    @mcp.tool()
    def semantic_caption_status() -> str:
        """Get captioning progress."""
        return _json(client.get("/ext/hailo-semantic/api/caption/status"))

    @mcp.tool()
    def semantic_caption_stop() -> str:
        """Stop running captioning."""
        return _json(client.post("/ext/hailo-semantic/api/caption/stop", {}))

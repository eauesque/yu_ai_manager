"""VLM and XMP tools for WD-Tagger."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .wd_tagger_tools_common import as_json


def register_wd_tagger_vlm_tools(mcp: FastMCP, client: YuManagerClient):
    """Register WD-Tagger VLM helper tools."""

    @mcp.tool()
    def wd_tagger_vlm_test(url: str) -> str:
        """Test connection to a VLM server (OpenAI-compatible API).

        Args:
            url: Base URL of the VLM server (e.g. http://localhost:11434)
        """
        if not url or not url.strip():
            return as_json({"error": "url is required"})
        return as_json(client.get("/api/wd-tagger/vlm/test", {"url": url.strip()}))

    @mcp.tool()
    def wd_tagger_vlm_models(url: str) -> str:
        """List available models on a VLM server (OpenAI-compatible API).

        Args:
            url: Base URL of the VLM server (e.g. http://localhost:11434)
        """
        if not url or not url.strip():
            return as_json({"error": "url is required"})
        return as_json(client.get("/api/wd-tagger/vlm/models", {"url": url.strip()}))

    @mcp.tool()
    def wd_tagger_get_xmp(file_id: int) -> str:
        """Get WD-Tagger XMP metadata for a file.
        Args:
            file_id: File ID
        """
        return as_json(client.get(f"/api/wd-tagger/xmp/{file_id}"))

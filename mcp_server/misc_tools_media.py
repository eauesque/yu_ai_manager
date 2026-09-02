"""Media-related misc tools."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .misc_tools_common import as_json


def register_misc_media_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def convert_image(file_id: int, format: str = "webp") -> str:
        """Convert an image to another format. Args: file_id: target file ID, format: target format (e.g. 'webp', 'png')"""
        return as_json(client.post("/api/convert", {"file_id": file_id, "format": format}))

    @mcp.tool()
    def get_video_analysis_config() -> str:
        """Get video analysis configuration."""
        return as_json(client.get("/api/video-analysis/config"))

    @mcp.tool()
    def save_video_analysis_config(config: dict) -> str:
        """Save video analysis configuration. Args: config: configuration dict"""
        return as_json(client.post("/api/video-analysis/config", config))

    @mcp.tool()
    def get_video_analysis_status() -> str:
        """Get video analysis status."""
        return as_json(client.get("/api/video-analysis/status"))

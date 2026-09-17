"""Video and audio analysis MCP tools."""

from mcp.server.fastmcp import FastMCP

from .analysis_tools_common import as_json
from .client import YuManagerClient
from .validators import validate_file_id


def register_analysis_media_tools(mcp: FastMCP, client: YuManagerClient):
    """Register video and audio analysis tools."""

    @mcp.tool()
    def analyze_video(file_id: int, engine: str = "", model: str = "", keyframe_count: int = 4) -> str:
        """Run multi-keyframe video analysis on a video file."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {"keyframe_count": keyframe_count}
        if engine:
            body["engine"] = engine
        if model:
            body["model"] = model
        return as_json(client.post(f"/api/video-analysis/analyze/{file_id}", body))

    @mcp.tool()
    def transcribe_audio(file_id: int, engine: str = "", model: str = "", language: str = "") -> str:
        """Transcribe audio/video file using Whisper."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {}
        if engine:
            body["engine"] = engine
        if model:
            body["model"] = model
        if language:
            body["language"] = language
        return as_json(client.post(f"/api/audio-analysis/transcribe/{file_id}", body))

    @mcp.tool()
    def get_audio_analysis_status() -> str:
        """Check audio analysis availability."""
        return as_json(client.get("/api/audio-analysis/status"))

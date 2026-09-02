"""MCP tools for the Freeze & Pull-back Generator extension."""

import json
import re

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import validate_file_id

_PFX = "/ext/freeze-pullback"
_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+$")


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_freeze_pullback_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Freeze & Pull-back tools on the MCP server."""

    @mcp.tool()
    def generate_freeze_pullback(
        file_id: int,
        hold_seconds: float = 2.0,
        pull_seconds: float = 5.0,
        fps: int = 30,
        scale_start: float = 2.0,
        scale_end: float = 1.0,
        out_width: int = 0,
        out_height: int = 0,
        focus_start_x: float = 0.5,
        focus_start_y: float = 0.5,
        focus_end_x: float = -1.0,
        focus_end_y: float = -1.0,
        direction: str = "zoom_out",
        output_format: str = "mp4",
        easing: str = "ease_in_out_cubic",
        vignette: bool = False,
        waypoints: str = "",
    ) -> str:
        """Generate a Freeze & Pull-back (Ken Burns) video from a static image.

        Creates a video that holds on a focus point then zooms out or in with panning.
        Supports multi-point camera path via waypoints parameter.

        Args:
            file_id: Source image file ID from the database
            hold_seconds: Duration of the initial freeze/hold phase (1.0-10.0). Ignored if waypoints is set
            pull_seconds: Duration of the zoom phase (1.0-20.0). Ignored if waypoints is set
            fps: Frames per second (15-60)
            scale_start: Initial zoom level (1.0-5.0). Ignored if waypoints is set
            scale_end: Final zoom level (1.0-5.0). Ignored if waypoints is set
            out_width: Output video width in pixels (256-3840). 0 = use source image resolution
            out_height: Output video height in pixels (256-2160). 0 = use source image resolution
            focus_start_x: Focus start X coordinate, normalized 0.0-1.0. Ignored if waypoints is set
            focus_start_y: Focus start Y coordinate, normalized 0.0-1.0. Ignored if waypoints is set
            focus_end_x: Focus end X coordinate (-1 = same as start). Ignored if waypoints is set
            focus_end_y: Focus end Y coordinate (-1 = same as start). Ignored if waypoints is set
            direction: Zoom direction - "zoom_out" or "zoom_in". Ignored if waypoints is set
            output_format: Output format - "mp4", "gif", "apng", "webp", or "webm"
            easing: Easing function name. Ignored if waypoints is set
            vignette: Apply vignette effect
            waypoints: JSON string of waypoint array. Each waypoint: {"x": 0.5, "y": 0.5, "scale": 2.0, "dwell": 1.5, "transition": 2.0, "easing": "ease_in_out_cubic"}. Minimum 2 waypoints required. When set, hold/pull/scale/focus/direction params are ignored
        """
        err = validate_file_id(file_id)
        if err:
            return err

        body = {
            "file_id": file_id,
            "fps": fps,
            "out_width": out_width,
            "out_height": out_height,
            "output_format": output_format,
            "vignette": vignette,
        }

        # Waypoint mode
        if waypoints:
            try:
                wp_list = json.loads(waypoints)
                if isinstance(wp_list, list) and len(wp_list) >= 2:
                    body["waypoints"] = wp_list
            except (json.JSONDecodeError, TypeError):
                return json.dumps({"error": "Invalid waypoints JSON string"})

        # Legacy mode (when waypoints not specified)
        if "waypoints" not in body:
            body["hold_seconds"] = hold_seconds
            body["pull_seconds"] = pull_seconds
            body["scale_start"] = scale_start
            body["scale_end"] = scale_end
            body["direction"] = direction
            body["easing"] = easing
            body["focus_start"] = [focus_start_x, focus_start_y]
            if focus_end_x >= 0 and focus_end_y >= 0:
                body["focus_end"] = [focus_end_x, focus_end_y]

        return _json(client.post(f"{_PFX}/api/generate", body))

    @mcp.tool()
    def get_fpb_status() -> str:
        """Get the current status of the Freeze & Pull-back render job.

        Returns job progress including phase, percent complete, and any errors.
        """
        return _json(client.get(f"{_PFX}/api/status"))

    @mcp.tool()
    def fpb_check() -> str:
        """Check Freeze & Pull-back prerequisites (ffmpeg etc.)."""
        return _json(client.get(f"{_PFX}/api/check"))

    @mcp.tool()
    def fpb_cancel() -> str:
        """Cancel running Freeze & Pull-back generation."""
        return _json(client.post(f"{_PFX}/api/cancel", {}))

    @mcp.tool()
    def fpb_list_outputs() -> str:
        """List generated Freeze & Pull-back output files."""
        return _json(client.get(f"{_PFX}/api/outputs"))

    @mcp.tool()
    def fpb_delete_output(filename: str) -> str:
        """Delete a Freeze & Pull-back output file.
        Args:
            filename: Output filename to delete (e.g., "fpb_123_1234567890.mp4")
        """
        if not _SAFE_FILENAME.match(filename):
            return _json({"error": "Invalid filename format"})
        return _json(client.delete(f"{_PFX}/api/outputs/{filename}"))

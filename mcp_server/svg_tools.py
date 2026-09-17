"""MCP tools for SVG rasterization."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_svg_tools(mcp: FastMCP, client: YuManagerClient):

    @mcp.tool()
    def svg_info() -> str:
        """Check SVG rasterization availability and backend info."""
        return _json(client.get("/api/svg/info"))

    @mcp.tool()
    def svg_rasterize(
        file_id: int = 0,
        svg_path: str = "",
        svg_data: str = "",
        width: int = 1024,
        height: int = 1024,
        format: str = "png",
        background: str = "",
    ) -> str:
        """Rasterize an SVG file to PNG/WebP bitmap.

        Use file_id to rasterize an SVG from the database,
        svg_path for a filesystem path, or svg_data for inline SVG XML.
        The returned base64 can be used directly as img2img input
        for nai_generate() or sd_generate().

        Args:
            file_id: Database file ID (SVG file)
            svg_path: Filesystem path to SVG file
            svg_data: Raw SVG XML string
            width: Target width in pixels (default 1024)
            height: Target height in pixels (default 1024)
            format: Output format "png" or "webp" (default "png")
            background: Background colour hex e.g. "#ffffff" (default transparent)
        """
        body = {"width": width, "height": height, "format": format}
        if file_id > 0:
            body["file_id"] = file_id
        elif svg_path:
            body["svg_path"] = svg_path
        elif svg_data:
            body["svg_data"] = svg_data
        if background:
            body["background"] = background
        return _json(client.post("/api/svg/rasterize", body))

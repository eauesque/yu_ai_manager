"""MCP tools for YOLO stream management: sources, rules, status."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_yolo_stream_tools(mcp: FastMCP, client: YuManagerClient):
    """Register YOLO stream management tools on the MCP server."""

    # -- Source listing / management ----------------------------------------

    @mcp.tool()
    def yolo_stream_sources() -> str:
        """List all YOLO stream sources and their current status.

        Returns source id, url, name, state (idle/active/error),
        resolution, and frame count for each registered source.
        """
        return _json(client.get("/ext/hailo-yolo/api/stream/sources"))

    @mcp.tool()
    def yolo_stream_start(source_id: str) -> str:
        """Start capturing and detecting on a stream source.

        Args:
            source_id: The stream source ID to start
        """
        if not source_id or not source_id.strip():
            return _json({"error": "source_id is required"})
        return _json(client.post(f"/ext/hailo-yolo/api/stream/sources/{source_id}/start", {}))

    @mcp.tool()
    def yolo_stream_stop(source_id: str) -> str:
        """Stop capturing on a stream source.

        Args:
            source_id: The stream source ID to stop
        """
        if not source_id or not source_id.strip():
            return _json({"error": "source_id is required"})
        return _json(client.post(f"/ext/hailo-yolo/api/stream/sources/{source_id}/stop", {}))

    @mcp.tool()
    def yolo_stream_add_source(id: str, url: str, name: str = "") -> str:
        """Add a new stream source (USB camera index, RTSP URL, or HTTP stream).

        Args:
            id: Unique identifier for the source (e.g. "cam1")
            url: Source URL or device index ("0" for USB, "rtsp://..." for RTSP)
            name: Human-readable display name (optional)
        """
        if not id or not id.strip():
            return _json({"error": "id is required"})
        if not url or not url.strip():
            return _json({"error": "url is required"})
        return _json(client.post("/ext/hailo-yolo/api/stream/sources", {
            "id": id.strip(),
            "url": url.strip(),
            "name": name.strip() if name else "",
        }))

    # -- Detection rules ----------------------------------------------------

    @mcp.tool()
    def yolo_stream_rules() -> str:
        """List all YOLO stream detection rules.

        Each rule specifies target classes, confidence threshold,
        cooldown period, and actions to execute on match.
        """
        return _json(client.get("/ext/hailo-yolo/api/stream/rules"))

    @mcp.tool()
    def yolo_stream_add_rule(
        id: str,
        name: str,
        classes: list,
        min_confidence: float = 0.5,
        cooldown_sec: int = 30,
        actions: list | None = None,
    ) -> str:
        """Add a detection rule that triggers actions when objects are detected.

        Args:
            id: Unique rule identifier (e.g. "person-alert")
            name: Human-readable rule name
            classes: COCO class names to detect (e.g. ["person", "car"])
            min_confidence: Minimum confidence threshold (0.0-1.0, default 0.5)
            cooldown_sec: Seconds between repeated triggers (default 30)
            actions: List of action dicts, e.g. [{"type": "snapshot"}, {"type": "record", "duration": 10}]
        """
        if not id or not id.strip():
            return _json({"error": "id is required"})
        if not classes:
            return _json({"error": "classes list is required"})
        payload = {
            "id": id.strip(),
            "name": name.strip() if name else id.strip(),
            "classes": classes,
            "min_confidence": min_confidence,
            "cooldown_sec": cooldown_sec,
        }
        if actions:
            payload["actions"] = actions
        return _json(client.post("/ext/hailo-yolo/api/stream/rules", payload))

    # -- Overall status -----------------------------------------------------

    @mcp.tool()
    def yolo_stream_status() -> str:
        """Get overall YOLO stream system status.

        Returns pipeline info (backend, model, running state),
        all sources with viewer counts, rules count, and recorder status.
        """
        return _json(client.get("/ext/hailo-yolo/api/stream/status"))

"""MCP tools for Hailo YOLO object detection."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def register_yolo_detect_tools(mcp: FastMCP, client):
    """Register Hailo YOLO detection MCP tools."""

    @mcp.tool()
    def yolo_status() -> str:
        """Get Hailo YOLO extension runtime state."""
        return _json(client.get("/ext/hailo-yolo/api/runtime"))

    @mcp.tool()
    def yolo_detect_start(
        file_ids: list | None = None,
        undetected_only: bool = True,
        model: str = "",
        batch_size: int = 0,
        confidence_threshold: float = 0.0,
        video_frame_interval: float = 0.0,
        backend: str = "",
        distributed: bool = False,
        archive: bool = False,
        media_filter: str = "",
    ) -> str:
        """Start YOLO object detection on images.

        Args:
            file_ids: List of file IDs to detect (None = all)
            undetected_only: Only process files without existing results (default True)
            model: Model name override (e.g. "yolov8n"). Empty = use extension config.
            batch_size: Inference batch size override (0 = use extension config)
            confidence_threshold: Detection confidence threshold override
                (0.0 = use extension config, e.g. 0.25)
            video_frame_interval: Seconds between sampled video frames override
                (0.0 = use extension config, e.g. 2.0)
            backend: Backend preference override: "auto", "hailo", "cpu", etc.
                Empty = use extension config.
            distributed: Enable distributed inference across LAN peers (default False)
            archive: Run detection on archive-mode scope (default False)
            media_filter: Filter media type: "all", "image", "video", etc.
                Empty = use extension config default.
        """
        body: dict = {"undetected_only": undetected_only}
        if file_ids is not None:
            body["file_ids"] = file_ids
        if model:
            body["model"] = model
        if batch_size > 0:
            body["batch_size"] = batch_size
        if confidence_threshold > 0.0:
            body["confidence_threshold"] = confidence_threshold
        if video_frame_interval > 0.0:
            body["video_frame_interval"] = video_frame_interval
        if backend:
            body["backend"] = backend
        if distributed:
            body["distributed"] = distributed
        if archive:
            body["archive"] = archive
        if media_filter:
            body["media_filter"] = media_filter
        return _json(client.post("/ext/hailo-yolo/api/detect/start", body))

    @mcp.tool()
    def yolo_detect_status() -> str:
        """Get current YOLO detection job progress."""
        return _json(client.get("/ext/hailo-yolo/api/detect/status"))

    @mcp.tool()
    def yolo_detect_stop() -> str:
        """Stop the running YOLO detection job."""
        return _json(client.post("/ext/hailo-yolo/api/detect/stop", {}))

    @mcp.tool()
    def yolo_get_results(file_id: int) -> str:
        """Get YOLO detection results for a specific file.

        Args:
            file_id: The file ID to get detection results for
        """
        return _json(client.get(f"/ext/hailo-yolo/api/detect/results/{file_id}"))

    @mcp.tool()
    def yolo_search(
        class_name: str = "",
        min_confidence: float = 0.0,
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """Search images by detected object class name.

        Args:
            class_name: COCO class name to search for (e.g. "person", "cat")
            min_confidence: Minimum confidence threshold (0.0-1.0)
            limit: Maximum number of results (default 50)
            offset: Result offset for pagination
        """
        params = {}
        if class_name:
            params["class_name"] = class_name
        if min_confidence > 0:
            params["min_confidence"] = str(min_confidence)
        if limit != 50:
            params["limit"] = str(limit)
        if offset > 0:
            params["offset"] = str(offset)
        return _json(client.get("/ext/hailo-yolo/api/detect/search", params or None))

    @mcp.tool()
    def yolo_clear_results(file_ids: list | None = None) -> str:
        """Clear YOLO detection results.

        Args:
            file_ids: List of file IDs to clear (None = clear all)
        """
        body = {}
        if file_ids is not None:
            body["file_ids"] = file_ids
        return _json(client.post("/ext/hailo-yolo/api/detect/clear", body))

    @mcp.tool()
    def yolo_model_status() -> str:
        """Get YOLO model download/load status."""
        return _json(client.get("/ext/hailo-yolo/api/model/status"))

    @mcp.tool()
    def yolo_model_download() -> str:
        """Download the YOLO HEF model file for Hailo-10H."""
        return _json(client.post("/ext/hailo-yolo/api/model/download", {}))

    @mcp.tool()
    def yolo_list_labels() -> str:
        """List all detected object labels in the database."""
        return _json(client.get("/ext/hailo-yolo/api/labels"))

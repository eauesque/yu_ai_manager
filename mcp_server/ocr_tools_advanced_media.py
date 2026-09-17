"""Media, overlay, and PDF OCR tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .ocr_job_client import OcrJobError, run_ocr_job
from .ocr_tools_common import as_json
from .validators import validate_batch_size, validate_file_id


def register_ocr_advanced_media_tools(mcp: FastMCP, client: YuManagerClient):
    """Register advanced OCR media and export tools."""

    @mcp.tool()
    def ocr_overlay(file_id: int, mode: str = "translated", target_lang: str = "", format: str = "png") -> str:
        """Generate an image with OCR/translation text overlaid on detected regions."""
        err = validate_file_id(file_id)
        if err:
            return err
        params = {"mode": mode, "format": format}
        if target_lang:
            params["target_lang"] = target_lang
        base = client.base_url.rstrip("/")
        url = f"{base}/api/ocr/overlay/{file_id}?" + "&".join(f"{k}={v}" for k, v in params.items())
        return f"Overlay image URL: {url}\nUse HTTP GET to download the image."

    @mcp.tool()
    def ocr_export_batch(
        file_ids: list,
        format: str = "",
        output_dir: str = "",
        overlay_mode: str = "translated",
        target_lang: str = "",
        include_translation: bool = False,
        expected_count: int = 0,
    ) -> str:
        """Batch export OCR results to files or ZIP download."""
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        body = {"file_ids": file_ids, "overlay_mode": overlay_mode}
        if format:
            body["format"] = format
        if output_dir:
            body["output_dir"] = output_dir
        if target_lang:
            body["target_lang"] = target_lang
        if include_translation:
            body["include_translation"] = True
        return as_json(client.post("/api/ocr/export/batch", body))

    @mcp.tool()
    def ocr_video(file_id: int, task: str = "ocr", language: str = "auto", server_id: str = "", keyframe_count: int = 4, strategy: str = "uniform") -> str:
        """Run OCR on a video file by extracting keyframes."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {"task": task, "language": language, "keyframe_count": keyframe_count, "strategy": strategy}
        if server_id:
            body["server_id"] = server_id
        try:
            job = run_ocr_job(client, f"/api/ocr/video/{file_id}", body)
        except OcrJobError as exc:
            return f"Error: {exc}"
        return as_json(job.get("result", {}))

    @mcp.tool()
    def ocr_pdf(file_id: int, task: str = "ocr_document", language: str = "auto", server_id: str = "", page_range: str = "", dpi: int = 200) -> str:
        """Run OCR on a PDF file."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {"task": task, "language": language, "dpi": max(72, min(dpi, 400))}
        if server_id:
            body["server_id"] = server_id
        if page_range:
            body["page_range"] = page_range
        try:
            job = run_ocr_job(client, f"/api/ocr/pdf/{file_id}", body)
        except OcrJobError as exc:
            return f"Error: {exc}"
        return as_json(job.get("result", {}))

    @mcp.tool()
    def ocr_bbox(file_id: int, task: str = "", server_id: str = "") -> str:
        """Run bounding-box detection on an OCR result."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {}
        if task:
            body["task"] = task
        if server_id:
            body["server_id"] = server_id
        return as_json(client.post(f"/api/ocr/bbox/{file_id}", body))

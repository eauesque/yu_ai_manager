"""OCR extraction and result retrieval tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .ocr_job_client import OcrJobError, run_ocr_job
from .ocr_tools_common import as_json
from .validators import validate_batch_size, validate_file_id


def register_ocr_core_extract_tools(mcp: FastMCP, client: YuManagerClient):
    """Register OCR extraction tools."""

    @mcp.tool()
    def ocr_extract(file_id: int, task: str = "ocr", language: str = "auto", server_id: str = "") -> str:
        """Run OCR on a single image file to extract text."""
        err = validate_file_id(file_id)
        if err:
            return err
        if task not in ("ocr", "ocr_document", "ocr_manga"):
            return f"Error: invalid task '{task}'. Must be ocr, ocr_document, or ocr_manga"
        body = {"task": task, "language": language}
        if server_id:
            body["server_id"] = server_id
        # 202 + poll: the route runs OCR as a job. The job result carries no
        # recognised text (/api/jobs/{id} has no authorization), so read it
        # from the admin-gated result endpoint afterwards.
        try:
            run_ocr_job(client, f"/api/ocr/{file_id}", body)
        except OcrJobError as exc:
            return f"Error: {exc}"
        return as_json(client.get(f"/api/ocr/result/{file_id}", {"task": task}))

    @mcp.tool()
    def ocr_batch(file_ids: list, task: str = "ocr", language: str = "auto", server_id: str = "", expected_count: int = 0) -> str:
        """Run OCR on multiple image files."""
        err = validate_batch_size(file_ids, expected_count)
        if err:
            return err
        body = {"file_ids": file_ids, "task": task, "language": language}
        if server_id:
            body["server_id"] = server_id
        try:
            job = run_ocr_job(client, "/api/ocr/batch", body)
        except OcrJobError as exc:
            return f"Error: {exc}"
        return as_json(job.get("result", {}))

    @mcp.tool()
    def ocr_get_result(file_id: int, task: str = "", engine: str = "", all_results: bool = False) -> str:
        """Get OCR result for a file."""
        err = validate_file_id(file_id)
        if err:
            return err
        params = {}
        if task:
            params["task"] = task
        if engine:
            params["engine"] = engine
        if all_results:
            params["all"] = "true"
        return as_json(client.get(f"/api/ocr/result/{file_id}", params))

    @mcp.tool()
    def ocr_delete(file_id: int, task: str = "", engine: str = "") -> str:
        """Delete OCR result for a file."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {}
        if task:
            body["task"] = task
        if engine:
            body["engine"] = engine
        return as_json(client.delete(f"/api/ocr/result/{file_id}", body))

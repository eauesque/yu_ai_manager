"""OCR export and translation tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .ocr_tools_common import as_json
from .validators import validate_file_id


def _format_markdown(data: dict) -> str:
    regions = data.get("regions", [])
    full_text = data.get("full_text", "")
    ocr_task = data.get("task", "ocr")
    lines = []
    if ocr_task == "ocr_document":
        for region in regions:
            label = region.get("label", "")
            text = region.get("text", "")
            if label == "heading":
                lines.append(f"## {text}\n")
            else:
                lines.append(text)
                lines.append("")
        for table in data.get("tables", []):
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            if headers:
                lines.append("| " + " | ".join(str(h) for h in headers) + " |")
                lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
            lines.append("")
    elif ocr_task == "ocr_manga":
        for region in regions:
            label = region.get("label", "")
            text = region.get("text", "")
            lines.append(f"[{label}] {text}" if label else text)
    else:
        for region in regions:
            lines.append(region.get("text", ""))
    if not lines:
        lines.append(full_text)
    return "\n".join(lines)


def register_ocr_core_output_tools(mcp: FastMCP, client: YuManagerClient):
    """Register OCR export and translation tools."""

    @mcp.tool()
    def ocr_export(file_id: int, format: str = "md", task: str = "") -> str:
        """Export OCR result in the specified format."""
        err = validate_file_id(file_id)
        if err:
            return err
        if format not in ("txt", "md", "json"):
            return "Error: MCP supports txt/md/json. For PDF use HTTP API."
        params = {}
        if task:
            params["task"] = task
        result = client.get(f"/api/ocr/result/{file_id}", params)
        if not result.get("ok", True) or result.get("error"):
            return as_json(result)
        if format == "json":
            return as_json(result)
        data = result.get("data", result)
        if format == "txt":
            return data.get("full_text", "") or "(no text)"
        return _format_markdown(data)

    @mcp.tool()
    def ocr_translate(file_id: int, target_lang: str = "en", server_id: str = "", task: str = "") -> str:
        """Translate OCR result for a file using LLM."""
        err = validate_file_id(file_id)
        if err:
            return err
        body = {"target_lang": target_lang}
        if server_id:
            body["server_id"] = server_id
        if task:
            body["task"] = task
        return as_json(client.post(f"/api/ocr/translate/{file_id}", body))

    @mcp.tool()
    def ocr_get_translations(file_id: int, target_lang: str = "") -> str:
        """Get translation results for a file."""
        err = validate_file_id(file_id)
        if err:
            return err
        params = {}
        if target_lang:
            params["target_lang"] = target_lang
        return as_json(client.get(f"/api/ocr/translations/{file_id}", params))

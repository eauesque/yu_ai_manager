"""MCP tools for diagnostics workflows."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.diagnostics.doctor import PROJECT_ROOT, run_all_checks
from core.diagnostics.doctor_report import render_json, render_markdown, write_report_files
from core.repair.update_package import rollback_latest_update, verify_update_package


def register_diagnostics_tools(mcp: FastMCP, client) -> None:
    @mcp.tool()
    def diagnostics_doctor() -> dict:
        """Run local environment diagnosis and write reports/doctor_*.{md,json}."""
        results = run_all_checks(project_root=PROJECT_ROOT)
        report_md = render_markdown(results)
        report_json = render_json(results)
        md_path, json_path = write_report_files(PROJECT_ROOT / "reports", report_md, report_json)
        return {
            "ok": report_json["summary"]["errors"] == 0,
            "summary": report_json["summary"],
            "report_md": report_md,
            "report_json": report_json,
            "report_md_path": str(md_path),
            "report_json_path": str(json_path),
        }

    @mcp.tool()
    def update_verify(zip_path: str) -> dict:
        """Verify a signed update.zip package. This does not apply changes."""
        result = verify_update_package(
            Path(zip_path),
            project_root=PROJECT_ROOT,
            current_version=_current_version(),
            current_schema_version=_current_schema_version(),
        )
        return {
            "ok": True,
            "manifest": result.manifest,
            "file_operations": result.file_operations,
            "patch_operations": result.patch_operations,
        }

    @mcp.tool()
    def update_rollback() -> dict:
        """Restore files from the latest update backup."""
        result = rollback_latest_update(project_root=PROJECT_ROOT)
        return {"ok": True, "backup_dir": str(result.backup_dir), "restored": result.restored}


def _current_version() -> str:
    try:
        return str(json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8")).get("version", "0.0.0"))
    except (OSError, json.JSONDecodeError):
        return "0.0.0"


def _current_schema_version() -> int:
    try:
        from core.search_api.server_info import get_meta_int, get_readonly_db

        return int(get_meta_int(get_readonly_db(), "schema_version", 0))
    except Exception:
        return 0

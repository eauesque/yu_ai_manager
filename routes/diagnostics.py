"""Diagnostics API routes."""

from __future__ import annotations

import asyncio
import platform
import subprocess
import uuid
from collections import OrderedDict
from pathlib import Path

from quart import Blueprint, request

from core.diagnostics.bug_report import create_bug_report, default_repair_root
from core.diagnostics.doctor import PROJECT_ROOT, cleanup_stale_update_pending, run_all_checks
from core.diagnostics.doctor_report import render_json, render_markdown, write_report_files
from core.diagnostics.zip_export import zip_repair_dir
from core.infra_core.api_errors import api_error, api_success
from core.system.safe_mode import SafeModeManager

bp = Blueprint("diagnostics", __name__)

_MAX_DOCTOR_JOBS = 10
_doctor_jobs: OrderedDict[str, dict] = OrderedDict()


def _register_job(job_id: str, value: dict) -> None:
    _doctor_jobs[job_id] = value
    while len(_doctor_jobs) > _MAX_DOCTOR_JOBS:
        _doctor_jobs.popitem(last=False)


async def _run_doctor_job(job_id: str) -> None:
    try:
        results = await asyncio.to_thread(run_all_checks, project_root=PROJECT_ROOT)
        report_md = await asyncio.to_thread(render_markdown, results)
        report_json = await asyncio.to_thread(render_json, results)
        md_path, json_path = await asyncio.to_thread(write_report_files, PROJECT_ROOT / "reports", report_md, report_json)
        _register_job(
            job_id,
            {
                "status": "done",
                "report_md": report_md,
                "report_json": report_json,
                "summary": report_json["summary"],
                "report_md_path": str(md_path),
                "report_json_path": str(json_path),
            },
        )
    except Exception as exc:
        _register_job(job_id, {"status": "error", "error": str(exc)})


def _resolve_repair_dir(value: str | None) -> Path:
    if not value:
        raise ValueError("repair_dir is required")
    path = Path(value).expanduser().resolve()
    return path


def _is_wsl() -> bool:
    try:
        text = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in text or "wsl" in text


def open_repair_folder(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        cmd = ["explorer", str(path)]
    elif _is_wsl():
        cmd = ["explorer.exe", str(path)]
    elif system == "Darwin":
        cmd = ["open", str(path)]
    else:
        cmd = ["xdg-open", str(path)]
    subprocess.Popen(cmd)  # noqa: S603


@bp.route("/api/diagnostics/bug-report", methods=["POST"])
async def api_bug_report():
    repair_dir = create_bug_report(default_repair_root())
    zip_path = zip_repair_dir(repair_dir)
    return api_success({"repair_dir": str(repair_dir), "zip_path": str(zip_path)})


@bp.route("/api/diagnostics/safe-mode", methods=["GET"])
async def api_safe_mode():
    manager = SafeModeManager()
    return api_success({"safe_mode": manager.is_active(), "marker_exists": manager.marker_exists()})


@bp.route("/api/diagnostics/doctor", methods=["POST"])
async def api_doctor():
    job_id = str(uuid.uuid4())
    _register_job(job_id, {"status": "running"})
    asyncio.ensure_future(_run_doctor_job(job_id))
    return api_success({"job_id": job_id, "status": "running"})


@bp.route("/api/diagnostics/doctor/<job_id>", methods=["GET"])
async def api_doctor_status(job_id: str):
    job = _doctor_jobs.get(job_id)
    if job is None:
        return api_error("Job not found", 404, code="job_not_found")
    return api_success(job)


@bp.route("/api/diagnostics/zip-repair", methods=["POST"])
async def api_zip_repair():
    payload = await request.get_json(silent=True) or {}
    try:
        repair_dir = _resolve_repair_dir(payload.get("repair_dir"))
        zip_path = zip_repair_dir(repair_dir)
    except Exception as exc:
        return api_error(str(exc), 400, code="zip_repair_failed")
    return api_success({"repair_dir": str(repair_dir), "zip_path": str(zip_path)})


@bp.route("/api/diagnostics/open-repair-folder", methods=["POST"])
async def api_open_repair_folder():
    payload = await request.get_json(silent=True) or {}
    try:
        repair_dir = _resolve_repair_dir(payload.get("repair_dir"))
        open_repair_folder(repair_dir)
    except Exception as exc:
        return api_error(str(exc), 400, code="open_repair_folder_failed")
    return api_success({"repair_dir": str(repair_dir)})


@bp.route("/api/diagnostics/cleanup-update-pending", methods=["POST"])
async def api_cleanup_update_pending():
    """Delete update_pending JSON entries older than 7 days."""
    deleted_count, deleted_names = await asyncio.to_thread(
        cleanup_stale_update_pending, PROJECT_ROOT
    )
    return api_success({"deleted": deleted_count, "names": deleted_names})

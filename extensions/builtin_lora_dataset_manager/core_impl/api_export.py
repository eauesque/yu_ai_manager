"""Dataset export API handlers."""

from __future__ import annotations

import threading

from quart import Blueprint, request

from core.event_bus import emit
from core.infra_core.api_errors import api_error, api_result

from . import store
from .export_writer import export_dataset

# Simple state tracker for export jobs
_export_state: dict = {"running": False, "result": None}


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register(bp: Blueprint) -> None:
    """Register export routes on the blueprint."""

    @bp.route("/projects/<int:pid>/export", methods=["POST"])
    async def start_export(pid: int):
        proj = store.get_project(pid)
        if not proj:
            return api_error("Project not found", 404)
        if not proj.file_ids:
            return api_error("No files in project", 400)

        from core.extensions_core.lifecycle.extensions_admin import (
            get_extension_config_value,
        )
        configured_base = get_extension_config_value(
            "builtin-lora-dataset-manager", "output_base_dir", ""
        )

        data = await request.get_json(silent=True) or {}
        output_dir = (data.get("output_dir") or "").strip()

        if not configured_base:
            # output_base_dir must be configured; reject arbitrary paths
            if output_dir:
                return api_error(
                    "output_base_dir must be configured before specifying output_dir",
                    400,
                )
            return api_error(
                "output_base_dir is required (set in extension settings)", 400,
            )

        if not output_dir:
            output_dir = configured_base

        # Validate output_dir is inside configured base to prevent
        # arbitrary filesystem writes
        import os
        try:
            real_out = os.path.realpath(output_dir)
            real_base = os.path.realpath(configured_base)
            if not (real_out == real_base
                    or real_out.startswith(real_base + os.sep)):
                return api_error(
                    "output_dir must be inside the configured output_base_dir",
                    403,
                )
        except (OSError, ValueError):
            return api_error("invalid output_dir path", 400)

        if _export_state["running"]:
            return api_error("Export already in progress", 429)

        _export_state["running"] = True
        _export_state["result"] = None

        def _worker():
            try:
                emit("lora_export.start", {
                    "project_id": pid, "file_count": len(proj.file_ids),
                })
                result = export_dataset(
                    project_id=pid,
                    project_name=proj.name,
                    concept=proj.concept,
                    repeat=proj.repeat,
                    base_model=proj.base_model,
                    tag_exclude=proj.tag_exclude,
                    file_ids=proj.file_ids,
                    output_base_dir=output_dir,
                    model_scope=proj.model_scope,
                )
                _export_state["result"] = {
                    "project_id": result.project_id,
                    "output_dir": result.output_dir,
                    "image_count": result.image_count,
                    "skipped_count": result.skipped_count,
                    "empty_caption_count": result.empty_caption_count,
                    "errors": result.errors[:50],
                }
                emit("lora_export.complete", _export_state["result"])
            except Exception as exc:
                _export_state["result"] = {"error": str(exc)}
                emit("lora_export.complete", {"error": str(exc)})
            finally:
                _export_state["running"] = False

        threading.Thread(target=_worker, daemon=True).start()

        return api_result({
            "accepted": True,
            "message": "Export started",
            "file_count": len(proj.file_ids),
        }, 202)

    @bp.route("/projects/<int:pid>/export/status", methods=["GET"])
    async def export_status(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        return api_result({
            "running": _export_state["running"],
            "result": _export_state["result"],
        }, 200)

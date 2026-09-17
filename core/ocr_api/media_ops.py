"""OCR API -- video OCR, PDF OCR, bbox detection, NPU status."""

from __future__ import annotations

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register(bp: Blueprint) -> None:
    """Register routes on the Blueprint."""


    # ── Video OCR ──

    @bp.route("/api/ocr/npu", methods=["GET"])
    async def api_ocr_npu():
        """Return NPU device status and recommended settings."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        task = request.args.get("task", "ocr")

        def _detect():
            from core.ocr_core.npu_offload import detect_npu, suggest_npu_optimization
            status = detect_npu()
            suggestions = suggest_npu_optimization(task)
            return {
                "npu": status.to_dict(),
                "optimization": suggestions,
            }

        return api_result(await run_db_sync(_detect))

    # ── PDF OCR ──

    @bp.route("/api/ocr/bbox/<int:file_id>", methods=["POST"])
    async def api_ocr_bbox(file_id: int):
        """Detect text bounding boxes (bbox) from OCR results.

        Runs a second pass on existing OCR results to add position information.
        """
        body = await request.get_json(silent=True) or {}
        task = body.get("task", "")
        server_id = body.get("server_id", "")

        from extensions.builtin_ocr.core_impl.route_services import run_bbox_detection

        payload, status = await run_db_sync(
            run_bbox_detection,
            file_id=file_id,
            task=task,
            server_id=server_id,
        )
        if status != 200:
            return api_error(payload.get("error", ""), status)
        return api_result(payload)

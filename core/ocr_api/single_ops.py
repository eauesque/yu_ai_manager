"""OCR API -- single OCR execution, result retrieval, deletion, engine listing."""

from __future__ import annotations

from quart import Blueprint, request

from core.infra_core.api_errors import api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register(bp: Blueprint) -> None:
    """Register routes on the Blueprint."""


    @bp.route("/api/ocr/result/<int:file_id>", methods=["GET"])
    async def api_ocr_result(file_id: int):
        """Get OCR result."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        task = request.args.get("task", "")
        engine = request.args.get("engine", "")
        all_results = request.args.get("all", "")

        from extensions.builtin_ocr.core_impl.route_services import get_ocr_result_service

        return api_result(
            await run_db_sync(
                get_ocr_result_service,
                file_id=file_id,
                task=task,
                engine=engine,
                all_results=all_results,
            )
        )

    @bp.route("/api/ocr/result/<int:file_id>", methods=["DELETE"])
    async def api_ocr_delete(file_id: int):
        """Delete OCR result."""
        body = await request.get_json(silent=True) or {}
        task = body.get("task", "")
        engine = body.get("engine", "")

        from extensions.builtin_ocr.core_impl.route_services import delete_ocr_result_service

        count = await run_db_sync(
            delete_ocr_result_service,
            file_id=file_id,
            task=task,
            engine=engine,
        )
        return api_result({"deleted": count})

    @bp.route("/api/ocr/engines", methods=["GET"])
    async def api_ocr_engines():
        """List available OCR engines."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        def _list_engines():
            from core.analysis_api.server_registry import get_all_servers
            from core.configuration.api import load_config_json
            from core.ocr_core.router import _get_model_score

            config = load_config_json(None)
            servers = get_all_servers(config)

            engines = []
            for srv in servers:
                if not srv.enabled:
                    continue
                model = srv.config.get("model", "")
                engines.append({
                    "server_id": srv.id,
                    "server_name": srv.name,
                    "model": model,
                    "type": srv.type,
                    "scores": {
                        "ocr": _get_model_score(model, "ocr"),
                        "ocr_document": _get_model_score(model, "ocr_document"),
                        "ocr_manga": _get_model_score(model, "ocr_manga"),
                    },
                })

            engines.sort(key=lambda e: e["scores"]["ocr"], reverse=True)

            try:
                from core.ocr_core.manga_ocr_engine import is_manga_ocr_available
                manga_ocr_available = is_manga_ocr_available()
            except Exception:
                manga_ocr_available = False

            return {
                "engines": engines,
                "manga_ocr_available": manga_ocr_available,
            }

        return api_result(await run_db_sync(_list_engines))

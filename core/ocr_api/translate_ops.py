"""OCR API -- translation and overlay image generation."""

from __future__ import annotations

from quart import Blueprint, request, send_file

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register(bp: Blueprint) -> None:
    """Register routes on the Blueprint."""


    @bp.route("/api/ocr/translate/<int:file_id>", methods=["POST"])
    async def api_ocr_translate(file_id: int):
        """Translate OCR result."""
        body = await request.get_json(silent=True) or {}
        target_lang = body.get("target_lang", "en")
        server_id = body.get("server_id", "")
        task = body.get("task", "")

        if not target_lang:
            return api_error("target_lang is required", 400)

        from extensions.builtin_ocr.core_impl.route_services import translate_ocr_result_service

        payload, status = await run_db_sync(
            translate_ocr_result_service,
            file_id=file_id,
            target_lang=target_lang,
            server_id=server_id,
            task=task,
        )
        if status != 200:
            return api_error(payload.get("error", ""), status)
        return api_result(payload)

    @bp.route("/api/ocr/translations/<int:file_id>", methods=["GET"])
    async def api_ocr_translations(file_id: int):
        """Get list of translation results for a file."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        target_lang = request.args.get("target_lang", "")

        from extensions.builtin_ocr.core_impl.route_services import list_translations_service

        return api_result(
            await run_db_sync(
                list_translations_service,
                file_id=file_id,
                target_lang=target_lang,
            )
        )

    @bp.route("/api/ocr/overlay/<int:file_id>", methods=["GET"])
    async def api_ocr_overlay(file_id: int):
        """Generate translated text overlay image."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        import io

        mode = request.args.get("mode", "translated")
        target_lang = request.args.get("target_lang", "")
        fmt = request.args.get("format", "png").upper()
        task = request.args.get("task", "")

        if mode not in ("translated", "original", "both"):
            return api_error("Invalid mode. Use: translated, original, both", 400)
        if fmt not in ("PNG", "JPEG"):
            return api_error("Invalid format. Use: png, jpeg", 400)

        from extensions.builtin_ocr.core_impl.route_services import generate_overlay_service

        img_bytes, err_msg = await run_db_sync(
            generate_overlay_service,
            file_id=file_id,
            mode=mode,
            target_lang=target_lang,
            fmt=fmt,
            task=task,
        )
        if err_msg:
            status = 404 if "not found" in err_msg.lower() else 500
            return api_error(err_msg, status)

        content_type = "image/png" if fmt == "PNG" else "image/jpeg"
        ext = "png" if fmt == "PNG" else "jpg"
        return await send_file(
            io.BytesIO(img_bytes),
            mimetype=content_type,
            as_attachment=False,
            attachment_filename=f"ocr_overlay_{file_id}.{ext}",
        )

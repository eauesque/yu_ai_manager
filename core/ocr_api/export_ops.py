"""OCR API -- export routes (single + batch).

Batch helper functions are in export_batch.py.
"""

from __future__ import annotations

import logging

from quart import Blueprint, request, send_file

from core.infra_core.api_errors import api_error
from core.ocr_api.export_batch import (
    batch_export_to_dir,
    batch_overlay_download,
)
from core.services_core.db_async import run_db_sync

logger = logging.getLogger(__name__)


def register(bp: Blueprint) -> None:
    """Register export routes on a Blueprint."""

    @bp.route("/api/ocr/export/<int:file_id>", methods=["GET"])
    async def api_ocr_export(file_id: int):
        """Export OCR result for a single file.

        ?include_translation=1&target_lang=en for translation-included export.
        """
        import io

        from core.ocr_core.export import EXPORT_FORMATS

        fmt = request.args.get("format", "md")
        task = request.args.get("task", "")
        include_trans = request.args.get("include_translation", "")
        target_lang = request.args.get("target_lang", "")

        if fmt not in EXPORT_FORMATS:
            return api_error(f"Invalid format: {fmt}. Supported: {', '.join(EXPORT_FORMATS)}", 400)

        from extensions.builtin_ocr.core_impl.route_services import export_single_ocr_service

        content, filename, content_type, err_msg = await run_db_sync(
            export_single_ocr_service,
            file_id=file_id,
            fmt=fmt,
            task=task,
            include_trans=include_trans,
            target_lang=target_lang,
        )
        if err_msg:
            status = 404 if "not found" in err_msg.lower() else 500
            return api_error(err_msg, status)

        return await send_file(
            io.BytesIO(content),
            mimetype=content_type,
            as_attachment=True,
            attachment_filename=filename,
        )

    @bp.route("/api/ocr/export/batch", methods=["POST"])
    async def api_ocr_export_batch():
        """Batch export OCR results as ZIP.

        If output_dir is specified, save directly to server-side directory.
        format=overlay generates overlay images.
        """
        import io

        body = await request.get_json(silent=True) or {}
        file_ids = body.get("file_ids", [])
        fmt = body.get("format", "")
        output_dir = body.get("output_dir", "")
        overlay_mode = body.get("overlay_mode", "translated")
        target_lang = body.get("target_lang", "")
        include_trans = body.get("include_translation", False)

        from core.ocr_core.export import export_ocr_batch
        from extensions.builtin_ocr.core_impl.route_services import prepare_batch_export_service

        payload, status = await run_db_sync(
            prepare_batch_export_service,
            file_ids=file_ids,
            fmt=fmt,
            output_dir=output_dir,
            overlay_mode=overlay_mode,
            target_lang=target_lang,
            include_trans=include_trans,
        )
        if status != 200:
            return api_error(payload.get("error", "OCR batch export failed"), status)

        if payload["output_dir"]:
            return batch_export_to_dir(
                payload["ocr_results"],
                payload["fmt"],
                payload["output_dir"],
                payload["file_paths"],
                overlay_mode=payload["overlay_mode"],
                target_lang=payload["target_lang"],
                translations_map=payload["translations_map"],
                full_text_map=payload["full_text_map"],
            )

        if payload["is_overlay"]:
            return await batch_overlay_download(
                payload["ocr_results"],
                payload["file_paths"],
                payload["overlay_mode"],
                payload["target_lang"],
                payload["translations_map"],
                payload["full_text_map"],
            )

        try:
            zip_bytes, zip_name = export_ocr_batch(
                payload["ocr_results"],
                payload["fmt"],
                translations_map=payload["translations_map"],
                full_text_map=payload["full_text_map"],
                target_lang=payload["target_lang"],
            )
        except RuntimeError:
            logger.exception("OCR batch export failed")
            return api_error("OCR batch export failed", 500)

        return await send_file(
            io.BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            attachment_filename=zip_name,
        )

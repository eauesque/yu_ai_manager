"""Output-oriented OCR route service helpers."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from .route_services_common import OCRRouteRuntimeDeps

logger = logging.getLogger(__name__)


def generate_overlay_impl(
    *,
    file_id: int,
    mode: str,
    target_lang: str,
    fmt: str,
    task: str = "",
    deps: OCRRouteRuntimeDeps,
) -> tuple[bytes | None, str | None]:
    from core.ocr_core.overlay import generate_overlay
    from core.ocr_core.store import get_ocr_result_obj

    from core.services_core.db_state import get_readonly_db

    con = get_readonly_db()
    ocr = get_ocr_result_obj(con, file_id, task=task)
    if not ocr:
        return None, "OCR result not found. Run OCR first."

    file_path = deps.get_file_path(file_id)
    if not file_path:
        return None, "File not found"

    translations = {}
    translated_full_text = ""
    if mode in ("translated", "both"):
        translations, translated_full_text = deps.load_overlay_translation_data(
            con,
            file_id,
            ocr_result_id=ocr.id,
            target_lang=target_lang,
        )

    with deps.resolve_image_path(file_path) as (image_path, path_err):
        if path_err:
            return None, path_err
        try:
            img_bytes = generate_overlay(
                image_path,
                ocr,
                translations=translations if translations else None,
                mode=mode,
                output_format=fmt,
                translated_full_text=translated_full_text,
                target_lang=target_lang,
            )
        except Exception as exc:
            logger.error("Overlay generation failed for file_id=%d: %s", file_id, exc)
            return None, f"Overlay generation failed: {exc}"

    return img_bytes, None


def export_single_ocr_impl(
    *,
    file_id: int,
    fmt: str,
    task: str = "",
    include_trans: str = "",
    target_lang: str = "",
    deps: OCRRouteRuntimeDeps,
) -> tuple[bytes | None, str | None, str | None, str | None]:
    from core.ocr_core.export import export_ocr
    from core.ocr_core.store import get_ocr_result_obj

    from core.services_core.db_state import get_readonly_db

    con = get_readonly_db()
    ocr = get_ocr_result_obj(con, file_id, task=task)
    if not ocr:
        return None, None, None, "OCR result not found"

    translations = None
    translated_full_text = ""
    if include_trans:
        translations, translated_full_text = deps.load_translations_for_export(con, file_id, target_lang)

    try:
        content, filename, content_type = export_ocr(
            ocr,
            fmt,
            translations=translations,
            translated_full_text=translated_full_text,
            target_lang=target_lang,
        )
    except RuntimeError as exc:
        return None, None, None, str(exc)

    return content, filename, content_type, None


def prepare_batch_export_impl(
    *,
    file_ids: Iterable[int],
    fmt: str,
    output_dir: str,
    overlay_mode: str,
    target_lang: str,
    include_trans: bool,
    deps: OCRRouteRuntimeDeps,
) -> tuple[dict[str, Any], int]:
    from core.ocr_core.export import EXPORT_FORMATS
    from core.ocr_core.store import get_ocr_result_obj

    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
    from core.services_core.db_state import get_readonly_db

    file_ids = list(file_ids)
    if not fmt:
        fmt = get_extension_config_value("builtin-ocr", "batch_export_format", "md")
    if not output_dir:
        output_dir = get_extension_config_value("builtin-ocr", "batch_output_dir", "")

    is_overlay = fmt == "overlay"
    valid_formats = list(EXPORT_FORMATS) + ["overlay"]
    if fmt not in valid_formats:
        return {"error": f"Invalid format: {fmt}. Supported: {', '.join(valid_formats)}"}, 400
    if not file_ids:
        return {"error": "file_ids is required"}, 400

    con = get_readonly_db()
    ocr_results = []
    file_paths = {}
    for file_id in file_ids:
        ocr = get_ocr_result_obj(con, file_id)
        if not ocr:
            continue
        ocr_results.append(ocr)
        if is_overlay:
            file_path = deps.get_file_path(file_id)
            if file_path:
                file_paths[file_id] = file_path

    if not ocr_results:
        return {"error": "No OCR results found for given file_ids"}, 404

    translations_map = None
    full_text_map = None
    if include_trans or is_overlay:
        translations_map, full_text_map = deps.build_translation_maps(
            con=con,
            ocr_results=ocr_results,
            target_lang=target_lang,
            loader=deps.load_translations_for_export,
        )

    return {
        "fmt": fmt,
        "output_dir": output_dir,
        "overlay_mode": overlay_mode,
        "target_lang": target_lang,
        "is_overlay": is_overlay,
        "ocr_results": ocr_results,
        "file_paths": file_paths,
        "translations_map": translations_map,
        "full_text_map": full_text_map,
    }, 200

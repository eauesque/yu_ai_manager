"""Translation-related OCR route service helpers."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def translate_ocr_result_impl(
    *,
    file_id: int,
    target_lang: str,
    server_id: str = "",
    task: str = "",
) -> tuple[dict[str, Any], int]:
    from core.ocr_core.store import get_ocr_result_obj
    from core.ocr_core.translation import translate_ocr_result

    from core.services_core.db_state import get_readonly_db
    from core.services_core.ocr_write_service import save_translation_payload

    con_ro = get_readonly_db()
    ocr = get_ocr_result_obj(con_ro, file_id, task=task)
    if not ocr:
        return {"error": "OCR result not found. Run OCR first."}, 404

    try:
        result = translate_ocr_result(ocr, target_lang, server_id=server_id or None)
    except Exception as exc:
        logger.error("Translation failed for file_id=%d: %s", file_id, exc)
        return {"error": f"Translation failed: {exc}"}, 500

    if ocr.id:
        save_translation_payload(ocr.id, result)

    return {
        "file_id": file_id,
        "target_lang": target_lang,
        "translated_text": result.translated_text,
        "engine": result.engine,
        "region_translations": result.region_translations,
    }, 200


def list_translations_impl(*, file_id: int, target_lang: str = "") -> dict[str, Any]:
    from core.ocr_core.translation import get_translations_for_file

    from core.services_core.db_state import get_readonly_db

    results = get_translations_for_file(get_readonly_db(), file_id)
    if target_lang:
        results = [result for result in results if result.get("target_lang") == target_lang]
    return {
        "file_id": file_id,
        "translations": results,
    }

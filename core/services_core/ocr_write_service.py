"""Write helpers for OCR and translation persistence."""

from __future__ import annotations


def save_ocr_result_payload(result) -> int:
    from core.ocr_core import ensure_ocr_tables, save_ocr_result
    from core.services_core.db_state import get_db

    con = get_db()
    ensure_ocr_tables(con)
    return save_ocr_result(con, result)


def delete_ocr_result_payload(file_id: int, *, task: str = "", engine: str = "") -> int:
    from core.ocr_core import delete_ocr_result
    from core.services_core.db_state import get_db

    return delete_ocr_result(get_db(), file_id, task=task, engine=engine)


def save_translation_payload(ocr_result_id: int, result) -> int:
    from core.ocr_core.translation import ensure_translation_table, save_translation
    from core.services_core.db_state import get_db

    con = get_db()
    ensure_translation_table(con)
    return save_translation(con, ocr_result_id, result)

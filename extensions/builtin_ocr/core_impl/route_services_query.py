"""Query and delete helpers for OCR route services."""
from __future__ import annotations

from typing import Any


def get_ocr_result_impl(
    *,
    file_id: int,
    task: str = "",
    engine: str = "",
    all_results: str = "",
) -> dict[str, Any]:
    from core.ocr_core import get_all_ocr_results, get_ocr_result

    from core.services_core.db_state import get_readonly_db

    con = get_readonly_db()
    if all_results:
        return {"file_id": file_id, "results": get_all_ocr_results(con, file_id)}
    result = get_ocr_result(con, file_id, task=task, engine=engine)
    if not result:
        return {"status": "not_found"}
    return result


def delete_ocr_result_impl(*, file_id: int, task: str = "", engine: str = "") -> int:
    from core.services_core.ocr_write_service import delete_ocr_result_payload

    return delete_ocr_result_payload(file_id, task=task, engine=engine)

"""Execution-oriented OCR route service helpers."""
from __future__ import annotations

import logging
from typing import Any

from .route_services_common import OCRRouteRuntimeDeps

logger = logging.getLogger(__name__)
_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def run_bbox_detection_impl(
    *,
    file_id: int,
    task: str = "",
    server_id: str = "",
    deps: OCRRouteRuntimeDeps,
) -> tuple[dict[str, Any], int]:
    from core.ocr_core import resolve_ocr_engine
    from core.ocr_core.bbox_detect import detect_bboxes
    from core.ocr_core.store import get_ocr_result_obj

    from core.services_core.db_state import get_readonly_db
    from core.services_core.ocr_write_service import save_ocr_result_payload

    con_ro = get_readonly_db()
    ocr = get_ocr_result_obj(con_ro, file_id, task=task)
    if not ocr:
        return {"error": "OCR result not found. Run OCR first."}, 404
    if not ocr.regions:
        return {"error": "No text regions to locate. Run OCR first."}, 400

    file_path = deps.get_file_path(file_id)
    if not file_path:
        return {"error": "File not found"}, 404

    engine, err = resolve_ocr_engine(task=task or "ocr", server_id=server_id or None)
    if err:
        return {"error": err}, 500

    analysis_engine = getattr(engine, "_engine", None)
    if not analysis_engine:
        return {"error": "bbox detection requires a VLM engine"}, 400

    with deps.resolve_image_path(file_path) as (image_path, path_err):
        if path_err:
            return {"error": path_err}, 404
        try:
            updated_regions = detect_bboxes(image_path, ocr.regions, analysis_engine)
        except Exception as exc:
            logger.error("bbox detection failed for file_id=%d: %s", file_id, exc)
            return {"error": f"bbox detection failed: {exc}"}, 500

    ocr.regions = updated_regions
    save_ocr_result_payload(ocr)
    detected = sum(1 for region in updated_regions if region.bbox)
    return {
        "file_id": file_id,
        "total_regions": len(updated_regions),
        "detected_bboxes": detected,
        "regions": [region.to_dict() for region in updated_regions],
    }, 200


"""Media-specific OCR execution wrappers."""
from __future__ import annotations

from typing import Any

from .route_services_common import MediaValidationError, OCRRouteRuntimeDeps, run_media_ocr


def run_single_ocr_impl(
    *,
    file_id: int,
    task: str,
    language: str,
    server_id: str = "",
    deps: OCRRouteRuntimeDeps | None = None,
) -> tuple[dict[str, Any], int]:
    def _execute(engine, image_path):
        return engine.extract_text(image_path, task=task, language=language)

    return run_media_ocr(
        file_id=file_id,
        task=task,
        language=language,
        server_id=server_id,
        count_key="regions_count",
        error_label="OCR",
        executor=_execute,
        deps=deps,
    )


def run_video_ocr_impl(
    *,
    file_id: int,
    task: str,
    language: str,
    server_id: str = "",
    keyframe_count: int = 4,
    strategy: str = "uniform",
    deps: OCRRouteRuntimeDeps | None = None,
) -> tuple[dict[str, Any], int]:
    from core.ocr_core.video_ocr import is_video_file, ocr_video_to_result

    def _execute(engine, video_path):
        if not is_video_file(video_path):
            raise MediaValidationError("File is not a video")
        return ocr_video_to_result(
            engine,
            video_path,
            file_id=file_id,
            task=task,
            language=language,
            keyframe_count=keyframe_count,
            strategy=strategy,
        )

    return run_media_ocr(
        file_id=file_id,
        task=task,
        language=language,
        server_id=server_id,
        count_key="frame_count",
        error_label="Video OCR",
        executor=_execute,
        deps=deps,
    )


def run_pdf_ocr_impl(
    *,
    file_id: int,
    task: str,
    language: str,
    server_id: str = "",
    page_range: str = "",
    dpi: int = 200,
    deps: OCRRouteRuntimeDeps | None = None,
) -> tuple[dict[str, Any], int]:
    from core.ocr_core.pdf_ocr import is_pdf_file, ocr_pdf_to_result

    def _execute(engine, pdf_path):
        if not is_pdf_file(pdf_path):
            raise MediaValidationError("File is not a PDF")
        return ocr_pdf_to_result(
            engine,
            pdf_path,
            file_id=file_id,
            task=task,
            language=language,
            page_range=page_range,
            dpi=dpi,
        )

    return run_media_ocr(
        file_id=file_id,
        task=task,
        language=language,
        server_id=server_id,
        count_key="page_count",
        error_label="PDF OCR",
        executor=_execute,
        deps=deps,
    )

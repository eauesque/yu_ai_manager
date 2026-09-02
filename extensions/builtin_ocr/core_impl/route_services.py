"""Synchronous OCR service helpers for Quart routes.

Route handlers should stay focused on request/response shaping. These helpers
own the blocking OCR + SQLite work and are intended to run via run_db_sync().
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.ocr_api.helpers import load_translations_for_export, resolve_image_path

from .route_services_common import (
    OCRRouteRuntimeDeps,
    build_translation_maps,
)
from .route_services_common import (
    get_file_path as _get_file_path,
)
from .route_services_common import (
    load_overlay_translation_data as _load_overlay_translation_data,
)
from .route_services_common import (
    resolve_engine as _resolve_engine,
)
from .route_services_exec import (
    run_bbox_detection_impl,
)
from .route_services_media import (
    run_single_ocr_impl,
)
from .route_services_output import (
    export_single_ocr_impl,
    generate_overlay_impl,
    prepare_batch_export_impl,
)
from .route_services_query import (
    delete_ocr_result_impl,
    get_ocr_result_impl,
)
from .route_services_runtime import build_runtime_deps, call_with_runtime_deps
from .route_services_translation import (
    list_translations_impl,
    translate_ocr_result_impl,
)

get_ocr_result_service = get_ocr_result_impl
delete_ocr_result_service = delete_ocr_result_impl
translate_ocr_result_service = translate_ocr_result_impl
list_translations_service = list_translations_impl


def _runtime_deps() -> OCRRouteRuntimeDeps:
    return build_runtime_deps(
        get_file_path=_get_file_path,
        resolve_image_path=resolve_image_path,
        resolve_engine=_resolve_engine,
        load_overlay_translation_data=_load_overlay_translation_data,
        load_translations_for_export=load_translations_for_export,
        build_translation_maps=build_translation_maps,
    )


def run_bbox_detection(
    *,
    file_id: int,
    task: str = "",
    server_id: str = "",
) -> tuple[dict[str, Any], int]:
    return call_with_runtime_deps(
        run_bbox_detection_impl,
        deps=_runtime_deps(),
        file_id=file_id,
        task=task,
        server_id=server_id,
    )


def run_single_ocr(
    *,
    file_id: int,
    task: str,
    language: str,
    server_id: str = "",
) -> tuple[dict[str, Any], int]:
    return call_with_runtime_deps(
        run_single_ocr_impl,
        deps=_runtime_deps(),
        file_id=file_id,
        task=task,
        language=language,
        server_id=server_id,
    )


def generate_overlay_service(
    *,
    file_id: int,
    mode: str,
    target_lang: str,
    fmt: str,
    task: str = "",
) -> tuple[bytes | None, str | None]:
    return call_with_runtime_deps(
        generate_overlay_impl,
        deps=_runtime_deps(),
        file_id=file_id,
        mode=mode,
        target_lang=target_lang,
        fmt=fmt,
        task=task,
    )


def export_single_ocr_service(
    *,
    file_id: int,
    fmt: str,
    task: str = "",
    include_trans: str = "",
    target_lang: str = "",
) -> tuple[bytes | None, str | None, str | None, str | None]:
    return call_with_runtime_deps(
        export_single_ocr_impl,
        deps=_runtime_deps(),
        file_id=file_id,
        fmt=fmt,
        task=task,
        include_trans=include_trans,
        target_lang=target_lang,
    )


def prepare_batch_export_service(
    *,
    file_ids: Iterable[int],
    fmt: str,
    output_dir: str,
    overlay_mode: str,
    target_lang: str,
    include_trans: bool,
) -> tuple[dict[str, Any], int]:
    return call_with_runtime_deps(
        prepare_batch_export_impl,
        deps=_runtime_deps(),
        file_ids=file_ids,
        fmt=fmt,
        output_dir=output_dir,
        overlay_mode=overlay_mode,
        target_lang=target_lang,
        include_trans=include_trans,
    )


__all__ = [
    "delete_ocr_result_service",
    "export_single_ocr_service",
    "generate_overlay_service",
    "get_ocr_result_service",
    "list_translations_service",
    "prepare_batch_export_service",
    "run_bbox_detection",
    "run_single_ocr",
    "translate_ocr_result_service",
]

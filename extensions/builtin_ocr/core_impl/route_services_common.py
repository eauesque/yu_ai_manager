"""Shared helpers for OCR route service execution."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from core.ocr_api.helpers import resolve_image_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OCRRouteRuntimeDeps:
    get_file_path: Callable[[int], str | None]
    resolve_image_path: Any
    resolve_engine: Callable[[str, str], tuple[Any, str | None]]
    load_overlay_translation_data: Callable[..., tuple[dict[int, str], str]]
    load_translations_for_export: Callable[[Any, int, str], tuple[Any, str]]
    build_translation_maps: Callable[..., tuple[dict[int, dict] | None, dict[int, str] | None]]


class MediaValidationError(Exception):
    """Raised when a requested OCR operation targets the wrong media type."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_file_path(file_id: int) -> str | None:
    from core.services_core.db_state import get_readonly_db

    row = get_readonly_db().execute(
        "SELECT path FROM files WHERE id=? AND is_deleted=0",
        (file_id,),
    ).fetchone()
    if not row:
        return None
    return row["path"]


def resolve_engine(task: str, server_id: str = ""):
    from core.ocr_core import resolve_ocr_engine

    return resolve_ocr_engine(task=task, server_id=server_id or None)


def load_overlay_translation_data(con, file_id: int, *, ocr_result_id: int | None, target_lang: str):
    from core.ocr_core.translation import get_translations_for_file

    translations: dict[int, str] = {}
    translated_full_text = ""
    trans_rows = get_translations_for_file(con, file_id)
    for tr in trans_rows:
        if ocr_result_id and tr.get("ocr_result_id") and tr["ocr_result_id"] != ocr_result_id:
            continue
        if target_lang and tr.get("target_lang") != target_lang:
            continue
        if not translated_full_text and tr.get("translated_text"):
            translated_full_text = tr["translated_text"]
        for region_translation in tr.get("region_translations", []):
            region_id = region_translation.get("region_id")
            if region_id is not None and region_translation.get("translated"):
                translations[region_id] = region_translation["translated"]
    return translations, translated_full_text


def persist_result_payload(result, *, file_id: int, task: str, count_key: str) -> tuple[dict[str, Any], int]:
    from core.services_core.ocr_write_service import save_ocr_result_payload

    row_id = save_ocr_result_payload(result)
    return {
        "file_id": file_id,
        "engine": result.engine,
        "task": task,
        "full_text": result.full_text,
        "language": getattr(result, "language", ""),
        count_key: len(result.regions),
        "row_id": row_id,
    }, 200


def run_media_ocr(
    *,
    file_id: int,
    task: str,
    language: str,
    server_id: str,
    count_key: str,
    error_label: str,
    executor: Callable[[Any, Any], Any],
    deps: OCRRouteRuntimeDeps | None = None,
) -> tuple[dict[str, Any], int]:
    deps = deps or OCRRouteRuntimeDeps(
        get_file_path=get_file_path,
        resolve_image_path=resolve_image_path,
        resolve_engine=resolve_engine,
        load_overlay_translation_data=load_overlay_translation_data,
        load_translations_for_export=lambda *_args, **_kwargs: ({}, ""),
        build_translation_maps=build_translation_maps,
    )

    file_path = deps.get_file_path(file_id)
    if not file_path:
        return {"error": "File not found"}, 404

    engine, err = deps.resolve_engine(task, server_id)
    if err:
        return {"error": err}, 500

    with deps.resolve_image_path(file_path) as (resolved_path, path_err):
        if path_err:
            return {"error": path_err}, 404
        try:
            result = executor(engine, resolved_path)
            result.file_id = file_id
            result.engine = engine.get_name()
        except MediaValidationError as exc:
            return {"error": str(exc)}, exc.status_code
        except Exception as exc:
            logger.error("%s failed for file_id=%d: %s", error_label, file_id, exc)
            return {"error": f"{error_label} failed: {exc}"}, 500

    return persist_result_payload(result, file_id=file_id, task=task, count_key=count_key)


def build_translation_maps(
    *,
    con,
    ocr_results: Iterable[Any],
    target_lang: str,
    loader: Callable[[Any, int, str], tuple[Any, str]],
) -> tuple[dict[int, dict] | None, dict[int, str] | None]:
    translations_map: dict[int, dict] = {}
    full_text_map: dict[int, str] = {}
    for ocr in ocr_results:
        file_id = ocr.file_id or 0
        region_translations, full_text = loader(con, file_id, target_lang)
        if region_translations:
            translations_map[file_id] = region_translations
        if full_text:
            full_text_map[file_id] = full_text
    return translations_map, full_text_map

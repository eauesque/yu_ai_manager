"""Runtime dependency assembly for OCR route service facades."""
from __future__ import annotations

from .route_services_common import OCRRouteRuntimeDeps


def build_runtime_deps(
    *,
    get_file_path,
    resolve_image_path,
    resolve_engine,
    load_overlay_translation_data,
    load_translations_for_export,
    build_translation_maps,
) -> OCRRouteRuntimeDeps:
    return OCRRouteRuntimeDeps(
        get_file_path=get_file_path,
        resolve_image_path=resolve_image_path,
        resolve_engine=resolve_engine,
        load_overlay_translation_data=load_overlay_translation_data,
        load_translations_for_export=load_translations_for_export,
        build_translation_maps=build_translation_maps,
    )


def call_with_runtime_deps(func, /, *, deps: OCRRouteRuntimeDeps, **kwargs):
    return func(deps=deps, **kwargs)

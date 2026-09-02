"""Detail payload helpers for file routes."""

import logging
import sqlite3
import time
from typing import Any

from core.file_api.detail_media import build_readonly_media_sections
from core.file_api.detail_parse import build_novelai_payload, resolve_detail_fields
from core.file_api.detail_payload_data import build_base_result, fetch_file_row, fetch_tag_list
from core.file_api.detail_payload_media import resolve_media_payload
from core.infra_core.debug_log import dlog
from core.services_core.db_api import get_readonly_db

logger = logging.getLogger(__name__)


def _invoke_build_sections(
    file_row: dict[str, Any], parsed_fields: dict[str, Any]
) -> list[Any]:
    """Run on_build_sections hook chain via extension manager.

    Returns a flat list of DetailSection from all participating extensions.
    Empty list if the manager is unavailable or if any failure path triggers.
    """
    try:
        from core.extensions_core.lifecycle.runtime import get_extension_manager
        mgr = get_extension_manager()
    except Exception:
        return []
    if mgr is None:
        return []
    try:
        # Convert sqlite3.Row → dict so extension code can use .get()
        # (Row supports __getitem__ but raises IndexError on missing keys).
        raw_meta_json = (
            file_row.get("raw_meta_json")
            if hasattr(file_row, "get")
            else file_row["raw_meta_json"]
        )
        result = mgr.invoke_hook(
            "on_build_sections",
            dict(file_row),
            raw_meta_json,
            parsed_fields,
        )
    except Exception:
        logger.exception("on_build_sections invocation failed")
        return []
    return result if isinstance(result, list) else []


def build_file_detail_payload(
    file_id: int,
    *,
    con: sqlite3.Connection | None = None,
    skip_deferred_writes: bool = False,
) -> tuple[dict[str, Any], int]:
    """Build file detail response payload.

    When `con` is provided, use it for reads (used by inspect API with its
    in-memory SQLite). Otherwise use the read-only main connection (modal flow).

    Uses a read-only connection by default to avoid write-lock contention during
    scans. Auxiliary writes (JSON normalization, state updates) are performed
    asynchronously via a separate connection inside resolve_media_payload.

    `skip_deferred_writes` must be True for inspect (in-memory DB) callers:
    file_id refers to the in-memory row, not production. Without this flag the
    deferred writer would target the production DB row with the same id.
    """
    t0 = time.perf_counter()

    ro_con = con if con is not None else get_readonly_db()
    t_db = time.perf_counter()
    file_row = fetch_file_row(ro_con, file_id)
    t1 = time.perf_counter()

    if not file_row:
        return {"error": "Not found", "code": "not_found"}, 404

    tag_list = fetch_tag_list(ro_con, file_id)
    t2 = time.perf_counter()
    parsed_fields = resolve_detail_fields(file_row)
    t3 = time.perf_counter()
    media_payload = resolve_media_payload(file_row, skip_deferred_writes=skip_deferred_writes)
    t4 = time.perf_counter()
    extension_sections = _invoke_build_sections(file_row, parsed_fields)
    t5 = time.perf_counter()

    result: dict[str, Any] = build_base_result(
        file_row, parsed_fields, tag_list, media_payload["raw_meta_json"]
    )
    t6 = time.perf_counter()
    total_ms = int((t6 - t0) * 1000)
    if total_ms >= 250:
        dlog(
            "file_detail",
            "build_file_detail_payload.steps",
            file_id=file_id,
            total_ms=total_ms,
            get_db_ms=int((t_db - t0) * 1000),
            query_ms=int((t1 - t_db) * 1000),
            fetch_tags_ms=int((t2 - t1) * 1000),
            resolve_fields_ms=int((t3 - t2) * 1000),
            resolve_media_ms=int((t4 - t3) * 1000),
            build_sections_ms=int((t5 - t4) * 1000),
            build_base_ms=int((t6 - t5) * 1000),
            tag_count=len(tag_list),
        )

    sections: list[Any] = []
    if media_payload["readonly_media_metadata"]:
        result["readonly_media_metadata"] = media_payload["readonly_media_metadata"]
        # Container info (readonly_media: ZIP-internal EXIF, etc.) comes first,
        # then content info (extension sections). UI shows file provenance first,
        # then parsed AI metadata. (rev2 N2)
        sections.extend(build_readonly_media_sections(media_payload["readonly_media_metadata"]) or [])
    sections.extend(extension_sections)
    if sections:
        result["sections"] = sections

    novelai_v4_payload = build_novelai_payload(parsed_fields["novelai_v4_data"])
    if novelai_v4_payload:
        result["novelai_v4"] = novelai_v4_payload

    return result, 200

"""RAR-internal scan worker — single-entry operations."""

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

from core.infra_core.file_hash import bytes_etag, file_etag
from core.infra_core.timeout import ARCHIVE_SCAN_TIMEOUT, run_with_timeout
from core.models_core.models_files import get_file_row, upsert_file
from core.models_core.models_templates import replace_template_tokens, upsert_template
from core.parsers.prompt_parse import parse_prompt_to_tags
from core.parsers.prompt_parse_candidates import effective_config
from core.rar_core.rar_support import read_bytes_from_rar
from core.rar_core.rar_support_core import get_mtime_and_size_from_rar
from core.scan.mtime_timezone import (
    correct_mtime_if_utc,
    is_utc_meta_source,
    naive_local_to_utc_timestamp,
)
from core.scan_core.scanner_io import extract_resolution
from core.schema_core.schema import CURRENT_PARSER_VERSION

from .archive_tag_diff import build_archive_meta_tag_rows, replace_archive_meta_tags_if_changed

ScanResult = tuple[str, int] | None


def _get_rar_info(archive_path: str, internal_path: str) -> tuple[int, int]:
    """Get mtime and size from RAR entry in a single archive open."""
    return get_mtime_and_size_from_rar(archive_path, internal_path)


def _backfill_rar_hash(
    con: sqlite3.Connection, archive_path: str, internal_path: str,
    file_id: int, old_hash: str | None, full_path: str,
) -> ScanResult:
    """Compute missing hash for an unchanged RAR member."""
    if old_hash is not None:
        return None
    try:
        from core.helpers_core.archive_member_temp import extracted_rar_member_path
        from core.zip_core.zip_support_extract_dispatch import is_media_metadata_extension

        if is_media_metadata_extension(internal_path):
            with extracted_rar_member_path(archive_path, internal_path) as extracted:
                content_hash = file_etag(extracted)
        else:
            file_bytes = run_with_timeout(
                lambda: read_bytes_from_rar(archive_path, internal_path),
                timeout=ARCHIVE_SCAN_TIMEOUT,
                label=f"backfill:{full_path}",
            )
            content_hash = bytes_etag(file_bytes, internal_path)
        if content_hash:
            cur = con.execute("UPDATE files SET hash=? WHERE id=? AND hash IS NOT ?", (content_hash, file_id, content_hash))
            if cur.rowcount:
                return ("backfilled", file_id)
    except Exception:
        logger.debug("scan step failed", exc_info=True)
    return None


def scan_one_rar(con: sqlite3.Connection, archive_full_path: str, config: dict[str, Any], force: bool, *, skip_backfill: bool = False) -> ScanResult:
    """Scan a file inside RAR archive."""
    from core.helpers_core.helpers_text_path import split_archive_path
    archive_path, internal_path = split_archive_path(archive_full_path)

    try:
        raw_mtime, size = run_with_timeout(
            lambda: _get_rar_info(archive_path, internal_path),
            timeout=ARCHIVE_SCAN_TIMEOUT,
            label=archive_full_path,
        )
    except TimeoutError:
        logger.warning(f"RAR info timed out ({ARCHIVE_SCAN_TIMEOUT}s): {archive_full_path}")
        return None
    except Exception as e:
        logger.warning(f"Failed to get RAR file info: {archive_full_path}: {type(e).__name__}: {e}")
        logger.warning(f"  archive_path={archive_path}  internal_path={internal_path!r}")
        return None

    path_s = archive_full_path
    mtime = correct_mtime_if_utc(con, path_s, raw_mtime)
    existing = get_file_row(con, path_s)
    should_scan = force or existing is None
    if existing is not None and not force:
        _fid, old_mtime, old_size, is_deleted, _old_hash, old_pv = existing
        should_scan = bool(
            is_deleted
            or old_mtime != mtime
            or old_size != size
            or old_pv < CURRENT_PARSER_VERSION
        )

    if not should_scan:
        if existing and not skip_backfill:
            return _backfill_rar_hash(con, archive_path, internal_path, existing[0], existing[4], path_s)
        return None

    is_new = existing is None

    from core.zip_core.zip_support_extract_dispatch import is_media_metadata_extension

    file_bytes = None
    if is_media_metadata_extension(internal_path):
        try:
            from core.helpers_core.archive_member_temp import extracted_rar_member_path
            from core.rar_core.rar_support_extract import _set_a1111_tag_source
            from core.zip_core.zip_support_extract_dispatch import apply_extractor_by_extension

            with extracted_rar_member_path(archive_path, internal_path) as extracted:
                metadata: dict[str, Any] = {
                    "meta_source": None, "format": None, "raw_prompt": None,
                    "raw_negative": None, "raw_meta_json": None, "success": False,
                }
                apply_extractor_by_extension(metadata, internal_path, extracted)
                _set_a1111_tag_source(metadata)
                content_hash = file_etag(extracted)
        except TimeoutError:
            logger.warning(f"RAR read timed out ({ARCHIVE_SCAN_TIMEOUT}s): {archive_full_path}")
            metadata = {"meta_source": "rar_error", "format": "unknown",
                        "raw_prompt": None, "raw_negative": None, "raw_meta_json": None}
            content_hash = None
        except Exception as e:
            logger.warning(f"Failed to read from RAR: {archive_full_path}: {e}")
            metadata = {"meta_source": "rar_error", "format": "unknown",
                        "raw_prompt": None, "raw_negative": None, "raw_meta_json": None}
            content_hash = None
    else:
        try:
            file_bytes = run_with_timeout(
                lambda: read_bytes_from_rar(archive_path, internal_path),
                timeout=ARCHIVE_SCAN_TIMEOUT,
                label=archive_full_path,
            )
        except TimeoutError:
            logger.warning(f"RAR read timed out ({ARCHIVE_SCAN_TIMEOUT}s): {archive_full_path}")
        except Exception as e:
            logger.warning(f"Failed to read from RAR: {archive_full_path}: {e}")

        if file_bytes is not None:
            try:
                from core.rar_core.rar_support_extract import _set_a1111_tag_source
                from core.zip_core.zip_support_extract_dispatch import apply_extractor_by_extension
                metadata: dict[str, Any] = {
                    "meta_source": None, "format": None, "raw_prompt": None,
                    "raw_negative": None, "raw_meta_json": None, "success": False,
                }
                apply_extractor_by_extension(metadata, internal_path, file_bytes)
                _set_a1111_tag_source(metadata)
            except Exception as e:
                logger.warning(f"Failed to extract metadata from RAR: {archive_full_path}: {e}")
                metadata = {"meta_source": "rar_error", "format": "unknown",
                            "raw_prompt": None, "raw_negative": None, "raw_meta_json": None}
        else:
            metadata = {"meta_source": "rar_error", "format": "unknown",
                        "raw_prompt": None, "raw_negative": None, "raw_meta_json": None}
        content_hash = bytes_etag(file_bytes, internal_path) if file_bytes else None

    meta_source = metadata.get('meta_source', 'rar_unknown')
    fmt = metadata.get('format', 'unknown')
    raw_prompt = metadata.get('raw_prompt')
    raw_negative = metadata.get('raw_negative')
    raw_meta_json = metadata.get('raw_meta_json')
    tag_source = metadata.get('tag_source')

    img_width, img_height = extract_resolution(raw_prompt, raw_meta_json)

    if is_utc_meta_source(meta_source):
        mtime = naive_local_to_utc_timestamp(raw_mtime)

    file_id = upsert_file(
        con,
        path_s,
        mtime,
        size,
        meta_source=meta_source,
        content_hash=content_hash,
        is_zip_member=True,
        width=img_width,
        height=img_height,
    )

    tag_extraction_source = tag_source if tag_source else raw_prompt
    if tag_extraction_source:
        parsed = parse_prompt_to_tags(tag_extraction_source, effective_config(config, meta_source))
        file_tag_rows = build_archive_meta_tag_rows(con, file_id, parsed.tags, mtime=mtime)
        replace_archive_meta_tags_if_changed(con, file_id, file_tag_rows)

        template_id = upsert_template(con, file_id, raw_prompt, raw_negative, fmt, raw_meta_json)
        replace_template_tokens(con, template_id, parsed.template_tokens)
    elif raw_meta_json is not None:
        replace_archive_meta_tags_if_changed(con, file_id, [])
        template_id = upsert_template(con, file_id, None, raw_negative, fmt, raw_meta_json)
        replace_template_tokens(con, template_id, [])
    else:
        replace_archive_meta_tags_if_changed(con, file_id, [])

    return ("added" if is_new else "updated", file_id)

"""7z-internal scan worker — batch operations."""

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

from core.infra_core.file_hash import bytes_etag
from core.infra_core.timeout import ARCHIVE_SCAN_TIMEOUT, run_with_timeout
from core.models_core.models_files import upsert_file
from core.models_core.models_templates import replace_template_tokens, upsert_template
from core.parsers.prompt_parse import parse_prompt_to_tags
from core.parsers.prompt_parse_candidates import effective_config
from core.scan.mtime_timezone import (
    correct_mtime_if_utc,
    is_utc_meta_source,
    naive_local_to_utc_timestamp,
)
from core.scan_core.scanner_io import extract_resolution
from core.sevenz_core.sevenz_support_core import batch_7z_info, batch_read_from_7z

from .archive_backfill import apply_hash_backfill_updates
from .archive_tag_diff import build_archive_meta_tag_rows, replace_archive_meta_tags_batch_if_changed

ScanResult = tuple[str, int] | None


def _try_cached_info_7z(
    archive_cache, archive_path: str
) -> dict[str, tuple] | None:
    """Return cached per-member info_map if the archive is unchanged."""
    if archive_cache is None:
        return None
    try:
        from pathlib import Path
        st = Path(archive_path).stat()
        raw = archive_cache.get_members_info(
            archive_path, int(st.st_mtime), st.st_size
        )
        if raw is not None:
            return {k: tuple(v) for k, v in raw.items()}
    except (OSError, Exception):
        logger.debug("scan step failed", exc_info=True)
    return None


def scan_batch_7z(
    con: sqlite3.Connection,
    archive_path: str,
    internal_paths: list[str],
    config: dict[str, Any],
    force: bool,
    *,
    skip_backfill: bool = False,
    archive_cache=None,
) -> list[ScanResult]:
    """Scan multiple files inside a single 7z with batch operations.

    Opens the 7z once for mtime/size, filters via DB prefetch,
    then extracts all changed entries in one pass.

    If *archive_cache* is provided and the archive is unchanged,
    Phase 1 (7z open for mtime/size) is skipped using cached info.
    """
    from core.models_core.models_files import get_file_rows_batch
    from core.sevenz_core.sevenz_support_extract import _set_a1111_tag_source
    from core.zip_core.zip_support_extract_dispatch import (
        apply_extractor_by_extension,
        is_media_metadata_extension,
    )

    from .archive_media_batch import (
        collect_media_backfill_updates,
        extract_media_metadata_and_hash,
        split_media_indices,
    )

    full_paths = [f"{archive_path}!{ip}" for ip in internal_paths]
    results: list[ScanResult] = [None] * len(internal_paths)

    # Phase 1: Try cached info first to avoid opening 7z
    info_map = None
    if not force:
        info_map = _try_cached_info_7z(archive_cache, archive_path)
        if info_map is not None:
            logger.debug("7z Phase 1 skip (cached): %s (%d members)", archive_path, len(internal_paths))

    if info_map is None:
        try:
            info_map = run_with_timeout(
                lambda: batch_7z_info(archive_path, internal_paths),
                timeout=ARCHIVE_SCAN_TIMEOUT,
                label=f"batch_info:{archive_path}",
            )
        except (TimeoutError, Exception) as e:
            logger.warning(f"7z batch info failed: {archive_path}: {e}")
            return results

    # Phase 2: DB prefetch
    db_rows = get_file_rows_batch(con, full_paths)
    from core.schema_core.schema import CURRENT_PARSER_VERSION

    needs_scan: list[int] = []
    needs_backfill_list: list[int] = []

    for idx, ip in enumerate(internal_paths):
        fp = full_paths[idx]
        info = info_map.get(ip)
        if info is None:
            continue
        raw_mtime, size = info
        mtime = correct_mtime_if_utc(con, fp, raw_mtime)

        existing = db_rows.get(fp)
        if existing is not None and not force:
            _fid, old_mtime, old_size, is_deleted, old_hash, old_pv = existing
            if not is_deleted and old_mtime == mtime and old_size == size and old_pv >= CURRENT_PARSER_VERSION:
                if not skip_backfill and old_hash is None:
                    needs_backfill_list.append(idx)
                continue
        needs_scan.append(idx)

    # Phase 2b: Backfill hashes
    if needs_backfill_list:
        media_backfill, regular_backfill = split_media_indices(
            needs_backfill_list, internal_paths, is_media_metadata_extension
        )
        try:
            backfill_bytes = run_with_timeout(
                lambda: batch_read_from_7z(archive_path, [internal_paths[i] for i in regular_backfill]),
                timeout=ARCHIVE_SCAN_TIMEOUT,
                label=f"batch_backfill:{archive_path}",
            ) if regular_backfill else {}
        except (TimeoutError, Exception):
            backfill_bytes = {}
        hash_updates: list[tuple[int, int, str]] = []
        for idx in regular_backfill:
            ip = internal_paths[idx]
            fp = full_paths[idx]
            fb = backfill_bytes.get(ip)
            if fb is not None:
                existing = db_rows.get(fp)
                if existing:
                    content_hash = bytes_etag(fb, ip)
                    if content_hash:
                        file_id = existing[0]
                        hash_updates.append((idx, file_id, content_hash))
        if media_backfill:
            from core.helpers_core.archive_member_temp import extracted_7z_member_path

            hash_updates.extend(
                collect_media_backfill_updates(
                    media_backfill,
                    internal_paths,
                    full_paths,
                    db_rows,
                    lambda ip: extracted_7z_member_path(archive_path, ip),
                )
            )
        if hash_updates:
            backfilled_results = apply_hash_backfill_updates(con, hash_updates)
            for idx, file_id in backfilled_results:
                results[idx] = ("backfilled", file_id)

    if not needs_scan:
        return results

    # Phase 3: Batch extract bytes for entries needing scan
    media_scan, regular_scan = split_media_indices(
        needs_scan, internal_paths, is_media_metadata_extension
    )
    try:
        bytes_map = run_with_timeout(
            lambda: batch_read_from_7z(archive_path, [internal_paths[i] for i in regular_scan]),
            timeout=ARCHIVE_SCAN_TIMEOUT,
            label=f"batch_read:{archive_path}",
        ) if regular_scan else {}
    except (TimeoutError, Exception) as e:
        logger.warning(f"7z batch read failed: {archive_path}: {e}")
        bytes_map = {}

    # Phase 4: Process each entry (batch optimized)
    # 4a: Extract metadata + upsert_file for all entries, collect file_ids
    rows_by_file_id: dict[int, list[tuple[int, int, float, str]]] = {}
    entry_data: list[tuple] = []  # (idx, file_id, is_new, parsed_or_none, metadata)

    for idx in needs_scan:
        ip = internal_paths[idx]
        fp = full_paths[idx]
        info = info_map.get(ip)
        if info is None:
            continue
        raw_mtime, size = info

        is_new = fp not in db_rows

        if idx in media_scan:
            try:
                from core.helpers_core.archive_member_temp import extracted_7z_member_path

                metadata, content_hash = extract_media_metadata_and_hash(
                    ip,
                    lambda inner: extracted_7z_member_path(archive_path, inner),
                    apply_extractor_by_extension,
                    _set_a1111_tag_source,
                )
            except Exception as e:
                logger.warning(f"Metadata extraction failed: {fp}: {e}")
                metadata = {"meta_source": "7z_error", "format": "unknown",
                            "raw_prompt": None, "raw_negative": None, "raw_meta_json": None}
                content_hash = None
        else:
            file_bytes = bytes_map.get(ip)
            if file_bytes is not None:
                try:
                    metadata = {
                        "meta_source": None, "format": None, "raw_prompt": None,
                        "raw_negative": None, "raw_meta_json": None, "success": False,
                    }
                    apply_extractor_by_extension(metadata, ip, file_bytes)
                    _set_a1111_tag_source(metadata)
                except Exception as e:
                    logger.warning(f"Metadata extraction failed: {fp}: {e}")
                    metadata = {"meta_source": "7z_error", "format": "unknown",
                                "raw_prompt": None, "raw_negative": None, "raw_meta_json": None}
            else:
                metadata = {"meta_source": "7z_error", "format": "unknown",
                            "raw_prompt": None, "raw_negative": None, "raw_meta_json": None}
            content_hash = bytes_etag(file_bytes, ip) if file_bytes else None

        meta_source = metadata.get('meta_source', '7z_unknown')
        fmt = metadata.get('format', 'unknown')
        raw_prompt = metadata.get('raw_prompt')
        raw_negative = metadata.get('raw_negative')
        raw_meta_json = metadata.get('raw_meta_json')
        tag_source = metadata.get('tag_source')

        img_width, img_height = extract_resolution(raw_prompt, raw_meta_json)

        mtime = correct_mtime_if_utc(con, fp, raw_mtime)
        if is_utc_meta_source(meta_source):
            mtime = naive_local_to_utc_timestamp(raw_mtime)

        file_id = upsert_file(
            con, fp, mtime, size,
            meta_source=meta_source, content_hash=content_hash,
            is_zip_member=True, width=img_width, height=img_height,
        )

        # Parse tags (CPU work, no DB)
        tag_extraction_source = tag_source if tag_source else raw_prompt
        parsed = None
        if tag_extraction_source:
            parsed = parse_prompt_to_tags(tag_extraction_source, effective_config(config, meta_source))
            rows_by_file_id[file_id] = build_archive_meta_tag_rows(con, file_id, parsed.tags, mtime=mtime)
        else:
            rows_by_file_id[file_id] = []

        entry_data.append((idx, file_id, is_new, parsed, metadata, mtime))

    # 4b: Diff-apply meta tags only for changed entries
    replace_archive_meta_tags_batch_if_changed(con, rows_by_file_id)

    # 4c: Resolve tags (cached) + collect file_tag rows + templates
    for idx, file_id, is_new, parsed, metadata, _mtime in entry_data:
        ip = internal_paths[idx]
        fp = full_paths[idx]
        fmt = metadata.get('format', 'unknown')
        raw_prompt = metadata.get('raw_prompt')
        raw_negative = metadata.get('raw_negative')
        raw_meta_json = metadata.get('raw_meta_json')

        if parsed is not None:
            template_id = upsert_template(con, file_id, raw_prompt, raw_negative, fmt, raw_meta_json)
            replace_template_tokens(con, template_id, parsed.template_tokens)
        elif raw_meta_json is not None:
            template_id = upsert_template(con, file_id, None, raw_negative, fmt, raw_meta_json)
            replace_template_tokens(con, template_id, [])

        results[idx] = ("added" if is_new else "updated", file_id)

    return results

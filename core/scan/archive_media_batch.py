"""Shared helpers for media-aware archive batch scans."""

from __future__ import annotations

import logging

from core.infra_core.file_hash import file_etag

logger = logging.getLogger(__name__)


def split_media_indices(indices, internal_paths, is_media_metadata_extension):
    media = [i for i in indices if is_media_metadata_extension(internal_paths[i])]
    regular = [i for i in indices if i not in media]
    return media, regular


def collect_media_backfill_updates(
    media_indices,
    internal_paths,
    full_paths,
    db_rows,
    open_temp_path,
):
    updates: list[tuple[int, int, str]] = []
    for idx in media_indices:
        ip = internal_paths[idx]
        fp = full_paths[idx]
        existing = db_rows.get(fp)
        if not existing:
            continue
        try:
            with open_temp_path(ip) as extracted:
                content_hash = file_etag(extracted)
            if content_hash:
                updates.append((idx, existing[0], content_hash))
        except Exception as exc:
            logger.debug("archive member skipped, it gets no content hash: %s", exc)
            continue
    return updates


def extract_media_metadata_and_hash(
    internal_path,
    open_temp_path,
    apply_extractor_by_extension,
    set_a1111_tag_source,
):
    metadata = {
        "meta_source": None,
        "format": None,
        "raw_prompt": None,
        "raw_negative": None,
        "raw_meta_json": None,
        "success": False,
    }
    with open_temp_path(internal_path) as extracted:
        apply_extractor_by_extension(metadata, internal_path, extracted)
        content_hash = file_etag(extracted)
    set_a1111_tag_source(metadata)
    return metadata, content_hash

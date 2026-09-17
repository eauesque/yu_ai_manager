"""Media metadata/state handling for file detail payloads.

Separates read (L1 cache resolution) from write (DB state update) to avoid
write-lock contention during scans. Writes are best-effort and do not affect
read results even if the lock cannot be acquired.
"""

import contextlib
import logging
from typing import Any

from core.file_api.detail_media import resolve_readonly_media_metadata
from core.services_core.media_extract_state import (
    queue_media_extract_access_touch,
)
from core.services_core.media_metadata_l1 import resolve_with_l1_cache
from core.services_core.media_payload_service import queue_deferred_media_writes

logger = logging.getLogger(__name__)


def resolve_media_payload(file_row, *, skip_deferred_writes: bool = False) -> dict[str, Any]:
    """Resolve media metadata (read-only).

    Resolves from L1 cache; auxiliary writes run in a background thread.

    `skip_deferred_writes` is for inspect callers using an in-memory DB.
    The file_id from :memory: collides with production rows, so deferred
    writes that target get_db() must be suppressed.
    """
    file_id = int(file_row["id"])
    mtime = int(file_row["mtime"])
    size = int(file_row["size"])
    content_hash = str(file_row["hash"]) if file_row["hash"] is not None else None
    raw_meta_json = file_row["raw_meta_json"]

    resolved = resolve_with_l1_cache(
        file_id=file_id,
        meta_source=str(file_row["meta_source"] or ""),
        mtime=mtime,
        size=size,
        content_hash=content_hash,
        raw_meta_json=raw_meta_json,
        resolver=resolve_readonly_media_metadata,
    )
    readonly_media_metadata = resolved["metadata"]
    normalized_json = resolved["normalized_json"]
    schedule_reextract = bool(resolved["schedule_reextract"])

    # Run write operations in background (avoid lock contention during scan)
    # Access touch is queued independently so frequent reads are coalesced.
    if not skip_deferred_writes:
        with contextlib.suppress(Exception):
            queue_media_extract_access_touch(file_id)

        if normalized_json is not None or schedule_reextract:
            queue_deferred_media_writes(
                file_id, mtime, size, content_hash, normalized_json,
                schedule_reextract, readonly_media_metadata,
            )

    # If normalized_json exists, return the normalized value
    if normalized_json is not None:
        raw_meta_json = normalized_json

    return {
        "raw_meta_json": raw_meta_json,
        "readonly_media_metadata": readonly_media_metadata,
    }

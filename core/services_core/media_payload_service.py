"""Background write helpers for file detail media payloads."""

from __future__ import annotations

import logging
from typing import Any

from core.services_core.media_extract_state import (
    mark_media_extract_schema_ready,
    mark_media_extract_state_stale,
)

logger = logging.getLogger(__name__)


def queue_deferred_media_writes(
    file_id: int,
    mtime: int,
    size: int,
    content_hash: str | None,
    normalized_json: str | None,
    schedule_reextract: bool,
    readonly_media_metadata: dict[str, Any] | None,
) -> None:
    """Queue auxiliary media metadata/state writes on the DB writer thread."""
    from core.services_core.db_api import get_db
    from core.services_core.db_write import submit_db_write_no_wait

    try:
        def _write() -> None:
            try:
                con = get_db()
                if normalized_json is not None:
                    con.execute(
                        "UPDATE templates SET raw_meta_json=? WHERE file_id=?",
                        (normalized_json, file_id),
                    )
                    if readonly_media_metadata:
                        mark_media_extract_schema_ready(
                            con,
                            file_id,
                            metadata_schema_version=int(readonly_media_metadata.get("metadata_schema_version") or 1),
                            metadata_source=str(readonly_media_metadata.get("metadata_source") or "ffprobe"),
                            metadata_source_version=str(readonly_media_metadata.get("metadata_source_version") or ""),
                            mtime=mtime,
                            size=size,
                            content_hash=content_hash,
                        )
                elif schedule_reextract:
                    mark_media_extract_state_stale(
                        con,
                        file_id,
                        mtime=mtime,
                        size=size,
                        content_hash=content_hash,
                    )
                con.commit()
            except Exception as exc:
                if "database is locked" in str(exc).lower():
                    logger.debug("deferred media write skipped (DB locked): file_id=%d", file_id)
                else:
                    logger.warning("deferred media write failed: file_id=%d: %s", file_id, exc)

        submit_db_write_no_wait(_write)
    except Exception as exc:
        if "database is locked" in str(exc).lower():
            logger.debug("deferred media write skipped (DB locked): file_id=%d", file_id)
        else:
            logger.warning("deferred media write failed: file_id=%d: %s", file_id, exc)

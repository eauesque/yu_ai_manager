"""Persist read-only media extraction lifecycle state."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger(__name__)


def _to_int(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def _safe_load_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except Exception as exc:
        logger.debug("Failed to parse JSON media state: %s", exc)
    return {}


def upsert_media_extract_state(
    con: sqlite3.Connection,
    file_id: int,
    meta_source: str,
    raw_meta_json: str | None,
) -> None:
    if not str(meta_source or "").startswith("media_"):
        return

    payload = _safe_load_json(raw_meta_json)
    fp = payload.get("fingerprint") if isinstance(payload.get("fingerprint"), dict) else {}
    cache_state = str(payload.get("cache_state") or ("error" if "error" in meta_source else "ready"))
    error_code = payload.get("error_code")
    error_at = _to_int(payload.get("error_at"))
    next_retry_after = _to_int(payload.get("next_retry_after"))
    meta_schema_version = _to_int(payload.get("metadata_schema_version"))
    extracted_at_in = _to_int(payload.get("metadata_extracted_at"))
    metadata_source = str(payload.get("metadata_source") or "ffprobe")
    metadata_source_version = str(payload.get("metadata_source_version") or "")
    fingerprint_mtime = _to_int(fp.get("mtime"))
    fingerprint_size = _to_int(fp.get("size"))
    fingerprint_hash = fp.get("hash")
    if fingerprint_hash is not None:
        fingerprint_hash = str(fingerprint_hash)

    current = con.execute(
        """
        SELECT
          cache_state,
          metadata_schema_version,
          metadata_extracted_at,
          metadata_source,
          metadata_source_version,
          fingerprint_mtime,
          fingerprint_size,
          fingerprint_hash,
          error_code,
          error_at,
          error_count,
          next_retry_after
        FROM media_extract_state
        WHERE file_id=?
        """,
        (file_id,),
    ).fetchone()
    prev_error_count = int(current[10]) if current and current[10] is not None else 0
    error_count = prev_error_count + 1 if cache_state == "error" else 0
    extracted_at = extracted_at_in
    if extracted_at is None:
        extracted_at = int(current[2]) if current and current[2] is not None else int(time.time())

    # Avoid no-op UPDATE for repeated identical media-ready rows.
    if current:
        same_ready = (
            str(current[0] or "") == cache_state
            and _to_int(current[1]) == meta_schema_version
            and _to_int(current[2]) == extracted_at
            and str(current[3] or "") == metadata_source
            and str(current[4] or "") == metadata_source_version
            and _to_int(current[5]) == fingerprint_mtime
            and _to_int(current[6]) == fingerprint_size
            and ((str(current[7]) if current[7] is not None else None) == fingerprint_hash)
            and ((str(current[8]) if current[8] is not None else None) == (str(error_code) if error_code else None))
            and _to_int(current[9]) == error_at
            and _to_int(current[10]) == error_count
            and _to_int(current[11]) == next_retry_after
        )
        if same_ready:
            return
    ts_now = int(time.time())

    con.execute(
        """
        INSERT INTO media_extract_state(
          file_id, cache_state, metadata_schema_version, metadata_extracted_at,
          metadata_source, metadata_source_version,
          fingerprint_mtime, fingerprint_size, fingerprint_hash,
          error_code, error_at, error_count, next_retry_after, last_access_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id) DO UPDATE SET
          cache_state=excluded.cache_state,
          metadata_schema_version=excluded.metadata_schema_version,
          metadata_extracted_at=excluded.metadata_extracted_at,
          metadata_source=excluded.metadata_source,
          metadata_source_version=excluded.metadata_source_version,
          fingerprint_mtime=excluded.fingerprint_mtime,
          fingerprint_size=excluded.fingerprint_size,
          fingerprint_hash=excluded.fingerprint_hash,
          error_code=excluded.error_code,
          error_at=excluded.error_at,
          error_count=excluded.error_count,
          next_retry_after=excluded.next_retry_after,
          updated_at=excluded.updated_at
        """,
        (
            file_id,
            cache_state,
            meta_schema_version,
            extracted_at,
            metadata_source,
            metadata_source_version,
            fingerprint_mtime,
            fingerprint_size,
            fingerprint_hash,
            str(error_code) if error_code else None,
            error_at,
            error_count,
            next_retry_after,
            ts_now,
            ts_now,
        ),
    )

"""Operations for media_extract_state lifecycle and access tracking."""

from __future__ import annotations

import contextlib
import sqlite3
import time
from threading import Condition, Lock, Thread

ACCESS_TOUCH_MIN_INTERVAL_SEC = 60
_TOUCH_FLUSH_INTERVAL = 1.0
_TOUCH_BATCH_SIZE = 256
_touch_pending: set[int] = set()
_touch_cv = Condition(Lock())
_touch_worker_started = False


def _now_ts() -> int:
    return int(time.time())


def _is_nonfatal_media_state_error(exc: sqlite3.OperationalError) -> bool:
    """Return True for recoverable media state write errors.

    media_extract_state is an auxiliary cache/state table. Read APIs must not fail
    when this table is unavailable or temporarily locked.
    """
    msg = str(exc).lower()
    return (
        "database is locked" in msg
        or "no such table: media_extract_state" in msg
        or "no such column" in msg
        or "has no column named" in msg
    )


def touch_media_extract_access(con: sqlite3.Connection, file_id: int) -> None:
    """Update last_access_at for an existing media_extract_state row."""
    ts = _now_ts()
    try:
        con.execute(
            """
            UPDATE media_extract_state
            SET last_access_at=?, updated_at=?
            WHERE file_id=?
              AND (last_access_at IS NULL OR last_access_at<?)
            """,
            (ts, ts, file_id, ts - ACCESS_TOUCH_MIN_INTERVAL_SEC),
        )
    except Exception as exc:
        if not _is_nonfatal_media_state_error(exc):
            raise


def touch_media_extract_access_batch(
    con: sqlite3.Connection, file_ids: list[int],
) -> None:
    """Batch-update last_access_at for existing rows (best-effort)."""
    if not file_ids:
        return
    ts = _now_ts()
    params = [(ts, ts, int(fid), ts - ACCESS_TOUCH_MIN_INTERVAL_SEC) for fid in file_ids]
    try:
        con.executemany(
            """
            UPDATE media_extract_state
            SET last_access_at=?, updated_at=?
            WHERE file_id=?
              AND (last_access_at IS NULL OR last_access_at<?)
            """,
            params,
        )
    except Exception as exc:
        if not _is_nonfatal_media_state_error(exc):
            raise


def _flush_touch_batch(batch: list[int]) -> None:
    from core.services_core.db_api import get_db
    from core.services_core.db_write import submit_db_write

    def _write() -> None:
        con = get_db()
        touch_media_extract_access_batch(con, batch)
        con.commit()

    submit_db_write(_write)


def _touch_worker_loop() -> None:
    while True:
        with _touch_cv:
            if not _touch_pending:
                _touch_cv.wait()
            if not _touch_pending:
                continue
            _touch_cv.wait(timeout=_TOUCH_FLUSH_INTERVAL)
            batch = list(_touch_pending)[:_TOUCH_BATCH_SIZE]
            for fid in batch:
                _touch_pending.discard(fid)
        if batch:
            with contextlib.suppress(Exception):
                _flush_touch_batch(batch)


def _ensure_touch_worker() -> None:
    global _touch_worker_started
    with _touch_cv:
        if _touch_worker_started:
            return
        Thread(target=_touch_worker_loop, daemon=True, name="media-touch-batch").start()
        _touch_worker_started = True


def queue_media_extract_access_touch(file_id: int) -> None:
    """Queue media last-access touch for batched writer flush."""
    _ensure_touch_worker()
    with _touch_cv:
        _touch_pending.add(int(file_id))
        _touch_cv.notify()


def mark_media_extract_state_stale(
    con: sqlite3.Connection,
    file_id: int,
    *,
    mtime: int,
    size: int,
    content_hash: str | None = None,
) -> None:
    """Mark extracted media metadata as stale before re-extraction."""
    ts = _now_ts()
    try:
        con.execute(
            """
            INSERT INTO media_extract_state(
              file_id, cache_state, metadata_schema_version, metadata_extracted_at,
              metadata_source, metadata_source_version, fingerprint_mtime, fingerprint_size,
              fingerprint_hash, error_code, error_at, error_count, next_retry_after, last_access_at, updated_at
            ) VALUES (?, 'none', NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, 0, NULL, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
              cache_state='none',
              fingerprint_mtime=excluded.fingerprint_mtime,
              fingerprint_size=excluded.fingerprint_size,
              fingerprint_hash=excluded.fingerprint_hash,
              updated_at=excluded.updated_at
            WHERE media_extract_state.cache_state IS NOT 'none'
               OR media_extract_state.fingerprint_mtime IS NOT excluded.fingerprint_mtime
               OR media_extract_state.fingerprint_size IS NOT excluded.fingerprint_size
               OR media_extract_state.fingerprint_hash IS NOT excluded.fingerprint_hash
            """,
            (file_id, int(mtime), int(size), content_hash, ts, ts),
        )
    except Exception as exc:
        if not _is_nonfatal_media_state_error(exc):
            raise


def mark_media_extract_schema_ready(
    con: sqlite3.Connection,
    file_id: int,
    *,
    metadata_schema_version: int,
    metadata_source: str,
    metadata_source_version: str,
    mtime: int,
    size: int,
    content_hash: str | None = None,
) -> None:
    """Persist schema/version reconciliation result without waiting for next scan."""
    ts = _now_ts()
    try:
        con.execute(
            """
            INSERT INTO media_extract_state(
              file_id, cache_state, metadata_schema_version, metadata_extracted_at,
              metadata_source, metadata_source_version, fingerprint_mtime, fingerprint_size,
              fingerprint_hash, error_code, error_at, error_count, next_retry_after, last_access_at, updated_at
            ) VALUES (?, 'ready', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, NULL, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
              cache_state='ready',
              metadata_schema_version=excluded.metadata_schema_version,
              metadata_extracted_at=excluded.metadata_extracted_at,
              metadata_source=excluded.metadata_source,
              metadata_source_version=excluded.metadata_source_version,
              fingerprint_mtime=excluded.fingerprint_mtime,
              fingerprint_size=excluded.fingerprint_size,
              fingerprint_hash=excluded.fingerprint_hash,
              error_code=NULL,
              error_at=NULL,
              error_count=0,
              next_retry_after=NULL,
              updated_at=excluded.updated_at
            WHERE media_extract_state.cache_state IS NOT 'ready'
               OR media_extract_state.metadata_schema_version IS NOT excluded.metadata_schema_version
               OR media_extract_state.metadata_extracted_at IS NOT excluded.metadata_extracted_at
               OR media_extract_state.metadata_source IS NOT excluded.metadata_source
               OR media_extract_state.metadata_source_version IS NOT excluded.metadata_source_version
               OR media_extract_state.fingerprint_mtime IS NOT excluded.fingerprint_mtime
               OR media_extract_state.fingerprint_size IS NOT excluded.fingerprint_size
               OR media_extract_state.fingerprint_hash IS NOT excluded.fingerprint_hash
               OR media_extract_state.error_code IS NOT NULL
               OR media_extract_state.error_at IS NOT NULL
               OR media_extract_state.error_count IS NOT 0
               OR media_extract_state.next_retry_after IS NOT NULL
            """,
            (
                file_id,
                int(metadata_schema_version),
                ts,
                str(metadata_source or "ffprobe"),
                str(metadata_source_version or ""),
                int(mtime),
                int(size),
                content_hash,
                ts,
                ts,
            ),
        )
    except Exception as exc:
        if not _is_nonfatal_media_state_error(exc):
            raise

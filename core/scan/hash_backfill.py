"""Independent hash backfill job -- computes hashes in the background, separate from scan.

Automatically pauses during scans and resumes after completion.
Progress is persisted in hash_backfill_state.json so it can resume from where it left off after restart.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from core.event_bus import emit
from core.event_bus.event_types import HASH_BACKFILL_COMPLETE, HASH_BACKFILL_PROGRESS
from core.infra_core.file_hash import file_etag
from core.services_core.db_api import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)

_BATCH_SIZE = 200
_WRITE_BATCH_SIZE = 50
_SLEEP_BETWEEN_BATCHES = 0.5  # seconds
_SLEEP_BETWEEN_FILES = 0.005  # seconds
_PROGRESS_EMIT_INTERVAL = 3.0  # seconds

# Scan coordination: pause during scan
_pause_event = threading.Event()
_pause_event.set()  # Initial state is "running"

_STATE_FILE = "hash_backfill_state.json"


def pause_backfill() -> None:
    """Called at scan start -- pause the backfill."""
    _pause_event.clear()
    logger.debug("hash backfill paused (scan started)")


def resume_backfill() -> None:
    """Called on scan completion/error -- resume the backfill."""
    _pause_event.set()
    logger.debug("hash backfill resumed (scan ended)")


def _state_path() -> Path:
    """Path to hash_backfill_state.json (parent directory of core/)."""
    return Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / _STATE_FILE


def _save_progress(last_id: int, computed: int, total: int) -> None:
    state = {
        "last_id": last_id,
        "computed": computed,
        "total": total,
        "updated_at": time.time(),
    }
    try:
        p = _state_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(p))
    except Exception as e:
        logger.debug("hash_backfill state save failed: %s", e)


def _load_progress() -> dict[str, Any] | None:
    p = _state_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "last_id" in data:
            return data
    except Exception as e:
        logger.debug("hash_backfill state load failed: %s", e)
    return None


def _clear_progress() -> None:
    p = _state_path()
    try:
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.debug("hash_backfill state clear failed: %s", e)


def _compute_hash_for_file(file_id: int, path: str) -> tuple[int, str] | None:
    """Compute hash for a single file. Returns (file_id, hash) on success."""
    try:
        p = Path(path)
        if not p.exists():
            return None
        h = file_etag(p)
        if h:
            return (file_id, h)
    except Exception as e:
        logger.debug("hash compute failed for id=%d path=%s: %s", file_id, path, e)
    return None


def _flush_hash_updates(updates: list[tuple[int, str]]) -> int:
    """Persist a batch of (file_id, hash) updates via the serialized DB writer."""
    if not updates:
        return 0

    def _write() -> int:
        con = get_db()
        con.executemany("UPDATE files SET hash=? WHERE id=?", [(h, fid) for fid, h in updates])
        con.commit()
        return len(updates)

    return submit_db_write(_write)


def run_hash_backfill(job=None) -> dict[str, Any]:
    """Main backfill loop. Called from a background thread."""
    from core.scan.runtime_execute_helpers import _lower_io_priority
    _lower_io_priority()

    read_con = get_readonly_db()

    # Get total count
    total_row = read_con.execute(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND hash IS NULL"
    ).fetchone()
    total = total_row[0] if total_row else 0

    if total == 0:
        _clear_progress()
        if job:
            job.complete("backfill 不要 (全ファイルにハッシュあり)")
        return {"computed": 0, "total": 0, "status": "no_work"}

    # Restore previous progress
    prev = _load_progress()
    last_id = prev["last_id"] if prev else 0
    computed = prev.get("computed", 0) if prev else 0

    if job:
        job.update(phase="backfilling", message=f"hash backfill: {total} files")
        job.progress(computed, total + computed)

    logger.info(f"hash backfill started: {total} files pending (resume from id>{last_id})")

    last_emit = 0.0
    pending_updates: list[tuple[int, str]] = []

    while True:
        # Pause during scan
        if not _pause_event.wait(timeout=1.0):
            if job and job.cancelled:
                break
            continue

        if job and job.cancelled:
            _save_progress(last_id, computed, total)
            if pending_updates:
                _flush_hash_updates(pending_updates)
                pending_updates.clear()
            if job:
                job.complete_cancelled(f"hash backfill 中断: {computed} 件処理済み")
            return {"computed": computed, "total": total, "status": "cancelled"}

        rows = read_con.execute(
            "SELECT id, path FROM files "
            "WHERE is_deleted=0 AND hash IS NULL AND id > ? "
            "ORDER BY id LIMIT ?",
            (last_id, _BATCH_SIZE),
        ).fetchall()

        if not rows:
            break

        for row in rows:
            # Pause check (also within batch)
            _pause_event.wait()

            if job and job.cancelled:
                _save_progress(last_id, computed, total)
                if pending_updates:
                    _flush_hash_updates(pending_updates)
                    pending_updates.clear()
                job.complete_cancelled(f"hash backfill 中断: {computed} 件処理済み")
                return {"computed": computed, "total": total, "status": "cancelled"}

            fid = row[0] if not hasattr(row, "keys") else row["id"]
            fpath = row[1] if not hasattr(row, "keys") else row["path"]
            update_item = _compute_hash_for_file(fid, fpath)
            if update_item is not None:
                computed += 1
                pending_updates.append(update_item)

            last_id = fid

            if len(pending_updates) >= _WRITE_BATCH_SIZE:
                _flush_hash_updates(pending_updates)
                pending_updates.clear()
                _save_progress(last_id, computed, total)

            if job:
                job.progress(computed, total + computed)

            now = time.time()
            if now - last_emit >= _PROGRESS_EMIT_INTERVAL:
                last_emit = now
                pct = int(computed * 100 / total) if total > 0 else 0
                emit(HASH_BACKFILL_PROGRESS, {
                    "computed": computed, "total": total, "percent": pct,
                    "job_id": getattr(job, "job_id", "hash-backfill"),
                }, source="hash_backfill")

            if _SLEEP_BETWEEN_FILES > 0:
                time.sleep(_SLEEP_BETWEEN_FILES)

    if _SLEEP_BETWEEN_BATCHES > 0:
        time.sleep(_SLEEP_BETWEEN_BATCHES)

    if pending_updates:
        _flush_hash_updates(pending_updates)
        pending_updates.clear()
    _clear_progress()

    emit(HASH_BACKFILL_COMPLETE, {
        "computed": computed, "total": total,
        "job_id": getattr(job, "job_id", "hash-backfill"),
    }, source="hash_backfill")

    msg = f"hash backfill 完了: {computed} 件のハッシュを計算"
    logger.info(msg)
    if job:
        job.complete(msg)

    return {"computed": computed, "total": total, "status": "complete"}


def get_backfill_status() -> dict[str, Any]:
    """Return the current backfill status (for API use)."""
    from core.jobs_core.jobs import job_manager

    running = job_manager.is_running("hash-backfill")
    prev = _load_progress()

    pending = 0
    try:
        con = get_readonly_db()
        row = con.execute(
            "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND hash IS NULL"
        ).fetchone()
        pending = row[0] if row else 0
    except Exception:
        logger.debug("scan step failed", exc_info=True)

    return {
        "running": running,
        "pending": pending,
        "computed": prev.get("computed", 0) if prev else 0,
        "last_id": prev.get("last_id", 0) if prev else 0,
        "paused": not _pause_event.is_set(),
    }

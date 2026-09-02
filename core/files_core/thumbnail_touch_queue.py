"""Touch throttling and batch-flush helpers for thumbnails."""

import logging
import time
from pathlib import Path
from threading import Condition, Lock, Thread

from core.services_core.cache_index import touch_thumbnail_cache_entries_batch_prepared

logger = logging.getLogger(__name__)

_touch_cooldown: dict[int, float] = {}
_touch_lock = Lock()
_TOUCH_INTERVAL = 300
_TOUCH_MAX_ENTRIES = 10000
_TOUCH_FLUSH_INTERVAL = 1.0
_TOUCH_BATCH_SIZE = 256
_touch_pending: dict[str, tuple[int, Path]] = {}
_touch_cv = Condition(Lock())
_touch_worker_started = False


def _should_touch(file_id: int) -> bool:
    now = time.monotonic()
    with _touch_lock:
        last = _touch_cooldown.get(file_id)
        if last and now - last < _TOUCH_INTERVAL:
            return False
        if len(_touch_cooldown) >= _TOUCH_MAX_ENTRIES:
            _touch_cooldown.clear()
        _touch_cooldown[file_id] = now
    return True


def _flush_touch_batch(batch: list[tuple[int, Path]]) -> None:
    """Pre-stat batch on the queue worker, then submit only SQL to the writer.

    Doing `Path.stat()` on the single SQLite writer thread blocks all other
    writes for 250-340 ms per 256-entry batch on Windows NTFS (observed in
    debug_log). We move the disk syscalls off that thread so the writer just
    runs `executemany` + commit (typically <10 ms).
    """
    from core.services_core.db_api import get_db
    from core.services_core.db_write import submit_db_write

    prepared: list[tuple[str, str, int, int]] = []
    for file_id, cache_path in batch:
        try:
            st = cache_path.stat()
        except (FileNotFoundError, NotADirectoryError, OSError):
            continue
        # Mode check via st_mode bit; avoids a second stat() that
        # cache_path.is_file() would do.
        import stat as _stat
        if not _stat.S_ISREG(st.st_mode):
            continue
        prepared.append((cache_path.name, str(cache_path), int(file_id), int(st.st_size)))

    if not prepared:
        return

    try:
        def _write() -> None:
            con = get_db()
            try:
                touch_thumbnail_cache_entries_batch_prepared(con, prepared)
                con.commit()
            except Exception:
                # The writer connection is now long-lived (v4.128.24); a
                # half-applied executemany would otherwise leak rows into the
                # next batch's commit on the cached connection.
                con.rollback()
                raise

        submit_db_write(_write)
    except Exception:
        logger.debug("touch batch submit failed", exc_info=True)
        return


def _touch_worker_loop() -> None:
    while True:
        with _touch_cv:
            if not _touch_pending:
                _touch_cv.wait()
            if not _touch_pending:
                continue
            _touch_cv.wait(timeout=_TOUCH_FLUSH_INTERVAL)
            items = list(_touch_pending.items())[:_TOUCH_BATCH_SIZE]
            for key, _ in items:
                _touch_pending.pop(key, None)
        batch = [value for _, value in items]
        if batch:
            _flush_touch_batch(batch)


def _ensure_touch_worker() -> None:
    global _touch_worker_started
    with _touch_cv:
        if _touch_worker_started:
            return
        Thread(target=_touch_worker_loop, daemon=True).start()
        _touch_worker_started = True


def queue_touch(file_id: int, cache_path: Path) -> None:
    if not _should_touch(file_id):
        return
    _ensure_touch_worker()
    with _touch_cv:
        _touch_pending[cache_path.name] = (int(file_id), cache_path)
        _touch_cv.notify()

"""Throttled background backfill helper.

A generic version of the sweep history backfill (v4.183.1). Use this any
time a migration introduces a new derived table / column whose population
depends on data that's expensive to compute (XMP reads, ONNX inference,
external API calls, etc.) and you don't want to block startup or hammer
the I/O subsystem.

Three things you provide:

* a unique ``name`` (used to namespace ``db_meta`` keys: ``<name>_cursor``,
  ``<name>_done``, ``<name>_started_at``)
* ``candidate_sql`` — an SQL query that takes ``(cursor, limit)`` bind
  parameters and returns rows ordered by the cursor column (typically
  ``files.id``). The first column of each row must be the cursor value.
* ``processor`` — ``(con, row) -> dict`` returning a stats delta. Whatever
  keys you put in there get summed into the run-total log line.

Everything else (cursor persistence, done flag, chunk loop, daemon
thread, graceful stop, resume after crash) is handled by the helper.

Example::

    task = BackfillTask(
        name="sweeps_backfill",
        candidate_sql=(
            "SELECT id, path, has_sweep FROM files "
            "WHERE id > ? AND is_deleted = 0 "
            "  AND path NOT LIKE '%!%' AND ("
            "    path LIKE '%.png' OR path LIKE '%.webp')"
            "ORDER BY id LIMIT ?"
        ),
        processor=_scan_one_for_sweep,
    )
    task.schedule()  # idempotent — safe to call from @app.before_serving
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

ProcessorFn = Callable[[Any, Any], "dict[str, int]"]
"""``(con, row) -> {stat_key: delta, ...}``. Free-form keys; helper sums."""


class BackfillTask:
    def __init__(
        self,
        *,
        name: str,
        candidate_sql: str,
        processor: ProcessorFn,
        chunk_size: int = 50,
        batch_sleep: float = 0.1,
        log_every: int = 50,
    ) -> None:
        self.name = name
        self.candidate_sql = candidate_sql
        self.processor = processor
        self.chunk_size = chunk_size
        self.batch_sleep = batch_sleep
        self.log_every = log_every

        self._cursor_key = f"{name}_cursor"
        self._done_key = f"{name}_done"
        self._started_key = f"{name}_started_at"

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # --- public API ------------------------------------------------------

    def schedule(self) -> None:
        """Idempotent. Spawns the daemon thread on first call."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._runner, name=self.name, daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the worker to stop after the current chunk."""
        self._stop_event.set()

    def is_done(self, con) -> bool:
        from core.services_core.db_meta import get_meta
        return (get_meta(con, self._done_key) or "") == "1"

    # --- internals -------------------------------------------------------

    def _read_cursor(self, con) -> int:
        from core.services_core.db_meta import get_meta_int
        return get_meta_int(con, self._cursor_key, 0)

    def _write_cursor(self, con, fid: int) -> None:
        from core.services_core.db_meta import set_meta
        set_meta(con, self._cursor_key, str(fid))

    def _mark_done(self, con) -> None:
        from core.services_core.db_meta import set_meta
        set_meta(con, self._done_key, "1")

    def _ensure_started(self, con) -> None:
        from core.services_core.db_meta import get_meta, set_meta
        if not get_meta(con, self._started_key):
            set_meta(con, self._started_key, str(int(time.time())))

    def _process_chunk(self, con, cursor: int) -> tuple[int, dict[str, int]]:
        """Run one chunk. Returns ``(last_cursor, stats_delta)``.

        ``last_cursor`` is the largest first-column value seen. When it
        equals ``cursor`` and stats are all zero, the loop is finished.
        """
        rows = con.execute(self.candidate_sql, (cursor, self.chunk_size)).fetchall()
        if not rows:
            return (cursor, {})
        stats: dict[str, int] = {}
        last_cursor = cursor
        for r in rows:
            if self._stop_event.is_set():
                break
            try:
                cur_val = int(r[0])
            except (TypeError, ValueError):
                continue
            if cur_val > last_cursor:
                last_cursor = cur_val
            try:
                delta = self.processor(con, r) or {}
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s: processor error at id=%s: %s",
                             self.name, cur_val, exc)
                continue
            for k, v in delta.items():
                stats[k] = stats.get(k, 0) + int(v)
        return (last_cursor, stats)

    def _runner(self) -> None:
        # All DB I/O is funneled through submit_db_write so the SQLite
        # single-writer guarantee is preserved. The daemon thread itself
        # never opens a raw connection — that previously caused
        # SQLITE_BUSY contention with the dedicated writer thread.
        from core.services_core.db_write import submit_db_write

        def _check_done_or_init() -> bool:
            from core.services_core.db_state import get_raw_db
            con = get_raw_db()
            if self.is_done(con):
                return True
            self._ensure_started(con)
            con.commit()
            return False

        try:
            already_done = submit_db_write(_check_done_or_init)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: cannot open DB: %s", self.name, exc)
            return
        if already_done:
            logger.debug("%s: already done", self.name)
            return

        def _read_cursor_w() -> int:
            from core.services_core.db_state import get_raw_db
            return self._read_cursor(get_raw_db())

        try:
            cursor = submit_db_write(_read_cursor_w)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: cannot read cursor: %s", self.name, exc)
            return

        totals: dict[str, int] = {}
        chunks = 0
        t0 = time.perf_counter()
        logger.info("%s: starting at cursor=%d", self.name, cursor)

        while not self._stop_event.is_set():
            def _do_chunk(c: int) -> tuple[int, dict[str, int]]:
                from core.services_core.db_state import get_raw_db
                con = get_raw_db()
                last_cursor, delta = self._process_chunk(con, c)
                if last_cursor != c or delta:
                    try:
                        self._write_cursor(con, last_cursor)
                        con.commit()
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("%s: cursor write failed: %s", self.name, exc)
                return last_cursor, delta

            try:
                last_cursor, delta = submit_db_write(_do_chunk, cursor)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s: chunk failed at cursor=%d: %s",
                               self.name, cursor, exc)
                time.sleep(self.batch_sleep * 5)
                continue
            if last_cursor == cursor and not delta:
                def _mark() -> None:
                    from core.services_core.db_state import get_raw_db
                    con = get_raw_db()
                    self._mark_done(con)
                    con.commit()

                try:
                    submit_db_write(_mark)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("%s: mark_done failed: %s", self.name, exc)
                logger.info(
                    "%s: done. totals=%s chunks=%d elapsed=%.1fs",
                    self.name, totals, chunks, time.perf_counter() - t0,
                )
                return
            cursor = last_cursor
            for k, v in delta.items():
                totals[k] = totals.get(k, 0) + v
            chunks += 1
            if chunks % self.log_every == 0:
                logger.info(
                    "%s: cursor=%d totals=%s chunks=%d",
                    self.name, cursor, totals, chunks,
                )
            time.sleep(self.batch_sleep)

        logger.info("%s: stopped at cursor=%d", self.name, cursor)


__all__ = ["BackfillTask", "ProcessorFn"]

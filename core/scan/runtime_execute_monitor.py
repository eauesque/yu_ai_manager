import contextlib
import logging
import time

from core.event_bus import emit
from core.event_bus.event_types import SCAN_PROGRESS
from core.scan_core.scan_state import save_scan_state

from .runtime_execute_helpers import (
    PROGRESS_THROTTLE,
    STATE_SAVE_INTERVAL,
    WAL_CHECKPOINT_INTERVAL,
)

logger = logging.getLogger(__name__)


class ScanLoopMonitor:
    def __init__(
        self,
        con,
        job,
        *,
        root_path: str,
        recursive: bool,
        force: bool,
        scan_zips: bool,
        total_files: int,
        started_at: float,
        commit_min_changes: int = 1,
        commit_max_defer_sec: float = 5.0,
    ):
        self.con = con
        self.job = job
        self.root_path = root_path
        self.recursive = recursive
        self.force = force
        self.scan_zips = scan_zips
        self.total_files = total_files
        self.started_at = started_at
        self.last_progress_emit = 0.0
        self.last_commit_at = 0
        self.last_commit_count = 0
        self.last_commit_total_changes = int(getattr(self.con, "total_changes", 0))
        self.commit_min_changes = max(1, int(commit_min_changes))
        self.commit_max_defer_sec = max(0.0, float(commit_max_defer_sec))
        self._supports_total_changes = hasattr(self.con, "total_changes")

    def save_state(self, current: int) -> None:
        save_scan_state(
            self.root_path,
            self.recursive,
            self.force,
            self.scan_zips,
            current=current,
            total=self.total_files,
            started_at=self.started_at,
        )

    def check_cancelled(self, current: int) -> bool:
        if not self.job.cancelled:
            return False
        self.commit_now(current)
        self.save_state(current)
        return True

    def _has_write_since_last_commit(self) -> bool:
        if not self._supports_total_changes:
            # Fallback for non-sqlite test doubles: preserve prior commit semantics.
            return True
        return int(getattr(self.con, "total_changes", 0)) > self.last_commit_total_changes

    def _write_delta(self) -> int:
        if not self._supports_total_changes:
            return self.commit_min_changes
        return max(0, int(getattr(self.con, "total_changes", 0)) - self.last_commit_total_changes)

    def commit_now(self, current: int | None = None, *, force: bool = False) -> None:
        if not force and not self._has_write_since_last_commit():
            if current is not None:
                self.last_commit_count = current
            return
        self.con.commit()
        self.last_commit_at = time.time()
        self.last_commit_total_changes = int(getattr(self.con, "total_changes", 0))
        if current is not None:
            self.last_commit_count = current

    def commit_if_due(self, current: int, interval: int) -> None:
        if interval <= 0 or current <= 0:
            return
        # `count` can jump by archive batch size; modulo-based checks can miss commit points.
        if (current - self.last_commit_count) >= interval:
            if self._has_write_since_last_commit():
                write_delta = self._write_delta()
                elapsed = (time.time() - self.last_commit_at) if self.last_commit_at else float("inf")
                if write_delta < self.commit_min_changes and elapsed < self.commit_max_defer_sec:
                    self.last_commit_count = current
                    return
            self.commit_now(current)

    def emit_progress(self, current: int, detail: str) -> None:
        now = time.time()
        if now - self.last_progress_emit < PROGRESS_THROTTLE:
            return
        self.last_progress_emit = now
        pct = int(current * 100 / self.total_files) if self.total_files else 0
        emit(
            SCAN_PROGRESS,
            {
                "current": current,
                "total": self.total_files,
                "percent": pct,
                "job_id": getattr(self.job, "job_id", "scan"),
                "label": getattr(self.job, "label", None),
                "detail": detail,
            },
            source="scan",
        )

    def run_periodic_maintenance(self, current: int, backfilled: int) -> None:
        if current % WAL_CHECKPOINT_INTERVAL == 0:
            self._wal_checkpoint_passive()
        if current % STATE_SAVE_INTERVAL == 0:
            if backfilled > 0:
                logger.info(
                    "hash backfill progress: %d hashes computed (%d/%d files)",
                    backfilled,
                    current,
                    self.total_files,
                )
            self.save_state(current)

    def _wal_checkpoint_passive(self) -> None:
        with contextlib.suppress(Exception):
            self.con.execute("PRAGMA wal_checkpoint(PASSIVE)")

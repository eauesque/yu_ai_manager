"""Periodic backup scheduler using threading.Timer.

Follows the same daemon-timer pattern as the auto-scan-watcher extension.
"""

import logging
import threading

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Periodically triggers database backups in the background."""

    def __init__(self) -> None:
        self._timer: threading.Timer | None = None
        self._interval: float = 0  # seconds
        self._running = False
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def interval_hours(self) -> float:
        return self._interval / 3600 if self._interval else 0

    def start(self, interval_hours: float) -> None:
        """Start the periodic scheduler."""
        if interval_hours <= 0:
            logger.info("Backup scheduler: disabled (interval=0)")
            return
        with self._lock:
            if self._running:
                logger.warning("Backup scheduler already running")
                return
            self._interval = interval_hours * 3600
            self._running = True
            self._schedule_next()
            logger.info(
                "Backup scheduler started: every %.1f hours", interval_hours
            )

    def stop(self) -> None:
        """Stop the periodic scheduler."""
        with self._lock:
            self._running = False
            if self._timer:
                self._timer.cancel()
                self._timer = None
            logger.info("Backup scheduler stopped")

    def reschedule(self, interval_hours: float) -> None:
        """Change the interval. Restarts the timer."""
        self.stop()
        if interval_hours > 0:
            self.start(interval_hours)

    def _schedule_next(self) -> None:
        """Schedule the next tick."""
        if not self._running or self._interval <= 0:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """Execute one backup cycle."""
        if not self._running:
            return

        from . import create_backup, is_within_cooldown

        if is_within_cooldown():
            logger.debug("Backup scheduler: skipped (within cooldown)")
        else:
            try:
                result = create_backup(reason="scheduled")
                if "error" in result:
                    logger.warning("Scheduled backup failed: %s", result["error"])
                else:
                    logger.info("Scheduled backup: %s", result.get("filename"))
            except Exception:
                logger.error("Scheduled backup error", exc_info=True)

        # Reschedule
        with self._lock:
            if self._running:
                self._schedule_next()


# Module-level singleton
backup_scheduler = BackupScheduler()

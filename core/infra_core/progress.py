"""Progress callback base class and CLI/JSON implementations."""

import logging

logger = logging.getLogger(__name__)


class ProgressCallback:
    """Progress callback interface for scan operations"""

    def on_start(self, total: int) -> None:
        pass

    def on_progress(self, current: int, total: int, current_file: str = "") -> None:
        pass

    def on_complete(self, total: int) -> None:
        pass

    def on_phase(self, phase: str, message: str = "") -> None:
        pass


class CLIProgressCallback(ProgressCallback):
    """CLI progress bar implementation"""

    def __init__(self):
        self.last_percent = -1

    def on_phase(self, phase: str, message: str = "") -> None:
        if message:
            logger.info(f"{phase}: {message}")
        else:
            logger.info(f"{phase}...")

    def on_start(self, total: int) -> None:
        logger.info(f"Found {total} files to process")
        self.last_percent = -1

    def on_progress(self, current: int, total: int, current_file: str = "") -> None:
        if total == 0:
            return
        percent = int((current / total) * 100)
        if percent != self.last_percent:
            bar_width = 30
            filled = int((current / total) * bar_width)
            bar = '#' * filled + '-' * (bar_width - filled)
            logger.info(f"[{bar}] {percent}% ({current}/{total})")
            self.last_percent = percent

    def on_complete(self, total: int) -> None:
        logger.info(f"Scan complete: {total} files processed")


class JSONProgressCallback(ProgressCallback):
    """JSON progress for WebUI"""

    def __init__(self):
        self.status = {
            "phase": "idle",
            "current": 0,
            "total": 0,
            "percent": 0,
            "current_file": "",
            "message": "",
        }

    def on_phase(self, phase: str, message: str = "") -> None:
        self.status["phase"] = phase
        self.status["message"] = message

    def on_start(self, total: int) -> None:
        self.status["total"] = total
        self.status["current"] = 0
        self.status["percent"] = 0

    def on_progress(self, current: int, total: int, current_file: str = "") -> None:
        self.status["current"] = current
        self.status["total"] = total
        self.status["percent"] = int((current / total) * 100) if total > 0 else 0
        self.status["current_file"] = current_file

    def on_complete(self, total: int) -> None:
        self.status["phase"] = "complete"
        self.status["current"] = total
        self.status["total"] = total
        self.status["percent"] = 100

    def get_status(self) -> dict:
        return self.status.copy()

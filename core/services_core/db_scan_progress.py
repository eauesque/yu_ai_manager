"""Shared scan progress state used by Web UI scan callbacks."""

import threading

scan_state = {
    "running": False,
    "phase": "idle",
    "current": 0,
    "total": 0,
    "percent": 0,
    "current_file": "",
    "message": "",
    "error": None,
}
scan_lock = threading.Lock()


class WebUIProgressCallback:
    """Progress callback for WebUI"""

    def on_phase(self, phase: str, message: str = "") -> None:
        with scan_lock:
            scan_state["phase"] = phase
            scan_state["message"] = message

    def on_start(self, total: int) -> None:
        with scan_lock:
            scan_state["total"] = total
            scan_state["current"] = 0
            scan_state["percent"] = 0

    def on_progress(self, current: int, total: int, current_file: str = "") -> None:
        with scan_lock:
            scan_state["current"] = current
            scan_state["total"] = total
            scan_state["percent"] = int((current / total) * 100) if total > 0 else 0
            scan_state["current_file"] = current_file

    def on_complete(self, total: int) -> None:
        with scan_lock:
            scan_state["phase"] = "complete"
            scan_state["current"] = total
            scan_state["total"] = total
            scan_state["percent"] = 100

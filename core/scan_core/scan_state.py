"""Scan state persistence -- enables scan resumption after restart"""

import contextlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCAN_STATE_FILE = "scan_state.json"


def _state_path() -> Path:
    """Path to scan_state.json (same directory as web_ui.py)"""
    return Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / SCAN_STATE_FILE


def save_scan_state(
    root: str,
    recursive: bool,
    force: bool,
    scan_zips: bool,
    current: int = 0,
    total: int = 0,
    started_at: float | None = None,
    state_file: str | None = None,
) -> None:
    """Persist scan parameters during scanning"""
    state = {
        "root": root,
        "recursive": recursive,
        "force": force,
        "scan_zips": scan_zips,
        "current": current,
        "total": total,
        "started_at": started_at or time.time(),
        "interrupted_at": time.time(),
    }
    try:
        p = Path(state_file) if state_file else _state_path()
        data = json.dumps(state, ensure_ascii=False, indent=2)
        # Atomic write: tempfile + os.replace to prevent partial state
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            os.write(fd, data.encode("utf-8"))
            os.close(fd)
            fd = -1  # Closed flag
            os.replace(tmp, str(p))
        except Exception:
            if fd != -1:
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except Exception as e:
        logger.warning(f"scan_state save failed: {e}")


def load_scan_state(state_file: str | None = None) -> dict[str, Any] | None:
    """Load saved scan state (None if absent)"""
    p = Path(state_file) if state_file else _state_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Minimal validation
        if "root" in data and "total" in data:
            return data
    except Exception as e:
        logger.warning(f"scan_state load failed: {e}")
    return None


def clear_scan_state(state_file: str | None = None) -> None:
    """Delete state file on scan completion/reset"""
    p = Path(state_file) if state_file else _state_path()
    try:
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.warning(f"scan_state clear failed: {e}")

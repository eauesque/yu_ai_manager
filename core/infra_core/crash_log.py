"""Crash diagnostics: faulthandler, stderr tee, and unhandled exception hook.

Captures traces that would otherwise be lost when the process dies silently
(segfaults, OOM kills, native-code crashes in ONNX/ffmpeg, etc.).

Call ``setup_crash_log()`` once at the very start of ``run_web_ui()``.
"""

from __future__ import annotations

import atexit
import faulthandler
import io
import logging
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Kept as module-level so the file stays open for the process lifetime.
_fault_file: io.TextIOWrapper | None = None
_crash_logger: logging.Logger | None = None


def _log_dir() -> Path:
    from core.paths import get_log_dir
    return get_log_dir()


def _crash_log_path() -> Path:
    return _log_dir() / "crash.log"


def _fault_log_path() -> Path:
    return _log_dir() / "faulthandler.log"


def _ensure_log_dir() -> None:
    _log_dir().mkdir(parents=True, exist_ok=True)


def _init_faulthandler() -> None:
    """Enable faulthandler to dump C-level tracebacks on segfault/abort."""
    global _fault_file
    _ensure_log_dir()
    try:
        _fault_file = open(_fault_log_path(), "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=_fault_file, all_threads=True)
    except Exception:
        # Fall back to stderr (default)
        faulthandler.enable()


def _get_crash_logger() -> logging.Logger:
    """Return a rotating file logger for crash.log."""
    global _crash_logger
    if _crash_logger is not None:
        return _crash_logger

    _ensure_log_dir()
    logger = logging.getLogger("tagdb.crash")
    logger.setLevel(logging.ERROR)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            _crash_log_path(),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s %(message)s")
        )
        logger.addHandler(handler)

    _crash_logger = logger
    return _crash_logger


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """sys.excepthook replacement that logs to crash.log before printing."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    try:
        logger = _get_crash_logger()
        logger.error("Unhandled exception at %s:\n%s", ts, tb_text)
    except Exception:
        logger.warning("infrastructure step failed", exc_info=True)

    # Still print to stderr so the console shows it too
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _cleanup() -> None:
    global _fault_file
    if _fault_file is not None:
        try:
            faulthandler.disable()
            _fault_file.close()
        except Exception:
            logging.getLogger("tagdb.crash").warning(
                "crash-log setup step failed", exc_info=True
            )
        _fault_file = None


def setup_crash_log() -> None:
    """Activate all crash diagnostic mechanisms.

    Must be called once, early in process startup.
    """
    _init_faulthandler()
    # Pre-create the crash logger so the file handle is ready
    _get_crash_logger()
    sys.excepthook = _excepthook
    atexit.register(_cleanup)

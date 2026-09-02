"""Lightweight debug logging utilities."""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_file_logger: logging.Logger | None = None

# Evaluate once at module load time and cache
_DEBUG_ENABLED: bool = (os.environ.get("TAGDB_DEBUG") or "").strip().lower() in {
    "1", "true", "yes", "on", "debug"
}


def is_debug_enabled() -> bool:
    """Return True when debug logging is enabled."""
    return _DEBUG_ENABLED


def get_debug_log_path() -> Path:
    """Return debug log file path."""
    raw = (os.environ.get("TAGDB_DEBUG_LOG") or "").strip()
    if raw:
        return Path(raw)
    from core.paths import log_path
    return log_path("debug.log")


def _get_file_logger() -> logging.Logger | None:
    """Initialize and return rotating file logger."""
    global _file_logger
    if _file_logger is not None:
        return _file_logger

    if not is_debug_enabled():
        return None

    try:
        log_path = get_debug_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        max_mb = int((os.environ.get("TAGDB_DEBUG_LOG_MAX_MB") or "10").strip())
        backup_count = int((os.environ.get("TAGDB_DEBUG_LOG_BACKUPS") or "5").strip())
        max_bytes = max(1, max_mb) * 1024 * 1024

        logger = logging.getLogger("tagdb.debug")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if not logger.handlers:
            handler = RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=max(1, backup_count),
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)

        _file_logger = logger
        return _file_logger
    except Exception:
        # Continue with stdout only if file logger fails
        return None


def _get_git_sha() -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def log_startup_banner(*, version: str, db_path: str) -> None:
    """Rotate debug log then write a session-start banner.

    Call once per process after TAGDB_DEBUG env is resolved and db_path is
    final. Rotating before the banner ensures each debug.log file begins with
    a single session, making before/after perf comparisons unambiguous.
    """
    if not is_debug_enabled():
        return
    flog = _get_file_logger()
    if flog is not None:
        for handler in flog.handlers:
            if isinstance(handler, RotatingFileHandler):
                with contextlib.suppress(Exception):
                    handler.doRollover()
                break
    dlog(
        "startup", "session_start",
        version=version,
        db=db_path,
        pid=os.getpid(),
        python=sys.version.split()[0],
        git=_get_git_sha(),
    )


def dlog(source: str, event: str, **fields: Any) -> None:
    """Print structured debug logs when TAGDB_DEBUG is enabled."""
    if not is_debug_enabled():
        return

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"[DEBUG] {ts}", source, event]
    if fields:
        kv = ", ".join(f"{k}={repr(v)}" for k, v in fields.items())
        parts.append(kv)
    line = " | ".join(parts)

    # Console output (default: on)
    stdout_enabled = (os.environ.get("TAGDB_DEBUG_STDOUT") or "1").strip().lower() not in {
        "0", "false", "off", "no"
    }
    if stdout_enabled:
        sys.stderr.write(line + "\n")

    # Rotating file output
    flog = _get_file_logger()
    if flog is not None:
        with contextlib.suppress(Exception):
            flog.info(line)

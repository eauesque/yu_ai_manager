"""JSONL writer for Hailo auto-reboot observation events."""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import Any

from core.paths import log_path

_FILE_LOG_NAME = "hailo.auto_reboot.jsonl"
_WARN_LOG_NAME = "hailo.auto_reboot"
_FILE_NAME = "hailo_auto_reboot.log"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 30

_lock = threading.Lock()
_initialized = False
_logger: logging.Logger | None = None


def _ensure_logger() -> logging.Logger | None:
    global _initialized, _logger
    if _initialized:
        return _logger
    with _lock:
        if _initialized:
            return _logger
        try:
            path = log_path(_FILE_NAME)
            path.parent.mkdir(parents=True, exist_ok=True)
            logger = logging.getLogger(_FILE_LOG_NAME)
            logger.setLevel(logging.INFO)
            logger.propagate = False
            handler = RotatingFileHandler(
                path,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            _logger = logger
        except Exception:
            _logger = None
            return None
        _initialized = True
        return _logger


def log_auto_reboot_event(
    event: str,
    *,
    cma_free_mb: int | None = None,
    hailo_runtime_version: str | None = None,
    **extra: Any,
) -> None:
    logger = _ensure_logger()
    if logger is None:
        return
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "cma_free_mb": cma_free_mb,
        "hailo_runtime_version": hailo_runtime_version,
        **extra,
    }
    try:
        logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except Exception:
        return


def log_warning_summary(event: str, **extra: Any) -> None:
    fields = " ".join(f"{key}={value}" for key, value in sorted(extra.items()))
    logging.getLogger(_WARN_LOG_NAME).warning("hailo_auto_reboot %s %s", event, fields)


def reset_logger_for_tests() -> None:
    global _initialized, _logger
    with _lock:
        if _logger is not None:
            for handler in list(_logger.handlers):
                handler.close()
                _logger.removeHandler(handler)
        _initialized = False
        _logger = None

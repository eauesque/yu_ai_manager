"""Shared bootstrap helpers for long-lived worker processes."""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

_PARENT_CHECK_INTERVAL = 60


def bootstrap_worker_runtime(*, db_path: str | Path, config_path: str | None):
    """Initialize shared app state required by background workers."""
    from core.configuration.api import load_config
    from core.paths import init_app_paths
    from core.services_core.db_state import init_app_state

    resolved_db = Path(db_path).resolve()
    config = load_config(config_path)
    init_app_state(resolved_db, config)
    init_app_paths()
    return config


def configure_worker_logging(log_tag: str) -> None:
    """Install a consistent logging format for worker CLIs."""
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{log_tag}] %(levelname)s %(name)s: %(message)s",
    )


def install_cancel_signal_handlers(
    cancel: Callable[[], None],
    *,
    logger: logging.Logger,
    message: str,
) -> None:
    """Translate SIGTERM/SIGINT into a cooperative cancellation request."""

    def handler(signum, _frame):
        logger.info("Signal %d received, %s", signum, message)
        cancel()

    signal.signal(signal.SIGTERM, handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGINT, handler)


def start_parent_monitor(
    *,
    parent_pid: int,
    is_running: Callable[[], bool],
    is_process_alive: Callable[[int], bool],
    cancel: Callable[[], None],
    logger: logging.Logger,
    message: str,
    interval: int = _PARENT_CHECK_INTERVAL,
) -> threading.Thread:
    """Cancel the worker when the launcher process disappears."""

    def monitor():
        while is_running():
            time.sleep(interval)
            if not is_process_alive(parent_pid):
                logger.info(message, parent_pid)
                cancel()
                break

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    return thread

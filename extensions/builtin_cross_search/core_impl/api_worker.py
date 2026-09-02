"""Cross Search worker process launch and progress bridge logic."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_JOB_ID = "cross_search_scan"
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
_POLL_INTERVAL = 2.0
_FINAL_STATE_KEEP = 10.0


def worker_cmd(roots: list[str]) -> list[str]:
    """Build the worker process launch command."""
    from core.services_core.db_state import get_config, get_db_path

    worker_script = str(
        Path(__file__).resolve().parent / "scan_worker.py"
    )
    cmd = [
        sys.executable, worker_script,
        "start",
        "--db", str(get_db_path()),
        "--roots", ",".join(roots),
        "--parent-pid", str(os.getpid()),
    ]

    config = get_config()
    config_path = config.get("_config_path")
    if config_path:
        cmd.extend(["--config", str(config_path)])

    return cmd


def start_worker_and_bridge(roots: list[str]) -> None:
    """Launch the worker process and start the progress bridge thread."""
    cmd = worker_cmd(roots)
    logger.info("Starting cross-search worker: %s", " ".join(cmd))

    subprocess.Popen(
        cmd,
        cwd=_PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    time.sleep(0.5)
    start_progress_bridge()


def start_progress_bridge() -> None:
    """Poll worker progress file and relay to JobManager."""
    from core.jobs_core.jobs import job_manager

    from .worker_ipc import clear_progress, is_worker_running, read_progress

    try:
        job = job_manager.start(_JOB_ID, "Cross Search scan")
    except ValueError:
        return

    def bridge():
        last_phase = ""
        try:
            while True:
                time.sleep(_POLL_INTERVAL)
                progress = read_progress()

                if progress is None:
                    if not is_worker_running():
                        job.fail("Worker process terminated unexpectedly")
                        break
                    continue

                phase = progress.get("phase", "")
                message = progress.get("message", "")
                current = progress.get("current", 0)
                total = progress.get("total", 0)
                detail = progress.get("detail", "")

                if phase and phase != last_phase:
                    job.update(phase=phase, message=message)
                    last_phase = phase
                elif message:
                    job.update(message=message)

                if total > 0:
                    job.progress(current, total, detail)

                running = progress.get("running", True)
                if not running:
                    handle_worker_finished(job, progress)
                    break

        except Exception as e:
            logger.error("Cross-search progress bridge error: %s", e)
            if job.running:
                job.fail(str(e))
        finally:
            time.sleep(_FINAL_STATE_KEEP)
            clear_progress()

    t = threading.Thread(target=bridge, daemon=True, name="cross-scan-bridge")
    t.start()


def handle_worker_finished(job, progress: dict[str, Any]) -> None:
    """Handle Job state transition when worker finishes."""
    phase = progress.get("phase", "")
    message = progress.get("message", "")

    if phase == "error":
        job.fail(progress.get("error", message or "Unknown error"))
    elif phase == "cancelled":
        job.complete_cancelled(message)
    else:
        job.complete(message or "Scan complete")

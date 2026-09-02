"""Worker process spawning and progress bridge for scan operations."""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from core.event_bus import emit
from core.event_bus.event_types import SCAN_COMPLETE, SCAN_DB_BUSY, SCAN_PROGRESS, SCAN_START
from core.infra_core.debug_log import dlog
from core.scan.worker_ipc import (
    clear_progress,
    is_worker_running,
    read_progress,
)
from core.scan_core.scan_state import clear_scan_state, load_scan_state

logger = logging.getLogger(__name__)

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])

# Polling interval (seconds)
_POLL_INTERVAL = 2.0
# Time to keep progress file after worker completes (seconds)
_FINAL_STATE_KEEP = 1.0


def _worker_cmd(
    root_path: str,
    recursive: bool,
    force: bool,
    scan_zips: bool,
    resume: bool = False,
) -> list:
    """Build command list for spawning a scan worker process."""
    from core.services_core.db_state import get_db_path

    cmd = [
        sys.executable, "-m", "core.scan.scan_worker", "start",
        "--db", str(get_db_path()),
        "--root", root_path,
        "--parent-pid", str(os.getpid()),
    ]
    if recursive:
        cmd.append("--recursive")
    else:
        cmd.append("--no-recursive")
    if force:
        cmd.append("--force")
    if scan_zips:
        cmd.append("--scan-zips")
    if resume:
        cmd.append("--resume")
    return cmd


def _start_worker_and_bridge(
    root_path: str,
    recursive: bool,
    force: bool,
    scan_zips: bool,
    resume: bool = False,
) -> None:
    """Spawn a worker process and start the progress bridge thread."""
    cmd = _worker_cmd(root_path, recursive, force, scan_zips, resume)

    dlog("scan", "worker.spawn", cmd=" ".join(cmd))
    subprocess.Popen(
        cmd,
        cwd=_PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # Prevent signal propagation when web_ui exits
    )

    # Wait briefly for worker startup before starting bridge
    time.sleep(0.5)
    _start_progress_bridge(root_path, recursive)


def _scan_all_worker_cmd(force: bool) -> list:
    """Build command list for spawning a scan-all worker process."""
    from core.services_core.db_state import get_db_path

    cmd = [
        sys.executable, "-m", "core.scan.scan_worker", "scan-all",
        "--db", str(get_db_path()),
        "--parent-pid", str(os.getpid()),
    ]
    if force:
        cmd.append("--force")
    return cmd


def _start_scan_all_worker_and_bridge(force: bool = False) -> None:
    """Spawn a scan-all worker process and start the progress bridge thread."""
    clear_scan_state()
    cmd = _scan_all_worker_cmd(force)

    dlog("scan", "scan_all_worker.spawn", cmd=" ".join(cmd))
    subprocess.Popen(
        cmd,
        cwd=_PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    time.sleep(0.5)
    _start_progress_bridge("__all__", True, label="全フォルダスキャン")


def _start_progress_bridge(root_path: str, recursive: bool, label: str = "フォルダスキャン") -> None:
    """Poll worker progress file and relay to JobManager + SSE."""
    from core.files_core.groups_index import invalidate_cache as invalidate_groups_cache
    from core.jobs_core.jobs import job_manager
    from core.query.tag_resolve_cache import path_match_probe_cache, tag_resolve_cache
    from core.search_api.count_cache import count_cache
    from core.search_api.search_page_cache import search_page_cache

    try:
        job = job_manager.start("scan", label)
    except ValueError:
        # Scan job already running (bridge already started in reconnection case)
        return

    def bridge():
        last_phase = ""
        try:
            emit(SCAN_START, {
                "root": root_path, "recursive": recursive,
                "force": False, "job_id": "scan", "label": job.label,
            }, source="scan")
            emit(SCAN_DB_BUSY, {"busy": True, "job_id": "scan"}, source="scan")

            while True:
                time.sleep(_POLL_INTERVAL)
                progress = read_progress()

                if progress is None:
                    # Worker has no PID file either -> abnormal termination
                    if not is_worker_running():
                        job.fail("ワーカープロセスが異常終了しました")
                        break
                    continue

                # Reflect state in JobManager
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

                # SSE progress event
                if total > 0:
                    pct = progress.get("percent", 0)
                    emit(SCAN_PROGRESS, {
                        "current": current, "total": total, "percent": pct,
                        "job_id": "scan", "label": job.label,
                        "detail": detail, "phase": phase,
                    }, source="scan")

                running = progress.get("running", True)
                if not running:
                    _handle_worker_finished(job, progress)
                    break

        except Exception as e:
            logger.error("Progress bridge error: %s", e)
            if job.running:
                job.fail(str(e))
        finally:
            emit(SCAN_DB_BUSY, {"busy": False, "job_id": "scan"}, source="scan")
            invalidate_groups_cache()
            tag_resolve_cache.invalidate()
            path_match_probe_cache.invalidate()
            count_cache.invalidate()
            search_page_cache.invalidate()
            # Wait briefly before cleaning up progress file
            time.sleep(_FINAL_STATE_KEEP)
            clear_progress()
            # Auto-start next scan from queue if available
            try:
                from core.scan_core.scan_queue_consumer import consume_next_queued_scan
                consume_next_queued_scan()
            except Exception as qe:
                logger.error("Queue consumer error: %s", qe)

    t = threading.Thread(target=bridge, daemon=True, name="scan-progress-bridge")
    t.start()


def _handle_worker_finished(job, progress: dict[str, Any]) -> None:
    """Handle job state transition and SSE event emission when worker finishes."""
    phase = progress.get("phase", "")
    message = progress.get("message", "")
    error = progress.get("error")

    if phase == "error":
        job.fail(error or message or "Unknown error")
    elif phase == "cancelled":
        job.complete_cancelled(message)
    else:
        job.complete(message)
        event_data: dict = {
            "count": progress.get("current", 0),
            "errors": 0,
            "deleted": progress.get("deleted", 0),
            "elapsed_seconds": progress.get("elapsed_seconds", 0),
            "job_id": "scan",
            "added_count": len(progress.get("added_ids") or []),
            "updated_count": len(progress.get("updated_ids") or []),
        }
        added_ids = progress.get("added_ids")
        if added_ids:
            event_data["added_ids"] = added_ids
        updated_ids = progress.get("updated_ids")
        if updated_ids:
            event_data["updated_ids"] = updated_ids
        deleted_ids = progress.get("deleted_ids")
        if deleted_ids:
            event_data["deleted_ids"] = deleted_ids
        emit(SCAN_COMPLETE, event_data, source="scan")


def reconnect_running_worker() -> bool:
    """Reconnect progress bridge to a running worker on web_ui startup.

    Returns True if a running worker was detected and bridge started.
    """
    if not is_worker_running():
        return False

    progress = read_progress()
    root_path = ""
    recursive = True
    if progress:
        # Root info is not in progress file, but available in scan_state.json
        state = load_scan_state()
        if state:
            root_path = state.get("root", "")
            recursive = state.get("recursive", True)

    logger.info("Running scan worker detected, reconnecting progress bridge")
    _start_progress_bridge(root_path, recursive)
    return True

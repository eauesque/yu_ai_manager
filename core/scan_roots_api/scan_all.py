"""Scan-all orchestration helpers for scan roots routes.

scan-all runs in a worker process (same architecture as individual scans).
"""

import logging
from typing import Any

from core.infra_core.api_errors import api_error, api_success
from core.jobs_core.jobs import job_manager
from core.scan.worker_ipc import is_worker_running

logger = logging.getLogger(__name__)


def run_scan_all_roots(data: dict[str, Any]):
    """Start background scan across all enabled roots."""
    if job_manager.is_running("scan") or is_worker_running():
        # Already running -> add to queue
        from core.event_bus import emit
        from core.event_bus.event_types import SCAN_QUEUED
        from core.scan_core.scan_queue import SCAN_ALL_ROOT, scan_queue

        try:
            item = scan_queue.enqueue(
                root=SCAN_ALL_ROOT,
                recursive=True,
                force=data.get("force", False),
                scan_zips=True,
                label="全フォルダスキャン",
                source="scan-all",
            )
            emit(SCAN_QUEUED, {
                "queue_id": item.queue_id,
                "root": SCAN_ALL_ROOT,
                "label": item.label,
                "position": scan_queue.size(),
            }, source="scan_queue")
            return api_success({
                "success": True, "status": "queued",
                "queue_id": item.queue_id,
                "position": scan_queue.size(),
            }, 202)
        except ValueError:
            logger.exception("Failed to enqueue scan-all request")
            return api_error("Scan-all request could not be queued", 409)

    return _start_scan_all_now(data)


def _start_scan_all_now(data: dict[str, Any]):
    """Start scan-all worker immediately (exclusion check already done)."""
    from core.scan_roots_api.ops import load_enabled_scan_roots

    _roots, enabled_roots = load_enabled_scan_roots()
    if not enabled_roots:
        return api_error("No enabled scan roots", 400)

    force = data.get("force", False)

    from core.scan_api.ops_runtime import _start_scan_all_worker_and_bridge
    _start_scan_all_worker_and_bridge(force=force)

    return api_success(
        {"success": True, "message": f"Scanning {len(enabled_roots)} root(s)"},
        200,
    )


def run_scan_all_background(force: bool = False) -> None:
    """Called during queue consumption: start scan-all worker."""
    from core.scan_api.ops_runtime import _start_scan_all_worker_and_bridge
    _start_scan_all_worker_and_bridge(force=force)

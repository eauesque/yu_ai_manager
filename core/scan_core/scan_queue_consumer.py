"""Scan queue consumer -- automatically starts the next queued item after scan completion.

Called from bridge()'s finally block to start the scan at the front of the queue.

Note: To avoid reverse dependency from core to routes layer, scan launcher functions are
injected from outside (routes layer) via register_scan_launchers().
"""

import logging
import time
from collections.abc import Callable

from core.event_bus import emit
from core.event_bus.event_types import SCAN_QUEUE_NEXT

logger = logging.getLogger(__name__)

# Wait time between scans (seconds)
_INTER_SCAN_DELAY = 2.0

# Callbacks injected from routes layer
_single_scan_launcher: Callable | None = None  # (root, recursive, force, scan_zips) -> None
_scan_all_launcher: Callable | None = None      # (force: bool) -> None


def register_scan_launchers(
    single: Callable,
    scan_all: Callable,
) -> None:
    """Register scan launcher functions (called from routes layer at app init).

    Args:
        single: (root, recursive, force, scan_zips) -> None
        scan_all: (force: bool) -> None
    """
    global _single_scan_launcher, _scan_all_launcher
    _single_scan_launcher = single
    _scan_all_launcher = scan_all


def consume_next_queued_scan() -> bool:
    """Dequeue the front item and start the scan.

    Returns True if a queued scan was started.
    """
    from core.scan_core.scan_queue import SCAN_ALL_ROOT, scan_queue

    item = scan_queue.pop_next()
    if item is None:
        return False

    remaining = scan_queue.size()
    logger.info(
        "Queue consumer: starting '%s' (remaining=%d)",
        item.label, remaining,
    )

    emit(SCAN_QUEUE_NEXT, {
        "queue_id": item.queue_id,
        "root": item.root,
        "label": item.label,
        "remaining": remaining,
    }, source="scan_queue")

    # Wait briefly to avoid interfering with previous scan's cleanup
    time.sleep(_INTER_SCAN_DELAY)

    if item.root == SCAN_ALL_ROOT:
        _start_queued_scan_all(item)
    else:
        _start_queued_scan_single(item)

    return True


def _start_queued_scan_single(item) -> None:
    """Start a single-folder scan from a queue item."""
    from core.scan_core.scan_state import clear_scan_state

    if _single_scan_launcher is None:
        logger.error("scan launcher not registered (single); call register_scan_launchers() at startup")
        return

    clear_scan_state()
    _single_scan_launcher(
        item.root, item.recursive, item.force, item.scan_zips,
    )


def _start_queued_scan_all(item) -> None:
    """Start a scan-all from a queue item."""
    if _scan_all_launcher is None:
        logger.error("scan launcher not registered (scan_all); call register_scan_launchers() at startup")
        return

    _scan_all_launcher(force=item.force)

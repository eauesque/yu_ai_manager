"""Event handler for scan-complete triggered backups."""

import logging
import threading

from core.event_bus import event_bus
from core.event_bus.event_types import SCAN_COMPLETE

logger = logging.getLogger(__name__)


def on_scan_complete(event) -> None:
    """Handle scan.complete event: trigger backup if configured."""
    from core.services_core.db_api import get_config

    from . import is_within_cooldown

    cfg = get_config()
    backup_cfg = cfg.get("backup", {})
    if not backup_cfg.get("enabled", True):
        return
    if not backup_cfg.get("backup_on_scan_complete", True):
        return
    if is_within_cooldown():
        logger.debug("Scan-complete backup skipped (within cooldown)")
        return

    # Run in daemon thread to avoid blocking the event bus
    t = threading.Thread(
        target=_do_backup,
        name="backup-scan-complete",
        daemon=True,
    )
    t.start()


def _do_backup() -> None:
    """Execute the backup in a background thread."""
    from . import create_backup

    try:
        result = create_backup(reason="scan_complete")
        if "error" in result:
            logger.warning("Scan-complete backup failed: %s", result["error"])
        else:
            logger.info("Scan-complete backup: %s", result.get("filename"))
    except Exception:
        logger.error("Scan-complete backup error", exc_info=True)


def subscribe_backup_events() -> None:
    """Register backup event handlers on the global event bus."""
    event_bus.subscribe(SCAN_COMPLETE, on_scan_complete)
    logger.info("Backup event handlers registered")

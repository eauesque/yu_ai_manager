"""Event bus handler for YOLO object detection.

Subscribes to scan.complete to optionally auto-detect on new files.
"""

import logging
import threading

from core.event_bus import event_bus
from core.event_bus.event_types import SCAN_COMPLETE

logger = logging.getLogger(__name__)


def on_scan_complete(event) -> None:
    """Handle scan.complete: auto-detect if configured."""
    from core.extensions_core.extensions_admin import get_extension_config_value

    auto_detect = get_extension_config_value(
        "builtin-hailo-yolo-detect", "auto_detect_on_scan", False
    )
    if not auto_detect:
        return

    added_count = event.data.get("added_count", 0)
    if added_count == 0:
        return

    logger.info(
        "Scan complete with %d new files, starting auto-detection", added_count
    )

    from .yolo_indexer import start_detection

    model = get_extension_config_value(
        "builtin-hailo-yolo-detect", "model", "yolov8n"
    )
    conf = get_extension_config_value(
        "builtin-hailo-yolo-detect", "confidence_threshold", 0.25
    )

    threading.Thread(
        target=start_detection,
        kwargs={"model_name": model, "conf_threshold": conf},
        name="yolo-auto-detect",
        daemon=True,
    ).start()


def subscribe_yolo_events() -> None:
    """Register YOLO detection event handlers on the global event bus."""
    event_bus.subscribe(SCAN_COMPLETE, on_scan_complete)
    logger.info("YOLO detection event handlers registered")

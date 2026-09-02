"""Worker helpers for the YOLO detection pipeline.

Re-export façade kept for backward-compatible imports. The real
implementations live in the sibling modules below; the rename refactor
left this module empty, which broke `yolo_detector_archive.py` and
`yolo_detector_live.py` at import time.
"""

import logging

from .yolo_detector_detect import detect_archive_video, detect_video
from .yolo_detector_distributed import process_images_distributed
from .yolo_detector_media import (
    group_by_archive,
    is_processable_file,
    mark_unprocessable_bulk,
)

logger = logging.getLogger(__name__)

__all__ = [
    "detect_archive_video",
    "detect_video",
    "group_by_archive",
    "is_processable_file",
    "mark_unprocessable_bulk",
    "process_images_distributed",
]

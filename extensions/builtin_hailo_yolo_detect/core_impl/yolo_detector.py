"""YOLO detection pipeline facade."""

from .yolo_detector_archive import run_archive_detection
from .yolo_detector_live import run_detection

__all__ = ["run_detection", "run_archive_detection"]

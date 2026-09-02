"""Public entrypoints for background YOLO indexing."""

from .yolo_indexer_queries import (
    annotation_source,
    clear_skip_annotations,
    count_detected,
    count_undetected,
    count_undetected_archive,
    get_file_paths,
    get_undetected_archive_ids,
    get_undetected_ids,
    media_filter_sql,
)
from .yolo_indexer_state import get_last_backend_name as _get_last_backend_name
from .yolo_indexer_state import set_last_backend_name as _set_last_backend_name

_last_backend_name = _get_last_backend_name()
from .yolo_indexer_runtime import (
    get_detect_status,
    start_archive_detection,
    start_detection,
    stop_detection,
)


def _annotation_source(model_name: str, backend_name: str = "") -> str:
    """Backward-compatible alias used by existing tests and callers."""
    global _last_backend_name
    if _last_backend_name != _get_last_backend_name():
        _set_last_backend_name(_last_backend_name)
    result = annotation_source(model_name, backend_name=backend_name)
    _last_backend_name = _get_last_backend_name()
    return result


__all__ = [
    "_annotation_source",
    "annotation_source",
    "clear_skip_annotations",
    "count_detected",
    "count_undetected",
    "count_undetected_archive",
    "get_detect_status",
    "get_file_paths",
    "get_undetected_archive_ids",
    "get_undetected_ids",
    "media_filter_sql",
    "start_archive_detection",
    "start_detection",
    "stop_detection",
]

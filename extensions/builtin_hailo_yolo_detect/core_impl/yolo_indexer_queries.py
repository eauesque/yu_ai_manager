"""DB query helpers for YOLO indexing."""

import contextlib
import threading

from core.infra_core.simple_ttl_cache import SimpleTTLCache

from .yolo_indexer_state import get_last_backend_name, set_last_backend_name

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif")
_VIDEO_EXTS = (".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv")

_DETECT_COUNT_CACHE = SimpleTTLCache(ttl_seconds=300.0)

_DETECT_COUNT_INFLIGHT_LOCK = threading.Lock()
_DETECT_COUNT_INFLIGHT: dict[tuple, threading.Event] = {}
_IN_CHUNK_SIZE = 500


def _compute_with_inflight(key: tuple, query_fn):
    """Compute via TTL cache + in-flight dedup."""
    cached = _DETECT_COUNT_CACHE.peek(key)
    if cached is not None:
        return cached

    with _DETECT_COUNT_INFLIGHT_LOCK:
        cached = _DETECT_COUNT_CACHE.peek(key)
        if cached is not None:
            return cached
        existing = _DETECT_COUNT_INFLIGHT.get(key)
        if existing is None:
            event = threading.Event()
            _DETECT_COUNT_INFLIGHT[key] = event
            owner = True
        else:
            event = existing
            owner = False

    if not owner:
        event.wait(timeout=30.0)
        cached = _DETECT_COUNT_CACHE.peek(key)
        if cached is not None:
            return cached
        # First-call failed or timed out: fall through and recompute ourselves.

    try:
        value = query_fn()
        _DETECT_COUNT_CACHE.put(key, value)
        return value
    finally:
        if owner:
            with _DETECT_COUNT_INFLIGHT_LOCK:
                _DETECT_COUNT_INFLIGHT.pop(key, None)
            event.set()


def annotation_source(model_name: str, backend_name: str = "") -> str:
    if not backend_name:
        from .backends.backend_registry import detect_available_backends, get_current_backend

        backend = get_current_backend()
        if backend:
            backend_name = backend.name
            set_last_backend_name(backend_name)
        elif get_last_backend_name():
            backend_name = get_last_backend_name()
        else:
            available = detect_available_backends()
            backend_name = available[0].name if available else "unknown"
            set_last_backend_name(backend_name)
    return f"{backend_name}:{model_name}"


_KNOWN_BACKEND_NAMES: tuple[str, ...] = ("hailo", "onnx", "opencv_dnn")


def _backend_sources_for_model(model_name: str) -> list[str]:
    return [f"{name}:{model_name}" for name in _KNOWN_BACKEND_NAMES]


def _meta_key_detected(model_name: str) -> str:
    return f"yolo_detected_count:{model_name}"


def _meta_key_undetected(model_name: str) -> str:
    return f"yolo_undetected_count:{model_name}"


def _run_detected_count_query(con, model_name: str) -> int:
    sources = _backend_sources_for_model(model_name)
    placeholders = ",".join("?" * len(sources))
    # `source IN (...)` + `key = 'detections'` hits
    # idx_file_annotations_source_key (added v4.119.25) for index seeks
    # instead of the previous full-scan from `source LIKE '%:model'`.
    row = con.execute(
        f"SELECT COUNT(DISTINCT a.file_id) FROM file_annotations a "  # noqa: S608
        f"JOIN files f ON a.file_id = f.id "
        f"WHERE f.is_deleted = 0 AND a.source IN ({placeholders}) AND a.key = 'detections'",
        sources,
    ).fetchone()
    return (row[0] if row else 0) or 0


def _run_total_files_query(con) -> int:
    from core.services_core.db_meta import get_meta_int

    total = get_meta_int(con, "total_files", -1)
    if total >= 0:
        return total
    return con.execute(
        "SELECT COUNT(*) FROM files WHERE is_deleted = 0"
    ).fetchone()[0] or 0


def recompute_and_persist_yolo_counts(model_name: str = "yolov8n") -> tuple[int, int]:
    """Run the heavy COUNT once, persist results to db_meta, return (detected, undetected).

    Designed to be called from a long-running background thread (process startup
    warm-up or detection finish hook). The COUNT itself runs against a read-only
    connection so it does not occupy the SQLite writer thread for 30+ seconds;
    only the small set_meta upsert is dispatched to the writer.
    """
    from core.services_core.db_api import get_readonly_db
    from core.services_core.db_write import submit_db_write_no_wait

    con = get_readonly_db()
    detected = _run_detected_count_query(con, model_name)
    total = _run_total_files_query(con)
    undetected = max(0, total - detected)

    def _persist():
        from core.services_core.db_api import get_db
        from core.services_core.db_meta import set_meta

        wcon = get_db()
        set_meta(wcon, _meta_key_detected(model_name), str(detected))
        set_meta(wcon, _meta_key_undetected(model_name), str(undetected))
        wcon.commit()

    with contextlib.suppress(Exception):
        submit_db_write_no_wait(_persist)

    _DETECT_COUNT_CACHE.put(("detected", model_name), detected)
    _DETECT_COUNT_CACHE.put(("undetected", model_name), undetected)
    return detected, undetected


def count_detected(model_name: str = "yolov8n") -> int:
    def _query() -> int:
        from core.services_core.db_api import get_readonly_db
        from core.services_core.db_meta import get_meta_int

        con = get_readonly_db()
        cached = get_meta_int(con, _meta_key_detected(model_name), -1)
        if cached >= 0:
            return cached
        return recompute_and_persist_yolo_counts(model_name)[0]

    return _compute_with_inflight(("detected", model_name), _query)


def count_undetected(model_name: str = "yolov8n") -> int:
    def _query() -> int:
        from core.services_core.db_api import get_readonly_db
        from core.services_core.db_meta import get_meta_int

        con = get_readonly_db()
        cached = get_meta_int(con, _meta_key_undetected(model_name), -1)
        if cached >= 0:
            return cached
        return recompute_and_persist_yolo_counts(model_name)[1]

    return _compute_with_inflight(("undetected", model_name), _query)


def invalidate_yolo_detect_count_cache() -> None:
    """Drop cached YOLO detect counts after a detection batch completes."""
    _DETECT_COUNT_CACHE.invalidate()


def get_undetected_ids(model_name: str, limit: int = 100) -> list:
    from core.services_core.db_api import get_readonly_db

    source = annotation_source(model_name)
    con = get_readonly_db()
    rows = con.execute(
        "SELECT f.id FROM files f "
        "WHERE f.is_deleted = 0 "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM file_annotations a "
        "  WHERE a.file_id = f.id AND a.source = ? AND a.key = 'detections'"
        ") LIMIT ?",
        (source, limit),
    ).fetchall()
    return [row[0] for row in rows]


def get_file_paths(file_ids: list) -> dict:
    from core.services_core.db_api import get_readonly_db

    if not file_ids:
        return {}
    con = get_readonly_db()
    out = {}
    for index in range(0, len(file_ids), _IN_CHUNK_SIZE):
        chunk = file_ids[index:index + _IN_CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders})",
            chunk,
        )
        out.update({row[0]: row[1] for row in rows})
    return out


def media_filter_sql(media_filter: str) -> str:
    from core.query.filters_common_media import _ext_in_clause

    if media_filter == "all":
        return ""
    if media_filter == "image":
        return _ext_in_clause(_IMAGE_EXTS)
    if media_filter == "video":
        return _ext_in_clause(_VIDEO_EXTS)
    exts = tuple(
        ext.strip().lower() if ext.strip().startswith(".") else f".{ext.strip().lower()}"
        for ext in media_filter.split(",")
        if ext.strip()
    )
    return _ext_in_clause(exts) if exts else ""


def clear_skip_annotations(source: str) -> int:
    from core.services_core.yolo_detection_service import (
        clear_skip_detection_annotations,
    )

    return clear_skip_detection_annotations(source)


def count_undetected_archive(model_name: str = "yolov8n", media_filter: str = "all") -> int:
    from core.services_core.db_api import get_readonly_db

    source = annotation_source(model_name)
    con = get_readonly_db()
    query = (
        "SELECT COUNT(*) FROM files f "
        "WHERE f.is_deleted = 0 AND f.path LIKE '%!%' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM file_annotations a "
        "  WHERE a.file_id = f.id AND a.source = ? AND a.key = 'detections'"
        ")"
    )
    ext_clause = media_filter_sql(media_filter)
    if ext_clause:
        query += " AND " + ext_clause
    row = con.execute(query, [source]).fetchone()
    return row[0] if row else 0


def get_undetected_archive_ids(model_name: str, media_filter: str = "all", limit: int = 1000) -> list:
    from core.services_core.db_api import get_readonly_db

    source = annotation_source(model_name)
    con = get_readonly_db()
    query = (
        "SELECT f.id, f.path FROM files f "
        "WHERE f.is_deleted = 0 AND f.path LIKE '%!%' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM file_annotations a "
        "  WHERE a.file_id = f.id AND a.source = ? AND a.key = 'detections'"
        ")"
    )
    params: list = [source]
    ext_clause = media_filter_sql(media_filter)
    if ext_clause:
        query += " AND " + ext_clause
    query += " LIMIT ?"
    params.append(limit)
    return con.execute(query, params).fetchall()

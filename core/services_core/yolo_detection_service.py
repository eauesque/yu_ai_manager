"""Write helpers for YOLO detection annotation operations."""

from __future__ import annotations

_MEDIA_EXTS = frozenset(
    {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif",
        ".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv",
    }
)


def clear_yolo_detection_annotations() -> int:
    """Delete all persisted YOLO detection annotations across sources."""
    from importlib import import_module

    from core.services_core.db_api import get_readonly_db

    annotations_mod = import_module("extensions.builtin_annotations.core_impl")
    delete_annotations_batch = annotations_mod.delete_annotations_batch

    # Read-only enumeration of distinct sources; deletion runs through the
    # writer queue inside delete_annotations_batch().
    con = get_readonly_db()
    rows = con.execute(
        "SELECT DISTINCT source FROM file_annotations "
        "WHERE source LIKE '%:yolo%' AND key = 'detections'"
    ).fetchall()
    sources = [row[0] for row in rows]

    total_deleted = 0
    for source in sources:
        result = delete_annotations_batch(source, key="detections")
        total_deleted += result.get("deleted", 0)
    return total_deleted


def _mark_unprocessable_detection_files_write(source: str, now: int, non_media_clause: str) -> int:
    from core.services_core.db_api import get_db

    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO file_annotations "
        "(file_id, source, key, value, created_at) "
        "SELECT f.id, ?, 'detections', '[]', ? "
        "FROM files f "
        "WHERE f.is_deleted = 0 "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM file_annotations a "
        "  WHERE a.file_id = f.id AND a.source = ? AND a.key = 'detections'"
        ") "
        "AND (f.path LIKE '%!%' OR " + non_media_clause + ")",
        (source, now, source),
    )
    if cur.rowcount > 0:
        db.commit()
    return cur.rowcount


def mark_unprocessable_detection_files(source: str) -> int:
    """Mark unsupported or archive-member files as skipped detections."""
    import time

    from core.query.filters_common_media import _ext_in_clause
    from core.services_core.db_write import submit_db_write

    now = int(time.time())
    # `_ext_in_clause` returns either `f.file_ext IN (...)` (indexed via
    # idx_files_deleted_ext on migration 50+) or a `lower(f.path) LIKE` OR
    # chain on legacy schemas. Negation gives us non-media files in either
    # form (NOT (a OR b OR c) ≡ NOT a AND NOT b AND NOT c).
    non_media_clause = f"NOT ({_ext_in_clause(tuple(_MEDIA_EXTS))})"
    return submit_db_write(_mark_unprocessable_detection_files_write, source, now, non_media_clause)


def _clear_skip_detection_annotations_write(source: str) -> int:
    from core.services_core.db_api import get_db

    db = get_db()
    cur = db.execute(
        "DELETE FROM file_annotations "
        "WHERE source = ? AND key = 'detections' AND value = '[]' "
        "AND file_id IN (SELECT id FROM files WHERE path LIKE '%!%' AND is_deleted = 0)",
        (source,),
    )
    if cur.rowcount > 0:
        db.commit()
    return cur.rowcount


def clear_skip_detection_annotations(source: str) -> int:
    """Delete archive-member skipped detection annotations for one source."""
    from core.services_core.db_write import submit_db_write

    return submit_db_write(_clear_skip_detection_annotations_write, source)

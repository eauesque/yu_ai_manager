"""Shared filter and format helpers for file metadata cache."""

from __future__ import annotations

import re
import threading
import time

# Per-thread timing record (see file_meta_cache_query._QR_TLS for rationale).
_FILTER_TLS = threading.local()
_FILTER_TIMING_TEMPLATE: dict[str, object] = {
    "model_ms": 0,
    "ts_ms": 0,
    "path_ms": 0,
    "wh_ms": 0,
    "model_active": False,
    "ts_active": False,
    "path_active": False,
    "wh_active": False,
    "model_filter_value": "",
    "input_size": 0,
    "after_model": 0,
    "after_ts": 0,
    "after_path": 0,
    "after_wh": 0,
}


def _filter_timing() -> dict:
    timing = getattr(_FILTER_TLS, "data", None)
    if timing is None:
        timing = dict(_FILTER_TIMING_TEMPLATE)
        _FILTER_TLS.data = timing
    return timing


def get_last_filter_timing() -> dict:
    return dict(_filter_timing())

_ID = 0
_PATH = 1
_MTIME = 2
_META_SOURCE = 3
_FILE_EXT = 4
_WIDTH = 5
_HEIGHT = 6

IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".avif", ".heif", ".heic", ".jxl", ".svg",
})
VIDEO_EXTS = frozenset({
    ".webm", ".mp4", ".mov", ".m4v", ".avi", ".mkv",
    ".ogv", ".ts", ".m2ts",
})
AUDIO_EXTS = frozenset({
    ".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac",
})

FORMAT_CATEGORIES = {
    "image": IMAGE_EXTS,
    "video": VIDEO_EXTS,
    "audio": AUDIO_EXTS,
}


def parse_custom_exts(format_exts: str) -> list[str]:
    """Return validated file extensions from a comma-separated filter."""
    return [
        f".{ext}"
        for ext in [s.strip().lower() for s in str(format_exts).split(",")]
        if re.fullmatch(r"[a-z0-9]{1,8}", ext)
    ]


def merge_sorted_records(a: list, b: list) -> list:
    """Merge two lists sorted by ``(mtime DESC, id DESC)``."""
    result = []
    i = 0
    j = 0
    while i < len(a) and j < len(b):
        if (a[i][_MTIME], a[i][_ID]) >= (b[j][_MTIME], b[j][_ID]):
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    result.extend(a[i:])
    result.extend(b[j:])
    return result


def filter_model_records(records: list, model_filter: str) -> list:
    """Filter records by metadata source family."""
    filters = [item.strip() for item in model_filter.split(",") if item.strip()]
    if not filters:
        return records

    def matches(meta_source: str | None) -> bool:
        lowered = (meta_source or "").lower()
        for model_name in filters:
            if model_name == "sd" and ("a1111" in lowered or "forge" in lowered):
                return True
            if model_name == "nai" and "novel" in lowered:
                return True
            if model_name == "comfy" and "comfy" in lowered:
                return True
            if model_name == "tensor" and "tensor" in lowered:
                return True
            if model_name == "unknown" and not lowered:
                return True
        return False

    return [record for record in records if matches(record[_META_SOURCE])]


def apply_record_filters(
    records: list,
    from_ts,
    to_ts,
    in_path,
    min_width,
    max_width,
    min_height,
    max_height,
    model_filter,
) -> list:
    """Apply record-level filters after the source list is selected."""
    result = records
    t0 = time.perf_counter()
    _filter_timing()["input_size"] = len(records)
    _filter_timing()["model_active"] = bool(model_filter and model_filter != "all")
    _filter_timing()["ts_active"] = from_ts is not None or to_ts is not None
    _filter_timing()["path_active"] = bool(in_path and in_path.strip())
    _filter_timing()["wh_active"] = any(
        value is not None for value in (min_width, max_width, min_height, max_height)
    )
    _filter_timing()["model_filter_value"] = (model_filter or "")[:40]

    if model_filter and model_filter != "all":
        result = filter_model_records(result, model_filter)
    t_model = time.perf_counter()
    _filter_timing()["model_ms"] = round((t_model - t0) * 1000)
    _filter_timing()["after_model"] = len(result)

    if from_ts is not None or to_ts is not None:
        result = [
            record for record in result
            if (from_ts is None or record[_MTIME] >= from_ts)
            and (to_ts is None or record[_MTIME] <= to_ts)
        ]
    t_ts = time.perf_counter()
    _filter_timing()["ts_ms"] = round((t_ts - t_model) * 1000)
    _filter_timing()["after_ts"] = len(result)

    if in_path and in_path.strip():
        path_lower = in_path.strip().lower().replace("\\", "/")
        result = [
            record for record in result
            if path_lower in (record[_PATH] or "").lower().replace("\\", "/")
        ]
    t_path = time.perf_counter()
    _filter_timing()["path_ms"] = round((t_path - t_ts) * 1000)
    _filter_timing()["after_path"] = len(result)

    if any(value is not None for value in (min_width, max_width, min_height, max_height)):
        result = [
            record for record in result
            if (min_width is None or (record[_WIDTH] or 0) >= min_width)
            and (max_width is None or (record[_WIDTH] or 0) <= max_width)
            and (min_height is None or (record[_HEIGHT] or 0) >= min_height)
            and (max_height is None or (record[_HEIGHT] or 0) <= max_height)
        ]
    t_wh = time.perf_counter()
    _filter_timing()["wh_ms"] = round((t_wh - t_path) * 1000)
    _filter_timing()["after_wh"] = len(result)

    return result


def can_use_cache(params: dict) -> bool:
    """Check if search params allow using in-memory cache."""
    for key in (
        "tag_query",
        "artist",
        "in_prompt",
        "in_negative",
        "in_char_negative",
        "in_char_positive",
        "checkpoint_filter",
        "or_tags",
    ):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return False

    # wd_model has no representation in FileMetaCache's records (only the
    # unrelated LoRA/checkpoint model_filter is cached) — force the SQL path.
    if (params.get("wd_model") or "").strip():
        return False

    if params.get("fav_only", False):
        return False
    if params.get("collection_id", 0) != 0:
        return False
    if params.get("ai_analyzed", False):
        return False
    if params.get("has_tags", False):
        return False
    if params.get("has_annotation", False):
        return False
    if params.get("has_sweep", False):
        return False
    if params.get("min_rating") is not None:
        return False
    if params.get("max_rating") is not None:
        return False
    if params.get("tag_query_regex", False) or params.get("in_prompt_regex", False):
        return False

    return params.get("sort_by", "date") in ("date", "date_new", "date_old", "path", "random")

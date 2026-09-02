import bisect
import threading
import time

from .file_meta_cache_rules import (
    apply_record_filters,
    merge_sorted_records,
    parse_custom_exts,
)

_ID = 0
_PATH = 1
_MTIME = 2
_META_SOURCE = 3
_FILE_EXT = 4

# Per-thread timing record so concurrent searches can't clobber each other's
# dlog values. Each search request runs on a single run_db_sync thread, so
# storing the breakdown in thread-local state keeps writers and readers paired.
_QR_TLS = threading.local()
_QR_TIMING_TEMPLATE: dict[str, object] = {
    "source_ms": 0,
    "filter_ms": 0,
    "sort_ms": 0,
    "len_ms": 0,
    "cursor_ms": 0,
    "slice_ms": 0,
    "dict_build_ms": 0,
    "source_size": 0,
    "needs_filter": False,
    "file_format": "",
    "format_exts": "",
}


def _qr_timing() -> dict:
    timing = getattr(_QR_TLS, "data", None)
    if timing is None:
        timing = dict(_QR_TIMING_TEMPLATE)
        _QR_TLS.data = timing
    return timing


def get_last_qr_timing() -> dict:
    return dict(_qr_timing())


def query_records(
    records: list,
    by_format: dict,
    mtime_keys: list[tuple[int, int]],
    *,
    by_model_family: dict | None = None,
    sort_by: str = "date",
    file_format: str = "all",
    format_exts: str = "",
    from_ts: int | None = None,
    to_ts: int | None = None,
    in_path: str | None = None,
    min_width: int | None = None,
    max_width: int | None = None,
    min_height: int | None = None,
    max_height: int | None = None,
    model_filter: str = "all",
    limit: int = 100,
    offset: int = 0,
    cursor_mtime: int | None = None,
    cursor_id: int | None = None,
) -> tuple[list[dict], int, bool]:
    if not records:
        return [], 0, False

    t0 = time.perf_counter()
    # Fast path: when model_filter targets a single pre-bucketed family AND
    # file_format is unrestricted, start from the per-family bucket so we
    # avoid filter_model_records()'s 1.6M-row .lower() scan. The bucket is
    # already sorted (mtime DESC, id DESC).
    model_prebucket_used = False
    if (
        by_model_family
        and model_filter
        and model_filter != "all"
        and (file_format or "all").lower() == "all"
        and not format_exts
    ):
        filters = [item.strip() for item in model_filter.split(",") if item.strip()]
        if len(filters) == 1 and filters[0] in by_model_family:
            source = by_model_family[filters[0]]
            model_prebucket_used = True
        else:
            source = get_source_list(records, by_format, file_format, format_exts)
    else:
        source = get_source_list(records, by_format, file_format, format_exts)
    t_source = time.perf_counter()
    needs_filter = any(
        value is not None
        for value in (from_ts, to_ts, min_width, max_width, min_height, max_height)
    ) or bool(
        (in_path and in_path.strip())
        or (not model_prebucket_used and model_filter and model_filter != "all")
    )
    if needs_filter:
        source = apply_record_filters(
            source,
            from_ts,
            to_ts,
            in_path,
            min_width,
            max_width,
            min_height,
            max_height,
            "all" if model_prebucket_used else model_filter,
        )
    t_filter = time.perf_counter()

    if sort_by == "date_old":
        source = list(reversed(source))
    elif sort_by == "path":
        source = sorted(source, key=lambda r: r[_PATH])
    elif sort_by == "random":
        import random

        source = list(source)
        random.shuffle(source)
    t_sort = time.perf_counter()

    total_count = len(source)
    t_len = time.perf_counter()
    start = 0
    if cursor_mtime is not None and cursor_id is not None:
        start = find_cursor_pos(source, records, mtime_keys, cursor_mtime, cursor_id, sort_by)
    elif offset > 0:
        start = min(offset, total_count)
    t_cursor = time.perf_counter()

    end = start + limit
    page = source[start:end]
    t_slice = time.perf_counter()
    out = [
        {
            "id": r[_ID],
            "path": r[_PATH],
            "mtime": r[_MTIME],
            "meta_source": r[_META_SOURCE],
            "positive": "",
            "negative": "",
        }
        for r in page
    ]
    t_dict = time.perf_counter()
    _qr_timing()["source_ms"] = round((t_source - t0) * 1000)
    _qr_timing()["filter_ms"] = round((t_filter - t_source) * 1000)
    _qr_timing()["sort_ms"] = round((t_sort - t_filter) * 1000)
    _qr_timing()["len_ms"] = round((t_len - t_sort) * 1000)
    _qr_timing()["cursor_ms"] = round((t_cursor - t_len) * 1000)
    _qr_timing()["slice_ms"] = round((t_slice - t_cursor) * 1000)
    _qr_timing()["dict_build_ms"] = round((t_dict - t_slice) * 1000)
    _qr_timing()["source_size"] = len(source)
    _qr_timing()["needs_filter"] = needs_filter
    _qr_timing()["file_format"] = file_format
    _qr_timing()["format_exts"] = format_exts
    return out, total_count, end < total_count


def get_source_list(records: list, by_format: dict, file_format: str, format_exts: str) -> list:
    ff = (file_format or "all").lower()
    if ff == "all" and not format_exts:
        return records
    if ff in by_format and not format_exts:
        return by_format[ff]

    ext_key = (
        f".{ff}"
        if ff not in ("all", "image", "video", "audio", "zip_member", "jpg", "jpeg", "heif", "heic")
        else None
    )
    if ext_key and ext_key in by_format and not format_exts:
        return by_format[ext_key]

    if ff in ("jpg", "jpeg"):
        return _merge_alias_records(by_format, ".jpg", ".jpeg")
    if ff in ("heif", "heic"):
        return _merge_alias_records(by_format, ".heif", ".heic")

    if format_exts:
        exts = parse_custom_exts(format_exts)
        if exts:
            ext_set = frozenset(exts)
            base = by_format.get(ff, records) if ff != "all" else records
            return [r for r in base if r[_FILE_EXT] in ext_set]

    return records


def find_cursor_pos(
    records: list,
    all_records: list,
    mtime_keys: list[tuple[int, int]],
    cursor_mtime: int,
    cursor_id: int,
    sort_by: str,
) -> int:
    n = len(records)
    if n == 0:
        return 0

    if sort_by in ("date", "date_new"):
        key = (-cursor_mtime, -cursor_id)
        if records is all_records and mtime_keys:
            return bisect.bisect_right(mtime_keys, key)
        for i, r in enumerate(records):
            if r[_MTIME] < cursor_mtime or (r[_MTIME] == cursor_mtime and r[_ID] < cursor_id):
                return i
        return n

    if sort_by == "date_old":
        for i, r in enumerate(records):
            if r[_MTIME] > cursor_mtime or (r[_MTIME] == cursor_mtime and r[_ID] > cursor_id):
                return i
        return n
    return 0


def _merge_alias_records(by_format: dict, left: str, right: str) -> list:
    r1 = by_format.get(left, [])
    r2 = by_format.get(right, [])
    if r1 and r2:
        return merge_sorted_records(r1, r2)
    return r1 or r2 or []

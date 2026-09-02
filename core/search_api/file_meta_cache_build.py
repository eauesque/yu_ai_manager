import logging
import time

from .file_meta_cache_rules import FORMAT_CATEGORIES

logger = logging.getLogger(__name__)

# Pre-bucketed model family keys. Keep in sync with filter_model_records()
# matching rules and the model_filter UI values: sd / nai / comfy / tensor /
# unknown. Each record is classified into exactly one family during cache
# build so that queries with model_filter='comfy' (etc.) can be served from
# an O(1) dict lookup instead of a 1.6M-row .lower() scan per request.
_MODEL_FAMILIES = ("sd", "nai", "comfy", "tensor", "unknown")
_SIGNATURE_HOT_TTL_SECONDS = 2
_SIGNATURE_MAX_ONLY_TTL_SECONDS = 30


def _classify_model_family(meta_source: str | None) -> str | None:
    """Match the same families filter_model_records() recognizes. Returns
    None when the record doesn't fit any known family (rare: meta_source is
    set to a value we don't bucket); such records remain queryable via the
    fallback filter_model_records path."""
    if not meta_source:
        return "unknown"
    lowered = meta_source.lower()
    if "a1111" in lowered or "forge" in lowered:
        return "sd"
    if "novel" in lowered:
        return "nai"
    if "comfy" in lowered:
        return "comfy"
    if "tensor" in lowered:
        return "tensor"
    return None


def get_signature(
    con,
    cached_sig: tuple[int, int] | None,
    cached_at: float,
) -> tuple[tuple[int, int], float]:
    now = time.monotonic()
    if cached_sig is not None:
        age = now - cached_at
        if age < _SIGNATURE_HOT_TTL_SECONDS:
            return cached_sig, now
        if age < _SIGNATURE_MAX_ONLY_TTL_SECONDS:
            max_mt = con.execute(
                "SELECT COALESCE(MAX(mtime), 0) FROM files WHERE is_deleted=0"
            ).fetchone()[0]
            if max_mt == cached_sig[1]:
                return cached_sig, now

    row = con.execute(
        "SELECT COUNT(*), COALESCE(MAX(mtime), 0) "
        "FROM files WHERE is_deleted=0"
    ).fetchone()
    return (row[0], row[1]), now


def build_cache_records(con, sig: tuple[int, int]) -> dict[str, object]:
    t0 = time.monotonic()
    cursor = con.execute(
        "SELECT id, path, mtime, meta_source, file_ext, width, height "
        "FROM files WHERE is_deleted=0 "
        "ORDER BY mtime DESC, id DESC"
    )

    records: list[tuple] = []
    by_id: dict[int, int] = {}
    mtime_keys: list[tuple[int, int]] = []
    fmt_buckets: dict[str, list[tuple]] = {k: [] for k in FORMAT_CATEGORIES}
    ext_buckets: dict[str, list[tuple]] = {}
    model_buckets: dict[str, list[tuple]] = {k: [] for k in _MODEL_FAMILIES}

    for i, row in enumerate(cursor):
        rec = (row[0], row[1], row[2], row[3], row[4], row[5], row[6])
        records.append(rec)
        by_id[row[0]] = i
        mtime_keys.append((-row[2], -row[0]))

        ext = row[4]
        if ext:
            for cat, ext_set in FORMAT_CATEGORIES.items():
                if ext in ext_set:
                    fmt_buckets[cat].append(rec)
            ext_buckets.setdefault(ext, []).append(rec)

        family = _classify_model_family(row[3])
        if family is not None:
            model_buckets[family].append(rec)

    elapsed = time.monotonic() - t0
    logger.info(
        "[file_meta_cache] Built: %d records in %.1fms (%.1f MB est)",
        len(records),
        elapsed * 1000,
        len(records) * 280 / (1024 * 1024),
    )
    return {
        "records": records,
        "by_id": by_id,
        "by_format": {**fmt_buckets, **ext_buckets},
        "by_model_family": model_buckets,
        "mtime_keys": mtime_keys,
        "signature": sig,
        "built_at": time.time(),
    }

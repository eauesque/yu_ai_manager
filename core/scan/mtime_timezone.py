"""Timezone correction for archive member timestamps."""

import datetime as _dt
import sqlite3

# meta_source values whose archive timestamps are stored in UTC.
# Add new values here when other UTC sources are discovered.
UTC_META_SOURCES: frozenset[str] = frozenset({
    "novelai_v4_png", "novelai_v4_webp", "novelai_v4",
    "novelai_png", "novelai_webp", "nai_webp",
})


def is_utc_meta_source(meta_source: str | None) -> bool:
    """Check if the given meta_source stores timestamps in UTC."""
    if not meta_source:
        return False
    return meta_source in UTC_META_SOURCES


def naive_local_to_utc_timestamp(naive_local_ts: int) -> int:
    """Re-interpret a timestamp wrongly computed as local time.

    datetime(*date_time).timestamp() treats UTC values as local.
    This recovers the Y/M/D/H/M/S and reinterprets as UTC.
    """
    # Naive on purpose: this function exists to recover the *local*
    # wall-clock fields and reinterpret them as UTC on the next line.
    # A tz here would defeat the correction entirely.
    naive_dt = _dt.datetime.fromtimestamp(naive_local_ts)  # noqa: DTZ006
    utc_dt = naive_dt.replace(tzinfo=_dt.UTC)
    return int(utc_dt.timestamp())


def correct_mtime_if_utc(con: sqlite3.Connection, path: str,
                         raw_mtime: int) -> int:
    """Correct raw_mtime if the file's existing meta_source is UTC-based.

    Called BEFORE should_rescan() so the mtime comparison matches the
    previously stored corrected value (prevents unnecessary rescans).
    """
    row = con.execute(
        "SELECT meta_source FROM files WHERE path=? AND is_deleted=0",
        (path,),
    ).fetchone()
    if row and is_utc_meta_source(row[0]):
        return naive_local_to_utc_timestamp(raw_mtime)
    return raw_mtime

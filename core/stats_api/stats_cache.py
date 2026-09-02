"""Server-side cache for Stats and Story API responses."""

import json
import logging
import threading
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

from core.stats_api.basic import build_basic_stats, build_hourly_stats
from core.stats_api.models_resolutions import build_model_stats, build_resolution_stats
from core.stats_api.monthly_report import build_monthly_report
from core.stats_api.story import build_story_stats
from core.stats_api.timeline import build_timeline_stats


def _stats_cache_path() -> Path:
    from core.paths import cache_path
    return cache_path("stats_cache.json")


def _story_cache_path() -> Path:
    from core.paths import cache_path
    return cache_path("story_cache.json")


def _monthly_cache_path(month: str | None = None) -> Path:
    from core.paths import cache_path
    if month is None:
        return cache_path("monthly_report_cache.json")
    return cache_path(f"monthly_report_cache_{month}.json")

_CACHE_VERSION = 10

_sig_cache: tuple | None = None
_sig_cache_ts: float = 0
_SIG_TTL = 120  # seconds -- stats don't change often, so use a long TTL
_sig_lock = threading.Lock()


def _db_signature(con) -> tuple:
    global _sig_cache, _sig_cache_ts
    now = time.monotonic()
    with _sig_lock:
        if _sig_cache is not None and now - _sig_cache_ts < _SIG_TTL:
            return _sig_cache

    file_row = con.execute(
        """SELECT COUNT(*), MAX(mtime), COALESCE(SUM(mtime), 0),
                  SUM(CASE WHEN is_deleted = 0
                            AND meta_source IS NOT NULL
                            AND meta_source NOT IN ('', 'unknown', 'not_modified')
                            AND meta_source NOT LIKE 'media_%'
                           THEN 1 ELSE 0 END)
           FROM files
           WHERE is_deleted = 0"""
    ).fetchone()

    def _table_sig(table: str, value_expr: str = "rowid") -> tuple[int, int, int]:
        try:
            row = con.execute(
                f"SELECT COUNT(*), COALESCE(MAX(rowid), 0), COALESCE(SUM({value_expr}), 0) FROM {table}"
            ).fetchone()
            return (row[0] or 0, row[1] or 0, row[2] or 0)
        except Exception:
            return (0, 0, 0)

    file_tags_sig = _table_sig("file_tags", "file_id + tag_id")
    tags_sig = _table_sig("tags", "id + length(COALESCE(tag, '')) + length(COALESCE(namespace, ''))")
    monthly_cache_sig = _table_sig("monthly_stats_cache", "updated_at")

    result = (
        file_row[0] or 0,
        file_row[1] or 0,
        file_row[2] or 0,
        file_row[3] or 0,
        file_tags_sig,
        tags_sig,
        monthly_cache_sig,
    )
    with _sig_lock:
        _sig_cache = result
        _sig_cache_ts = now
    return result


def invalidate_signature_cache() -> None:
    global _sig_cache, _sig_cache_ts
    with _sig_lock:
        _sig_cache = None
        _sig_cache_ts = 0


def _try_read_disk_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _json_tuple(value):
    if isinstance(value, list):
        return tuple(_json_tuple(v) for v in value)
    return value


def _read_cache(path: Path, db_sig: tuple):
    cached = _try_read_disk_cache(path)
    if cached is None:
        return None
    if (_json_tuple(cached.get("db_sig") or ()) == db_sig
            and cached.get("cache_version") == _CACHE_VERSION):
        return cached
    return None


def _write_cache(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


_bg_rebuild_running = False
_bg_rebuild_lock = threading.Lock()


def get_cached_stats_all(con) -> dict:
    db_sig = _db_signature(con)

    stats_cache = _stats_cache_path()
    cached = _read_cache(stats_cache, db_sig)
    if cached is not None:
        return cached

    stale = _try_read_disk_cache(stats_cache)
    if stale is not None and stale.get("basic"):
        _trigger_background_rebuild()
        stale["_stale"] = True
        return stale

    return _build_stats_all(con, db_sig)


def _build_stats_all(con, db_sig: tuple) -> dict:
    result = {
        "file_count_sig": db_sig[0],
        "max_mtime_sig": db_sig[1],
        "db_sig": db_sig,
        "cache_version": _CACHE_VERSION,
        "basic": build_basic_stats(con),
        "hourly": build_hourly_stats(con),
        "timeline": build_timeline_stats(con, "month"),
        "models": build_model_stats(con),
        "resolutions": build_resolution_stats(con),
    }
    try:
        _write_cache(_stats_cache_path(), result)
    except OSError:
        _logger.debug("stats cache write failed (permission or disk error)", exc_info=True)
    return result


def _trigger_background_rebuild() -> None:
    global _bg_rebuild_running
    with _bg_rebuild_lock:
        if _bg_rebuild_running:
            return
        _bg_rebuild_running = True

    def _rebuild():
        global _bg_rebuild_running
        try:
            from core.services_core.db_cipher import apply_key as _apply_key
            from core.services_core.db_cipher import sqlite3 as _cipher_sqlite3
            from core.services_core.db_state import get_db_path

            con = _cipher_sqlite3.connect(str(get_db_path()), timeout=30.0)
            try:
                _apply_key(con)
                con.row_factory = _cipher_sqlite3.Row
                con.execute("PRAGMA busy_timeout=30000")
                db_sig = _db_signature(con)
                _build_stats_all(con, db_sig)
            finally:
                con.close()
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Background stats rebuild failed", exc_info=True,
            )
        finally:
            with _bg_rebuild_lock:
                _bg_rebuild_running = False

    t = threading.Thread(target=_rebuild, daemon=True, name="stats-rebuild")
    t.start()


def warmup_stats_cache() -> None:
    from core.services_core.db_cipher import apply_key as _apply_key
    from core.services_core.db_cipher import sqlite3 as _cipher_sqlite3
    from core.services_core.db_state import get_db_path

    try:
        con = _cipher_sqlite3.connect(str(get_db_path()), timeout=30.0)
        _apply_key(con)
        con.row_factory = _cipher_sqlite3.Row
        con.execute("PRAGMA busy_timeout=30000")
        db_sig = _db_signature(con)
        existing = _read_cache(_stats_cache_path(), db_sig)
        if existing is None:
            _build_stats_all(con, db_sig)
        con.close()
    except Exception:
        _logger.debug("stats step failed", exc_info=True)


_bg_monthly_rebuild_inflight: set[str] = set()
_bg_monthly_rebuild_lock = threading.Lock()


def _trigger_background_monthly_rebuild(month: str) -> None:
    with _bg_monthly_rebuild_lock:
        if month in _bg_monthly_rebuild_inflight:
            return
        _bg_monthly_rebuild_inflight.add(month)

    def _rebuild():
        try:
            from core.services_core.db_cipher import apply_key as _apply_key
            from core.services_core.db_cipher import sqlite3 as _cipher_sqlite3
            from core.services_core.db_state import get_db_path

            con = _cipher_sqlite3.connect(str(get_db_path()), timeout=30.0)
            try:
                _apply_key(con)
                con.row_factory = _cipher_sqlite3.Row
                con.execute("PRAGMA busy_timeout=30000")
                db_sig = _db_signature(con)
                result = build_monthly_report(con, month)
                result["file_count_sig"] = db_sig[0]
                result["max_mtime_sig"] = db_sig[1]
                result["db_sig"] = db_sig
                result["cache_version"] = _CACHE_VERSION
                result["_month"] = month
                _write_cache(_monthly_cache_path(month), result)
            finally:
                con.close()
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Background monthly_report rebuild failed", exc_info=True,
            )
        finally:
            with _bg_monthly_rebuild_lock:
                _bg_monthly_rebuild_inflight.discard(month)

    threading.Thread(target=_rebuild, daemon=True, name=f"monthly-rebuild-{month}").start()


def get_cached_monthly_report(con, month: str) -> dict:
    db_sig = _db_signature(con)

    monthly_cache = _monthly_cache_path(month)
    cached = _read_cache(monthly_cache, db_sig)
    if cached is not None and cached.get("_month") == month:
        return cached

    stale = _try_read_disk_cache(monthly_cache)
    if stale is not None and stale.get("_month") == month:
        _trigger_background_monthly_rebuild(month)
        stale["_stale"] = True
        return stale

    result = build_monthly_report(con, month)
    result["file_count_sig"] = db_sig[0]
    result["max_mtime_sig"] = db_sig[1]
    result["db_sig"] = db_sig
    result["cache_version"] = _CACHE_VERSION
    result["_month"] = month

    try:
        _write_cache(monthly_cache, result)
    except OSError:
        _logger.debug("monthly_report cache write failed", exc_info=True)
    return result


_bg_story_rebuild_running = False
_bg_story_rebuild_lock = threading.Lock()

def _trigger_background_story_rebuild() -> None:
    global _bg_story_rebuild_running
    with _bg_story_rebuild_lock:
        if _bg_story_rebuild_running:
            return
        _bg_story_rebuild_running = True

    def _rebuild():
        global _bg_story_rebuild_running
        try:
            from core.services_core.db_cipher import apply_key as _apply_key
            from core.services_core.db_cipher import sqlite3 as _cipher_sqlite3
            from core.services_core.db_state import get_db_path

            con = _cipher_sqlite3.connect(str(get_db_path()), timeout=30.0)
            try:
                _apply_key(con)
                con.row_factory = _cipher_sqlite3.Row
                con.execute("PRAGMA busy_timeout=30000")
                db_sig = _db_signature(con)
                result = build_story_stats(con)
                result["file_count_sig"] = db_sig[0]
                result["max_mtime_sig"] = db_sig[1]
                result["db_sig"] = db_sig
                result["cache_version"] = _CACHE_VERSION
                _write_cache(_story_cache_path(), result)
            finally:
                con.close()
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Background story rebuild failed", exc_info=True,
            )
        finally:
            with _bg_story_rebuild_lock:
                _bg_story_rebuild_running = False

    threading.Thread(target=_rebuild, daemon=True, name="story-rebuild").start()

def get_cached_story(con) -> dict:
    db_sig = _db_signature(con)

    story_cache = _story_cache_path()
    cached = _read_cache(story_cache, db_sig)
    if cached is not None:
        return cached

    stale = _try_read_disk_cache(story_cache)
    if stale is not None:
        _trigger_background_story_rebuild()
        stale["_stale"] = True
        return stale

    result = build_story_stats(con)
    result["file_count_sig"] = db_sig[0]
    result["max_mtime_sig"] = db_sig[1]
    result["db_sig"] = db_sig
    result["cache_version"] = _CACHE_VERSION

    try:
        _write_cache(story_cache, result)
    except OSError:
        _logger.debug("story cache write failed", exc_info=True)
    return result

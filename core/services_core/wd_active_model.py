"""Persistent active WD-Tagger model state and model inventory helpers."""

from __future__ import annotations

import sqlite3
import threading
import time
import unicodedata
from typing import Any

from core.services_core import kv_state
from core.services_core.db_state import get_readonly_db
from core.services_core.wd_dict_resolver import resolve_model_id_readonly

# TTL cache for list_available_model_ids — refreshed at most once per interval.
# Retag batch jobs write to file_wd_tags at high frequency (2000+ writes/session);
# caching avoids lock-contention stalls on the profiles endpoint during retag.
_available_model_ids_cache: set[str] | None = None
_available_model_ids_ts: float = 0.0
_available_model_ids_lock = threading.Lock()
_AVAILABLE_MODEL_IDS_TTL = 30.0  # seconds

KEY_WD_ACTIVE_MODEL_ID = "wd_active_model_id"
MODEL_ID_MAX_LEN = 128

_UPSERT_ACTIVE_MODEL_SQL = (
    "INSERT INTO kv_state(key, value) VALUES(?, ?) "
    "ON CONFLICT(key) DO UPDATE SET "
    "value = excluded.value, "
    "updated_at = strftime('%s','now')"
)


def validate_model_id(raw: str | None) -> str | None:
    """Normalize and validate a WD model id."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("model_id must be a string or null")
    model_id = raw.strip()
    if not model_id:
        return None
    if len(model_id) > MODEL_ID_MAX_LEN:
        raise ValueError("model_id is too long")
    if any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in model_id):
        raise ValueError("model_id contains disallowed control characters")
    return model_id


def get_active_wd_model_id() -> str | None:
    """Return the active WD model id, normalizing missing/empty state to None."""
    value = kv_state.get(KEY_WD_ACTIVE_MODEL_ID)
    if value == "":
        return None
    return value


def try_get_active_wd_model_id_for_legacy_schema() -> str | None:
    """Return active WD model id with narrow legacy/minimal-test fallbacks.

    Some fast-path tests use a minimal schema that predates ``kv_state``. That
    case, and tests that skip DB_PATH initialization entirely, should behave
    like "active model unset"; other OperationalError / RuntimeError cases
    such as locks, corruption, or SQL mistakes must propagate.
    """
    try:
        return get_active_wd_model_id()
    except RuntimeError as exc:
        if "DB_PATH is not initialized" in str(exc):
            return None
        raise
    except Exception as exc:
        if (
            isinstance(exc, sqlite3.OperationalError)
            or exc.__class__.__name__ == "OperationalError"
        ) and "kv_state" in str(exc):
            return None
        raise


def invalidate_available_model_ids_cache() -> None:
    """Invalidate the list_available_model_ids TTL cache (call after tag writes)."""
    global _available_model_ids_cache, _available_model_ids_ts
    with _available_model_ids_lock:
        _available_model_ids_cache = None
        _available_model_ids_ts = 0.0


def set_active_wd_model_id(model_id: str | None) -> None:
    """Persist the active WD model id, or delete the setting for None/empty."""
    validated = validate_model_id(model_id)

    def _write() -> None:
        con = kv_state.get_db()
        if validated is None:
            con.execute("DELETE FROM kv_state WHERE key = ?", (KEY_WD_ACTIVE_MODEL_ID,))
        else:
            con.execute(_UPSERT_ACTIVE_MODEL_SQL, (KEY_WD_ACTIVE_MODEL_ID, validated))
        con.commit()
        invalidate_available_model_ids_cache()
        from core.search_api.count_cache import count_cache

        count_cache.invalidate()

    kv_state.submit_db_write(_write)


def set_active_wd_model_id_writer(model_id: str | None, con: Any) -> None:
    """Set active WD model id inside an existing writer transaction.

    This helper follows the single-writer convention and intentionally does
    not commit; the caller owns commit/rollback. Example: call it inside
    ``submit_db_write`` together with
    ``replace_wd_tags_atomic_batch(commit=False)`` to make tag replacement and
    active-model switching part of one transaction.
    """
    validated = validate_model_id(model_id)
    if validated is None:
        con.execute("DELETE FROM kv_state WHERE key = ?", (KEY_WD_ACTIVE_MODEL_ID,))
        return
    con.execute(_UPSERT_ACTIVE_MODEL_SQL, (KEY_WD_ACTIVE_MODEL_ID, validated))


def list_available_models() -> list[dict]:
    """List WD models that currently have file_wd_tags rows."""
    rows = get_readonly_db().execute(
        "SELECT md.model, COUNT(DISTINCT fwt.file_id) AS file_count "
        "FROM file_wd_tags fwt "
        "JOIN wd_model_dict md ON md.id = fwt.model_id "
        "GROUP BY fwt.model_id, md.model "
        "ORDER BY md.model"
    ).fetchall()
    return [
        {"model_id": str(row["model"]), "file_count": int(row["file_count"])}
        for row in rows
    ]


def list_available_model_ids() -> set[str]:
    """Return the set of model ids that have at least one file_wd_tags row.

    Cheaper than :func:`list_available_models` because it skips the
    COUNT(DISTINCT file_id) aggregation entirely — useful when the caller
    only needs a per-model boolean (e.g. ``has_tags`` flag in the profiles
    UI). Backed by ``idx_fwt_model_file`` (migration 73) so this is
    an index-only scan even on multi-million-row DBs.

    Result is cached for _AVAILABLE_MODEL_IDS_TTL seconds to avoid stalls
    during high-frequency retag batch writes.
    """
    global _available_model_ids_cache, _available_model_ids_ts
    now = time.monotonic()
    with _available_model_ids_lock:
        if _available_model_ids_cache is not None and (now - _available_model_ids_ts) < _AVAILABLE_MODEL_IDS_TTL:
            return set(_available_model_ids_cache)
    rows = get_readonly_db().execute(
        "SELECT DISTINCT md.model "
        "FROM file_wd_tags fwt "
        "JOIN wd_model_dict md ON md.id = fwt.model_id"
    ).fetchall()
    result = {str(row["model"]) for row in rows}
    with _available_model_ids_lock:
        _available_model_ids_cache = result
        _available_model_ids_ts = time.monotonic()
    return result


def model_has_tags(model_id: str) -> bool:
    """Return True if file_wd_tags contains at least one row for model_id."""
    con = get_readonly_db()
    mid = resolve_model_id_readonly(con, model_id)
    if mid is None:
        return False
    row = con.execute(
        "SELECT 1 FROM file_wd_tags WHERE model_id = ? LIMIT 1",
        (mid,),
    ).fetchone()
    return row is not None


def model_is_builtin_profile(model_id: str) -> bool:
    """Return True when model_id resolves to a bundled WD tagger profile."""
    from extensions.builtin_wd_tagger.core_impl.registry import TaggerRegistry

    return TaggerRegistry.get().resolve_any(model_id) is not None


def model_is_known_for_activation(model_id: str) -> bool:
    """Return True for models that can be selected as active.

    A model is selectable when it already has tags in the DB or when it is a
    bundled profile that can be used before the first tagging run.
    """
    if model_is_builtin_profile(model_id):
        return True
    return model_has_tags(model_id)

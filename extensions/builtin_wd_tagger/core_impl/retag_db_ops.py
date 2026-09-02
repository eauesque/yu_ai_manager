"""Shared DB helpers for WD retag jobs."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from core.services_core.wd_tagger_write_service import replace_wd_tags_atomic_batch

logger = logging.getLogger(__name__)


def is_missing_kv_state_error(exc: sqlite3.OperationalError) -> bool:
    return "no such table: kv_state" in str(exc)


def get_read_db():
    from core.services_core.db_state import get_readonly_db

    return get_readonly_db()


def submit_db_write(fn, *args, **kwargs):
    from core.services_core.db_write import submit_db_write as _submit_db_write

    return _submit_db_write(fn, *args, **kwargs)


def write_retag_items(
    *,
    items: list[tuple[int, str, Any]],
    overwrite_same_model: bool = True,
    auto_set_active: bool = True,
    invalidate_count_cache: bool = True,
    get_db_fn=None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    try:
        inserted = replace_wd_tags_atomic_batch(
            items,
            overwrite_same_model=overwrite_same_model,
            commit=False,
            get_db_fn=lambda: con,
        )
        if auto_set_active:
            _set_active_for_items(con, items)
        con.commit()
        if invalidate_count_cache:
            _invalidate_count_cache()
        return inserted
    except Exception:
        con.rollback()
        raise


def finalize_retag_batch(
    *,
    model_id: str,
    auto_set_active: bool = True,
    invalidate_count_cache: bool = True,
    get_db_fn=None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    try:
        if auto_set_active:
            _set_active_model_id(con, model_id)
        con.commit()
        if invalidate_count_cache:
            _invalidate_count_cache()
    except Exception:
        con.rollback()
        raise


def _set_active_for_items(con, items: list[tuple[int, str, Any]]) -> None:
    model_ids = sorted({model_id for _, model_id, _ in items})
    if len(model_ids) == 1:
        _set_active_model_id(con, model_ids[0])
    elif len(model_ids) > 1:
        logger.warning("retag worker: multiple model_ids (%s), skipping auto_set_active", model_ids)


def _set_active_model_id(con, model_id: str) -> None:
    from core.services_core.wd_active_model import set_active_wd_model_id_writer

    try:
        set_active_wd_model_id_writer(model_id, con)
    except sqlite3.OperationalError as exc:
        if not is_missing_kv_state_error(exc):
            raise
        logger.warning("retag worker: kv_state table missing, skipping auto_set_active")


def _invalidate_count_cache() -> None:
    from core.search_api.count_cache import count_cache
    from core.services_core.wd_active_model import invalidate_available_model_ids_cache

    count_cache.invalidate()
    invalidate_available_model_ids_cache()

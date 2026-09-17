"""Database operations for WD-Tagger tags.

CRUD operations on the file_wd_tags table.
Uses parameterized SQL throughout.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write
from core.services_core.wd_dict_resolver import resolve_model_id_readonly

from .types import WdTagResult

logger = logging.getLogger(__name__)


def _like_escape(value: str) -> str:
    return value.replace("~", "~~").replace("%", "~%").replace("_", "~_")


def _scan_root_like_patterns(scan_root: str) -> tuple[str, str]:
    root = scan_root.rstrip("/\\")
    fwd = _like_escape(root.replace("\\", "/").rstrip("/"))
    bck = _like_escape(root.replace("/", "\\").rstrip("\\"))
    return f"{fwd}/%", f"{bck}\\%"


def _is_missing_kv_state_error(exc: sqlite3.OperationalError) -> bool:
    return "no such table: kv_state" in str(exc)


def _get_active_wd_model_id_for_store() -> str | None:
    from core.services_core import wd_active_model

    try:
        return wd_active_model.try_get_active_wd_model_id_for_legacy_schema()
    except RuntimeError:
        return None


def save_wd_tags(
    file_id: int,
    result: WdTagResult,
    *,
    auto_set_active: bool = False,
) -> int:
    """Save WD tag predictions to database (atomic full replace)."""
    return save_wd_tags_batch([(file_id, result)], auto_set_active=auto_set_active)


def save_wd_tags_batch(
    items: list[tuple[int, WdTagResult]],
    *,
    auto_set_active: bool = False,
) -> int:
    """Save multiple WD results in one serialized writer transaction."""
    if not items:
        return 0

    from core.services_core.wd_tagger_write_service import (
        replace_wd_tags_atomic_batch,
    )

    new_items = []
    for fid, result in items:
        model_id = result.model_id
        if not model_id:
            raise ValueError(f"WD tag result for file_id={fid} has empty model_id")
        new_items.append((fid, model_id, result))

    def _write() -> int:
        from core.services_core.wd_active_model import set_active_wd_model_id_writer

        con = get_db()
        try:
            inserted = replace_wd_tags_atomic_batch(
                new_items,
                overwrite_same_model=True,
                commit=False,
                get_db_fn=lambda: con,
            )
            model_ids = sorted({model_id for _, model_id, _ in new_items})
            if auto_set_active and len(model_ids) == 1:
                try:
                    set_active_wd_model_id_writer(model_ids[0], con)
                except sqlite3.OperationalError as exc:
                    if not _is_missing_kv_state_error(exc):
                        raise
                    logger.warning(
                        "save_wd_tags_batch: kv_state table missing, "
                        "skipping auto_set_active",
                    )
            elif auto_set_active and len(model_ids) > 1:
                logger.warning(
                    "save_wd_tags_batch: multiple model_ids in batch (%s), "
                    "skipping auto_set_active",
                    model_ids,
                )
            con.commit()
            from core.search_api.count_cache import count_cache
            from core.services_core.wd_active_model import (
                invalidate_available_model_ids_cache,
            )

            invalidate_available_model_ids_cache()
            count_cache.invalidate()
            return inserted
        except Exception:
            con.rollback()
            raise

    return submit_db_write(_write)


def get_files_with_wd_tags(file_ids: list[int]) -> set[int]:
    """Return the subset of file_ids that already have at least one WD tag.

    Single readonly query (chunked to stay below SQLITE_MAX_VARIABLE_NUMBER).
    Replaces N-times-per-file existence checks done inside batch loops
    (SQLITE_IMPLEMENTATION_GUIDE.md § 3.6 / § 10.2: avoid loop-internal
    SELECTs).
    """
    if not file_ids:
        return set()
    con = get_readonly_db()
    active_model_id = _get_active_wd_model_id_for_store()
    out: set[int] = set()
    CHUNK = 500
    for start in range(0, len(file_ids), CHUNK):
        chunk = file_ids[start:start + CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        params: list = list(chunk)
        model_clause = ""
        if active_model_id is not None:
            mid = resolve_model_id_readonly(con, active_model_id)
            if mid is None:
                return set()
            model_clause = " AND model_id = ?"
            params.append(mid)
        rows = con.execute(
            f"SELECT DISTINCT file_id FROM file_wd_tags "
            f"WHERE file_id IN ({placeholders}){model_clause}",
            params,
        )
        for r in rows:
            out.add(r[0])
    return out


def get_wd_tags(
    file_id: int,
    model: str | None = None,
    *,
    include_all: bool = False,
) -> list[dict]:
    """Get WD tags for a file, optionally filtered by model."""
    con = get_readonly_db()
    effective_model = (
        None
        if include_all
        else model if model is not None else _get_active_wd_model_id_for_store()
    )
    if effective_model:
        mid = resolve_model_id_readonly(con, effective_model)
        if mid is None:
            return []
        rows = con.execute(
            """SELECT td.tag_name, fwt.confidence_milli / 1000.0 AS confidence,
                      cd.category, md.model, fwt.created_at
               FROM file_wd_tags fwt
               JOIN wd_tag_dict td ON td.id = fwt.tag_id
               JOIN wd_category_dict cd ON cd.id = fwt.category_id
               JOIN wd_model_dict md ON md.id = fwt.model_id
               WHERE fwt.file_id = ? AND fwt.model_id = ?
               ORDER BY fwt.confidence_milli DESC, fwt.id""",
            (file_id, mid),
        ).fetchall()
    else:
        rows = con.execute(
            """SELECT td.tag_name, fwt.confidence_milli / 1000.0 AS confidence,
                      cd.category, md.model, fwt.created_at
               FROM file_wd_tags fwt
               JOIN wd_tag_dict td ON td.id = fwt.tag_id
               JOIN wd_category_dict cd ON cd.id = fwt.category_id
               JOIN wd_model_dict md ON md.id = fwt.model_id
               WHERE fwt.file_id = ?
               ORDER BY fwt.confidence_milli DESC, fwt.id""",
            (file_id,),
        ).fetchall()

    return [dict(r) for r in rows]


def delete_wd_tags(file_id: int, model: str | None = None) -> int:
    """Delete WD tags for a file. Returns count of deleted rows."""
    from core.services_core.wd_tagger_write_service import delete_wd_tags_for_files

    result = submit_db_write(
        lambda: delete_wd_tags_for_files([file_id], model, get_db_fn=get_db)
    )
    return result["deleted_tags"]


def delete_wd_tags_batch(
    file_ids: list[int], model: str | None = None,
) -> dict:
    """Delete WD tags for multiple files at once.

    Returns {"deleted_files": int, "deleted_tags": int}
    """
    if not file_ids:
        return {"deleted_files": 0, "deleted_tags": 0}

    from core.services_core.wd_tagger_write_service import delete_wd_tags_for_files

    return submit_db_write(
        lambda: delete_wd_tags_for_files(file_ids, model, get_db_fn=get_db)
    )


def get_wd_tag_stats() -> dict:
    """Compute WD tag statistics by running the full aggregate queries.

    Caller should prefer ``load_wd_tag_stats_cache`` for the hot path;
    this function is only called from the background refresh thread.
    """
    con = get_readonly_db()

    total_tags = con.execute("SELECT COUNT(*) FROM file_wd_tags").fetchone()[0]
    tagged_files = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT file_id FROM file_wd_tags)"
    ).fetchone()[0]
    unique_tags = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT tag_id FROM file_wd_tags)"
    ).fetchone()[0]

    cats = con.execute(
        "SELECT cd.category, COUNT(*) "
        "FROM file_wd_tags fwt "
        "JOIN wd_category_dict cd ON cd.id = fwt.category_id "
        "GROUP BY fwt.category_id, cd.category ORDER BY cd.category"
    ).fetchall()
    by_category = {r[0]: r[1] for r in cats}

    models = con.execute(
        "SELECT md.model, COUNT(*) "
        "FROM (SELECT DISTINCT model_id, file_id FROM file_wd_tags) x "
        "JOIN wd_model_dict md ON md.id = x.model_id "
        "GROUP BY x.model_id, md.model"
    ).fetchall()
    by_model = {r[0]: r[1] for r in models}

    return {
        "total_tags": total_tags,
        "tagged_files": tagged_files,
        "unique_tags": unique_tags,
        "by_category": by_category,
        "by_model": by_model,
    }


def load_wd_tag_stats_cache() -> dict | None:
    """Return cached stats from the DB (O(1)), or None if empty/table missing."""
    try:
        con = get_readonly_db()
        row = con.execute(
            "SELECT stats_json, computed_at FROM wd_tag_stats_cache WHERE id=1"
        ).fetchone()
        if row is None or not row[0] or row[0] == "{}":
            return None
        return json.loads(row[0])
    except Exception:
        return None


def save_wd_tag_stats_cache(stats: dict) -> None:
    """Persist computed stats to the DB cache (called from background thread)."""
    payload = json.dumps(stats, ensure_ascii=False)
    now = int(time.time())

    def _write() -> None:
        con = get_db()
        try:
            con.execute(
                "INSERT OR REPLACE INTO wd_tag_stats_cache (id, stats_json, computed_at)"
                " VALUES (1, ?, ?)",
                (payload, now),
            )
            con.commit()
        except Exception:
            con.rollback()
            raise

    submit_db_write(_write)


def get_untagged_unknown_files(
    limit: int = 100, offset: int = 0, scan_root: str = "",
) -> list[dict]:
    """Get all untagged files (no WD tags) regardless of meta_source.

    Returns every active file that has not yet been tagged by WD-Tagger.
    Non-taggable types (audio / PDF / text) are filtered at the
    batch_ops prescan stage via ``is_taggable_file()``, so we deliberately
    do NOT filter by meta_source at the SQL layer — generated images with
    parsed metadata (``a1111_*`` / ``novelai_*`` / ``comfy*``) are eligible
    too, allowing WD tags to complement prompt-derived tags.

    Args:
        limit: Max files to return. 0 or negative = no limit (all files).
        offset: Offset for pagination (only used when limit > 0).
        scan_root: Limit to files under this directory path prefix.

    """
    con = get_readonly_db()
    active_model_id = _get_active_wd_model_id_for_store()
    where_extra = ""
    params: list = []
    model_clause = ""
    if active_model_id is not None:
        mid = resolve_model_id_readonly(con, active_model_id)
        model_clause = " AND w.model_id = ?"
        params.append(mid if mid is not None else -1)
    if scan_root:
        where_extra = " AND (f.path LIKE ? ESCAPE '~' OR f.path LIKE ? ESCAPE '~')"
        params.extend(_scan_root_like_patterns(scan_root))

    base_sql = f"""SELECT f.id, f.path, f.meta_source
           FROM files f
           WHERE f.is_deleted = 0
             AND NOT EXISTS (
               SELECT 1 FROM file_wd_tags w
               WHERE w.file_id = f.id{model_clause}
             ){where_extra}
           ORDER BY f.id"""
    if limit > 0:
        rows = con.execute(base_sql + " LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    else:
        rows = con.execute(base_sql, params).fetchall()
    return [dict(r) for r in rows]


def count_untagged_unknown_files(scan_root: str = "") -> int:
    """Count all untagged files (no WD tags) regardless of meta_source.

    Mirrors ``get_untagged_unknown_files`` filter semantics; non-taggable
    types are still counted here but skipped at prescan time.
    """
    con = get_readonly_db()
    active_model_id = _get_active_wd_model_id_for_store()
    where_extra = ""
    params: list = []
    model_clause = ""
    if active_model_id is not None:
        mid = resolve_model_id_readonly(con, active_model_id)
        model_clause = " AND w.model_id = ?"
        params.append(mid if mid is not None else -1)
    if scan_root:
        where_extra = " AND (f.path LIKE ? ESCAPE '~' OR f.path LIKE ? ESCAPE '~')"
        params.extend(_scan_root_like_patterns(scan_root))

    row = con.execute(
        f"""SELECT COUNT(*)
           FROM files f
           WHERE f.is_deleted = 0
             AND NOT EXISTS (
               SELECT 1 FROM file_wd_tags w
               WHERE w.file_id = f.id{model_clause}
             ){where_extra}""",
        params,
    ).fetchone()
    return row[0]

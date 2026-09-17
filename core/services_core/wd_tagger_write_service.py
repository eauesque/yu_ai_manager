"""Write helpers for WD-Tagger tag persistence."""

from __future__ import annotations

from collections.abc import Callable

from core.services_core.wd_confidence_scale import confidence_to_milli
from core.services_core.wd_dict_resolver import (
    resolve_category_id,
    resolve_model_id,
    resolve_model_id_readonly,
    resolve_tag_ids,
)


def _invalidate_count_cache() -> None:
    from core.search_api.count_cache import count_cache

    count_cache.invalidate()


def _invalidate_wd_write_caches() -> None:
    from core.services_core.wd_active_model import (
        invalidate_available_model_ids_cache,
    )

    invalidate_available_model_ids_cache()
    _invalidate_count_cache()


def delete_wd_tags_for_files(
    file_ids: list[int],
    model: str | None = None,
    *,
    get_db_fn: Callable | None = None,
) -> dict:
    """Delete WD tags for files, optionally scoped to one model.

    Returns {"deleted_files": int, "deleted_tags": int}.
    """
    if not file_ids:
        return {"deleted_files": 0, "deleted_tags": 0}

    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    unique_file_ids = list(dict.fromkeys(file_ids))
    mid: int | None = None
    if model:
        mid = resolve_model_id_readonly(con, model)
        if mid is None:
            return {"deleted_files": 0, "deleted_tags": 0}
    deleted_by_file: dict[int, int] = {}
    chunk_size = 500
    for start in range(0, len(unique_file_ids), chunk_size):
        chunk = unique_file_ids[start:start + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        if model:
            rows = con.execute(
                "SELECT file_id, COUNT(*) AS c FROM file_wd_tags "
                f"WHERE file_id IN ({placeholders}) AND model_id = ? "
                "GROUP BY file_id",
                (*chunk, mid),
            )
        else:
            rows = con.execute(
                "SELECT file_id, COUNT(*) AS c FROM file_wd_tags "
                f"WHERE file_id IN ({placeholders}) "
                "GROUP BY file_id",
                chunk,
            )
        for row in rows:
            deleted_by_file[int(row[0])] = int(row[1])

    try:
        if model:
            con.executemany(
                "DELETE FROM file_wd_tags WHERE file_id = ? AND model_id = ?",
                [(file_id, mid) for file_id in unique_file_ids],
            )
        else:
            con.executemany(
                "DELETE FROM file_wd_tags WHERE file_id = ?",
                [(file_id,) for file_id in unique_file_ids],
            )
        con.commit()
        _invalidate_wd_write_caches()
    except Exception:
        con.rollback()
        raise
    return {
        "deleted_files": len(deleted_by_file),
        "deleted_tags": sum(deleted_by_file.values()),
    }


# ============================================================
# Atomic replace helpers (Phase 1b, spec § 5.1)
# ============================================================
#
# Used by all retag entry points (single / batch / backfill / query) to
# guarantee that "DELETE existing tags for (file_id, model_id) THEN
# INSERT new tags" runs as a single SQLite transaction. UNIQUE(file_id,
# tag_id, model_id) is the hard guard; this helper provides the logical
# atomicity (no race window between DELETE and INSERT).

from extensions.builtin_wd_tagger.core_impl.adapters.base import TagResult


def replace_wd_tags_atomic(
    file_id: int,
    model_id: str,
    new_result: TagResult,
    *,
    overwrite_same_model: bool = True,
    commit: bool = True,
    get_db_fn=None,
) -> int:
    """Atomically replace all tags for (file_id, model_id).

    Single SQLite transaction:
      1. (if overwrite_same_model) DELETE FROM file_wd_tags
         WHERE file_id=? AND model_id=?
      2. INSERT new tag rows

    **MUST be called from the single-writer thread**: callers must wrap
    invocation in `submit_db_write(lambda: replace_wd_tags_atomic(...))`
    to satisfy `SQLITE_IMPLEMENTATION_GUIDE.md` § 3.2 (write serialization).
    By default the helper executes `con.commit()` / `con.rollback()` because
    DELETE + INSERT must be atomic against concurrent readers; calling this
    from a non-writer thread violates the single-writer guarantee and may
    deadlock or corrupt WAL state. When ``commit=False``, this helper never
    calls ``commit()`` or ``rollback()``; the caller must always commit or
    roll back in its own outer ``try`` / ``except`` block. This allows multiple
    atomic writes to be combined into one transaction, for example retagging
    rows and switching the active WD model together.

    Args:
        file_id: target file id
        model_id: model identifier string (resolved to `model_id` FK internally)
        new_result: TagResult holding the new tag predictions. The
            ``model_id`` arg is authoritative — if `new_result.model_id`
            is set and disagrees, ValueError is raised to catch wiring
            bugs.
        overwrite_same_model: when True (default), drop existing rows for
            (file_id, model_id) before inserting. When False, keep them
            and rely on UNIQUE constraint to silently skip duplicates
            (rows already present count as 0 toward the return value).
        commit: when True (default), commit on success and roll back on
            exception. When False, do not commit or roll back; caller owns
            the surrounding transaction.
        get_db_fn: dependency-injected DB connection getter (defaults to
            `core.services_core.db_state.get_db`).

    Returns:
        Number of rows inserted (excludes ``OR IGNORE`` skips).
    """
    if new_result.model_id and new_result.model_id != model_id:
        raise ValueError(
            f"model_id mismatch: arg={model_id!r}, "
            f"new_result.model_id={new_result.model_id!r}"
        )

    if get_db_fn is None:
        from core.services_core.db_state import get_db
        get_db_fn = get_db

    con = get_db_fn()
    inserted = 0
    # Single transaction. SQLite's autocommit (BEGIN ... COMMIT) is
    # implicit; commit/rollback keeps DELETE and INSERT atomic here.
    try:
        cursor = con.cursor()
        mid = resolve_model_id(con, model_id)
        if overwrite_same_model:
            cursor.execute(
                "DELETE FROM file_wd_tags WHERE file_id = ? AND model_id = ?",
                (file_id, mid),
            )
        tag_ids = resolve_tag_ids(con, [tag.tag for tag in new_result.tags])
        category_ids = {
            category: resolve_category_id(con, category)
            for category in dict.fromkeys(tag.category for tag in new_result.tags)
        }
        rows = [
            (
                file_id,
                tag_ids[tag.tag],
                confidence_to_milli(tag.confidence),
                category_ids[tag.category],
                mid,
            )
            for tag in new_result.tags
        ]
        if rows:
            cursor.executemany(
                "INSERT OR IGNORE INTO file_wd_tags "
                "(file_id, tag_id, confidence_milli, category_id, model_id) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            inserted = cursor.rowcount
        if commit:
            con.commit()
            _invalidate_wd_write_caches()
    except Exception:
        if commit:
            con.rollback()
        raise
    return inserted


def replace_wd_tags_atomic_batch(
    items: list[tuple[int, str, TagResult]],
    *,
    overwrite_same_model: bool = True,
    commit: bool = True,
    get_db_fn=None,
) -> int:
    """Batch version: atomic replace for multiple (file_id, model_id, result).

    All replacements run inside a single transaction so a mid-batch failure
    rolls back every modification when ``commit=True``. When ``commit=False``,
    this helper never calls ``commit()`` or ``rollback()``; the caller must
    always commit or roll back in its own outer ``try`` / ``except`` block.
    This allows multiple atomic writes to be combined into one transaction,
    for example retagging rows and switching the active WD model together.

    **MUST be called from the single-writer thread** — see
    `replace_wd_tags_atomic` docstring for the wrapping requirement.

    Args:
        items: list of (file_id, model_id, TagResult) tuples. Each
            ``model_id`` must agree with ``result.model_id`` (raises
            ValueError on mismatch). Duplicate ``(file_id, model_id)``
            keys are rejected with ValueError — callers must coalesce
            upstream because the bulk path cannot reproduce the legacy
            loop's last-write-wins ordering.
        overwrite_same_model: see replace_wd_tags_atomic
        commit: see replace_wd_tags_atomic
        get_db_fn: see replace_wd_tags_atomic

    Returns:
        Total number of rows inserted across all items.
    """
    if not items:
        return 0
    seen: set[tuple[int, str]] = set()
    for file_id, model_id, result in items:
        if result.model_id and result.model_id != model_id:
            raise ValueError(
                f"model_id mismatch in batch item file_id={file_id}: "
                f"arg={model_id!r}, result.model_id={result.model_id!r}"
            )
        # The bulk DELETE/INSERT path can't replicate the per-item
        # last-write-wins semantics of the legacy loop, so reject
        # duplicate (file_id, model_id) keys explicitly. Callers must
        # coalesce upstream; silent merge would mask wiring bugs.
        key = (file_id, model_id)
        if key in seen:
            raise ValueError(
                f"duplicate (file_id, model_id)={key!r} in batch items"
            )
        seen.add(key)

    if get_db_fn is None:
        from core.services_core.db_state import get_db
        get_db_fn = get_db

    con = get_db_fn()
    total_inserted = 0
    try:
        cursor = con.cursor()
        model_ids = {
            model: resolve_model_id(con, model)
            for model in dict.fromkeys(model_id for _, model_id, _ in items)
        }
        if overwrite_same_model:
            delete_keys = [(fid, model_ids[model]) for fid, model, _ in items]
            cursor.executemany(
                "DELETE FROM file_wd_tags WHERE file_id = ? AND model_id = ?",
                delete_keys,
            )
        tag_ids = resolve_tag_ids(
            con,
            [tag.tag for _, _, result in items for tag in result.tags],
        )
        category_ids = {
            category: resolve_category_id(con, category)
            for category in dict.fromkeys(
                tag.category for _, _, result in items for tag in result.tags
            )
        }
        insert_rows = [
            (
                file_id,
                tag_ids[tag.tag],
                confidence_to_milli(tag.confidence),
                category_ids[tag.category],
                model_ids[model_id],
            )
            for file_id, model_id, result in items
            for tag in result.tags
        ]
        if insert_rows:
            cursor.executemany(
                "INSERT OR IGNORE INTO file_wd_tags "
                "(file_id, tag_id, confidence_milli, category_id, model_id) "
                "VALUES (?, ?, ?, ?, ?)",
                insert_rows,
            )
            total_inserted = cursor.rowcount
        if commit:
            con.commit()
            _invalidate_wd_write_caches()
    except Exception:
        if commit:
            con.rollback()
        raise
    return total_inserted

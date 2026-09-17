"""Throttled backfill of tag_name_normalized for legacy file_wd_tags rows.

spec: docs/superpowers/specs/2026-05-10-tagger-pluggable-models-design.md
§ 5.6.2

Selects rows where ``tag_name_normalized IS NULL`` in chunks of
``batch_size``, computes ``normalize_tag(tag_name)``, UPDATEs them
through the writer thread, then sleeps ``sleep_ms`` ms between chunks
to limit I/O contention. Marks ``kv_state.tag_normalized_backfill_v1``
as ``"running"`` while active and ``"completed"`` when no NULL rows
remain.

Idempotent and resumable: if the process is killed mid-backfill, the
next call (e.g. on app restart) re-selects the remaining NULL rows
and continues. The file write path always sets ``tag_name_normalized``
on new INSERT/UPDATE, so backfill only handles legacy rows.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from core.tagging.tag_normalize import normalize_tag

logger = logging.getLogger(__name__)

BACKFILL_MARKER_KEY = "tag_normalized_backfill_v1"


def backfill_tag_normalized(
    *,
    get_read_fn: Callable | None = None,
    get_db_fn: Callable | None = None,
    submit_fn: Callable | None = None,
    batch_size: int = 200,
    sleep_ms: int = 200,
) -> int:
    """Run v71-v80 legacy backfill until no NULL rows remain. Idempotent.

    This touches legacy ``file_wd_tags.tag_name`` and
    ``file_wd_tags.tag_name_normalized`` columns only. Schema v81 and later
    normalize WD tags into dictionary tables, so this function is a no-op
    there.

    Returns the total number of rows updated.

    Args:
        get_read_fn: returns a readonly DB connection (defaults to
            ``core.services_core.db_state.get_readonly_db``).
        get_db_fn: returns the writer DB connection (defaults to
            ``core.services_core.db_state.get_db``). Used inside
            ``submit_fn``-wrapped callbacks.
        submit_fn: writer-thread dispatch (defaults to
            ``core.services_core.db_write.submit_db_write``).
        batch_size: number of rows to process per chunk.
        sleep_ms: ms to sleep between chunks to throttle I/O.
    """
    if get_read_fn is None:
        from core.services_core.db_state import get_readonly_db
        get_read_fn = get_readonly_db

    from core.schema_core.schema_migrate_version import get_schema_version

    schema_version = get_schema_version(get_read_fn())
    if schema_version >= 81:
        logger.warning(
            "tag_normalized backfill skipped: schema_version=%d uses "
            "dictionary-normalized file_wd_tags",
            schema_version,
        )
        return 0

    if get_db_fn is None:
        from core.services_core.db_state import get_db
        get_db_fn = get_db
    if submit_fn is None:
        from core.services_core.db_write import submit_db_write
        submit_fn = submit_db_write

    # Use injected writer for the marker too (tests pass _passthrough so
    # the inline DB sees the change). Production callers use the default
    # submit_db_write which dispatches to the writer thread.
    # Marker writes are observability-only; swallow OperationalError so a
    # startup-time lock contention (concurrent ANALYZE / file_meta_cache
    # warmup holding the write lock past busy_timeout) does not abort the
    # actual UPDATE batches that follow.
    _try_set_marker(submit_fn, get_db_fn, "running")

    total_updated = 0
    while True:
        rows = get_read_fn().execute(
            "SELECT id, tag_name FROM file_wd_tags "
            "WHERE tag_name_normalized IS NULL "
            "ORDER BY id LIMIT ?",
            (batch_size,),
        ).fetchall()
        if not rows:
            break
        updates = [(normalize_tag(r["tag_name"]), r["id"]) for r in rows]
        submit_fn(lambda u=updates: _apply_updates_write(get_db_fn, u))
        total_updated += len(updates)
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    _try_set_marker(submit_fn, get_db_fn, "completed")
    logger.info(
        "tag_normalized backfill complete: %d rows updated", total_updated
    )
    return total_updated


def _try_set_marker(submit_fn: Callable, get_db_fn: Callable, value: str) -> None:
    """Best-effort marker write; logs and swallows OperationalError.

    The marker is observability state ("running"/"completed"). At app
    startup the writer thread can be blocked behind concurrent ANALYZE /
    file_meta_cache warmup that hold the write lock past busy_timeout;
    failing the marker write must not abort the resumable UPDATE work
    that follows (and the next boot will set it correctly).
    """
    try:
        submit_fn(lambda: _set_marker_write(get_db_fn, value))
    except Exception:
        logger.warning(
            "tag_normalized backfill marker write failed (value=%s); "
            "continuing without marker update",
            value,
            exc_info=True,
        )


def _apply_updates_write(get_db_fn: Callable, updates: list[tuple[str, int]]) -> None:
    con = get_db_fn()
    con.executemany(
        "UPDATE file_wd_tags SET tag_name_normalized = ? WHERE id = ?",
        updates,
    )
    con.commit()


def _set_marker_write(get_db_fn: Callable, value: str) -> None:
    con = get_db_fn()
    con.execute(
        "INSERT INTO kv_state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET "
        "value = excluded.value, "
        "updated_at = strftime('%s','now')",
        (BACKFILL_MARKER_KEY, value),
    )
    con.commit()

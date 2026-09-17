"""Write helpers for webhook delivery log operations."""

from __future__ import annotations

import time

# Number of rows to delete per purge invocation. Each chunk runs as one writer-thread
# task; callers re-invoke until rowcount drops below this so other writes can interleave.
PURGE_CHUNK_SIZE = 5000


def _insert_webhook_delivery_write(row: tuple) -> None:
    from core.services_core.db_api import get_db

    con = get_db()
    con.execute(
        "INSERT INTO webhook_deliveries "
        "(webhook_id, event_type, payload_json, status_code, response_body, "
        " attempt, success, error, created_at, delivered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        row,
    )
    con.commit()


def insert_webhook_delivery(
    webhook_id: str,
    event_type: str,
    payload_json: str,
    status_code: int | None,
    response_body: str | None,
    attempt: int,
    success: bool,
    error: str | None,
) -> None:
    from core.services_core.db_write import submit_db_write

    now = int(time.time())
    row = (
        webhook_id,
        event_type,
        payload_json,
        status_code,
        response_body,
        attempt,
        1 if success else 0,
        error,
        now,
        now if success else None,
    )
    submit_db_write(_insert_webhook_delivery_write, row)


def _purge_webhook_deliveries_write(cutoff: int) -> int:
    from core.services_core.db_api import get_db

    con = get_db()
    cur = con.execute(
        "DELETE FROM webhook_deliveries WHERE id IN ("
        " SELECT id FROM webhook_deliveries WHERE created_at < ? LIMIT ?"
        ")",
        (cutoff, PURGE_CHUNK_SIZE),
    )
    con.commit()
    return cur.rowcount


def purge_webhook_deliveries_older_than(max_age_days: int) -> int:
    """Delete one chunk of webhook delivery rows older than max_age_days.

    Returns the number of rows deleted in this single chunk. The caller is
    expected to re-invoke until the rowcount drops below PURGE_CHUNK_SIZE so
    that each chunk is a short, independent writer-thread task — letting other
    queued writes interleave between chunks instead of being starved by one
    multi-second DELETE.
    """
    from core.services_core.db_write import submit_db_write

    cutoff = int(time.time()) - (max_age_days * 86400)
    return submit_db_write(_purge_webhook_deliveries_write, cutoff)

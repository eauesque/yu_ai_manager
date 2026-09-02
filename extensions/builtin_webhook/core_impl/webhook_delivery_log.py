"""Webhook delivery log — DB read/write for delivery history."""

from __future__ import annotations

from typing import Any


def _do_log_delivery(
    webhook_id: str,
    event_type: str,
    payload_json: str,
    status_code: int | None,
    response_body: str | None,
    attempt: int,
    success: bool,
    error: str | None,
) -> None:
    """Perform the actual DB insert on the dedicated writer thread."""
    from core.services_core.webhook_delivery_service import insert_webhook_delivery

    insert_webhook_delivery(
        webhook_id,
        event_type,
        payload_json,
        status_code,
        response_body,
        attempt,
        success,
        error,
    )
    # pooled connection: do not close


def log_delivery(
    webhook_id: str,
    event_type: str,
    payload_json: str,
    *,
    status_code: int | None = None,
    response_body: str | None = None,
    attempt: int = 1,
    success: bool = False,
    error: str | None = None,
) -> None:
    """Insert a delivery log entry via the dedicated DB-writer thread.

    Routes through submit_db_write_no_wait so that webhook thread-pool
    workers (up to 4 concurrent) do not compete with other writers for
    the SQLite WAL write lock.
    """
    from core.services_core.db_write import submit_db_write_no_wait
    submit_db_write_no_wait(
        _do_log_delivery,
        webhook_id, event_type, payload_json,
        status_code, response_body, attempt, success, error,
    )


def list_deliveries(
    webhook_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List recent delivery log entries."""
    from core.services_core.db_api import get_readonly_db
    con = get_readonly_db()
    if webhook_id:
        rows = con.execute(
            "SELECT id, webhook_id, event_type, status_code, attempt, "
            "success, error, created_at, delivered_at "
            "FROM webhook_deliveries WHERE webhook_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (webhook_id, limit),
        )
    else:
        rows = con.execute(
            "SELECT id, webhook_id, event_type, status_code, attempt, "
            "success, error, created_at, delivered_at "
            "FROM webhook_deliveries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    return [
        {
            "id": r[0], "webhook_id": r[1], "event_type": r[2],
            "status_code": r[3], "attempt": r[4],
            "success": bool(r[5]), "error": r[6],
            "created_at": r[7], "delivered_at": r[8],
        }
        for r in rows
    ]
    # pooled connection: do not close


def _do_purge_old_deliveries(max_age_days: int) -> int:
    """Delete one chunk on the writer thread; re-queue self if more remain.

    Each chunk is a separate writer task so other queued writes can interleave
    between chunks instead of being starved by a single multi-second DELETE.
    """
    from core.services_core.db_write import submit_db_write_no_wait
    from core.services_core.webhook_delivery_service import (
        PURGE_CHUNK_SIZE,
        purge_webhook_deliveries_older_than,
    )

    deleted = purge_webhook_deliveries_older_than(max_age_days)
    if deleted >= PURGE_CHUNK_SIZE:
        # More rows likely remain — schedule the next chunk as a fresh task.
        submit_db_write_no_wait(_do_purge_old_deliveries, max_age_days)
    return deleted
    # pooled connection: do not close


def purge_old_deliveries(max_age_days: int = 7) -> int:
    """Delete delivery logs older than max_age_days via the dedicated writer thread.

    Fire-and-forget chunked purge: returns 0 immediately and processes the table
    in 5000-row chunks on the writer thread, re-queuing itself until done.
    Callers (e.g. startup housekeeping) are never blocked, and other writes can
    interleave between chunks.
    """
    from core.services_core.db_write import submit_db_write_no_wait
    submit_db_write_no_wait(_do_purge_old_deliveries, max_age_days)
    return 0

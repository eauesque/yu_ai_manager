"""Write helpers for Bluesky notification queue operations."""

from __future__ import annotations

from collections.abc import Iterable


def _enqueue_notifications_write(rows: list[tuple]) -> dict[str, int]:
    from core.services_core.db_state import get_db

    db = get_db()
    counts: dict[str, int] = {}
    for row in rows:
        ntype = row[0]
        cur = db.execute(
            "INSERT OR IGNORE INTO bluesky_notification_queue "
            "(notification_type, author_handle, author_display_name, "
            "uri, cid, subject_uri, text, indexed_at, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        if cur.rowcount > 0:
            counts[ntype] = counts.get(ntype, 0) + 1
    db.commit()
    return counts


def enqueue_notifications(rows: Iterable[tuple]) -> dict[str, int]:
    """Insert notification queue rows, ignoring duplicates."""
    from core.services_core.db_write import submit_db_write

    return submit_db_write(_enqueue_notifications_write, list(rows))


def _update_queue_status_write(queue_id: int, status: str) -> bool:
    from core.services_core.db_state import get_db

    db = get_db()
    db.execute(
        "UPDATE bluesky_notification_queue SET status = ? WHERE id = ?",
        (status, queue_id),
    )
    db.commit()
    return db.total_changes > 0


def update_queue_status(queue_id: int, status: str) -> bool:
    from core.services_core.db_write import submit_db_write

    return submit_db_write(_update_queue_status_write, queue_id, status)


def _update_queue_triage_result_write(queue_id: int, result: str) -> bool:
    from core.services_core.db_state import get_db

    db = get_db()
    db.execute(
        "UPDATE bluesky_notification_queue SET triage_result = ? WHERE id = ?",
        (result, queue_id),
    )
    db.commit()
    return db.total_changes > 0


def update_queue_triage_result(queue_id: int, result: str) -> bool:
    from core.services_core.db_write import submit_db_write

    return submit_db_write(_update_queue_triage_result_write, queue_id, result)


def _mark_auto_response_sent_write(queue_id: int) -> None:
    from core.services_core.db_state import get_db

    db = get_db()
    db.execute(
        "UPDATE bluesky_notification_queue "
        "SET auto_response_sent = 1, status = 'notified' WHERE id = ?",
        (queue_id,),
    )
    db.commit()


def mark_auto_response_sent(queue_id: int) -> None:
    from core.services_core.db_write import submit_db_write

    submit_db_write(_mark_auto_response_sent_write, queue_id)

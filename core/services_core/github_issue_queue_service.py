"""Write helpers for GitHub issue queue operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _enqueue_issue_write(
    repo: str, issue_number: int, title: str, body: str, created_at: str, now: str
) -> bool:
    from core.services_core.db_state import get_db

    db = get_db()
    try:
        cur = db.execute(
            "INSERT OR IGNORE INTO github_issue_queue "
            "(repo, issue_number, title, body, created_at, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (repo, issue_number, title, body[:3000], created_at, now),
        )
        db.commit()
        return cur.rowcount > 0
    except Exception as exc:
        logger.warning("Failed to enqueue issue %s#%d: %s", repo, issue_number, exc)
        return False


def enqueue_issue(
    repo: str,
    issue_number: int,
    title: str,
    body: str,
    created_at: str,
) -> bool:
    """Add an issue to the queue. Returns True if newly inserted."""
    from core.services_core.db_write import submit_db_write

    now = datetime.now(UTC).isoformat()
    return submit_db_write(
        _enqueue_issue_write, repo, issue_number, title, body, created_at, now
    )


def _update_triage_result_write(queue_id: int, result: str) -> bool:
    from core.services_core.db_state import get_db

    db = get_db()
    db.execute(
        "UPDATE github_issue_queue SET triage_result = ? WHERE id = ?",
        (result, queue_id),
    )
    db.commit()
    return db.total_changes > 0


def update_triage_result(queue_id: int, result: str) -> bool:
    from core.services_core.db_write import submit_db_write

    return submit_db_write(_update_triage_result_write, queue_id, result)


def _update_status_write(queue_id: int, status: str) -> bool:
    from core.services_core.db_state import get_db

    db = get_db()
    db.execute(
        "UPDATE github_issue_queue SET status = ? WHERE id = ?",
        (status, queue_id),
    )
    db.commit()
    return db.total_changes > 0


def update_status(queue_id: int, status: str) -> bool:
    from core.services_core.db_write import submit_db_write

    return submit_db_write(_update_status_write, queue_id, status)


def dismiss_invalid(queue_id: int) -> bool:
    return update_status(queue_id, "dismissed")

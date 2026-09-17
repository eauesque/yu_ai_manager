"""Issue queue management -- local DB cache for GitHub issues.

Pending issues are queued for MCP notification on connection.
"""

from __future__ import annotations

from typing import Any

from core.services_core.db_state import get_readonly_db

# Auto-close comment for invalid issues
INVALID_ISSUE_COMMENT = (
    "Thank you for your report.\n\n"
    "This issue has been reviewed by an automated triage system and does not meet "
    "the criteria for a valid bug report (technical reproduction steps, error logs, "
    "and environment information are required).\n\n"
    "If you believe this is a valid bug, please resubmit with:\n"
    "- Steps to reproduce\n"
    "- Error log or stack trace\n"
    "- Environment (OS, version)\n\n"
    "Refer to the FAQ for support policy."
)


def get_pending_count() -> int:
    """Return count of pending issues in the queue."""
    db = get_readonly_db()
    row = db.execute(
        "SELECT COUNT(*) FROM github_issue_queue WHERE status = 'pending'"
    ).fetchone()
    return row[0] if row else 0


def get_pending_issues() -> list[dict[str, Any]]:
    """Return all pending issues."""
    db = get_readonly_db()
    rows = db.execute(
        "SELECT id, repo, issue_number, title, body, created_at, "
        "fetched_at, status, triage_result "
        "FROM github_issue_queue WHERE status = 'pending' "
        "ORDER BY fetched_at DESC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_queue_items(
    status: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Return queue items, optionally filtered by status."""
    db = get_readonly_db()
    if status:
        rows = db.execute(
            "SELECT id, repo, issue_number, title, body, created_at, "
            "fetched_at, status, triage_result "
            "FROM github_issue_queue WHERE status = ? "
            "ORDER BY fetched_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, repo, issue_number, title, body, created_at, "
            "fetched_at, status, triage_result "
            "FROM github_issue_queue "
            "ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def enqueue_issue(
    repo: str,
    issue_number: int,
    title: str,
    body: str,
    created_at: str,
) -> bool:
    """Add an issue to the queue. Returns True if newly inserted."""
    from core.services_core.github_issue_queue_service import enqueue_issue as _enqueue

    return _enqueue(repo, issue_number, title, body, created_at)


def update_triage_result(
    queue_id: int, result: str
) -> bool:
    """Update triage_result for a queue item. result: 'valid' | 'invalid'."""
    if result not in ("valid", "invalid"):
        return False
    from core.services_core.github_issue_queue_service import (
        update_triage_result as _update_triage_result,
    )

    return _update_triage_result(queue_id, result)


def update_status(
    queue_id: int, status: str
) -> bool:
    """Update status for a queue item. status: 'pending' | 'notified' | 'dismissed'."""
    if status not in ("pending", "notified", "dismissed"):
        return False
    from core.services_core.github_issue_queue_service import (
        update_status as _update_status,
    )

    return _update_status(queue_id, status)


def dismiss_invalid(queue_id: int) -> bool:
    """Mark as dismissed (used after auto-close)."""
    return update_status(queue_id, "dismissed")


def get_queue_stats() -> dict[str, int]:
    """Return summary counts by status."""
    db = get_readonly_db()
    rows = db.execute(
        "SELECT status, COUNT(*) FROM github_issue_queue GROUP BY status"
    ).fetchall()
    stats = {"pending": 0, "notified": 0, "dismissed": 0}
    for row in rows:
        stats[row[0]] = row[1]
    stats["total"] = sum(stats.values())
    return stats


def _row_to_dict(row) -> dict[str, Any]:
    """Convert a DB row to dict."""
    return {
        "id": row[0],
        "repo": row[1],
        "issue_number": row[2],
        "title": row[3],
        "body": row[4],
        "created_at": row[5],
        "fetched_at": row[6],
        "status": row[7],
        "triage_result": row[8],
    }

"""Bluesky notification monitoring -- poll and queue notifications.

Reuses bluesky_session for authentication. Fetches mentions, replies,
quotes, follows, likes, and reposts, then stores them in the local
bluesky_notification_queue table for MCP notification.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Notification types we track
NOTIF_TYPES = ("mention", "reply", "quote", "follow", "like", "repost")


def poll_notifications() -> dict[str, int]:
    """Poll Bluesky for new notifications and enqueue them.

    Returns dict of {type: count} for newly inserted notifications.
    """
    from .bluesky_session import get_client

    client, err = get_client()
    if err or not client:
        logger.warning("[BSKY_MONITOR] Cannot get client: %s", err)
        return {}

    try:
        response = client.app.bsky.notification.list_notifications(
            params={"limit": 50}
        )
    except Exception as exc:
        logger.warning("[BSKY_MONITOR] Failed to fetch notifications: %s", exc)
        return {}

    notifications = response.notifications if response else []
    if not notifications:
        return {}

    now = datetime.now(UTC).isoformat()
    rows_to_insert = []

    for notif in notifications:
        ntype = _map_reason(notif.reason)
        if ntype not in NOTIF_TYPES:
            continue

        author_handle = notif.author.handle if notif.author else ""
        author_name = ""
        if notif.author and notif.author.display_name:
            author_name = notif.author.display_name

        uri = notif.uri or ""
        cid = notif.cid or ""
        subject_uri = ""
        text = ""

        # Extract text from record for mentions/replies/quotes
        if hasattr(notif, "record") and notif.record:
            rec = notif.record
            if hasattr(rec, "text"):
                text = (rec.text or "")[:3000]
            # For quotes, the subject is in the embed
            if hasattr(rec, "embed") and rec.embed:
                embed = rec.embed
                if hasattr(embed, "record") and hasattr(embed.record, "uri"):
                    subject_uri = embed.record.uri

        # For likes/reposts, the subject is the target post
        if ntype in ("like", "repost") and hasattr(notif, "reason_subject"):
            subject_uri = notif.reason_subject or ""

        indexed_at = ""
        if hasattr(notif, "indexed_at") and notif.indexed_at:
            indexed_at = str(notif.indexed_at)

        rows_to_insert.append(
            (ntype, author_handle, author_name, uri, cid, subject_uri, text, indexed_at, now)
        )

    from core.services_core.bsky_notification_service import enqueue_notifications

    try:
        return enqueue_notifications(rows_to_insert)
    except Exception as exc:
        logger.warning("[BSKY_MONITOR] Failed to enqueue notifications: %s", exc)
        return {}


def get_pending_notifications(limit: int = 50) -> list[dict[str, Any]]:
    """Return pending notifications from the queue."""
    from core.services_core.db_state import get_readonly_db

    db = get_readonly_db()
    rows = db.execute(
        "SELECT id, notification_type, author_handle, author_display_name, "
        "uri, cid, subject_uri, text, indexed_at, fetched_at, "
        "status, triage_result, auto_response_sent "
        "FROM bluesky_notification_queue WHERE status = 'pending' "
        "ORDER BY fetched_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_queue_items(
    status: str = "", notif_type: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Return queue items with optional filters."""
    from core.services_core.db_state import get_readonly_db

    db = get_readonly_db()
    query = (
        "SELECT id, notification_type, author_handle, author_display_name, "
        "uri, cid, subject_uri, text, indexed_at, fetched_at, "
        "status, triage_result, auto_response_sent "
        "FROM bluesky_notification_queue"
    )
    conditions = []
    params: list = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if notif_type:
        conditions.append("notification_type = ?")
        params.append(notif_type)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY fetched_at DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_queue_stats() -> dict[str, int]:
    """Return summary counts by status and type."""
    from core.services_core.db_state import get_readonly_db

    db = get_readonly_db()
    rows = db.execute(
        "SELECT status, COUNT(*) FROM bluesky_notification_queue GROUP BY status"
    ).fetchall()
    stats: dict[str, int] = {"pending": 0, "notified": 0, "dismissed": 0}
    for row in rows:
        stats[row[0]] = row[1]
    stats["total"] = sum(stats.values())

    # Type breakdown
    type_rows = db.execute(
        "SELECT notification_type, COUNT(*) "
        "FROM bluesky_notification_queue WHERE status = 'pending' "
        "GROUP BY notification_type"
    ).fetchall()
    for row in type_rows:
        stats[f"pending_{row[0]}"] = row[1]

    return stats


def update_status(queue_id: int, status: str) -> bool:
    """Update status for a queue item."""
    if status not in ("pending", "notified", "dismissed"):
        return False
    from core.services_core.bsky_notification_service import update_queue_status

    return update_queue_status(queue_id, status)


def update_triage_result(queue_id: int, result: str) -> bool:
    """Update triage result for a queue item."""
    if result not in ("valid", "invalid"):
        return False
    from core.services_core.bsky_notification_service import update_queue_triage_result

    return update_queue_triage_result(queue_id, result)


def send_auto_response(queue_id: int, response_text: str) -> bool:
    """Send an auto-response reply to a notification's post.

    Only works for mentions/replies/quotes that have a URI.
    """
    from core.services_core.bsky_notification_service import mark_auto_response_sent
    from core.services_core.db_state import get_readonly_db

    from .bluesky_session import get_client

    rdb = get_readonly_db()
    row = rdb.execute(
        "SELECT uri, cid, notification_type FROM bluesky_notification_queue "
        "WHERE id = ?", (queue_id,)
    ).fetchone()
    if not row:
        return False

    uri, cid, ntype = row[0], row[1], row[2]
    if ntype not in ("mention", "reply", "quote"):
        return False
    if not uri:
        return False

    client, err = get_client()
    if err or not client:
        logger.warning("[BSKY_MONITOR] Cannot send response: %s", err)
        return False

    try:
        # Build reply reference
        from atproto import models
        parent_ref = models.create_strong_ref(uri, cid)
        root_ref = parent_ref  # Simplification: assume top-level
        client.send_post(
            text=response_text[:300],
            reply_to=models.AppBskyFeedPost.ReplyRef(
                parent=parent_ref,
                root=root_ref,
            ),
        )
    except Exception as exc:
        logger.warning("[BSKY_MONITOR] Auto-response failed: %s", exc)
        return False

    # Mark as responded
    mark_auto_response_sent(queue_id)
    return True


def _map_reason(reason: str) -> str:
    """Map AT Protocol notification reason to our type."""
    mapping = {
        "mention": "mention",
        "reply": "reply",
        "quote": "quote",
        "follow": "follow",
        "like": "like",
        "repost": "repost",
    }
    return mapping.get(reason, reason)


def _row_to_dict(row) -> dict[str, Any]:
    """Convert a DB row to dict."""
    return {
        "id": row[0],
        "notification_type": row[1],
        "author_handle": row[2],
        "author_display_name": row[3],
        "uri": row[4],
        "cid": row[5],
        "subject_uri": row[6],
        "text": row[7],
        "indexed_at": row[8],
        "fetched_at": row[9],
        "status": row[10],
        "triage_result": row[11],
        "auto_response_sent": bool(row[12]),
    }

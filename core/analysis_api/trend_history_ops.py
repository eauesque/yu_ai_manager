"""Prompt trend history persistence operations."""

import json
import time
from typing import Any

from core.services_core.db_api import get_raw_db

_MAX_HISTORY = 50


def _save_trend_history_write(
    engine: str, prompt_count: int, result_json: str
) -> int:
    con = get_raw_db()
    cur = con.execute(
        """
        INSERT INTO prompt_trend_history
            (engine, analyzed_at, prompt_count, result_json)
        VALUES (?, ?, ?, ?)
        """,
        (engine, int(time.time()), prompt_count, result_json),
    )
    row_id = cur.lastrowid
    con.execute(
        """
        DELETE FROM prompt_trend_history
        WHERE id NOT IN (
            SELECT id FROM prompt_trend_history
            ORDER BY analyzed_at DESC LIMIT ?
        )
        """,
        (_MAX_HISTORY,),
    )
    con.commit()
    return row_id or 0


def save_trend_history(
    engine: str, prompt_count: int, result: dict[str, Any]
) -> int:
    """Save a trend analysis result and prune old entries beyond _MAX_HISTORY."""
    from core.services_core.db_write import submit_db_write
    return submit_db_write(
        _save_trend_history_write, engine, prompt_count, json.dumps(result)
    )


def get_trend_history(
    limit: int = 20, offset: int = 0
) -> list[dict[str, Any]]:
    """Return trend history entries (newest first)."""
    from core.services_core.db_api import get_readonly_db
    con = get_readonly_db()
    rows = con.execute(
        """
        SELECT id, engine, analyzed_at, prompt_count, result_json
        FROM prompt_trend_history
        ORDER BY analyzed_at DESC
        LIMIT ? OFFSET ?
        """,
        (min(limit, _MAX_HISTORY), max(offset, 0)),
    )
    items: list[dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "id": r["id"],
                "engine": r["engine"],
                "analyzed_at": r["analyzed_at"],
                "prompt_count": r["prompt_count"],
                "result": json.loads(r["result_json"]),
            }
        )
    return items


def _delete_trend_history_write(history_id: int) -> bool:
    con = get_raw_db()
    cur = con.execute(
        "DELETE FROM prompt_trend_history WHERE id = ?", (history_id,)
    )
    con.commit()
    return cur.rowcount > 0


def delete_trend_history(history_id: int) -> bool:
    """Delete a single trend history entry. Returns True if deleted."""
    from core.services_core.db_write import submit_db_write
    return submit_db_write(_delete_trend_history_write, history_id)

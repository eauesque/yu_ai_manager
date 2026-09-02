"""Undo Engine — orchestration layer for agent operation rollback.

Coordinates before-state capture, after-state capture, undo execution,
and undo-able action queries. Delegates to:
  - undo_capture.py  — before-state capture handlers per tool
  - undo_handlers.py — undo execution handlers per action
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .undo_capture import CAPTURE_HANDLERS
from .undo_handlers import UNDO_HANDLERS

logger = logging.getLogger(__name__)

# Set of tool names that support undo
REVERSIBLE_TOOLS = {
    "rate_images",
    "set_tags",
    "set_annotations",
    "add_to_collection",
    "remove_from_collection",
    "create_collection",
    "create_prompt",
}


def is_reversible(tool_name: str) -> bool:
    """Return whether a tool supports undo."""
    return tool_name in REVERSIBLE_TOOLS


def _get_db() -> sqlite3.Connection:
    """Get DB connection via ServiceRegistry."""
    from core.extensions_core.service_registry import ServiceRegistry
    get_db_fn = ServiceRegistry.get("db")
    if callable(get_db_fn):
        return get_db_fn()
    return get_db_fn


def capture_before_state(
    tool_name: str, params: dict
) -> dict[str, Any] | None:
    """Capture state before tool execution for later undo.

    Returns:
        Undo parameters dict (JSON-serializable), or None.
    """
    if tool_name not in REVERSIBLE_TOOLS:
        return None

    try:
        handler = CAPTURE_HANDLERS.get(tool_name)
        if handler:
            return handler(params)
    except Exception as exc:
        logger.debug("undo capture failed for %s: %s", tool_name, exc)

    return None


def capture_after_state(
    tool_name: str, params: dict, result: Any, before_state: dict | None
) -> dict[str, Any] | None:
    """Finalize undo parameters using post-execution result.

    Used for tools like create_collection/create_prompt where the
    created ID is only known after execution.
    """
    if before_state is None:
        before_state = {}

    try:
        if tool_name == "create_collection":
            # Get created collection_id from result
            if isinstance(result, dict):
                cid = result.get("id") or result.get("data", {}).get("id")
                if cid:
                    return {"action": "delete_collection", "collection_id": cid}
        elif tool_name == "create_prompt" and isinstance(result, dict):
            pid = result.get("id") or result.get("data", {}).get("id")
            if pid:
                return {"action": "delete_prompt", "prompt_id": pid}
    except Exception as exc:
        logger.debug("undo after-capture failed for %s: %s", tool_name, exc)

    return before_state if before_state else None


def execute_undo(journal_id: int) -> dict[str, Any]:
    """Execute undo for the given journal entry.

    Returns:
        {"ok": bool, "message": str, "undone_tool": str}
    """
    from core.services_core.db_api import get_readonly_db
    ro = get_readonly_db()
    row = ro.execute(
        """SELECT id, tool_name, params_json, undo_params_json,
                  reversible, undone, status
           FROM agent_action_journal WHERE id = ?""",
        (journal_id,),
    ).fetchone()

    if row is None:
        return {"ok": False, "message": "操作が見つかりません"}

    _, tool_name, params_json, undo_params_json, reversible, undone, status = row

    if not reversible:
        return {"ok": False, "message": f"この操作 ({tool_name}) は undo 非対応です"}
    if undone:
        return {"ok": False, "message": "この操作は既に undo 済みです"}
    if status != "success":
        return {"ok": False, "message": f"ステータスが '{status}' の操作は undo できません"}
    if not undo_params_json:
        return {"ok": False, "message": "undo 情報が記録されていません"}

    try:
        undo_params = json.loads(undo_params_json)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "message": "undo パラメータのパースに失敗しました"}

    action = undo_params.get("action", "")
    handler = UNDO_HANDLERS.get(action)
    if handler is None:
        return {"ok": False, "message": f"undo アクション '{action}' のハンドラが見つかりません"}

    # Run the handler and the journal flag update on the dedicated DB
    # writer thread so all undo writes share the single-writer queue and
    # cannot race with the scanner / other writers.
    now = datetime.now(UTC).isoformat()

    def _run_undo_write() -> Any:
        from core.services_core.db_api import get_raw_db
        h_result = handler(undo_params)
        wcon = get_raw_db()
        wcon.execute(
            "UPDATE agent_action_journal SET undone = 1, undone_at = ? WHERE id = ?",
            (now, journal_id),
        )
        wcon.commit()
        return h_result

    try:
        from core.services_core.db_write import submit_db_write
        result = submit_db_write(_run_undo_write)
    except Exception as exc:
        logger.error("undo execution failed (journal_id=%d): %s", journal_id, exc)
        return {"ok": False, "message": f"undo 実行エラー: {exc}"}

    logger.info("undo completed: journal_id=%d, tool=%s", journal_id, tool_name)
    return {
        "ok": True,
        "message": f"{tool_name} の undo が完了しました",
        "undone_tool": tool_name,
        "undo_result": result,
    }


def get_undoable_actions(
    session_id: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Return list of undo-able actions."""
    db = _get_db()
    params: list = []

    base_sql = """SELECT id, session_id, timestamp, tool_name, params_json,
                   undo_params_json, affected_count
            FROM agent_action_journal
            WHERE reversible = 1 AND undone = 0 AND status = 'success'"""

    if session_id:
        base_sql += " AND session_id = ?"
        params.append(session_id)

    base_sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(base_sql, params)

    items = []
    for row in rows:
        items.append({
            "id": row[0],
            "session_id": row[1],
            "timestamp": row[2],
            "tool_name": row[3],
            "params_json": row[4],
            "undo_params_json": row[5],
            "affected_count": row[6],
        })
    return items

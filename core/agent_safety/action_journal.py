"""Action Journal -- recording, searching, and statistics of agent operations.

Records all MCP tool calls in the agent_action_journal table.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Maximum byte size for params_json
_MAX_PARAMS_BYTES = 10_000

# Keys whose values must be redacted before persisting to the journal
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "api_key", "apikey", "key", "password", "passwd", "pwd",
    "token", "secret", "auth", "authorization", "credential",
    "access_token", "refresh_token", "private_key", "bearer",
    "api_token", "export_data", "pin",
})
# Substrings that mark a key as sensitive (case-insensitive check)
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "secret",
    "api_key",
    "apikey",
    "api_token",
    "authorization",
    "export_data",
    "token",
    "pin",
)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _redact_params(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _redact_params(params: dict) -> dict:
    """Recursively replace sensitive key values with '[REDACTED]'."""
    result: dict = {}
    for k, v in params.items():
        k_lower = k.lower()
        if k_lower in _SENSITIVE_KEYS or any(s in k_lower for s in _SENSITIVE_SUBSTRINGS):
            result[k] = "[REDACTED]"
        else:
            result[k] = _redact_value(v)
    return result


def _redact_result_summary(result_summary: str) -> str:
    """Redact sensitive values in JSON result summaries before persistence."""
    if not result_summary:
        return result_summary
    try:
        parsed = json.loads(result_summary)
    except (TypeError, ValueError):
        return result_summary
    redacted = _redact_value(parsed)
    try:
        return json.dumps(redacted, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return result_summary


def _get_db_path_for_debug() -> str:
    """Return DB_PATH as a string for diagnostic logging. Never raises."""
    try:
        from core.services_core.app_runtime_state import DB_PATH
        return str(DB_PATH)
    except Exception:
        return "unavailable"


def _report_to_web_server(level: str, message: str, extra: dict) -> None:
    """Forward a log message from MCP subprocess to the Web Server's log ring.

    Fire-and-forget with a short timeout — never raises.
    Only used as a diagnostic channel when journal writes fail; this does NOT
    replace the journal itself (the journal must stay independent per COVENANT).
    Uses urllib.request (not httpx) to avoid RuntimeError when called from an
    asyncio context (_intercepted_call_tool is async; httpx sync client crashes
    with 'This event loop is already running' and is silently swallowed).
    """
    try:
        import json as _json
        import os
        import urllib.request

        base = os.environ.get("YU_BASE_URL", "http://localhost:5000").rstrip("/")
        payload: dict = {"level": level, "message": message, "source": "mcp_subprocess"}
        payload.update(extra)
        data = _json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{base}/api/internal/log",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.0):
            pass
    except Exception:
        # Must never crash journal code -- but a forwarder that has been down
        # for a week should not look identical to one that is working.
        logger.warning("journal entry was not forwarded", exc_info=True)


def _get_db() -> sqlite3.Connection:
    """Get DB connection via ServiceRegistry, with fallback for standalone MCP mode.

    When running as ``python -m mcp_server`` (stdio subprocess), ServiceRegistry
    is not initialized by the web-server bootstrap.  In that case we fall back
    to ``db_state.get_db()`` directly, which works as long as
    ``app_runtime_state.DB_PATH`` has been set (see ``mcp_server/__main__.py``).
    """
    try:
        from core.extensions_core.service_registry import ServiceRegistry
        get_db_fn = ServiceRegistry.get("db")
        if callable(get_db_fn):
            return get_db_fn()
        if get_db_fn is not None:
            return get_db_fn  # type: ignore[return-value]
    except Exception as e:
        logger.debug("ServiceRegistry.get('db') failed: %s", e)
    # Fallback: standalone MCP process — log the DB_PATH so we can diagnose mismatches
    db_path = _get_db_path_for_debug()
    logger.info("[mcp_subprocess] _get_db fallback, DB_PATH=%s", db_path)
    from core.services_core.db_state import get_db as _direct_get_db
    return _direct_get_db()


def _truncate_params(params: dict) -> str:
    """Redact sensitive keys and truncate parameter JSON to the byte size limit."""
    safe = _redact_params(params)
    try:
        raw = json.dumps(safe, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = str(safe)
    encoded = raw.encode("utf-8")
    if len(encoded) > _MAX_PARAMS_BYTES:
        # Truncate on byte boundary, then decode safely to avoid split multibyte chars
        raw = encoded[:_MAX_PARAMS_BYTES].decode("utf-8", errors="ignore") + "...(truncated)"
    return raw


def record_action(
    session_id: str,
    tool_name: str,
    params: dict | None = None,
    result_summary: str = "",
    status: str = "success",
    duration_ms: int = 0,
    caller_info: str = "",
    affected_count: int = 0,
    reversible: bool = False,
    undo_params: dict | None = None,
) -> int | None:
    """Record an operation in the journal. Returns the inserted row ID."""
    try:
        db = _get_db()
        params_json = _truncate_params(params or {})
        timestamp = datetime.now(UTC).isoformat()

        result_summary = _redact_result_summary(result_summary)

        # Truncate result_summary if too long
        if result_summary and len(result_summary) > 2000:
            result_summary = result_summary[:2000] + "...(truncated)"

        # Serialize undo_params_json (redact sensitive keys)
        undo_params_json = None
        if undo_params:
            try:
                undo_params_json = json.dumps(
                    _redact_params(undo_params), ensure_ascii=False, default=str
                )
            except (TypeError, ValueError):
                undo_params_json = None

        cursor = db.execute(
            """INSERT INTO agent_action_journal
               (session_id, timestamp, tool_name, params_json,
                result_summary, status, duration_ms, caller_info, affected_count,
                reversible, undo_params_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, timestamp, tool_name, params_json,
             result_summary, status, duration_ms, caller_info, affected_count,
             1 if reversible else 0, undo_params_json),
        )
        db.commit()
        return cursor.lastrowid
    except Exception as exc:
        db_path = _get_db_path_for_debug()
        logger.warning("Failed to record action journal [%s]: %s", tool_name, exc)
        logger.warning("DB_PATH at time of failure: %s", db_path)
        _report_to_web_server(
            level="WARNING",
            message=f"record_action failed [{tool_name}]: {exc}",
            extra={"db_path": db_path},
        )
        return None


def search_journal(
    tool_name: str = "",
    status: str = "",
    session_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Search the journal."""
    db = _get_db()
    conditions: list[str] = []
    params: list[Any] = []

    if tool_name:
        conditions.append("tool_name = ?")
        params.append(tool_name)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Get total count
    count_row = db.execute(
        f"SELECT COUNT(*) FROM agent_action_journal {where}", params
    ).fetchone()
    total = count_row[0] if count_row else 0

    # Fetch data
    rows = db.execute(
        f"""SELECT id, session_id, timestamp, tool_name, params_json,
                   result_summary, status, duration_ms, caller_info, affected_count
            FROM agent_action_journal {where}
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )

    items = []
    for row in rows:
        items.append({
            "id": row[0],
            "session_id": row[1],
            "timestamp": row[2],
            "tool_name": row[3],
            "params_json": row[4],
            "result_summary": row[5],
            "status": row[6],
            "duration_ms": row[7],
            "caller_info": row[8],
            "affected_count": row[9],
        })

    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_journal_stats() -> dict[str, Any]:
    """Return journal statistics."""
    db = _get_db()

    # Derive total from GROUP BY status (saves one full scan)
    by_status: dict[str, int] = {}
    total = 0
    for row in db.execute(
        "SELECT status, COUNT(*) FROM agent_action_journal GROUP BY status"
    ):
        by_status[row[0]] = row[1]
        total += row[1]

    by_tool = []
    for row in db.execute(
        """SELECT tool_name, COUNT(*) as cnt
           FROM agent_action_journal
           GROUP BY tool_name ORDER BY cnt DESC LIMIT 20"""
    ):
        by_tool.append({"tool_name": row[0], "count": row[1]})

    sessions = db.execute(
        "SELECT COUNT(DISTINCT session_id) FROM agent_action_journal"
    ).fetchone()[0]

    return {
        "total_actions": total,
        "by_status": by_status,
        "top_tools": by_tool,
        "total_sessions": sessions,
    }

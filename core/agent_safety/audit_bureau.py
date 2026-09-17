"""Audit Bureau -- independent audit mechanism for Agent Safety Gateway.

Operates outside the 7-layer Gateway. Reads from Action Journal and
Anomaly Detection but cannot be written to by any extension or agent.
Information flows one-way only.

Records to audit_log table (separate from agent_action_journal).
Emits SSE events for user notification.

This module re-exports constants from sub-modules
to maintain backward compatibility.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import threading
import time

# Re-export constants for backward compatibility
from core.agent_safety.audit_bureau_constants import (  # noqa: F401
    EVENT_ANOMALY,
    EVENT_BUDGET_WARNING,
    EVENT_CB_TRIGGERED,
    EVENT_EXTERNAL_SEND,
    EVENT_REPORT,
    EVENT_RULE_GAP,
    EVENT_SECRET_WRITE,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    _emit_sse,
    _get_db,
    _now_iso,
)
from core.agent_safety.audit_bureau_constants import (
    EXTERNAL_SEND_PATTERNS as _EXTERNAL_SEND_PATTERNS,
)
from core.agent_safety.audit_bureau_constants import (
    SECRET_TOOL_PATTERNS as _SECRET_TOOL_PATTERNS,
)
from core.agent_safety.audit_bureau_queries import (
    AuditBureauQueriesMixin,
)

logger = logging.getLogger(__name__)


class AuditBureau(AuditBureauQueriesMixin):
    """Independent audit mechanism.

    Cannot be disabled by Kill Switch or any other Gateway layer.
    """

    _instance: AuditBureau | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._report_interval = 86400  # 24 hours default
        self._last_report_time = time.time()
        self._enabled = True

    @classmethod
    def get_instance(cls) -> AuditBureau:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record(
        self,
        event_type: str,
        source: str,
        severity: str = SEVERITY_INFO,
        target: str = "",
        reported_to: str = "user",
        detail: dict | None = None,
    ) -> int | None:
        """Record an audit event with hash chain. Returns the audit log ID."""
        if not self._enabled:
            return None
        try:
            db = _get_db()
            timestamp = _now_iso()
            detail_json = json.dumps(
                detail or {}, ensure_ascii=False, default=str
            )[:5000]
            target_str = target or ""

            # Use BEGIN IMMEDIATE to prevent concurrent inserts from breaking
            # the hash chain (ensures prev_hash read + INSERT are atomic).
            db.execute("BEGIN IMMEDIATE")
            try:
                prev = db.execute(
                    "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = (prev[0] or "") if prev else ""
                raw = (
                    f"{prev_hash}{timestamp}{event_type}"
                    f"{source}{target_str}{severity}{detail_json}"
                )
                entry_hash = hashlib.sha256(raw.encode()).hexdigest()

                cursor = db.execute(
                    """INSERT INTO audit_log
                       (timestamp, event_type, source, target, severity,
                        reported_to, detail_json, prev_hash, entry_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (timestamp, event_type, source, target_str,
                     severity, reported_to, detail_json,
                     prev_hash, entry_hash),
                )
                db.commit()
                return cursor.lastrowid
            except Exception:
                with contextlib.suppress(Exception):
                    db.rollback()
                raise
        except Exception as exc:
            logger.warning("Audit Bureau: failed to record: %s", exc)
            return None

    def on_tool_call(
        self,
        tool_name: str,
        params: dict,
        source: str = "",
        status: str = "success",
    ) -> None:
        """Called after each MCP tool execution.

        Checks if the operation is audit-worthy and records accordingly.
        """
        tool_lower = tool_name.lower()

        # Check for secret/credential operations
        if any(pat in tool_lower for pat in _SECRET_TOOL_PATTERNS):
            self.record(
                event_type=EVENT_SECRET_WRITE,
                source=source or tool_name,
                severity=SEVERITY_CRITICAL,
                target=tool_name,
                reported_to="all",
                detail={"tool": tool_name, "status": status},
            )
            _emit_sse("audit.secret_access", {
                "source": source or tool_name,
                "target": tool_name,
                "type": EVENT_SECRET_WRITE,
                "requires_approval": True,
            })

        # Check for external send operations
        if any(pat in tool_lower for pat in _EXTERNAL_SEND_PATTERNS):
            # Sanitize params to not leak sensitive data
            safe_params = {
                k: v for k, v in (params or {}).items()
                if k in ("destination", "url", "target", "format", "count")
            }
            self.record(
                event_type=EVENT_EXTERNAL_SEND,
                source=source or tool_name,
                severity=SEVERITY_WARNING,
                target=safe_params.get("destination", safe_params.get("url", "")),
                reported_to="user",
                detail={"tool": tool_name, "summary": safe_params},
            )
            _emit_sse("audit.external_send", {
                "source": source or tool_name,
                "destination": safe_params.get("destination", ""),
                "summary": str(safe_params)[:200],
            })

    def on_anomaly_detected(
        self,
        pattern: str,
        severity: str,
        tool_name: str,
        message: str,
    ) -> None:
        """Called when Anomaly Detector raises an alert."""
        self.record(
            event_type=EVENT_ANOMALY,
            source=tool_name,
            severity=severity,
            reported_to="user",
            detail={"pattern": pattern, "message": message},
        )

    def on_circuit_breaker_triggered(
        self, tool_name: str, reason: str
    ) -> None:
        """Called when Circuit Breaker opens."""
        self.record(
            event_type=EVENT_CB_TRIGGERED,
            source=tool_name,
            severity=SEVERITY_WARNING,
            reported_to="all",
            detail={"reason": reason},
        )
        _emit_sse("audit.rule_gap_detected", {
            "pattern": "circuit_breaker_triggered",
            "suggestion": f"Circuit breaker triggered by {tool_name}: {reason}",
        })

    def on_budget_warning(
        self, session_id: str, usage_pct: float, detail: dict
    ) -> None:
        """Called when budget reaches 80%."""
        self.record(
            event_type=EVENT_BUDGET_WARNING,
            source=session_id,
            severity=SEVERITY_WARNING,
            reported_to="user",
            detail={"usage_pct": usage_pct, **detail},
        )


def get_audit_bureau() -> AuditBureau:
    """Get the singleton AuditBureau instance."""
    return AuditBureau.get_instance()

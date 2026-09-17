"""HITL Approval Gate -- manages the approval flow for Level 2 tools.

Approval flow:
1. Level 2 tool call -> added to pending approval queue
2. SSE event agent.approval_required is sent
3. Approval dialog displayed in UI
4. User responds -> POST /api/agent/approval/<request_id>
5. Tool executed or denied

Timeout: default 300 seconds (5 minutes). Treated as denial on expiry.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .approval_gate_events import emit_approval_required, emit_notify
from .approval_gate_singleton import get_or_create_gate

logger = logging.getLogger(__name__)

# Approval decisions
DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_ALWAYS_ALLOW = "always_allow"
DECISION_TIMEOUT = "timeout"

DEFAULT_TIMEOUT = 300  # 5 minutes


@dataclass
class ApprovalRequest:
    """Approval request."""

    request_id: str
    session_id: str
    tool_name: str
    params: dict
    created_at: float = field(default_factory=time.time)
    timeout: float = DEFAULT_TIMEOUT
    decision: str | None = None
    decided_at: float | None = None
    _event: threading.Event = field(default_factory=threading.Event, repr=False)


class ApprovalGate:
    """Approval gate for Level 2 tools."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[dict[str, Any]] = []  # Recent approval history
        self._max_history = 100

    def create_request(
        self,
        session_id: str,
        tool_name: str,
        params: dict,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> ApprovalRequest:
        """Create an approval request and send an SSE event."""
        req = ApprovalRequest(
            request_id=uuid.uuid4().hex[:12],
            session_id=session_id,
            tool_name=tool_name,
            params=params,
            timeout=timeout,
        )

        with self._lock:
            self._pending[req.request_id] = req

        # Send SSE event
        self._emit_approval_required(req)
        logger.info(
            "承認リクエスト作成: %s (tool=%s, session=%s)",
            req.request_id, tool_name, session_id,
        )
        return req

    def respond(self, request_id: str, decision: str) -> bool:
        """Respond to an approval request.

        Returns:
            True: Response successful
            False: Request not found or already responded
        """
        if decision not in (DECISION_ALLOW, DECISION_DENY, DECISION_ALWAYS_ALLOW):
            return False

        with self._lock:
            req = self._pending.get(request_id)
            if req is None:
                return False
            if req.decision is not None:
                return False

            req.decision = decision
            req.decided_at = time.time()
            req._event.set()

            # Add to history
            self._history.append({
                "request_id": req.request_id,
                "session_id": req.session_id,
                "tool_name": req.tool_name,
                "decision": decision,
                "created_at": req.created_at,
                "decided_at": req.decided_at,
                "wait_seconds": round(req.decided_at - req.created_at, 1),
            })
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        logger.info(
            "承認応答: %s → %s (tool=%s)",
            request_id, decision, req.tool_name,
        )
        return True

    async def wait_for_decision(
        self,
        request_id: str,
        timeout: float | None = None,
    ) -> str:
        """Wait asynchronously for the approval decision.

        Returns:
            DECISION_ALLOW / DECISION_DENY / DECISION_ALWAYS_ALLOW / DECISION_TIMEOUT
        """
        with self._lock:
            req = self._pending.get(request_id)
        if req is None:
            return DECISION_DENY

        wait_timeout = timeout or req.timeout
        loop = asyncio.get_running_loop()

        # Run threading.Event.wait in executor to make it async
        decided = await loop.run_in_executor(
            None, req._event.wait, wait_timeout
        )

        with self._lock:
            self._pending.pop(request_id, None)

        if not decided or req.decision is None:
            req.decision = DECISION_TIMEOUT
            req.decided_at = time.time()
            logger.warning(
                "承認タイムアウト: %s (tool=%s)", request_id, req.tool_name
            )
            return DECISION_TIMEOUT

        return req.decision

    def get_pending(self) -> list[dict[str, Any]]:
        """Return a list of pending approval requests."""
        now = time.time()
        result = []
        with self._lock:
            expired = []
            for rid, req in self._pending.items():
                elapsed = now - req.created_at
                if elapsed > req.timeout:
                    expired.append(rid)
                    continue
                result.append({
                    "request_id": req.request_id,
                    "session_id": req.session_id,
                    "tool_name": req.tool_name,
                    "params": req.params,
                    "created_at": req.created_at,
                    "remaining_seconds": round(req.timeout - elapsed, 1),
                })
            # Clean up expired requests
            for rid in expired:
                req = self._pending.pop(rid)
                req.decision = DECISION_TIMEOUT
                req._event.set()
        return result

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return approval history."""
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def cancel_all(self, session_id: str | None = None) -> int:
        """Cancel all pending approval requests."""
        count = 0
        with self._lock:
            to_remove = []
            for rid, req in self._pending.items():
                if session_id is None or req.session_id == session_id:
                    req.decision = DECISION_DENY
                    req._event.set()
                    to_remove.append(rid)
                    count += 1
            for rid in to_remove:
                self._pending.pop(rid, None)
        return count

    def status(self) -> dict[str, Any]:
        """Return the gate status."""
        return {
            "pending_count": len(self._pending),
            "pending": self.get_pending(),
            "recent_history": self.get_history(10),
        }

    def _emit_approval_required(self, req: ApprovalRequest) -> None:
        emit_approval_required(req)

    def _emit_notify(self, session_id: str, tool_name: str, params: dict) -> None:
        emit_notify(session_id, tool_name, params)


def get_approval_gate() -> ApprovalGate:
    return get_or_create_gate(ApprovalGate)

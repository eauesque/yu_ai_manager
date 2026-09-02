"""HITL gate handling for MCP interceptor."""

from __future__ import annotations

import logging

from .interceptor_checks_common import SESSION_ID

logger = logging.getLogger(__name__)


async def check_hitl_gate(tool_name: str, params: dict) -> str | None:
    from .interceptor_recording import _record
    try:
        from core.agent_safety.approval_gate import (
            DECISION_ALLOW,
            DECISION_ALWAYS_ALLOW,
            DECISION_TIMEOUT,
            get_approval_gate,
        )
        from core.agent_safety.scope_fence import add_auto_approve_rule, check_auto_approve
        from core.agent_safety.tool_classification import LEVEL_APPROVE, LEVEL_NOTIFY, classify

        level = classify(tool_name)
        if level == LEVEL_NOTIFY or level != LEVEL_APPROVE:
            return None
        if check_auto_approve(tool_name, params):
            logger.debug("Auto-approved: %s", tool_name)
            return None

        gate = get_approval_gate()
        request = gate.create_request(session_id=SESSION_ID, tool_name=tool_name, params=params)
        decision = await gate.wait_for_decision(request.request_id)

        if decision == DECISION_ALLOW:
            return None
        if decision == DECISION_ALWAYS_ALLOW:
            add_auto_approve_rule(tool_name)
            return None
        if decision == DECISION_TIMEOUT:
            message = (
                f"Approval timed out for '{tool_name}'. "
                f"The user did not respond within the timeout period. "
                f"Please try a different approach or ask the user directly."
            )
            _record(tool_name, params, "approval_timeout", 0, message)
            return message

        message = (
            f"Operation '{tool_name}' was denied by the user. "
            f"Do not retry this operation without explicit user permission."
        )
        _record(tool_name, params, "approval_denied", 0, message)
        return message
    except Exception as exc:
        logger.warning("HITL gate error (denying): %s", exc)
        return f"Approval unavailable for '{tool_name}'. Operation was not run."

"""Pre-execution safety checks for MCP interceptor."""

from __future__ import annotations

from .interceptor_checks_common import SESSION_ID, get_budget_tracker, get_circuit_breaker, get_kill_switch


def check_kill_switch(tool_name: str) -> str | None:
    from .interceptor_recording import _record
    kill_switch = get_kill_switch()
    if kill_switch and kill_switch.is_killed():
        status = kill_switch.status()
        message = "Agent kill switch is active. All tool calls are blocked."
        reason = status.get("reason", "")
        if reason:
            message += f" Reason: {reason}"
        _record(tool_name, {}, "killed", 0, message)
        return message
    return None


def check_circuit_breaker(tool_name: str) -> str | None:
    from .interceptor_recording import _record
    circuit_breaker = get_circuit_breaker()
    if circuit_breaker:
        message = circuit_breaker.check(tool_name)
        if message:
            _record(tool_name, {}, "circuit_blocked", 0, message)
            return message
    return None


def check_budget(tool_name: str) -> str | None:
    from .interceptor_recording import _record
    budget_tracker = get_budget_tracker()
    if budget_tracker:
        message = budget_tracker.check(tool_name)
        if message:
            _record(tool_name, {}, "budget_blocked", 0, message)
            return message
    return None


def check_scope(tool_name: str) -> str | None:
    from .interceptor_recording import _record
    try:
        from core.agent_safety.scope_fence import get_scope_fence
        message = get_scope_fence().check(SESSION_ID, tool_name)
    except Exception:
        # FAIL-SAFE: inability to evaluate scope must deny, not allow, so a
        # storage/import failure cannot silently remove the permission boundary.
        message = (
            "Scope check could not be evaluated. "
            "Denying the operation by default (fail-safe)."
        )
    if message:
        _record(tool_name, {}, "scope_blocked", 0, message)
        return message
    return None


def pre_check(tool_name: str) -> str | None:
    for check in (check_kill_switch, check_circuit_breaker, check_budget, check_scope):
        message = check(tool_name)
        if message:
            return message
    return None

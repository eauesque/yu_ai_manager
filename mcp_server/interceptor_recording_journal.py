"""Journal and undo recording helpers for interceptor."""

from __future__ import annotations

from .interceptor_checks_common import SESSION_ID, get_budget_tracker, get_circuit_breaker
from .interceptor_recording_anomaly import run_anomaly_detection
from .interceptor_recording_common import logger


def record_tool_action(
    tool_name: str,
    params: dict,
    status: str,
    duration_ms: int,
    result_summary: str = "",
    reversible: bool = False,
    undo_params: dict | None = None,
) -> None:
    try:
        from core.agent_safety.action_journal import record_action
        record_action(
            session_id=SESSION_ID,
            tool_name=tool_name,
            params=params,
            result_summary=result_summary,
            status=status,
            duration_ms=duration_ms,
            reversible=reversible,
            undo_params=undo_params,
        )
    except Exception as exc:
        logger.warning("Failed to record action: %s", exc)
    try:
        from core.agent_safety.audit_bureau import get_audit_bureau
        get_audit_bureau().on_tool_call(tool_name=tool_name, params=params or {}, source=SESSION_ID, status=status)
    except Exception:
        # A tool call the audit bureau never saw leaves no trace it happened.
        logger.warning("audit bureau did not record %s", tool_name, exc_info=True)


def capture_undo_before(tool_name: str, params: dict) -> dict | None:
    try:
        from core.agent_safety.undo_engine import capture_before_state
        return capture_before_state(tool_name, params)
    except Exception:
        return None


def record_success(tool_name: str, params: dict, duration_ms: int, result_summary: str = "", undo_before: dict | None = None, result_data: dict | None = None) -> None:
    reversible = False
    undo_params = undo_before
    try:
        from core.agent_safety.undo_engine import capture_after_state, is_reversible
        if is_reversible(tool_name):
            undo_params = capture_after_state(tool_name, params, result_data, undo_before)
            reversible = undo_params is not None
    except Exception:
        # `reversible` stays False, so the action is simply not offered for
        # undo -- correct, but worth knowing the capture keeps failing.
        logger.debug("undo capture failed for %s", tool_name, exc_info=True)
    record_tool_action(tool_name, params, "success", duration_ms, result_summary, reversible=reversible, undo_params=undo_params)
    circuit_breaker = get_circuit_breaker()
    if circuit_breaker:
        circuit_breaker.record(tool_name, params, is_error=False)
    budget_tracker = get_budget_tracker()
    if budget_tracker:
        budget_tracker.consume(tool_name)
    run_anomaly_detection(tool_name, params, is_error=False)
    try:
        from core.agent_safety.approval_gate import get_approval_gate
        from core.agent_safety.tool_classification import LEVEL_NOTIFY, classify
        if classify(tool_name) == LEVEL_NOTIFY:
            get_approval_gate()._emit_notify(SESSION_ID, tool_name, params)
    except Exception:
        # The operator was meant to be told about this call and was not.
        logger.warning("notify for %s did not reach the operator", tool_name, exc_info=True)


def record_error(tool_name: str, params: dict, duration_ms: int, error: str = "") -> None:
    record_tool_action(tool_name, params, "error", duration_ms, error)
    circuit_breaker = get_circuit_breaker()
    if circuit_breaker:
        circuit_breaker.record(tool_name, params, is_error=True, error_str=error)
    budget_tracker = get_budget_tracker()
    if budget_tracker:
        budget_tracker.consume(tool_name)
    run_anomaly_detection(tool_name, params, is_error=True)


def summarize_result(result_text: str) -> str:
    if not result_text:
        return ""
    if len(result_text) <= 200:
        return result_text
    return result_text[:200] + "..."

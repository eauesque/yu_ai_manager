"""MCP Interceptor -- all tool call recording and safety checks.

Re-exports from interceptor_checks and interceptor_recording
for backward compatibility.

Check order: Kill Switch -> Circuit Breaker -> Budget -> Scope Fence -> HITL Gate -> tool execution
"""

from .interceptor_checks import (  # noqa: F401
    SESSION_ID,
    check_budget,
    check_circuit_breaker,
    check_hitl_gate,
    check_kill_switch,
    check_scope,
    get_safety_level,
    pre_check,
)
from .interceptor_recording import (  # noqa: F401
    _record,
    _run_anomaly_detection,
    _summarize_result,
    capture_undo_before,
    record_error,
    record_success,
)

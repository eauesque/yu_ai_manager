"""Agent Safety Gateway -- mechanisms to ensure safety of agent operations.

Phase 1: Action Journal + Kill Switch
Phase 2: Circuit Breaker + Budget Enforcer
Phase 3: HITL Gate + Scope Fence
Phase 4: Undo + Anomaly Detection
"""

from .action_journal import get_journal_stats, record_action, search_journal
from .anomaly_detector import AnomalyDetector, get_anomaly_detector
from .approval_gate import ApprovalGate, get_approval_gate
from .budget_tracker import PRESETS, BudgetTracker, classify_tool, get_budget_tracker
from .circuit_breaker import AgentCircuitBreaker, get_circuit_breaker
from .kill_switch import AgentKillSwitch, get_kill_switch
from .scope_fence import (
    PRESETS as SCOPE_PRESETS,
)
from .scope_fence import (
    ScopeFence,
    add_auto_approve_rule,
    check_auto_approve,
    get_auto_approve_rules,
    get_scope_fence,
    remove_auto_approve_rule,
)
from .tool_classification import (
    LEVEL_APPROVE,
    LEVEL_AUTO,
    LEVEL_NOTIFY,
)
from .tool_classification import (
    classify as classify_safety_level,
)
from .tool_classification import (
    classify_name as classify_safety_level_name,
)
from .tool_classification import (
    configure as configure_tool_classification,
)
from .undo_engine import (
    REVERSIBLE_TOOLS,
    capture_after_state,
    capture_before_state,
    execute_undo,
    get_undoable_actions,
    is_reversible,
)

__all__ = [
    "get_kill_switch",
    "AgentKillSwitch",
    "record_action",
    "search_journal",
    "get_journal_stats",
    "get_circuit_breaker",
    "AgentCircuitBreaker",
    "get_budget_tracker",
    "BudgetTracker",
    "classify_tool",
    "PRESETS",
    # Phase 3
    "classify_safety_level",
    "classify_safety_level_name",
    "LEVEL_AUTO",
    "LEVEL_NOTIFY",
    "LEVEL_APPROVE",
    "configure_tool_classification",
    "get_approval_gate",
    "ApprovalGate",
    "get_scope_fence",
    "ScopeFence",
    "check_auto_approve",
    "get_auto_approve_rules",
    "add_auto_approve_rule",
    "remove_auto_approve_rule",
    "SCOPE_PRESETS",
    # Phase 4
    "is_reversible",
    "capture_before_state",
    "capture_after_state",
    "execute_undo",
    "get_undoable_actions",
    "REVERSIBLE_TOOLS",
    "get_anomaly_detector",
    "AnomalyDetector",
]

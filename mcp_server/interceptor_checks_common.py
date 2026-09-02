"""Shared helpers for interceptor safety checks."""

from __future__ import annotations

import uuid

SESSION_ID = uuid.uuid4().hex[:8]


def get_kill_switch():
    try:
        from core.agent_safety.kill_switch import get_kill_switch as factory
        return factory()
    except Exception:
        return None


def get_circuit_breaker():
    try:
        from core.agent_safety.circuit_breaker import get_circuit_breaker as factory
        return factory()
    except Exception:
        return None


def get_budget_tracker():
    try:
        from core.agent_safety.budget_tracker import get_budget_tracker as factory
        return factory(SESSION_ID)
    except Exception:
        return None


def get_safety_level(tool_name: str) -> int:
    try:
        from core.agent_safety.tool_classification import classify
        return classify(tool_name)
    except Exception:
        return 0

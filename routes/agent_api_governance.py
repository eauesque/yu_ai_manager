"""Agent governance route registration facade."""

from .agent_governance_approval import register_approval_routes
from .agent_governance_audit import register_audit_routes
from .agent_governance_scope import register_scope_routes


def register_routes(bp):
    register_approval_routes(bp)
    register_scope_routes(bp)
    register_audit_routes(bp)

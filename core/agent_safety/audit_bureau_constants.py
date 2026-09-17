"""Audit Bureau shared constants and helpers.

Shared between audit_bureau.py and audit_bureau_queries.py
to avoid circular imports.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Severity levels
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# Event types
EVENT_SECRET_WRITE = "secret_write"
EVENT_EXTERNAL_SEND = "external_send"
EVENT_ANOMALY = "anomaly"
EVENT_REPORT = "report"
EVENT_CB_TRIGGERED = "circuit_breaker_triggered"
EVENT_BUDGET_WARNING = "budget_warning"
EVENT_RULE_GAP = "rule_gap"

# Sensitive tool patterns (secret/credential operations)
SECRET_TOOL_PATTERNS = frozenset({
    "save_secret", "delete_secret", "set_secret",
    "api_key", "apikey", "credential",
    "ssh_key", "token_create", "token_delete",
})

# External send tool patterns
EXTERNAL_SEND_PATTERNS = frozenset({
    "share_to_", "bridge_generate", "webhook_",
    "bluesky_post", "sns_share", "export_",
})


def _get_db() -> sqlite3.Connection:
    """Get DB connection via ServiceRegistry."""
    from core.extensions_core.service_registry import ServiceRegistry
    get_db_fn = ServiceRegistry.get("db")
    if callable(get_db_fn):
        return get_db_fn()
    return get_db_fn


def _emit_sse(event_type: str, data: dict) -> None:
    """Emit SSE event via event_bus (best effort)."""
    try:
        from core.event_bus.event_types import emit_event
        emit_event(event_type, data)
    except Exception:
        logger.warning("audit event %s was not emitted", event_type, exc_info=True)


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()

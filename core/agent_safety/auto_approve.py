"""Auto-Approve rule management for Scope Fence (SQLite-backed).

Manages rules that allow automatic approval of specific tool calls, bypassing
the normal HITL (Human-in-the-Loop) gate for pre-approved patterns.

Rules are persisted to ``agent_auto_approve_rules`` (migration 85) so that a
rule added via the web API is visible **cross-process**: the MCP subprocess and
the Rust server read the same table. Single-writer(web) / multi-reader, no IPC.
This replaces the prior config.json-backed in-memory list, where runtime adds
never reached the MCP subprocess (which loaded rules only at startup).

``check_auto_approve`` is FAIL-SAFE: a storage error returns ``False`` (do NOT
auto-approve), so a DB failure cannot silently bypass the HITL gate.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from core.agent_safety.shared_state import _get_db

logger = logging.getLogger(__name__)


def _now() -> str:
    # Naive on purpose: this string is stored as `approved_at` in
    # `agent_auto_approve_rules`, which the Rust side reads too. An aware
    # `.isoformat()` appends the offset and changes the stored format.
    return datetime.datetime.now().isoformat()  # noqa: DTZ005


def _read_rules(db) -> list[dict[str, Any]]:
    """Return all rules in insertion order. Shape matches the legacy dict."""
    rows = db.execute(
        "SELECT tool, conditions_json, approved_at, approved_by "
        "FROM agent_auto_approve_rules ORDER BY id"
    ).fetchall()
    rules: list[dict[str, Any]] = []
    for row in rows:
        try:
            conditions = json.loads(row[1]) if row[1] else {}
        except (TypeError, ValueError):
            conditions = {}
        rules.append({
            "tool": row[0],
            "conditions": conditions,
            "approved_at": row[2],
            "approved_by": row[3],
        })
    return rules


def load_auto_approve_rules(config: dict) -> None:
    """One-time seed of agent_auto_approve_rules from config.json (when empty).

    Existing deployments keep their rules in config.json; on first load we copy
    them into the table, which then becomes the source of truth. Subsequent
    add/remove operate on the table only.
    """
    rules = config.get("agent_safety", {}).get("auto_approve_rules", [])
    if not rules:
        return
    try:
        db = _get_db()
        count = db.execute("SELECT COUNT(*) FROM agent_auto_approve_rules").fetchone()[0]
        if count:
            return  # already populated -> table is authoritative
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            db.execute(
                "INSERT INTO agent_auto_approve_rules "
                "(tool, conditions_json, approved_at, approved_by) VALUES (?, ?, ?, ?)",
                (
                    str(rule.get("tool", "")),
                    json.dumps(rule.get("conditions", {}) or {}),
                    str(rule.get("approved_at") or _now()),
                    str(rule.get("approved_by", "user")),
                ),
            )
        db.commit()
    except Exception as exc:
        logger.warning("auto-approve seed from config failed: %s", exc)


def check_auto_approve(tool_name: str, params: dict) -> bool:
    """Check if a tool call matches any Auto-Approve rule.

    Returns True to auto-approve. FAIL-SAFE: a storage read error returns False
    (do NOT auto-approve) so a DB failure cannot bypass the HITL gate.
    """
    try:
        db = _get_db()
        rules = _read_rules(db)
    except Exception as exc:
        logger.warning("check_auto_approve storage read failed: %s", exc)
        return False
    for rule in rules:
        if rule.get("tool") != tool_name:
            continue
        conditions = rule.get("conditions", {})
        if not conditions:
            # No conditions = always approve
            return True
        # Condition matching (simple key equality / prefix wildcard)
        match = True
        for key, pattern in conditions.items():
            param_val = str(params.get(key, ""))
            if isinstance(pattern, str) and pattern.endswith("*"):
                if not param_val.startswith(pattern[:-1]):
                    match = False
                    break
            elif str(pattern) != param_val:
                match = False
                break
        if match:
            return True
    return False


def add_auto_approve_rule(
    tool_name: str, conditions: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Add an Auto-Approve rule (returns the existing rule on duplicate)."""
    conditions = conditions or {}
    approved_at = _now()
    try:
        db = _get_db()
        for existing in _read_rules(db):
            if existing.get("tool") == tool_name and existing.get("conditions", {}) == conditions:
                return existing
        db.execute(
            "INSERT INTO agent_auto_approve_rules "
            "(tool, conditions_json, approved_at, approved_by) VALUES (?, ?, ?, ?)",
            (tool_name, json.dumps(conditions), approved_at, "user"),
        )
        db.commit()
    except Exception as exc:
        logger.warning("add_auto_approve_rule failed: %s", exc)
    return {
        "tool": tool_name,
        "conditions": conditions,
        "approved_at": approved_at,
        "approved_by": "user",
    }


def remove_auto_approve_rule(index: int) -> bool:
    """Remove an Auto-Approve rule by its position (index) in insertion order."""
    if index < 0:
        return False
    try:
        db = _get_db()
        row = db.execute(
            "SELECT id FROM agent_auto_approve_rules ORDER BY id LIMIT 1 OFFSET ?",
            (index,),
        ).fetchone()
        if row is None:
            return False
        db.execute("DELETE FROM agent_auto_approve_rules WHERE id = ?", (row[0],))
        db.commit()
        return True
    except Exception as exc:
        logger.warning("remove_auto_approve_rule failed: %s", exc)
        return False


def get_auto_approve_rules() -> list[dict[str, Any]]:
    """Return all Auto-Approve rules in insertion order."""
    try:
        db = _get_db()
        return _read_rules(db)
    except Exception as exc:
        logger.warning("get_auto_approve_rules read failed: %s", exc)
        return []

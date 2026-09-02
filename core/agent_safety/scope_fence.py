"""Scope Fence -- per-session operation scope restrictions (SQLite-backed).

Defines session scopes and denies tool calls matching denied patterns.
Presets: Read Only / Tagger / Organizer / Full Access

Scopes are persisted to ``agent_session_scopes`` (migration 84) so that a scope
set via the web API is enforced **cross-process**: the MCP subprocess and the
Rust server read the same table. Single-writer (web) / multi-reader, no
inter-process calls — COVENANT-compliant. This fixes the prior enforcement gap
where a scope set on the web process never reached the MCP subprocess's own
in-memory ScopeFence (which fell back to the default preset, fail-open).

Enforcement is FAIL-SAFE: if the scope store cannot be read, ``check()`` denies
(returns a reason) instead of allowing — a storage failure must not silently
remove the permission boundary (COVENANT Liber III.iv).

``denied_json`` stores the FULLY EXPANDED fnmatch deny patterns, so readers
(MCP, Rust) never interpret preset names — they read the expanded list directly.

This module re-exports auto-approve functions from auto_approve.py
to maintain backward compatibility.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

# Re-export auto-approve functions for backward compatibility
from core.agent_safety.auto_approve import (  # noqa: F401
    add_auto_approve_rule,
    check_auto_approve,
    get_auto_approve_rules,
    load_auto_approve_rules,
    remove_auto_approve_rule,
)
from core.agent_safety.shared_state import _get_db

logger = logging.getLogger(__name__)

# Scope preset definitions
PRESETS: dict[str, dict[str, Any]] = {
    "read_only": {
        "label": "Read Only",
        "description": "閲覧・分析のみ。書き込み操作は全て拒否",
        "denied": [
            "set_*", "add_*", "create_*", "update_*", "delete_*",
            "remove_*", "rate_*", "trigger_*", "scan_*",
            "archive_*", "install_*", "uninstall_*",
            "toggle_*", "switch_*", "share_*", "restore_*",
            "import_*", "reprocess_*", "compute_*",
            "wd_tagger_tag*", "wd_tagger_batch", "wd_tagger_delete*",
            "analyze_*", "semantic_index_start", "semantic_index_stop",
            "generate_*", "batch_download_*",
            "agent_kill", "agent_resume",
            "agent_budget_reset", "agent_circuit_breaker_reset",
        ],
    },
    "tagger": {
        "label": "Tagger",
        "description": "タグ付け・アノテーション作業。削除操作は拒否",
        "denied": [
            "delete_*", "remove_scan_root",
            "archive_cleanup_execute",
            "install_*", "uninstall_*",
            "toggle_extension", "set_extension_config",
            "share_*", "restore_*",
            "add_scan_root", "toggle_scan_root",
            "create_backup",
            "agent_kill", "agent_resume",
        ],
    },
    "organizer": {
        "label": "Organizer",
        "description": "整理作業。レーティング・タグ・コレクション操作可。削除は拒否",
        "denied": [
            "delete_*", "archive_cleanup_execute",
            "install_*", "uninstall_*",
            "toggle_extension",
            "share_*", "restore_*",
            "add_scan_root", "remove_scan_root", "toggle_scan_root",
            "create_backup",
            "agent_kill", "agent_resume",
        ],
    },
    "full_access": {
        "label": "Full Access",
        "description": "全権限。破壊的操作は HITL Gate による承認が引き続き有効",
        "denied": [],
    },
}


@dataclass
class SessionScope:
    """Session scope definition (kept for backward-compat imports).

    Storage is now SQLite (agent_session_scopes); this dataclass is no longer the
    source of truth but remains for callers that import it.
    """

    session_id: str
    preset: str = "organizer"
    name: str = ""
    denied: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None  # None = no expiration


def _expand_denied(preset: str, custom: list[str] | None) -> list[str]:
    """Build the effective deny list: preset patterns plus custom patterns."""
    effective = list(PRESETS[preset]["denied"])
    if custom:
        for pattern in custom:
            if pattern not in effective:
                effective.append(pattern)
    return effective


class ScopeFence:
    """Per-session scope management, persisted to agent_session_scopes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._default_preset = "organizer"

    def configure(self, config: dict) -> None:
        """Load settings from config.json."""
        safety_cfg = config.get("agent_safety", {})
        self._default_preset = safety_cfg.get("default_scope_preset", "organizer")
        if self._default_preset not in PRESETS:
            self._default_preset = "organizer"

    def set_scope(
        self,
        session_id: str,
        preset: str = "",
        denied: list[str] | None = None,
        name: str = "",
        duration_hours: float | None = None,
    ) -> dict[str, Any]:
        """Set (UPSERT) a session scope. Stores the fully expanded deny list."""
        if not preset:
            preset = self._default_preset
        if preset not in PRESETS:
            preset = self._default_preset

        effective_denied = _expand_denied(preset, denied)
        now = datetime.now(UTC)
        created_at = now.isoformat()
        expires_at: str | None = None
        if duration_hours and duration_hours > 0:
            expires_at = (now + timedelta(hours=float(duration_hours))).isoformat()
        scope_name = name or PRESETS[preset]["label"]

        try:
            db = _get_db()
            db.execute(
                """INSERT INTO agent_session_scopes
                   (session_id, preset, name, denied_json, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     preset       = excluded.preset,
                     name         = excluded.name,
                     denied_json  = excluded.denied_json,
                     created_at   = excluded.created_at,
                     expires_at   = excluded.expires_at""",
                (
                    session_id, preset, scope_name,
                    json.dumps(effective_denied), created_at, expires_at,
                ),
            )
            db.commit()
        except Exception as exc:
            logger.warning("set_scope persist failed for %s: %s", session_id, exc)

        logger.info(
            "Scope set: session=%s, preset=%s, denied=%d patterns",
            session_id, preset, len(effective_denied),
        )
        return {
            "session_id": session_id,
            "preset": preset,
            "name": scope_name,
            "denied": effective_denied,
            "created_at": created_at,
            "expires_at": expires_at,
        }

    def check(self, session_id: str, tool_name: str) -> str | None:
        """Check whether a tool call is within session scope.

        Returns None when allowed, or a denial-reason string. FAIL-SAFE: a
        storage read error denies (returns a reason) rather than allowing.
        """
        try:
            db = _get_db()
            row = db.execute(
                "SELECT preset, name, denied_json, expires_at "
                "FROM agent_session_scopes WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        except Exception as exc:
            # Storage failure must NOT remove the permission boundary.
            logger.warning("scope check storage read failed for %s: %s", session_id, exc)
            return (
                "Scope check unavailable due to a storage error. "
                "Denying the operation by default (fail-safe)."
            )

        if row is None:
            # No scope set for this session -> apply the default preset's deny list.
            preset = self._default_preset
            name = PRESETS.get(preset, {}).get("label", preset)
            denied = list(PRESETS.get(preset, {}).get("denied", []))
            expires_at = None
        else:
            preset, name, denied_json, expires_at = row[0], row[1], row[2], row[3]
            try:
                denied = json.loads(denied_json) if denied_json else []
            except (TypeError, ValueError):
                denied = []

        if expires_at:
            try:
                if datetime.now(UTC) > datetime.fromisoformat(expires_at):
                    return (
                        f"Session scope expired. "
                        f"Preset '{preset}' has expired. "
                        f"Please reconnect to set a new scope."
                    )
            except ValueError:
                pass

        for pattern in denied:
            if fnmatch.fnmatch(tool_name, pattern):
                return (
                    f"Operation denied by scope fence. "
                    f"Tool '{tool_name}' is blocked by scope '{name}' "
                    f"(preset: {preset}). "
                    f"Matching deny pattern: '{pattern}'"
                )

        return None

    def get_scope(self, session_id: str) -> dict[str, Any] | None:
        """Get session scope info, or None when not set."""
        try:
            db = _get_db()
            row = db.execute(
                "SELECT session_id, preset, name, denied_json, created_at, expires_at "
                "FROM agent_session_scopes WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        except Exception as exc:
            logger.warning("get_scope read failed for %s: %s", session_id, exc)
            return None
        if row is None:
            return None
        try:
            denied = json.loads(row[3]) if row[3] else []
        except (TypeError, ValueError):
            denied = []
        expires_at = row[5]
        expired = False
        if expires_at:
            try:
                expired = datetime.now(UTC) > datetime.fromisoformat(expires_at)
            except ValueError:
                expired = False
        return {
            "session_id": row[0],
            "preset": row[1],
            "name": row[2],
            "denied_count": len(denied),
            "denied_patterns": denied,
            "created_at": row[4],
            "expires_at": expires_at,
            "expired": expired,
        }

    def remove_scope(self, session_id: str) -> bool:
        """Remove a session scope. Returns True when a row was deleted."""
        try:
            db = _get_db()
            cursor = db.execute(
                "DELETE FROM agent_session_scopes WHERE session_id = ?",
                (session_id,),
            )
            db.commit()
            return cursor.rowcount > 0
        except Exception as exc:
            logger.warning("remove_scope failed for %s: %s", session_id, exc)
            return False

    def status(self) -> dict[str, Any]:
        """Return status of all scopes."""
        sessions: dict[str, Any] = {}
        try:
            db = _get_db()
            rows = db.execute(
                "SELECT session_id, preset, name, denied_json "
                "FROM agent_session_scopes ORDER BY session_id"
            ).fetchall()
            for row in rows:
                try:
                    denied = json.loads(row[3]) if row[3] else []
                except (TypeError, ValueError):
                    denied = []
                sessions[row[0]] = {
                    "preset": row[1],
                    "name": row[2],
                    "denied_count": len(denied),
                }
        except Exception as exc:
            logger.warning("scope status read failed: %s", exc)

        return {
            "default_preset": self._default_preset,
            "active_sessions": len(sessions),
            "sessions": sessions,
            "available_presets": {
                k: {"label": v["label"], "description": v["description"]}
                for k, v in PRESETS.items()
            },
        }


# Singleton
_fence: ScopeFence | None = None
_fence_lock = threading.Lock()


def get_scope_fence() -> ScopeFence:
    """Get the ScopeFence singleton."""
    global _fence
    if _fence is None:
        with _fence_lock:
            if _fence is None:
                fence = ScopeFence()
                try:
                    from core.configuration import get_config_value
                    cfg = {"agent_safety": get_config_value("agent_safety", {})}
                    fence.configure(cfg)
                    load_auto_approve_rules(cfg)
                except Exception:
                    # Both the fence limits AND the auto-approve rules come from
                    # here; defaults are the permissive end of both.
                    logger.warning("scope fence fell back to defaults", exc_info=True)
                _fence = fence
    return _fence

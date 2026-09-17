"""Agent Budget Tracker -- manages per-session resource consumption limits.

Automatically classifies tools by category (read/write/destructive) from tool name,
and consumes budget. Warning at 80%, denial at 100%.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Category classification by tool name prefix.
#
# These are deliberate, hand-picked decisions and they WIN over the token rules
# below wherever they are stricter (install_/restore_/share_to_ are treated as
# destructive on purpose, and wd_tagger_batch as a write although neither reads
# as one word-wise). Classification only ever moves up, never down.
_DESTRUCTIVE_PREFIXES = (
    "delete_", "remove_", "archive_cleanup_execute",
    "uninstall_", "restore_", "share_to_", "install_",
)
_WRITE_PREFIXES = (
    "set_", "add_", "create_", "update_", "rate_",
    "trigger_", "scan_", "wd_tagger_tag", "wd_tagger_batch",
    "analyze_", "compute_", "semantic_index_start",
    "import_", "reprocess_", "switch_", "toggle_",
)
_READ_PREFIXES = (
    "get_", "list_", "search_", "find_", "debug_",
)

# Token-level classification.
#
# The prefix table above only matches the START of a name, so a tool called
# wd_tagger_delete_tags, clear_tag_dictionary or agent_kill fell through to
# "read": not charged against the write/destructive budget, and reported as a
# read by anomaly_detector's `classify_tool(...) != "read"`. Measuring the
# shipped table against all 633 registered tools found 173 such names, 41 of
# them state-destroying. See scripts/internal/audit_tool_classification.py.
_READ_VERBS = frozenset({
    "get", "list", "search", "find", "show", "read", "check", "debug",
    "validate", "sample", "view", "fetch", "describe", "count", "preview",
})
_READ_NOUNS = frozenset({
    "status", "info", "stats", "list", "count", "history", "detail", "details",
    "models", "options", "config", "settings", "queue", "alerts", "log", "logs",
    "report", "entries", "state", "types", "profiles", "roots", "result",
    "results", "servers", "engines", "samplers", "schedulers", "loras",
    "embeddings", "nodes", "encoders", "dtypes", "controlnets", "undoable",
    "level", "params", "prompts", "tags", "xmp", "backups", "conversations",
    "connection", "decisions", "summary", "full", "untagged", "duplicates",
})
_DESTRUCTIVE_WORDS = frozenset({
    "delete", "remove", "uninstall", "restore", "purge", "wipe", "reset",
    "cancel", "kill", "revoke", "clear", "prune", "drop", "stop",
})
_WRITE_WORDS = frozenset({
    "set", "add", "create", "update", "save", "write", "rename", "reorder",
    "rate", "trigger", "scan", "import", "export", "migrate", "start",
    "toggle", "switch", "enable", "disable", "install", "register", "post",
    "share", "upload", "download", "generate", "tag", "retag", "apply",
    "acknowledge", "respond", "resume", "lock", "unlock", "logout", "login",
    "reprocess", "reindex", "backfill", "compute", "rebuild", "undo",
    "convert", "verify", "train", "run", "execute", "send", "push",
    "pull", "sync", "refresh", "analyze", "transcribe", "detect", "extract",
    "rasterize", "open", "test", "dismiss", "triage",
})

_RANK = {"read": 0, "write": 1, "destructive": 2}

# Preset definitions
PRESETS: dict[str, dict[str, int]] = {
    "conservative": {"total_actions": 200, "write_actions": 20, "destructive_actions": 3},
    "standard": {"total_actions": 500, "write_actions": 100, "destructive_actions": 10},
    "power_user": {"total_actions": 2000, "write_actions": 500, "destructive_actions": 50},
    "unlimited": {"total_actions": 999999, "write_actions": 999999, "destructive_actions": 999999},
}


@dataclass
class _BudgetCounters:
    """Consumption counters."""

    total: int = 0
    write: int = 0
    destructive: int = 0


class BudgetTracker:
    """Per-session budget management."""

    def __init__(self, session_id: str) -> None:
        self._lock = threading.Lock()
        self.session_id = session_id
        self._limits = dict(PRESETS["standard"])
        self._counters = _BudgetCounters()
        self._warned_80: dict[str, bool] = {}  # Per-category 80% warning sent flag

    def configure(self, config: dict[str, Any]) -> None:
        """Load settings from agent_safety.budget in config.json."""
        with self._lock:
            budget_cfg = config.get("agent_safety", {}).get("budget", {})
            preset_name = budget_cfg.get("preset", "standard")
            if preset_name in PRESETS:
                self._limits = dict(PRESETS[preset_name])
            else:
                self._limits = dict(PRESETS["standard"])
            # Custom overrides
            for key in ("total_actions", "write_actions", "destructive_actions"):
                if key in budget_cfg and isinstance(budget_cfg[key], int):
                    self._limits[key] = budget_cfg[key]

    def check(self, tool_name: str) -> str | None:
        """Check budget. Returns error message when exhausted."""
        category = classify_tool(tool_name)

        with self._lock:
            # Total actions check
            if self._counters.total >= self._limits["total_actions"]:
                return (
                    f"Budget exhausted: total actions "
                    f"({self._counters.total}/{self._limits['total_actions']})"
                )
            # Write actions check
            if category in ("write", "destructive"):  # noqa: SIM102
                if self._counters.write >= self._limits["write_actions"]:
                    return (
                        f"Budget exhausted: write actions "
                        f"({self._counters.write}/{self._limits['write_actions']})"
                    )
            # Destructive actions check
            if category == "destructive":  # noqa: SIM102
                if self._counters.destructive >= self._limits["destructive_actions"]:
                    return (
                        f"Budget exhausted: destructive actions "
                        f"({self._counters.destructive}/{self._limits['destructive_actions']})"
                    )

        return None

    def consume(self, tool_name: str) -> None:
        """Consume budget. Sends warning event at 80% threshold."""
        category = classify_tool(tool_name)

        with self._lock:
            self._counters.total += 1
            if category in ("write", "destructive"):
                self._counters.write += 1
            if category == "destructive":
                self._counters.destructive += 1

            # 80% warning check
            self._check_warning("total", self._counters.total, self._limits["total_actions"])
            if category in ("write", "destructive"):
                self._check_warning("write", self._counters.write, self._limits["write_actions"])
            if category == "destructive":
                self._check_warning(
                    "destructive",
                    self._counters.destructive,
                    self._limits["destructive_actions"],
                )

            # 100% reached notification
            if self._counters.total >= self._limits["total_actions"]:
                self._emit("agent.budget_exhausted", {
                    "category": "total",
                    "used": self._counters.total,
                    "limit": self._limits["total_actions"],
                })
            elif category in ("write", "destructive") and \
                    self._counters.write >= self._limits["write_actions"]:
                self._emit("agent.budget_exhausted", {
                    "category": "write",
                    "used": self._counters.write,
                    "limit": self._limits["write_actions"],
                })
            elif category == "destructive" and \
                    self._counters.destructive >= self._limits["destructive_actions"]:
                self._emit("agent.budget_exhausted", {
                    "category": "destructive",
                    "used": self._counters.destructive,
                    "limit": self._limits["destructive_actions"],
                })

            # Persist usage to SQLite so the other process can observe it.
            _total = self._counters.total
            _write = self._counters.write
            _destr = self._counters.destructive

        try:
            from core.agent_safety.shared_state import write_budget_usage
            write_budget_usage(self.session_id, _total, _write, _destr)
        except Exception:
            # Not persisted means the next process enforces a stale, lower total.
            logger.warning("budget usage was not persisted", exc_info=True)

    def _check_warning(self, category: str, used: int, limit: int) -> None:
        """Send warning at 80% (once only). Assumes _lock is held."""
        if limit <= 0:
            return
        if category in self._warned_80:
            return
        if used >= int(limit * 0.8):
            self._warned_80[category] = True
            self._emit("agent.budget_warning", {
                "category": category,
                "used": used,
                "limit": limit,
                "percent": round(used / limit * 100),
            })

    def reset(self) -> None:
        """Reset the budget counters."""
        with self._lock:
            self._counters = _BudgetCounters()
            self._warned_80.clear()
        logger.info("Budget tracker reset for session %s", self.session_id)

    def status(self) -> dict[str, Any]:
        """Return the current budget status as a dict."""
        with self._lock:
            limits = dict(self._limits)
            return {
                "session_id": self.session_id,
                "limits": limits,
                "used": {
                    "total": self._counters.total,
                    "write": self._counters.write,
                    "destructive": self._counters.destructive,
                },
                "remaining": {
                    "total": max(0, limits["total_actions"] - self._counters.total),
                    "write": max(0, limits["write_actions"] - self._counters.write),
                    "destructive": max(0, limits["destructive_actions"] - self._counters.destructive),
                },
            }

    def _emit(self, event_type: str, data: dict) -> None:
        """Emit an event via event_bus."""
        try:
            from core.event_bus import emit
            emit(event_type, {**data, "session_id": self.session_id})
        except Exception:
            logger.warning("budget event %s was not emitted", event_type, exc_info=True)


def _classify_by_prefix(tool_name: str) -> str:
    if tool_name.startswith(_DESTRUCTIVE_PREFIXES):
        return "destructive"
    if tool_name.startswith(_WRITE_PREFIXES):
        return "write"
    return "read"


def _classify_by_tokens(tool_name: str) -> str:
    """Classify from the words in the name rather than its first few characters.

    Rule order matters; each rule is here because of a name it otherwise got
    wrong:
      1. ``check_for_update`` is a read — a read verb in front settles it.
      2. ``wd_tagger_delete_tags`` is destructive, and its last word (``tags``)
         is a read noun. Destructive evidence must therefore be weighed BEFORE
         the trailing-noun rule, or the noun hides the verb. Both this function
         and the audit script got this wrong in the same way at first, and
         agreed on the wrong answer; the fixtures in
         tests/mcp/test_tool_classification.py are what caught it.
      3. ``auto_scan_info`` is a read but ``save_analysis_config`` is a write,
         so a trailing read noun only wins when nothing writes in front.
      4. ``wd_tagger_delete_tags`` is destructive even though ``delete`` is not
         a prefix. This is the case the prefix table cannot see.
    """
    tokens = re.split(r"[_\-]+", tool_name.lower())
    if not tokens:
        return "read"
    head, tail = tokens[0], tokens[-1]
    token_set = set(tokens)

    if head in _READ_VERBS:
        return "read"
    if token_set & _DESTRUCTIVE_WORDS:
        return "destructive"
    if tail in _READ_NOUNS and head not in _WRITE_WORDS:
        return "read"
    if token_set & _WRITE_WORDS:
        return "write"
    return "read"


def classify_tool(tool_name: str) -> str:
    """Classify tool category from tool name.

    Takes the STRICTER of the hand-picked prefix table and the token rules, so
    adding the token rules can only ever move a tool up the scale. A tool that
    the prefix table already calls destructive stays destructive even if its
    words read as a plain write.
    """
    by_prefix = _classify_by_prefix(tool_name)
    by_tokens = _classify_by_tokens(tool_name)
    return by_prefix if _RANK[by_prefix] >= _RANK[by_tokens] else by_tokens


# Manage per-session BudgetTracker instances
_trackers: dict[str, BudgetTracker] = {}
_trackers_lock = threading.Lock()


def get_budget_tracker(session_id: str) -> BudgetTracker:
    """Get the BudgetTracker for a session ID (creates one if absent)."""
    if session_id not in _trackers:
        with _trackers_lock:
            if session_id not in _trackers:
                tracker = BudgetTracker(session_id)
                try:
                    from core.configuration import get_config_value
                    cfg = {"agent_safety": get_config_value("agent_safety", {})}
                    tracker.configure(cfg)
                except Exception:
                    # Falling back to defaults silently drops an operator's
                    # deliberately tighter budget.
                    logger.warning(
                        "budget limits fell back to defaults for %s", session_id, exc_info=True
                    )
                _trackers[session_id] = tracker
    return _trackers[session_id]

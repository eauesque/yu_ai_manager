"""Agent Circuit Breaker -- automatically detects and stops runaway agents.

3-state transition: closed (normal) -> open (blocked) -> half_open (trial recovery) -> closed
Manages action history in an in-memory ring buffer.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default thresholds
_DEFAULT_THRESHOLDS = {
    "max_actions_per_minute": 60,
    "max_identical_consecutive": 3,
    "max_same_tool_per_minute": 15,
    "max_consecutive_errors": 10,
    "error_rate_threshold": 0.5,
    "cooldown_seconds": 60,
}

# Error message substrings that indicate infrastructure failures rather than
# agent runaway behaviour.  These are excluded from identical-consecutive counting
# because a retry on a genuinely down server is not a "runaway loop".
_INFRA_ERROR_SIGNATURES: tuple[str, ...] = (
    "Connection refused",
    "ConnectionRefusedError",
    "ConnectError",
    "WinError 10061",  # Windows: target machine actively refused connection
    "Connection reset",
    "BrokenPipeError",
)

# Read-only prefixes allowed in half_open state (bare verbs, e.g. get_files)
_READ_PREFIXES = ("get_", "list_", "search_", "find_")
# Read-only suffixes allowed in half_open state (e.g. agent_status)
_READ_SUFFIXES = ("_status", "_info", "_list", "_stats")
# Explicit read-only tools that don't fit the prefix/suffix patterns above
_READ_EXPLICIT: frozenset[str] = frozenset({
    "agent_journal",
    "agent_journal_stats",
    "debug_info",
    "semantic_backend_info",
    "wd_tagger_vlm_models",
    "wd_tagger_untagged",
})


def _is_infra_error(error_str: str) -> bool:
    """Return True when the error string looks like an infrastructure failure.

    Infrastructure errors (connection refused, reset, etc.) should NOT trigger
    the identical-consecutive-call check because retrying a tool while the
    server is restarting is expected behaviour, not an agent runaway loop.
    """
    return any(sig in error_str for sig in _INFRA_ERROR_SIGNATURES)


def _is_read_op(tool_name: str) -> bool:
    """Return True if *tool_name* is a safe read-only probe for HALF_OPEN state.

    Handles four patterns:
    1. Bare read verb: ``get_*``, ``list_*``, ``search_*``, ``find_*``
    2. Read-like suffix: ``*_status``, ``*_info``, ``*_list``, ``*_stats``
    3. Extension-namespaced read ops — any token ``_<verb>_`` in the name:
       ``comfyui_list_model_registry``, ``sd_get_config``, ``wd_tagger_get_*``
    4. Explicit whitelist for tools that match none of the above patterns
       (e.g. ``agent_journal`` which has no read prefix/suffix).
    """
    if tool_name.startswith(_READ_PREFIXES):
        return True
    if tool_name.endswith(_READ_SUFFIXES):
        return True
    # Extension-namespaced: comfyui_list_*, sd_get_*, wd_tagger_get_*, etc.
    for verb in _READ_PREFIXES:
        if f"_{verb}" in tool_name:
            return True
    return tool_name in _READ_EXPLICIT


@dataclass
class _ActionRecord:
    """Action record kept in the ring buffer."""

    tool_name: str
    params_hash: str  # Simple hash of tool_name + params
    timestamp: float
    is_error: bool


class AgentCircuitBreaker:
    """Singleton, thread-safe Circuit Breaker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: str = "closed"  # closed / open / half_open
        self._opened_at: float = 0.0
        self._open_reason: str = ""
        self._history: deque[_ActionRecord] = deque(maxlen=100)
        self._consecutive_errors: int = 0
        self._thresholds: dict[str, Any] = dict(_DEFAULT_THRESHOLDS)
        self._enabled: bool = True
        self._half_open_trials: int = 0

    def configure(self, config: dict[str, Any]) -> None:
        """Configure thresholds from agent_safety.circuit_breaker in config.json."""
        with self._lock:
            cb_cfg = config.get("agent_safety", {}).get("circuit_breaker", {})
            self._enabled = cb_cfg.get("enabled", True)
            for key, default in _DEFAULT_THRESHOLDS.items():
                self._thresholds[key] = cb_cfg.get(key, default)

    def check(self, tool_name: str) -> str | None:
        """Pre-call check. Returns error message when blocked."""
        if not self._enabled:
            return None

        _cb_write: tuple | None = None  # (state, reason, errors) — written after lock release
        _retval: str | None = None      # single exit point so _cb_write is always processed
        with self._lock:
            if self._state == "open":
                # Cooldown elapsed -> transition to half_open
                elapsed = time.time() - self._opened_at
                if elapsed >= self._thresholds["cooldown_seconds"]:
                    self._state = "half_open"
                    self._half_open_trials = 0
                    logger.info("Circuit breaker: open -> half_open")
                    self._emit_event("agent.circuit_half_open", {})
                    # Snapshot inside lock; write after lock released to avoid I/O under lock.
                    _cb_write = ("HALF_OPEN", self._open_reason, self._consecutive_errors)
                    # Fall through: check half_open gate below for this very call.
                else:
                    remaining = int(self._thresholds["cooldown_seconds"] - elapsed)
                    _retval = (
                        f"Circuit breaker is OPEN ({self._open_reason}). "
                        f"Cooldown: {remaining}s remaining."
                    )

            if _retval is None and self._state == "half_open":
                # Only allow read operations
                if not _is_read_op(tool_name):
                    _retval = (
                        "Circuit breaker is in HALF_OPEN state. "
                        "Only read operations are allowed "
                        "(get_*, list_*, comfyui_list_*, sd_get_*, *_status, etc.)."
                    )
                else:
                    self._half_open_trials += 1
                    # Return to closed after 5 successes (checked in record)

        # Write shared state AFTER lock released — ensures HALF_OPEN is persisted even
        # when the immediately following gate check blocks the tool (write-op rejection).
        if _cb_write:
            try:
                from core.agent_safety.shared_state import write_cb_state
                write_cb_state(*_cb_write)
            except Exception:
                # Not persisted means the next process reads CLOSED.
                logger.warning("circuit breaker state was not persisted", exc_info=True)
        return _retval

    def record(self, tool_name: str, params: dict, is_error: bool, error_str: str = "") -> None:
        """Record action result and detect anomaly patterns.

        Args:
            error_str: Optional error message string.  When the error looks like
                an infrastructure failure (Connection refused, etc.) the record
                is excluded entirely from history and anomaly detection so that
                expected retries during a server restart never trip the breaker.
        """
        if not self._enabled:
            return

        # Infrastructure errors are environment failures, NOT agent runaway behaviour.
        # Exclude them from history and all anomaly checks (consecutive errors,
        # error rate, actions/min, identical calls, same-tool/min) so that retrying
        # a tool against a temporarily-down server does not falsely trip the breaker.
        if is_error and _is_infra_error(error_str):
            return

        params_hash = f"{tool_name}:{_stable_hash(params)}"
        now = time.time()
        record = _ActionRecord(
            tool_name=tool_name,
            params_hash=params_hash,
            timestamp=now,
            is_error=is_error,
        )

        _cb_write: tuple | None = None  # (state, reason, errors) — written after lock release
        with self._lock:
            self._history.append(record)

            if is_error:
                self._consecutive_errors += 1
            else:
                self._consecutive_errors = 0

            # Success in half_open state -> return to closed
            if self._state == "half_open" and not is_error:
                if self._half_open_trials >= 5:
                    self._state = "closed"
                    self._open_reason = ""
                    logger.info("Circuit breaker: half_open -> closed")
                    self._emit_event("agent.circuit_closed", {})
                    # Snapshot inside lock; write after lock released to avoid I/O under lock.
                    _cb_write = ("CLOSED", "", 0)
                # (early return — _cb_write written below after lock is released)

            # Error in half_open -> revert to open
            elif self._state == "half_open" and is_error:
                _cb_write = self._trip("Error during half_open trial")

            # Closed state: detect anomaly patterns
            elif self._state == "closed":
                reason = self._detect_anomaly(now)
                if reason:
                    _cb_write = self._trip(reason)

        # Write shared state AFTER lock is released to avoid SQLite I/O under lock.
        if _cb_write:
            try:
                from core.agent_safety.shared_state import write_cb_state
                write_cb_state(*_cb_write)
            except Exception:
                logger.warning("circuit breaker state was not persisted", exc_info=True)

    def _detect_anomaly(self, now: float) -> str | None:
        """Detect anomaly patterns. Called with _lock held.

        Infrastructure errors are excluded upstream (in ``record()``) before
        reaching this method, so all history entries here reflect genuine agent
        behaviour and are checked unconditionally.
        """
        thresholds = self._thresholds
        one_min_ago = now - 60.0

        # 1. Consecutive errors
        if self._consecutive_errors >= thresholds["max_consecutive_errors"]:
            return f"Consecutive errors: {self._consecutive_errors}"

        # 2. Error rate (last 20 actions)
        recent = list(self._history)[-20:]
        if len(recent) >= 20:
            error_count = sum(1 for r in recent if r.is_error)
            rate = error_count / len(recent)
            if rate >= thresholds["error_rate_threshold"]:
                return f"Error rate: {rate:.0%} in last 20 actions"

        # 3. Actions per minute
        actions_in_min = sum(1 for r in self._history if r.timestamp > one_min_ago)
        if actions_in_min >= thresholds["max_actions_per_minute"]:
            return f"Actions per minute: {actions_in_min}"

        # 4. Identical tool+params consecutive calls
        max_identical = thresholds["max_identical_consecutive"]
        if len(self._history) >= max_identical:
            recent_n = list(self._history)[-max_identical:]
            if all(r.params_hash == recent_n[0].params_hash for r in recent_n):
                return f"Identical consecutive calls: {max_identical}x {recent_n[0].tool_name}"

        # 5. Same tool calls per minute
        tool_counts: dict[str, int] = {}
        for r in self._history:
            if r.timestamp > one_min_ago:
                tool_counts[r.tool_name] = tool_counts.get(r.tool_name, 0) + 1
        max_same = thresholds["max_same_tool_per_minute"]
        for tool, count in tool_counts.items():
            if count >= max_same:
                return f"Same tool per minute: {tool} x{count}"

        return None

    def _trip(self, reason: str) -> tuple:
        """Trip the Circuit Breaker to open state. Called with _lock held.

        Returns a (state, reason, errors) snapshot tuple that the caller must
        pass to write_cb_state() AFTER releasing _lock to avoid holding the
        lock across SQLite I/O.
        """
        self._state = "open"
        self._opened_at = time.time()
        self._open_reason = reason
        logger.warning("Circuit breaker tripped: %s", reason)
        self._emit_event("agent.circuit_open", {"reason": reason})
        # Notify Audit Bureau (independent, one-way)
        try:
            from core.agent_safety.audit_bureau import get_audit_bureau
            get_audit_bureau().on_circuit_breaker_triggered("circuit_breaker", reason)
        except Exception:
            # A trip nobody recorded leaves no trace of why the breaker opened.
            logger.warning("audit bureau was not notified of the trip", exc_info=True)
        # Return snapshot — caller writes after releasing lock.
        return ("OPEN", reason, self._consecutive_errors)

    def trip(self, reason: str) -> None:
        """Public method to trip the Circuit Breaker to open state from outside."""
        with self._lock:
            _cb_write = self._trip(reason)
        try:
            from core.agent_safety.shared_state import write_cb_state
            write_cb_state(*_cb_write)
        except Exception:
            logger.warning("circuit breaker state was not persisted", exc_info=True)

    def reset(self) -> None:
        """Manually reset to closed state."""
        with self._lock:
            prev = self._state
            self._state = "closed"
            self._opened_at = 0.0
            self._open_reason = ""
            self._consecutive_errors = 0
            self._half_open_trials = 0
        if prev != "closed":
            logger.info("Circuit breaker manually reset: %s -> closed", prev)
            self._emit_event("agent.circuit_closed", {"manual": True})
            try:
                from core.agent_safety.shared_state import write_cb_state
                write_cb_state("CLOSED", "", 0)
            except Exception:
                # A reset nobody persisted leaves the next process reading OPEN.
                logger.warning("circuit breaker reset was not persisted", exc_info=True)

    def status(self) -> dict[str, Any]:
        """Return the current state as a dict."""
        with self._lock:
            now = time.time()
            one_min_ago = now - 60.0
            actions_in_min = sum(1 for r in self._history if r.timestamp > one_min_ago)
            errors_in_min = sum(
                1 for r in self._history if r.timestamp > one_min_ago and r.is_error
            )
            return {
                "enabled": self._enabled,
                "state": self._state,
                "reason": self._open_reason,
                "actions_per_minute": actions_in_min,
                "errors_per_minute": errors_in_min,
                "consecutive_errors": self._consecutive_errors,
                "total_recorded": len(self._history),
                "thresholds": dict(self._thresholds),
            }

    def _emit_event(self, event_type: str, data: dict) -> None:
        """Emit an event via event_bus."""
        try:
            from core.event_bus import emit
            emit(event_type, data)
        except Exception:
            # Every open/close notification rides this path.
            logger.warning("circuit breaker event %s was not emitted", event_type, exc_info=True)


def _stable_hash(params: dict) -> str:
    """Generate a stable hash string for parameters."""
    import hashlib
    import json

    try:
        s = json.dumps(params, sort_keys=True, default=str)
    except (TypeError, ValueError):
        s = str(params)
    # Dedup key for parameter comparison, not a security primitive.
    return hashlib.md5(s.encode(), usedforsecurity=False).hexdigest()[:8]


# Singleton
_instance: AgentCircuitBreaker | None = None
_lock = threading.Lock()


def get_circuit_breaker() -> AgentCircuitBreaker:
    """Get the Circuit Breaker singleton instance."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AgentCircuitBreaker()
                # Load thresholds from config
                try:
                    from core.configuration import get_config_value
                    cfg = {"agent_safety": get_config_value("agent_safety", {})}
                    _instance.configure(cfg)
                except Exception:
                    # Silently falling back to defaults hides an operator's
                    # deliberately stricter thresholds.
                    logger.warning(
                        "circuit breaker thresholds fell back to defaults", exc_info=True
                    )
    return _instance

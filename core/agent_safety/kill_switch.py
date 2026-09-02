"""Agent Kill Switch -- emergency mechanism to immediately stop all agent operations.

Dual-check via file flag (data/agent_kill.flag) + threading.Event
to support stops from other processes.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _kill_flag_path() -> Path:
    """Resolve the kill flag file path lazily via core.paths."""
    from core.paths import data_path
    return data_path("agent_kill.flag")


class AgentKillSwitch:
    """Independent stop mechanism that operates outside the agent."""

    def __init__(self) -> None:
        self._killed = threading.Event()
        self._reason: str = ""
        self._killed_at: str = ""
        # Sync with file flag on startup
        flag_path = _kill_flag_path()
        if flag_path.exists():
            self._killed.set()
            try:
                self._reason = flag_path.read_text().strip() or "file flag"
            except OSError:
                self._reason = "file flag"
            logger.warning("Agent kill switch is active (file flag found)")

    def kill(self, reason: str = "") -> None:
        """Immediate stop. Triggered via UI button / API / file flag."""
        self._killed.set()
        self._reason = reason
        self._killed_at = datetime.now(UTC).isoformat()
        flag_path = _kill_flag_path()
        try:
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.write_text(reason)
        except OSError as exc:
            logger.warning("Failed to write kill flag file: %s", exc)
        # Notify via event_bus
        try:
            from core.event_bus import emit
            emit("agent.killed", {"reason": reason, "at": self._killed_at})
        except Exception:
            # The kill itself stands; only the notification was lost.
            logger.warning("kill-switch activation was not broadcast", exc_info=True)
        logger.warning("Agent kill switch activated: %s", reason)

    def is_killed(self) -> bool:
        """Check if stopped. Also checks file flag (supports kill from another process)."""
        if self._killed.is_set():
            return True
        # Check file flag (detect kill from another process)
        flag_path = _kill_flag_path()
        if flag_path.exists():
            self._killed.set()
            try:
                self._reason = flag_path.read_text().strip() or "file flag"
            except OSError:
                self._reason = "file flag"
            return True
        return False

    def resume(self) -> None:
        """Reset by explicit user action."""
        self._killed.clear()
        self._reason = ""
        self._killed_at = ""
        try:
            _kill_flag_path().unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove kill flag file: %s", exc)
        # Notify via event_bus
        try:
            from core.event_bus import emit
            emit("agent.resumed", {})
        except Exception:
            logger.warning("kill-switch deactivation was not broadcast", exc_info=True)
        logger.info("Agent kill switch deactivated")

    def status(self) -> dict:
        """Return the current state as a dict."""
        killed = self.is_killed()
        return {
            "killed": killed,
            "reason": self._reason if killed else "",
            "killed_at": self._killed_at if killed else "",
        }


# Singleton instance
_instance: AgentKillSwitch | None = None
_lock = threading.Lock()


def get_kill_switch() -> AgentKillSwitch:
    """Get the Kill Switch singleton instance."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AgentKillSwitch()
    return _instance

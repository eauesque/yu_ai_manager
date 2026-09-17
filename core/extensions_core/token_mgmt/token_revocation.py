"""RevocationTracker: Tracking automatic token revocation conditions.

Revocation conditions:
- File tampering -> immediate revocation (IntegrityMonitor directly revokes)
- 10+ denials within 60 seconds -> revocation
- 24h TTL -> handled by CapabilityToken itself
- 7 days of inactivity -> revocation
"""

from __future__ import annotations

import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

# Revocation thresholds
_DENIAL_WINDOW = 60.0  # seconds
_DENIAL_THRESHOLD = 10  # times

# Inactivity timeout
_INACTIVITY_TIMEOUT = 7 * 24 * 3600  # 7 days (seconds)


class RevocationTracker:
    """Tracks automatic token revocation conditions.

    Receives notifications from ImportGuard and ServiceRegistry,
    and returns True when revocation conditions are met.
    """

    def __init__(self) -> None:
        # ext_name -> deque of denial timestamps
        self._denials: dict[str, deque[float]] = {}
        # ext_name -> last access timestamp
        self._last_access: dict[str, float] = {}

    def record_denial(self, ext_name: str) -> tuple[bool, str]:
        """Record a denial and check whether revocation conditions are met.

        Returns:
            (should_revoke, reason) tuple
        """
        now = time.time()

        if ext_name not in self._denials:
            self._denials[ext_name] = deque()

        dq = self._denials[ext_name]
        dq.append(now)

        # Remove old entries outside the window
        while dq and dq[0] < now - _DENIAL_WINDOW:
            dq.popleft()

        if len(dq) >= _DENIAL_THRESHOLD:
            return True, f"{_DENIAL_THRESHOLD}+ denials in {_DENIAL_WINDOW}s"

        return False, ""

    def record_access(self, ext_name: str) -> None:
        """Record a service access."""
        self._last_access[ext_name] = time.time()

    def check_inactivity(self, ext_name: str) -> tuple[bool, str]:
        """Check for inactivity timeout.

        Returns:
            (should_revoke, reason) tuple
        """
        last = self._last_access.get(ext_name)
        if last is None:
            # No access yet -> do not revoke
            return False, ""

        elapsed = time.time() - last
        if elapsed > _INACTIVITY_TIMEOUT:
            return True, f"inactive for {elapsed / 86400:.1f} days"

        return False, ""

    def get_denial_count(self, ext_name: str) -> int:
        """Return the denial count within the current window."""
        dq = self._denials.get(ext_name)
        if dq is None:
            return 0
        now = time.time()
        while dq and dq[0] < now - _DENIAL_WINDOW:
            dq.popleft()
        return len(dq)

    def get_last_access(self, ext_name: str) -> float | None:
        """Return the last access timestamp."""
        return self._last_access.get(ext_name)

    def reset_extension(self, ext_name: str) -> None:
        """Reset tracking data for an extension."""
        self._denials.pop(ext_name, None)
        self._last_access.pop(ext_name, None)


# --- Singleton ---

_tracker: RevocationTracker | None = None


def get_revocation_tracker() -> RevocationTracker:
    """Return the singleton RevocationTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = RevocationTracker()
    return _tracker


def reset_revocation_tracker() -> None:
    """For testing: reset the singleton."""
    global _tracker
    _tracker = None

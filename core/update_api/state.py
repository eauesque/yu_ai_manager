"""Update runtime shared state and request admission."""

from __future__ import annotations

import threading
import time
from typing import Any

from core.infra_core.api_errors import api_error

_update_state_lock = threading.Lock()
_update_state = {
    "in_progress": False,
    "last_requested_at": 0.0,
}


def get_update_state_snapshot() -> dict[str, Any]:
    """Return a copy of the current update runtime state."""
    with _update_state_lock:
        return dict(_update_state)


def begin_update_request(cooldown_sec: int = 60):
    """Reserve the update runtime slot or return an API error tuple."""
    now = time.time()
    with _update_state_lock:
        if _update_state["in_progress"]:
            return api_error(
                "更新が既に実行中です",
                429,
                code="update_in_progress",
            )
        if now - _update_state["last_requested_at"] < cooldown_sec:
            remaining = max(1, int(cooldown_sec - (now - _update_state["last_requested_at"])))
            return api_error(
                f"更新要求のクールダウン中です ({remaining}秒)",
                429,
                code="update_cooldown",
            )
        _update_state["in_progress"] = True
        _update_state["last_requested_at"] = now
    return None


def mark_update_finished() -> None:
    """Release the update runtime slot."""
    with _update_state_lock:
        _update_state["in_progress"] = False

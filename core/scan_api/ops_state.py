"""State-only operations for scan routes."""

import time
from typing import Any

from core.scan_core.scan_state import clear_scan_state, load_scan_state

# Maximum age (seconds) for interrupted scan state to be shown.
# If the state file is older than this, it's considered stale and auto-dismissed.
# This prevents old state from surviving edge cases (e.g. file not deleted).
_MAX_INTERRUPTED_AGE = 24 * 3600  # 24 hours


def interrupted_scan_payload() -> dict[str, Any]:
    state = load_scan_state()
    if state is None:
        return {"interrupted": False}

    from core.jobs_core.jobs import job_manager
    if job_manager.is_running("scan") or job_manager.is_running("scan-all"):
        return {"interrupted": False}

    # Auto-dismiss very old interrupted states (e.g. from a crash days ago)
    interrupted_at = state.get("interrupted_at")
    if interrupted_at and (time.time() - interrupted_at) > _MAX_INTERRUPTED_AGE:
        clear_scan_state()
        return {"interrupted": False}

    return {
        "interrupted": True,
        "root": state.get("root", ""),
        "recursive": state.get("recursive", True),
        "force": state.get("force", False),
        "scan_zips": state.get("scan_zips", False),
        "current": state.get("current", 0),
        "total": state.get("total", 0),
        "interrupted_at": interrupted_at,
    }


def dismiss_interrupted_scan_payload() -> dict[str, str]:
    clear_scan_state()
    return {"status": "dismissed"}

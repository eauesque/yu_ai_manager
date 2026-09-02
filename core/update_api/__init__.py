"""Compatibility facade for update runtime helpers."""

from core.update_api.policy import (
    accepted_update_response,
    check_update_auth,
    get_version_string,
)
from core.update_api.state import begin_update_request, get_update_state_snapshot
from core.update_api.workers import (
    start_single_update_worker,
    start_unified_update_worker,
)

__all__ = [
    "accepted_update_response",
    "begin_update_request",
    "check_update_auth",
    "get_update_state_snapshot",
    "get_version_string",
    "start_single_update_worker",
    "start_unified_update_worker",
]

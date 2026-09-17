"""Config operations for scan roots routes (compatibility facade)."""

from core.scan_roots_api.ops_read import get_scan_roots_with_exists, load_enabled_scan_roots
from core.scan_roots_api.ops_recovery import recovery_apply, recovery_check, recovery_dismiss
from core.scan_roots_api.ops_write import (
    add_scan_root,
    batch_toggle_scan_roots,
    edit_scan_root,
    remove_scan_root,
    reorder_scan_roots,
    toggle_scan_root,
)

__all__ = [
    "get_scan_roots_with_exists",
    "load_enabled_scan_roots",
    "add_scan_root",
    "remove_scan_root",
    "toggle_scan_root",
    "batch_toggle_scan_roots",
    "reorder_scan_roots",
    "edit_scan_root",
    "recovery_check",
    "recovery_apply",
    "recovery_dismiss",
]

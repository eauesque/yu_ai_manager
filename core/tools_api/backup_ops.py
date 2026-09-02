"""Payload functions for database backup management APIs."""

from importlib import import_module
from typing import Any

# Import from relocated backup extension
_backup_mod = import_module("extensions.builtin_backup.core_impl")
create_backup = _backup_mod.create_backup
delete_backup = _backup_mod.delete_backup
get_last_backup_time = _backup_mod.get_last_backup_time
is_within_cooldown = _backup_mod.is_within_cooldown
list_backups = _backup_mod.list_backups
restore_backup = _backup_mod.restore_backup

_bk_sched = import_module("extensions.builtin_backup.core_impl.scheduler")
backup_scheduler = _bk_sched.backup_scheduler


def create_backup_payload() -> tuple[dict[str, Any], int]:
    """Create a manual backup."""
    result = create_backup(reason="manual")
    if "error" in result:
        return result, 500
    return result, 200


def list_backups_payload() -> tuple[dict[str, Any], int]:
    """List all available backups."""
    backups = list_backups()
    return {"backups": backups, "count": len(backups)}, 200


def restore_backup_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Restore from a named backup."""
    filename = data.get("filename", "")
    if not filename:
        return {"error": "filename is required"}, 400
    result = restore_backup(filename)
    if "error" in result:
        return result, 400
    return result, 200


def delete_backup_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Delete a specific backup."""
    filename = data.get("filename", "")
    if not filename:
        return {"error": "filename is required"}, 400
    result = delete_backup(filename)
    if "error" in result:
        return result, 400
    return result, 200


def get_backup_status_payload() -> tuple[dict[str, Any], int]:
    """Return current backup system status."""
    from core.services_core.db_api import get_config

    cfg = get_config()
    backup_cfg = cfg.get("backup", {})
    last_time = get_last_backup_time()

    return {
        "enabled": backup_cfg.get("enabled", True),
        "backup_on_scan_complete": backup_cfg.get("backup_on_scan_complete", True),
        "periodic_interval_hours": backup_cfg.get("periodic_interval_hours", 24),
        "max_generations": backup_cfg.get("max_generations", 5),
        "cooldown_minutes": backup_cfg.get("cooldown_minutes", 5),
        "scheduler_running": backup_scheduler.running,
        "last_backup_time": last_time,
        "within_cooldown": is_within_cooldown(),
    }, 200

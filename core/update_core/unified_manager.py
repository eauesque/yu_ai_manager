"""Unified update manager: check and apply updates for system + all extensions."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .unified_manager_support import (
    backup_extension_configs,
    git_commit_count_behind,
    git_local_head,
    git_remote_head,
)

logger = logging.getLogger(__name__)

# Cache for unified check results
_unified_cache: dict = {}
_UNIFIED_CACHE_TTL = 600  # 10 minutes

def check_unified_updates(force: bool = False) -> dict:
    """Check update status for system and all extensions.

    Returns a dict with:
      - system: system update info (from version_check)
      - extensions: list of extension update status dicts
      - summary: {total, up_to_date, update_available, unknown, builtin}
    """
    now = time.time()
    if (not force and _unified_cache.get("result")
            and (now - _unified_cache.get("ts", 0)) < _UNIFIED_CACHE_TTL):
        return _unified_cache["result"]

    from core.update_core.version_check import check_for_update
    system_info = check_for_update()

    # Get extension manager
    ext_statuses = []
    summary = {
        "total": 0,
        "up_to_date": 0,
        "update_available": 0,
        "unknown": 0,
        "builtin": 0,
    }

    try:
        from core.extensions_core.lifecycle.runtime import get_extension_manager
        mgr = get_extension_manager()
        manifests = dict(mgr.manifests)

        for ext_name, manifest in manifests.items():
            summary["total"] += 1
            ext_dir = manifest.directory

            # Builtin extensions are tied to system version
            if ext_name.startswith("builtin-"):
                status = "builtin"
                summary["builtin"] += 1
                ext_statuses.append({
                    "name": ext_name,
                    "version": getattr(manifest, "version", ""),
                    "source": "builtin",
                    "status": status,
                    "enabled": getattr(manifest, "enabled", True),
                    "description": getattr(manifest, "description", ""),
                })
                continue

            # Git-based external extension
            if ext_dir and (ext_dir / ".git").exists():
                local_head = git_local_head(ext_dir)
                remote_head = git_remote_head(ext_dir)

                if local_head is None or remote_head is None:
                    status = "unknown"
                    summary["unknown"] += 1
                    commits_behind = 0
                elif local_head == remote_head:
                    status = "up_to_date"
                    summary["up_to_date"] += 1
                    commits_behind = 0
                else:
                    status = "update_available"
                    summary["update_available"] += 1
                    commits_behind = git_commit_count_behind(ext_dir)

                ext_statuses.append({
                    "name": ext_name,
                    "version": getattr(manifest, "version", ""),
                    "source": "git",
                    "status": status,
                    "enabled": getattr(manifest, "enabled", True),
                    "description": getattr(manifest, "description", ""),
                    "local_head": (local_head or "")[:8],
                    "remote_head": (remote_head or "")[:8],
                    "commits_behind": commits_behind if status == "update_available" else 0,
                })
            else:
                # Local/manual install — cannot check remotely
                status = "unknown"
                summary["unknown"] += 1
                ext_statuses.append({
                    "name": ext_name,
                    "version": getattr(manifest, "version", ""),
                    "source": "local",
                    "status": status,
                    "enabled": getattr(manifest, "enabled", True),
                    "description": getattr(manifest, "description", ""),
                })

    except Exception as exc:
        logger.error("Failed to check extension updates: %s", exc)

    result = {
        "system": system_info,
        "extensions": ext_statuses,
        "summary": summary,
    }

    _unified_cache["result"] = result
    _unified_cache["ts"] = now
    return result


def apply_unified_updates(
    emit_progress: Callable[[str, str, str], None],
    update_system: bool = True,
    update_extensions: bool = True,
    extension_names: list[str] | None = None,
) -> dict:
    """Apply updates for system and/or extensions.

    Args:
        emit_progress: Callback(step, status, detail)
        update_system: Whether to update the system
        update_extensions: Whether to update extensions
        extension_names: If provided, only update these extensions.
                         None means update all git-based extensions.

    Returns:
        {"success": bool, "system_result": dict | None,
         "extension_results": list, "restart_required": bool}
    """
    results = {
        "success": True,
        "system_result": None,
        "extension_results": [],
        "restart_required": False,
    }

    # Step 1: Backup extension configs
    if update_extensions:
        emit_progress("ext_config_backup", "running", "")
        backup = backup_extension_configs()
        if backup.get("skipped"):
            emit_progress("ext_config_backup", "done", "No config to backup")
        elif backup["success"]:
            emit_progress("ext_config_backup", "done", backup["backup_path"])
        else:
            emit_progress("ext_config_backup", "error", backup.get("error", ""))
            # Non-fatal: continue with updates

    # Step 2: Update extensions first (before system update restarts)
    if update_extensions:
        try:
            from core.extensions_core.lifecycle.extensions_api_git_ops import (
                update_extension_from_git,
            )
            from core.extensions_core.lifecycle.runtime import get_extension_manager
            mgr = get_extension_manager()
            manifests = dict(mgr.manifests)

            targets = []
            for ext_name, manifest in manifests.items():
                if ext_name.startswith("builtin-"):
                    continue
                ext_dir = manifest.directory
                if ext_dir is None or not (ext_dir / ".git").exists():
                    continue
                if extension_names is not None and ext_name not in extension_names:
                    continue
                targets.append(ext_name)

            for i, ext_name in enumerate(targets):
                step_id = f"ext_update_{ext_name}"
                emit_progress(step_id, "running", f"({i+1}/{len(targets)})")
                try:
                    resp, status = update_extension_from_git(mgr, ext_name)
                    if status == 200:
                        emit_progress(step_id, "done", resp.get("message", "OK"))
                        results["extension_results"].append({
                            "name": ext_name, "status": "updated",
                        })
                    else:
                        emit_progress(step_id, "error", resp.get("error", "Failed"))
                        results["extension_results"].append({
                            "name": ext_name, "status": "error",
                            "reason": resp.get("error", ""),
                        })
                except Exception as exc:
                    emit_progress(step_id, "error", str(exc))
                    results["extension_results"].append({
                        "name": ext_name, "status": "error", "reason": str(exc),
                    })

        except Exception as exc:
            logger.error("Extension update phase failed: %s", exc)
            emit_progress("ext_update", "error", str(exc))

    # Step 3: Update system (last, because it may restart)
    if update_system:
        from core.update_core.detect import detect_install_type
        install_type = detect_install_type()

        if install_type == "git":
            from core.update_core.git_updater import run_git_update
            sys_result = run_git_update(emit_progress)
            results["system_result"] = sys_result
            results["restart_required"] = sys_result.get("restart_required", False)
            if not sys_result["success"]:
                results["success"] = False
        elif install_type == "portable":
            from core.update_core.portable_updater import run_portable_update
            sys_result = run_portable_update(emit_progress)
            results["system_result"] = sys_result
            results["restart_required"] = sys_result.get("restart_required", False)
            if not sys_result["success"]:
                results["success"] = False
        else:
            emit_progress("system", "done",
                          f"System update skipped ({install_type} install)")
            results["system_result"] = {
                "success": True,
                "skipped": True,
                "install_type": install_type,
            }

    # Invalidate cache
    _unified_cache.clear()

    return results

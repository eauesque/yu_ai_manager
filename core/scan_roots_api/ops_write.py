"""Mutation operations for scan roots config."""

import os
from typing import Any

from core.configuration.api import load_config_json, save_config_json
from core.event_bus import emit
from core.event_bus.event_types import SCAN_ROOTS_CHANGED
from core.helpers_core.helpers_text_path import sanitize_user_path
from core.infra_core.api_params import get_arg, get_bool_arg, get_str_arg
from core.infra_core.api_validation import error_payload, validate_index


def add_scan_root(data: dict[str, Any]) -> tuple[dict[str, Any] | None, tuple[dict[str, str], int] | None]:
    path = sanitize_user_path(get_str_arg(data, ("path", "root", "dir"), ""))
    if not path:
        return None, error_payload("path is required", "path_required", 400)

    config = load_config_json(None)
    if "scan_roots" not in config:
        config["scan_roots"] = []

    norm_path = os.path.normcase(path.replace("/", os.sep).replace("\\", os.sep))
    for root in config["scan_roots"]:
        existing = os.path.normcase(root["path"].replace("/", os.sep).replace("\\", os.sep))
        if existing == norm_path:
            return None, error_payload(f"既に登録済みです: {root['path']}", "scan_root_already_exists", 409)

    new_root = {
        "path": path,
        "enabled": get_bool_arg(data, ("enabled", "on"), True),
        "recursive": get_bool_arg(data, ("recursive", "recurse"), True),
        "comment": get_str_arg(data, ("comment", "note"), ""),
    }
    config["scan_roots"].append(new_root)
    save_config_json(config)
    emit(SCAN_ROOTS_CHANGED, {"action": "add", "path": new_root["path"]})
    return new_root, None


def remove_scan_root(index: int):
    config = load_config_json(None)
    roots = config.get("scan_roots", [])
    idx_err = validate_index(index, len(roots))
    if idx_err:
        return None, idx_err
    removed = roots.pop(index)
    config["scan_roots"] = roots
    save_config_json(config)


    # Auto-purge DB records under the removed root
    removed_path = removed.get("path", "")
    purged = 0
    if removed_path:
        from core.debug_api.roots_ops import purge_db_root
        result, _status = purge_db_root(removed_path)
        purged = result.get("purged", 0) if isinstance(result, dict) else 0

    emit(SCAN_ROOTS_CHANGED, {"action": "remove", "path": removed_path})
    removed["purged"] = purged
    return removed, None


def toggle_scan_root(index: int):
    config = load_config_json(None)
    roots = config.get("scan_roots", [])
    idx_err = validate_index(index, len(roots))
    if idx_err:
        return None, idx_err
    roots[index]["enabled"] = not roots[index].get("enabled", True)
    config["scan_roots"] = roots
    save_config_json(config)
    emit(SCAN_ROOTS_CHANGED, {"action": "toggle", "path": roots[index].get("path", "")})
    return roots[index], None


def batch_toggle_scan_roots(enabled: bool):
    """Set all scan roots to enabled or disabled."""
    config = load_config_json(None)
    roots = config.get("scan_roots", [])
    changed = 0
    for root in roots:
        if root.get("enabled", True) != enabled:
            root["enabled"] = enabled
            changed += 1
    if changed:
        config["scan_roots"] = roots
        save_config_json(config)
        emit(SCAN_ROOTS_CHANGED, {"action": "batch_toggle", "enabled": enabled})
    return {"changed": changed, "total": len(roots), "enabled": enabled}, None


def reorder_scan_roots(data: dict[str, Any]):
    config = load_config_json(None)
    roots_data = get_arg(data, ("roots", "items"), None)
    order_data = get_arg(data, ("order", "indexes"), None)
    if roots_data is not None:
        # Validate each root object before saving
        validated = []
        for r in roots_data:
            if not isinstance(r, dict):
                continue
            path = r.get("path", "")
            if not path or not isinstance(path, str) or len(path.strip()) < 2:
                continue
            validated.append(r)
        if not validated:
            return None, error_payload("No valid roots in payload", "invalid_roots", 400)
        config["scan_roots"] = validated
    elif order_data is not None:
        new_order = order_data
        roots = config.get("scan_roots", [])
        if sorted(new_order) != list(range(len(roots))):
            return None, error_payload("Invalid order array", "invalid_order_array", 400)
        config["scan_roots"] = [roots[i] for i in new_order]
    else:
        return None, error_payload("roots or order required", "roots_or_order_required", 400)
    save_config_json(config)
    emit(SCAN_ROOTS_CHANGED, {"action": "reorder"})
    return config["scan_roots"], None


def edit_scan_root(index: int, data: dict[str, Any]):
    config = load_config_json(None)
    roots = config.get("scan_roots", [])
    idx_err = validate_index(index, len(roots))
    if idx_err:
        return None, idx_err

    path_value = get_arg(data, ("path", "root", "dir"), None)
    if path_value is not None:
        new_path = sanitize_user_path(path_value)
        if not new_path:
            return None, error_payload("path is required", "path_required", 400)
        roots[index]["path"] = new_path
    if "recursive" in data or "recurse" in data:
        roots[index]["recursive"] = get_bool_arg(data, ("recursive", "recurse"), True)
    if "comment" in data or "note" in data:
        roots[index]["comment"] = get_str_arg(data, ("comment", "note"), "")

    config["scan_roots"] = roots
    save_config_json(config)
    emit(SCAN_ROOTS_CHANGED, {"action": "edit", "path": roots[index].get("path", "")})
    return roots[index], None

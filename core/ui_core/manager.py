"""UI management — list, switch, install, uninstall."""

import logging
import shutil
from pathlib import Path

from core.configuration.json_rw import load_config_json, save_config_json

from .installer import install_ui as _install_from_url
from .manifest import list_ui_dirs, load_ui_manifest
from .resolver import resolve_active_ui

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def list_uis() -> list[dict]:
    """Return metadata for all installed UIs."""
    root = _project_root()
    active = resolve_active_ui(load_config_json())
    result: list[dict] = []
    for ui_dir in list_ui_dirs(root):
        manifest = load_ui_manifest(ui_dir)
        if manifest is None:
            continue
        name = ui_dir.name
        result.append({
            "name": name,
            "active": name == active,
            "manifest": manifest,
            "has_templates": (ui_dir / "templates").is_dir(),
            "has_static": (ui_dir / "static").is_dir(),
        })
    return result


def switch_ui(name: str, config_path: str | None = None) -> tuple[dict, int]:
    """Set the active UI in config.json.

    Returns (response_dict, http_status).
    """
    root = _project_root()
    ui_dir = root / "ui" / name
    if not ui_dir.is_dir():
        return {"error": f"UI '{name}' not found"}, 404
    manifest = load_ui_manifest(ui_dir)
    if manifest is None:
        return {"error": f"UI '{name}' has no valid manifest.json"}, 400

    try:
        config = load_config_json(config_path)
        config["ui"] = name if name != "default" else None
        save_config_json(config, config_path)
    except PermissionError as e:
        logger.error("Permission denied saving config: %s", e)
        return {"error": f"Config save failed (permission denied): {config_path}"}, 500
    except Exception as e:
        logger.error("Failed to save config: %s", e)
        return {"error": f"Config save failed: {e}"}, 500
    logger.info("Switched active UI to '%s'", name)
    return {"name": name, "restart_required": True}, 200


def install_ui(url: str) -> tuple[dict, int]:
    """Install a UI from URL (delegates to installer)."""
    return _install_from_url(url)


def uninstall_ui(name: str) -> tuple[dict, int]:
    """Remove an installed UI (not 'default')."""
    if name == "default":
        return {"error": "Cannot uninstall the default UI"}, 400

    root = _project_root()
    ui_dir = root / "ui" / name
    if not ui_dir.is_dir():
        return {"error": f"UI '{name}' not found"}, 404

    # If this UI is currently active, reset config
    config = load_config_json()
    if config.get("ui") == name:
        config["ui"] = None
        save_config_json(config)

    shutil.rmtree(ui_dir, ignore_errors=True)
    logger.info("Uninstalled UI '%s'", name)
    return {"name": name, "uninstalled": True}, 200

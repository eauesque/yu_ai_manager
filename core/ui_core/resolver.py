"""Active UI resolution — determines which UI directory to use.

Priority order:
1. ``config["ui"]`` explicitly set  -> ``ui/<name>/``
2. ``ui/custom/`` with valid manifest -> ``"custom"``
3. Fallback -> ``"default"``
"""

import logging
from pathlib import Path

from .manifest import load_ui_manifest

logger = logging.getLogger(__name__)

_PROJECT_ROOT: Path | None = None


def _project_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    return _PROJECT_ROOT


def resolve_active_ui(config: dict) -> str:
    """Return the name of the active UI based on config and filesystem.

    Returns one of: an explicit name from config, ``"custom"``, or
    ``"default"``.
    """
    root = _project_root()

    # 1. Explicit config override
    explicit = config.get("ui")
    if explicit and isinstance(explicit, str):
        ui_dir = root / "ui" / explicit
        if ui_dir.is_dir() and load_ui_manifest(ui_dir) is not None:
            logger.info("Active UI: '%s' (config)", explicit)
            return explicit
        logger.warning(
            "Config specifies ui='%s' but no valid UI found at %s; falling back",
            explicit,
            ui_dir,
        )

    # 2. Auto-detect ui/custom/
    custom_dir = root / "ui" / "custom"
    if custom_dir.is_dir() and load_ui_manifest(custom_dir) is not None:
        logger.info("Active UI: 'custom' (auto-detected)")
        return "custom"

    # 3. Default fallback
    logger.info("Active UI: 'default'")
    return "default"


def get_ui_paths(ui_name: str) -> dict:
    """Return absolute paths for the given UI name.

    Keys: ``template_folder``, ``static_folder``, ``ui_dir``.
    """
    root = _project_root()
    ui_dir = root / "ui" / ui_name
    return {
        "template_folder": ui_dir / "templates",
        "static_folder": ui_dir / "static",
        "ui_dir": ui_dir,
    }

"""UI manifest.json loading and validation.

Each UI directory (ui/<name>/) must contain a manifest.json with at least
``name`` and ``version`` fields.  Optional fields: ``description``,
``author``, ``api_version``, ``type`` ("full" | "theme").
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("name", "version")
_OPTIONAL_FIELDS = ("description", "author", "api_version", "type", "label", "preview_image", "is_sample")
_VALID_TYPES = ("full", "theme")


def load_ui_manifest(ui_dir: Path) -> dict | None:
    """Load and validate manifest.json from a UI directory.

    Returns the parsed dict on success, or ``None`` if the file is missing,
    unreadable, or fails validation.
    """
    manifest_path = ui_dir / "manifest.json"
    if not manifest_path.is_file():
        return None

    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read UI manifest %s: %s", manifest_path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("UI manifest %s is not a JSON object", manifest_path)
        return None

    # Required field check
    for field in _REQUIRED_FIELDS:
        if field not in data or not isinstance(data[field], str) or not data[field].strip():
            logger.warning(
                "UI manifest %s missing or empty required field: %s",
                manifest_path,
                field,
            )
            return None

    # Validate type if present
    ui_type = data.get("type")
    if ui_type is not None and ui_type not in _VALID_TYPES:
        logger.warning(
            "UI manifest %s has invalid type '%s' (expected one of %s)",
            manifest_path,
            ui_type,
            _VALID_TYPES,
        )
        return None

    return data


def list_ui_dirs(base_dir: Path | None = None) -> list[Path]:
    """Return all directories under ``ui/`` that contain a valid manifest."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parents[2]
    ui_root = base_dir / "ui"
    if not ui_root.is_dir():
        return []
    dirs: list[Path] = []
    for child in sorted(ui_root.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            dirs.append(child)
    return dirs

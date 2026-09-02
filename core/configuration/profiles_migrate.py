"""One-way migration: config.json inline profiles -> profiles/ directory.

Safe strategy:
  1. Write all profile files to profiles/
  2. Only then remove the ``profiles`` key from config.json
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .json_rw import load_config_json, save_config_json
from .profiles import _profile_path, save_profile, validate_profile_name

logger = logging.getLogger(__name__)

# Sentinel: when None, _current_profiles_dir() resolves via core.paths.get_profiles_dir().
# Tests may monkey-patch this attribute directly to override the location.
PROFILES_DIR: Path | None = None


def _current_profiles_dir() -> Path:
    """Resolve the profiles directory, honoring test monkey-patches."""
    if PROFILES_DIR is not None:
        return PROFILES_DIR
    from core.paths import get_profiles_dir
    return get_profiles_dir()


def needs_migration() -> bool:
    """Return True if config.json has an inline ``profiles`` dict that
    contains entries not yet present in ``profiles/``."""
    cfg = load_config_json(None)
    inline = cfg.get("profiles")
    if not isinstance(inline, dict) or not inline:
        return False
    return any(not _profile_path(name).exists() for name in inline)


def migrate_inline_profiles() -> int:
    """Migrate inline profiles from config.json to ``profiles/`` files.

    Returns the number of profiles migrated.
    """
    cfg = load_config_json(None)
    inline = cfg.get("profiles")
    if not isinstance(inline, dict) or not inline:
        return 0

    _current_profiles_dir().mkdir(parents=True, exist_ok=True)
    migrated = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for name, prof_data in inline.items():
        if _profile_path(name).exists():
            logger.debug("Profile '%s' already exists on disk — skip", name)
            continue
        err = validate_profile_name(name)
        if err:
            logger.warning("Skipping invalid profile name '%s': %s", name, err)
            continue

        data = dict(prof_data) if isinstance(prof_data, dict) else {}
        data.setdefault("name", name)
        data.setdefault("label", name)
        data.setdefault("description", "")
        data.setdefault("favorite", False)
        data.setdefault("created_at", now)
        data.setdefault("last_used_at", None)

        try:
            save_profile(name, data)
            migrated += 1
            logger.info("Migrated profile '%s' to %s", name, _profile_path(name))
        except Exception as exc:
            logger.error("Failed to migrate profile '%s': %s", name, exc)

    # Remove inline profiles key only after all files are written
    if migrated > 0:
        cfg.pop("profiles", None)
        save_config_json(cfg)
        logger.info("Removed inline 'profiles' key from config.json (%d migrated)", migrated)

    return migrated


def ensure_profiles_ready() -> None:
    """Call at startup: run migration if needed + ensure profiles/ exists."""
    _current_profiles_dir().mkdir(parents=True, exist_ok=True)
    if needs_migration():
        count = migrate_inline_profiles()
        if count:
            logger.info(f"  [PROFILE] Migrated {count} profile(s) from config.json to profiles/")

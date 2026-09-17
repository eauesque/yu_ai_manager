"""Config loading API for app/CLI entrypoints."""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

from core.configuration.defaults import DEFAULT_CONFIG
from core.configuration.env_override import apply_env_overrides
from core.configuration.json_io import (
    load_config_json,
    repair_json_backslashes,
    safe_load_config,
    safe_load_json,
    safe_load_yaml,
    save_config_json,
)


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """DEFAULT_CONFIG merged with the config file, then env overrides.

    Parsing is delegated to `load_config_json` so the format follows the
    file: startup now resolves to config.toml when it exists (matching
    yu-server), and a `json.loads` here would fail on it and silently serve
    defaults for the whole process.

    `config_path=None` means "the file a read would land on" -- the same
    answer the settings API and yu-server give. It used to mean "no file at
    all", which made every caller that passed None see defaults no matter
    what the user had configured.
    """
    config = dict(DEFAULT_CONFIG)
    try:
        loaded = load_config_json(config_path)
        if isinstance(loaded, dict):
            config.update(loaded)
    except Exception as exc:
        logger.debug("Failed to load config %s: %s", config_path, exc)
    config = apply_env_overrides(config)
    return config


load_or_default_config = load_config


def validate_profile_db_path(db_path: str) -> None:
    """Raise ValueError if db_path contains path traversal or suspicious patterns."""
    if not isinstance(db_path, str) or not db_path.strip():
        raise ValueError("Profile db path must be a non-empty string")
    normalized = os.path.normpath(db_path)
    if ".." in normalized.split(os.sep):
        raise ValueError(f"Path traversal detected in profile db path: {db_path!r}")
    if normalized.startswith(("/etc/", "/proc/", "/sys/", "/dev/")):
        raise ValueError(f"Disallowed system path in profile db: {db_path!r}")


_PROFILE_SKIP_KEYS = frozenset({
    "label", "db", "name", "description", "favorite",
    "last_used_at", "created_at",
})


def resolve_profile_config(config: dict, profile_name: str) -> tuple:
    """Return (merged_config, profile_db_path_or_None).

    Looks up profiles/ directory first, then falls back to config.json
    inline profiles for pre-migration compatibility.

    Raises ValueError if profile not found.
    """
    from core.configuration.profiles import load_profile

    prof = load_profile(profile_name)
    if prof is None:
        # Fallback: config.json inline (pre-migration compat)
        profiles = config.get("profiles", {})
        if profile_name not in profiles:
            available = ", ".join(profiles.keys()) or "(none)"
            raise ValueError(f"Profile '{profile_name}' not found. Available: {available}")
        prof = profiles[profile_name]

    merged = {**config}
    for k, v in prof.items():
        if k in _PROFILE_SKIP_KEYS:
            continue
        if k == "server" and isinstance(v, dict):
            merged["server"] = {**merged.get("server", {}), **v}
        else:
            merged[k] = v
    merged["active_profile"] = profile_name
    db_path = prof.get("db")
    if db_path is not None:
        validate_profile_db_path(db_path)
    return merged, db_path

__all__ = [
    "DEFAULT_CONFIG",
    "apply_env_overrides",
    "load_config",
    "load_or_default_config",
    "validate_profile_db_path",
    "resolve_profile_config",
    "repair_json_backslashes",
    "load_config_json",
    "save_config_json",
    "safe_load_json",
    "safe_load_yaml",
    "safe_load_config",
]

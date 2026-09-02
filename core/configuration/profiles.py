"""Profile CRUD operations — profiles/ directory-based storage.

Each profile is stored as ``profiles/<name>.json``.
File locking reuses the primitives from ``json_rw``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from .json_rw import save_config_json as _atomic_save

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

# Sentinel: when None, _current_profiles_dir() resolves via core.paths.get_profiles_dir().
# Tests may monkey-patch this attribute directly to override the location.
PROFILES_DIR: Path | None = None


def _current_profiles_dir() -> Path:
    """Resolve the profiles directory, honoring test monkey-patches."""
    if PROFILES_DIR is not None:
        return PROFILES_DIR
    from core.paths import get_profiles_dir
    return get_profiles_dir()

_METADATA_KEYS = frozenset({
    "name", "label", "description", "favorite",
    "last_used_at", "created_at", "db",
})
_SENSITIVE_PATTERNS = frozenset({
    "pin", "restart_token", "secret", "token", "key",
})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_sensitive_key(key: str) -> bool:
    """Return True if *key* looks like a credential field."""
    low = key.lower()
    return any(pat in low for pat in _SENSITIVE_PATTERNS)


def validate_profile_name(name: str) -> str | None:
    """Return an error message if *name* is invalid, else ``None``."""
    if not name:
        return "Profile name must not be empty"
    if not PROFILE_NAME_RE.match(name):
        return (
            "Profile name must be 1-64 chars of [a-zA-Z0-9_-]"
        )
    return None


def _profile_path(name: str) -> Path:
    return _current_profiles_dir() / f"{name}.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_save(data, str(path))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_profiles() -> list[dict[str, Any]]:
    """Return metadata-only dicts for every profile, favorites first."""
    profiles_dir = _current_profiles_dir()
    profiles_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict] = []
    for p in sorted(profiles_dir.glob("*.json")):
        try:
            data = _read_json(p)
            result.append({
                "name": data.get("name", p.stem),
                "label": data.get("label", p.stem),
                "description": data.get("description", ""),
                "favorite": data.get("favorite", False),
                "last_used_at": data.get("last_used_at"),
                "created_at": data.get("created_at"),
                "db": data.get("db"),
            })
        except Exception as exc:
            logger.warning("profile entry skipped, it will not appear in the list: %s", exc)
            continue
    # favorites first, then alphabetical
    result.sort(key=lambda x: (not x.get("favorite", False), (x.get("label") or x.get("name", "")).lower()))
    return result


def load_profile(name: str) -> dict[str, Any] | None:
    """Load a profile by name.  Returns ``None`` if not found."""
    err = validate_profile_name(name)
    if err:
        return None
    path = _profile_path(name)
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except Exception:
        return None


def save_profile(name: str, data: dict) -> None:
    """Write *data* to ``profiles/<name>.json`` with file locking."""
    err = validate_profile_name(name)
    if err:
        raise ValueError(err)
    data["name"] = name
    _write_json(_profile_path(name), data)


def create_profile(
    name: str,
    label: str,
    description: str = "",
    base_config: dict | None = None,
) -> dict:
    """Create a new profile and return its data."""
    err = validate_profile_name(name)
    if err:
        raise ValueError(err)
    if _profile_path(name).exists():
        raise ValueError(f"Profile '{name}' already exists")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data: dict[str, Any] = {
        "name": name,
        "label": label,
        "description": description,
        "favorite": False,
        "created_at": now,
        "last_used_at": None,
    }
    if base_config:
        for k, v in base_config.items():
            if k not in _METADATA_KEYS:
                data[k] = v
    save_profile(name, data)
    return data


def delete_profile(name: str) -> None:
    """Delete a profile file.  Raises ``ValueError`` for invalid / missing."""
    err = validate_profile_name(name)
    if err:
        raise ValueError(err)
    path = _profile_path(name)
    if not path.exists():
        raise ValueError(f"Profile '{name}' not found")
    path.unlink()


def duplicate_profile(source: str, new_name: str, new_label: str) -> dict:
    """Copy *source* profile to *new_name* with *new_label*."""
    src_data = load_profile(source)
    if src_data is None:
        raise ValueError(f"Source profile '{source}' not found")
    err = validate_profile_name(new_name)
    if err:
        raise ValueError(err)
    if _profile_path(new_name).exists():
        raise ValueError(f"Profile '{new_name}' already exists")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    new_data = dict(src_data)
    new_data["name"] = new_name
    new_data["label"] = new_label
    new_data["created_at"] = now
    new_data["last_used_at"] = None
    save_profile(new_name, new_data)
    return new_data


def rename_profile(old_name: str, new_name: str) -> dict:
    """Rename profile file and update internal name field."""
    old_data = load_profile(old_name)
    if old_data is None:
        raise ValueError(f"Profile '{old_name}' not found")
    err = validate_profile_name(new_name)
    if err:
        raise ValueError(err)
    if _profile_path(new_name).exists():
        raise ValueError(f"Profile '{new_name}' already exists")

    old_data["name"] = new_name
    save_profile(new_name, old_data)
    _profile_path(old_name).unlink()
    return old_data


def update_profile_metadata(name: str, **kwargs: Any) -> dict:
    """Update mutable metadata fields (label / description / favorite)."""
    allowed = {"label", "description", "favorite"}
    bad = set(kwargs) - allowed
    if bad:
        raise ValueError(f"Cannot update: {bad}")
    data = load_profile(name)
    if data is None:
        raise ValueError(f"Profile '{name}' not found")
    data.update(kwargs)
    save_profile(name, data)
    return data


def touch_last_used(name: str) -> None:
    """Set ``last_used_at`` to the current UTC time."""
    data = load_profile(name)
    if data is None:
        return
    data["last_used_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_profile(name, data)


def export_for_qr(name: str) -> dict:
    """Return profile data with sensitive fields stripped."""
    data = load_profile(name)
    if data is None:
        raise ValueError(f"Profile '{name}' not found")
    result: dict[str, Any] = {}
    for k, v in data.items():
        if _is_sensitive_key(k):
            continue
        if isinstance(v, dict):
            v = {sk: sv for sk, sv in v.items() if not _is_sensitive_key(sk)}
        result[k] = v
    return result

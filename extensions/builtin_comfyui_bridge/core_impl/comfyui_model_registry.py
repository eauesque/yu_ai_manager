"""ComfyUI model registry — user-configurable model compatibility table.

Built-in entries are loaded from ``model_registry_builtin.json`` (alongside
this extension).  User overrides are stored in the extension config DB under
the key ``model_registry_user``.

Lookup order: user entries first, then built-in entries.  The first entry
whose ``unet_patterns`` contains a case-insensitive substring of the model
filename is returned.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

logger = logging.getLogger(__name__)

EXT_NAME = "builtin-comfyui-bridge"
_BUILTIN_JSON = Path(__file__).parent.parent / "model_registry_builtin.json"
_USER_CONFIG_KEY = "model_registry_user"
_REGISTRY_LOCK = threading.Lock()  # guards read-modify-write on user registry


@dataclass
class RegistryEntry:
    id: str
    unet_patterns: list[str]
    vae: str = ""
    clip_1: str = ""
    clip_2: str = ""
    clip_type: str = ""
    latent_node: str = ""
    source_url: str = ""
    default_sampler: str = ""
    default_scheduler: str = ""
    default_cfg: float | None = None
    default_steps: int | None = None
    notes: str = ""
    builtin: bool = False         # runtime-only flag, not persisted to user config
    shadows_builtin: bool = False  # runtime-only: True when this user entry shadows a same-id builtin


def _entry_from_dict(d: dict[str, Any], *, builtin: bool = False) -> RegistryEntry | None:
    """Parse a raw dict into a RegistryEntry. Returns None if mandatory fields are missing."""
    eid = str(d.get("id") or "").strip()
    if not eid:
        return None

    # Accept both "unet_patterns" (list) and "unet_pattern" (string, legacy).
    raw_patterns = d.get("unet_patterns")
    if raw_patterns is None:
        single = str(d.get("unet_pattern") or "").strip()
        patterns: list[str] = [single] if single else []
    elif isinstance(raw_patterns, str):
        patterns = [raw_patterns.strip()] if raw_patterns.strip() else []
    elif isinstance(raw_patterns, list):
        patterns = [str(p).strip() for p in raw_patterns if str(p).strip()]
    else:
        patterns = []

    if not patterns:
        return None

    cfg_raw = d.get("default_cfg")
    steps_raw = d.get("default_steps")
    try:
        cfg_val: float | None = float(cfg_raw) if cfg_raw is not None else None
    except (TypeError, ValueError):
        cfg_val = None
    try:
        steps_val: int | None = int(steps_raw) if steps_raw is not None else None
    except (TypeError, ValueError):
        steps_val = None

    return RegistryEntry(
        id=eid,
        unet_patterns=patterns,
        vae=str(d.get("vae") or ""),
        clip_1=str(d.get("clip_1") or ""),
        clip_2=str(d.get("clip_2") or ""),
        clip_type=str(d.get("clip_type") or ""),
        latent_node=str(d.get("latent_node") or ""),
        source_url=str(d.get("source_url") or ""),
        default_sampler=str(d.get("default_sampler") or ""),
        default_scheduler=str(d.get("default_scheduler") or ""),
        default_cfg=cfg_val,
        default_steps=steps_val,
        notes=str(d.get("notes") or ""),
        builtin=builtin,
    )


def _entry_to_dict(entry: RegistryEntry, *, include_builtin_flag: bool = True) -> dict[str, Any]:
    """Serialise a RegistryEntry to a plain dict suitable for JSON / API responses."""
    d: dict[str, Any] = {
        "id": entry.id,
        "unet_patterns": entry.unet_patterns,
        "vae": entry.vae,
        "clip_1": entry.clip_1,
        "clip_2": entry.clip_2,
        "clip_type": entry.clip_type,
        "latent_node": entry.latent_node,
        "source_url": entry.source_url,
        "default_sampler": entry.default_sampler,
        "default_scheduler": entry.default_scheduler,
        "default_cfg": entry.default_cfg,
        "default_steps": entry.default_steps,
        "notes": entry.notes,
    }
    if include_builtin_flag:
        d["builtin"] = entry.builtin
        if entry.shadows_builtin:
            d["shadows_builtin"] = True
    return d


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_builtin_registry() -> list[RegistryEntry]:
    """Load built-in model registry from the bundled JSON file."""
    try:
        raw = json.loads(_BUILTIN_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load builtin model registry from %s: %s", _BUILTIN_JSON, exc)
        return []
    entries: list[RegistryEntry] = []
    for item in raw.get("entries", []):
        if isinstance(item, dict):
            e = _entry_from_dict(item, builtin=True)
            if e:
                entries.append(e)
    return entries


def load_user_registry() -> list[RegistryEntry]:
    """Load user model registry from the extension config DB."""
    raw = get_extension_config_value(EXT_NAME, _USER_CONFIG_KEY, [])
    if not isinstance(raw, list):
        return []
    entries: list[RegistryEntry] = []
    for item in raw:
        if isinstance(item, dict):
            e = _entry_from_dict(item, builtin=False)
            if e:
                entries.append(e)
    return entries


def get_merged_registry() -> list[RegistryEntry]:
    """Return user + built-in entries merged (user entries appear first).

    User entries shadow built-in entries with the same ``id``.
    When a user entry has the same id as a built-in, it is marked with
    ``shadows_builtin=True`` so callers (e.g. the WebUI) can indicate
    the override visually.
    """
    from dataclasses import replace as _dc_replace

    user = load_user_registry()
    builtin = load_builtin_registry()
    builtin_ids = {e.id for e in builtin}
    user_ids = {e.id for e in user}

    merged: list[RegistryEntry] = []
    for e in user:
        if e.id in builtin_ids:
            e = _dc_replace(e, shadows_builtin=True)
        merged.append(e)
    for e in builtin:
        if e.id not in user_ids:
            merged.append(e)
    return merged


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _save_user_registry(entries: list[RegistryEntry]) -> None:
    """Persist user registry to extension config DB (overwrites existing list)."""
    data = [_entry_to_dict(e, include_builtin_flag=False) for e in entries]
    save_extension_config_values(EXT_NAME, {_USER_CONFIG_KEY: data})


def upsert_user_entry(entry_dict: dict[str, Any]) -> tuple[RegistryEntry, bool]:
    """Insert or update a user registry entry.

    Returns ``(entry, created)`` where ``created`` is True for new entries.
    Raises ``ValueError`` if the entry dict is missing mandatory fields.
    """
    entry = _entry_from_dict(entry_dict, builtin=False)
    if entry is None:
        raise ValueError("Invalid entry: 'id' and at least one pattern in 'unet_patterns' are required")

    with _REGISTRY_LOCK:
        user = load_user_registry()
        created = True
        new_user: list[RegistryEntry] = []
        for existing in user:
            if existing.id == entry.id:
                created = False  # replacing
            else:
                new_user.append(existing)
        new_user.append(entry)
        _save_user_registry(new_user)
    return entry, created


def delete_user_entry(entry_id: str) -> bool:
    """Delete a user registry entry by id.

    Returns True if deleted, False if no user entry had that id.
    Raises ``ValueError`` when the id belongs to a built-in entry that has
    no user override (built-in entries cannot be deleted directly).
    """
    with _REGISTRY_LOCK:
        user = load_user_registry()
        orig_len = len(user)
        new_user = [e for e in user if e.id != entry_id]
        if len(new_user) == orig_len:
            # Not in user registry — check if it's a builtin before returning 404.
            builtin = load_builtin_registry()
            if any(e.id == entry_id for e in builtin):
                raise ValueError(
                    f"Built-in entry '{entry_id}' cannot be deleted. "
                    "Create a user entry with the same id to override it instead."
                )
            return False
        _save_user_registry(new_user)
    return True


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def find_entry_for_model(unet_filename: str) -> RegistryEntry | None:
    """Find the first registry entry whose patterns match *unet_filename*.

    Matching is a case-insensitive substring check: any pattern in the entry's
    ``unet_patterns`` list must appear in the lowercased filename.
    User entries are checked before built-in entries.

    Entries are evaluated in declaration order; place more specific patterns
    (e.g. "wan2.2") before generic fallbacks (e.g. "wan") so the first match
    is always the most specific one.
    """
    name_lower = unet_filename.lower()
    for entry in get_merged_registry():
        for pattern in entry.unet_patterns:
            if pattern.lower() in name_lower:
                return entry
    return None

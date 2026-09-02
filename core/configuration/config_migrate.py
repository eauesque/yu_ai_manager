"""Migrate shadowed config.json data into the effective TOML config."""

from __future__ import annotations

import datetime
import json
import logging
import tomllib
from pathlib import Path
from typing import Any

from .json_rw import candidate_config_paths, effective_config_path, save_config_json

logger = logging.getLogger(__name__)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge dictionaries recursively; override wins for scalars and lists."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _without_none(value: Any) -> Any:
    """Drop null config values, matching settings saves' unset semantics."""
    if isinstance(value, dict):
        cleaned = {key: _without_none(item) for key, item in value.items() if item is not None}
        # Empty TOML tables carry no information, so match Rust by dropping them.
        return {key: item for key, item in cleaned.items() if not isinstance(item, dict) or item}
    if isinstance(value, list):
        return [_without_none(item) for item in value if item is not None]
    return value


def _primary_path(primary: str | Path | None) -> Path | None:
    requested = str(primary) if primary is not None else None
    resolved = effective_config_path(requested)
    if resolved:
        return Path(resolved).resolve()
    if requested:
        return Path(candidate_config_paths(requested)[0]).resolve()
    return None


def _display_path(path: Path | None) -> str | None:
    # API payloads use names for parity and avoid exposing local filesystem paths.
    return path.name if path else None


def _load_config_strict(path: Path) -> dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain an object")
    return data


def _migration_state(
    primary: str | Path | None = None,
) -> tuple[Path | None, Path | None, dict[str, Any], dict[str, Any], list[str], str | None]:
    primary_path = _primary_path(primary)
    if primary_path is None:
        return None, None, {}, {}, [], None
    legacy_path = primary_path.with_name("config.json")
    if primary_path.name != "config.toml" or not legacy_path.exists():
        return primary_path, None, {}, {}, [], None
    try:
        legacy = _load_config_strict(legacy_path)
        current = _load_config_strict(primary_path)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        logger.warning("Legacy migration parse failed for %s or %s: %s", primary_path, legacy_path, exc)
        return primary_path, legacy_path, {}, {}, [], f"legacy migration parse failed: {exc}"
    merged = _without_none(_deep_merge(legacy, current))
    keys = [key for key in merged if merged.get(key) != current.get(key)]
    return primary_path, legacy_path, legacy, current, keys, None


def legacy_migration_status(primary: str | Path | None = None) -> dict:
    """Report whether a shadowed config.json contains data absent from TOML."""
    primary_path, legacy_path, _legacy, _current, keys, error = _migration_state(primary)
    return {
        "pending": bool(keys),
        "primary": _display_path(primary_path) or "",
        "legacy": _display_path(legacy_path),
        "keys": keys,
        "error": error,
    }


def migrate_legacy_config(primary: str | Path | None = None, *, dry_run: bool = False) -> dict:
    """Merge a shadowed config.json into TOML and rename the legacy file."""
    primary_path, legacy_path, legacy, current, keys, error = _migration_state(primary)
    result = {
        "migrated": False,
        "merged_keys": keys,
        "backup": None,
        "primary": _display_path(primary_path) or "",
        "error": error,
    }
    if error or not keys or primary_path is None or legacy_path is None or dry_run:
        return result
    try:
        save_config_json(_without_none(_deep_merge(legacy, current)), str(primary_path))
    except Exception as exc:
        logger.warning("Legacy migration save failed for %s: %s", primary_path, exc)
        result["error"] = str(exc)
        return result
    backup_path = legacy_path.with_name(
        f"config.json.pre-toml-{datetime.datetime.now(datetime.UTC).astimezone():%Y%m%d%H%M%S}.bak"
    )
    try:
        legacy_path.rename(backup_path)
    except OSError as exc:
        logger.warning("Legacy migration backup rename failed for %s to %s: %s", legacy_path, backup_path, exc)
        result["error"] = f"legacy backup rename failed: {exc}"
        return result
    logger.info("Migrated legacy config from %s into %s; backup: %s", legacy_path, primary_path, backup_path)
    result.update(migrated=True, backup=_display_path(backup_path))
    return result

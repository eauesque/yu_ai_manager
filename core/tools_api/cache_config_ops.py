"""Cache/config helper payloads for tools routes."""

import json
import logging
import tomllib
from pathlib import Path
from typing import Any

from core.configuration.config_migrate import legacy_migration_status, migrate_legacy_config
from core.tools_api.ops import clear_cache, get_cache_info, get_merged_config, rebuild_groups, save_partial_config

logger = logging.getLogger(__name__)

_TOML_PATH = Path("config.toml")
_JSON_PATH = Path("config.json")
_TOML_DEFAULT = "compute_hash = false\nenable_fts   = true\nscan_roots   = []\n"


def _toml_scalar(v: object) -> str | None:
    """Serialize v to a TOML inline value, or None if it cannot be inlined."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        if not v:
            return "[]"
        if all(not isinstance(x, (dict, list)) for x in v):
            parts = [_toml_scalar(x) for x in v]
            if all(p is not None for p in parts):
                return "[" + ", ".join(parts) + "]"  # type: ignore[arg-type]
    return None


def _emit_section(d: dict, path: list[str], lines: list[str]) -> None:
    """Recursively emit TOML lines for dict d rooted at dotted path."""
    deferred_tables: list[tuple[str, dict]] = []
    deferred_aot: list[tuple[str, list]] = []  # array-of-tables

    for k, v in d.items():
        if isinstance(v, dict):
            deferred_tables.append((k, v))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            deferred_aot.append((k, v))
        else:
            iv = _toml_scalar(v)
            if iv is not None:
                lines.append(f"{k} = {iv}")

    for k, sub in deferred_tables:
        sub_path = path + [k]
        lines.append(f"\n[{'.'.join(sub_path)}]")
        _emit_section(sub, sub_path, lines)

    for k, items in deferred_aot:
        sub_path = path + [k]
        for entry in items:
            lines.append(f"\n[[{'.'.join(sub_path)}]]")
            _emit_section(entry, sub_path, lines)


def _json_dict_to_toml(d: dict) -> str:
    """Convert a config dict to TOML text (recursive; handles nested sections)."""
    lines: list[str] = []
    _emit_section(d, [], lines)
    return "\n".join(lines) + "\n"


def cache_info_payload() -> dict[str, Any]:
    """Return thumbnail cache status payload."""
    return get_cache_info()


def clear_cache_payload() -> dict[str, Any]:
    """Clear thumbnail cache payload."""
    return clear_cache()


def rebuild_groups_payload() -> dict[str, Any]:
    """Force rebuild groups index cache payload."""
    return rebuild_groups()


def get_config_payload() -> dict[str, Any]:
    """Return merged config payload."""
    return get_merged_config()


def save_config_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Save partial config payload."""
    return save_partial_config(data)


def legacy_migration_status_payload() -> dict:
    return legacy_migration_status()


def migrate_legacy_config_payload() -> dict:
    return migrate_legacy_config()


def get_toml_config_payload() -> tuple[str, int]:
    """Return raw config.toml text.

    If config.toml is absent but config.json exists, convert it to TOML so that
    saving the editor does not shadow the user's existing settings.
    """
    if _TOML_PATH.exists():
        return _TOML_PATH.read_text(encoding="utf-8"), 200
    if _JSON_PATH.exists():
        try:
            d = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return _json_dict_to_toml(d), 200
        except Exception:
            logger.warning("tools API step failed", exc_info=True)
    return _TOML_DEFAULT, 200


def save_toml_config_payload(raw: str) -> tuple[dict[str, Any], int]:
    """Validate and save raw TOML text to config.toml."""
    try:
        tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        return {"status": "error", "error": f"TOML parse error: {e}"}, 400
    _TOML_PATH.write_text(raw, encoding="utf-8")
    return {"status": "saved"}, 200

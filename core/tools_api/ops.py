"""Helper operations for tools routes."""

import contextlib
import copy
import shutil
import time as _time
from typing import Any

from core.configuration.api import DEFAULT_CONFIG, load_config_json, save_config_json
from core.services_core.db_write import submit_db_write
from core.services_core.tools_service import (
    clear_thumbnail_cache_entries,
    rebuild_groups_index_cache,
)

_ALLOWED_CONFIG_KEYS = frozenset({
    "timezone",
    "server",
    "extract_a1111",
    "extract_comfyui",
    "lowercase_tags",
    "compute_hash",
    "enable_fts",
    "remote_fs",
    "fast_mode_source",
})
_ALLOWED_SERVER_KEYS = frozenset({
    "host",
    "port",
    "lan",
    "pin",
    "pin_boss_login_ui",
    "allow_remote_restart",
    "restart_token",
})
_ALLOWED_REMOTE_FS_KEYS = frozenset({
    "probe_retries",
    "probe_wait",
    "enumerate_retries",
    "enumerate_wait",
})
_CONFIG_REDACTIONS = (
    ("api_keys", []),
    ("webhooks", []),
    ("webhook_secret", None),
    ("sns", None),
)


def _apply_redactions(config: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(config)
    for key, replacement in _CONFIG_REDACTIONS:
        if key in sanitized:
            sanitized[key] = replacement
    server = sanitized.get("server")
    if isinstance(server, dict):
        if "pin" in server:
            server["pin"] = None
        if "restart_token" in server:
            server["restart_token"] = None
        server["_pin_configured"] = bool(config.get("server", {}).get("pin"))
        server["_restart_token_configured"] = bool(
            config.get("server", {}).get("restart_token")
        )
    return sanitized


def _validate_partial_config(data: dict[str, Any]) -> str | None:
    unknown = set(data.keys()) - _ALLOWED_CONFIG_KEYS
    if unknown:
        return f"Unsupported config keys: {', '.join(sorted(unknown))}"

    server = data.get("server")
    if server is not None:
        if not isinstance(server, dict):
            return "server must be an object"
        unknown_server = set(server.keys()) - _ALLOWED_SERVER_KEYS
        if unknown_server:
            return f"Unsupported server keys: {', '.join(sorted(unknown_server))}"

    remote_fs = data.get("remote_fs")
    if remote_fs is not None:
        if not isinstance(remote_fs, dict):
            return "remote_fs must be an object"
        unknown_remote_fs = set(remote_fs.keys()) - _ALLOWED_REMOTE_FS_KEYS
        if unknown_remote_fs:
            return (
                "Unsupported remote_fs keys: "
                + ", ".join(sorted(unknown_remote_fs))
            )

    return None

_CACHE_INFO_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_INFO_TTL = 30.0  # seconds


def _invalidate_cache_info_cache() -> None:
    _CACHE_INFO_CACHE["data"] = None
    _CACHE_INFO_CACHE["ts"] = 0.0


def get_cache_info() -> dict[str, Any]:
    now = _time.time()
    cached = _CACHE_INFO_CACHE["data"]
    if cached is not None and now - _CACHE_INFO_CACHE["ts"] < _CACHE_INFO_TTL:
        return cached  # type: ignore[no-any-return]

    from core.paths import cache_path
    cache_dir = cache_path("thumbnails")
    if not cache_dir.exists():
        result: dict[str, Any] = {"count": 0, "size_mb": 0}
    else:
        count = 0
        total = 0
        for f in cache_dir.iterdir():
            if f.is_file() and f.suffix == ".jpg":
                count += 1
                total += f.stat().st_size
        result = {"count": count, "size_mb": round(total / (1024 * 1024), 1)}

    _CACHE_INFO_CACHE["data"] = result
    _CACHE_INFO_CACHE["ts"] = now
    return result


def clear_cache() -> dict[str, Any]:
    from core.paths import cache_path
    cache_dir = cache_path("thumbnails")
    cleared = 0
    if cache_dir.exists():
        cleared = sum(1 for f in cache_dir.iterdir() if f.is_file())
        shutil.rmtree(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
    _invalidate_cache_info_cache()
    with contextlib.suppress(Exception):
        submit_db_write(clear_thumbnail_cache_entries)
    return {"cleared": cleared}


def rebuild_groups() -> dict[str, Any]:
    """Force rebuild the groups index cache and return summary."""
    return rebuild_groups_index_cache()


def get_merged_config() -> dict[str, Any]:
    config = load_config_json()
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return _apply_redactions(merged)


def save_partial_config(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    if not data:
        return {"error": "No data", "code": "no_data"}, 400

    err = _validate_partial_config(data)
    if err:
        return {"error": err, "code": "invalid_config_keys"}, 400

    config = load_config_json()
    for key, val in data.items():
        if val is None:
            config.pop(key, None)
            continue
        if isinstance(val, dict) and isinstance(config.get(key), dict):
            if key == "server":
                for nested_key, nested_val in val.items():
                    # Blank UI fields must not erase existing secrets.
                    if nested_key in {"pin", "restart_token"} and (
                        nested_val is None or nested_val == ""
                    ):
                        continue
                    if nested_val is None:
                        config[key].pop(nested_key, None)
                        continue
                    config[key][nested_key] = nested_val
            else:
                config[key].update(val)
        else:
            config[key] = val

    save_config_json(config)
    return {"status": "saved"}, 200

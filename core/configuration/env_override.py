"""Override config values from TAGDB_* environment variables."""

import os
from typing import Any

# (ENV name, config key path, type hint)
_ENV_MAP: list[tuple[str, tuple[str, ...], str]] = [
    # server
    ("TAGDB_HOST",              ("server", "host"),              "str"),
    ("TAGDB_PORT",              ("server", "port"),              "int"),
    ("TAGDB_LAN",               ("server", "lan"),               "bool"),
    ("TAGDB_PIN",               ("server", "pin"),               "str"),
    ("TAGDB_PIN_BOSS_LOGIN_UI", ("server", "pin_boss_login_ui"), "bool"),
    # extraction / indexing
    ("TAGDB_EXTRACT_A1111",     ("extract_a1111",),              "bool"),
    ("TAGDB_EXTRACT_COMFYUI",   ("extract_comfyui",),            "bool"),
    ("TAGDB_LOWERCASE_TAGS",    ("lowercase_tags",),             "bool"),
    ("TAGDB_COMPUTE_HASH",      ("compute_hash",),               "bool"),
    ("TAGDB_ENABLE_FTS",        ("enable_fts",),                 "bool"),
    # media cache
    ("TAGDB_MEDIA_CACHE_MAX_ITEMS", ("media_cache", "l1_max_items"), "int"),
    ("TAGDB_MEDIA_CACHE_MAX_MB",    ("media_cache", "l1_max_mb"),    "int"),
    # remote filesystem
    ("TAGDB_REMOTE_FS_PROBE_RETRIES",     ("remote_fs", "probe_retries"),     "int"),
    ("TAGDB_REMOTE_FS_PROBE_WAIT",        ("remote_fs", "probe_wait"),        "float"),
    ("TAGDB_REMOTE_FS_ENUMERATE_RETRIES", ("remote_fs", "enumerate_retries"), "int"),
    ("TAGDB_REMOTE_FS_ENUMERATE_WAIT",    ("remote_fs", "enumerate_wait"),    "float"),
    # webhook
    ("TAGDB_WEBHOOK_SECRET",               ("webhook_secret",),                "str"),
]

_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "off"})


def _coerce(value: str, type_hint: str) -> Any:
    """Convert a string env value to the appropriate Python type."""
    if type_hint == "bool":
        low = value.strip().lower()
        if low in _BOOL_TRUE:
            return True
        if low in _BOOL_FALSE:
            return False
        raise ValueError(f"Cannot convert {value!r} to bool")
    if type_hint == "int":
        return int(value)
    if type_hint == "float":
        return float(value)
    return value


def apply_env_overrides(config: dict) -> dict:
    """Apply TAGDB_* environment variables to *config* (mutates in place, also returns it)."""
    for env_name, key_path, type_hint in _ENV_MAP:
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        coerced = _coerce(raw, type_hint)
        # Navigate to the parent dict, creating nested dicts as needed
        target = config
        for key in key_path[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[key_path[-1]] = coerced
    return config

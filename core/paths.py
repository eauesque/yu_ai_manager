"""Central writable-path resolver.

Call ``init_app_paths()`` exactly once at process startup (from ``web_ui.py``),
then use the getters / helpers to obtain paths for data, cache, logs, and
profiles. This module is the single source of truth so that Tauri-installed
builds can redirect writes to %APPDATA% while dev builds stay CWD-relative.

Resolution priority (first hit wins per directory):

    1. Explicit argument to ``init_app_paths()``
    2. Environment variable (``TAGDB_DATA_DIR`` / ``TAGDB_CACHE_DIR`` /
       ``TAGDB_LOG_DIR`` / ``TAGDB_PROFILES_DIR``)
    3. CWD-relative fallback (``./data``, ``./cache``, ``./logs``,
       ``./profiles``) — matches legacy dev layout

All returned paths are absolute and their directories are created on
``init_app_paths()``.
"""

from __future__ import annotations

import os
from pathlib import Path

_data_dir: Path | None = None
_cache_dir: Path | None = None
_log_dir: Path | None = None
_profiles_dir: Path | None = None
_initialized: bool = False


def init_app_paths(
    data_dir: Path | None = None,
    cache_dir: Path | None = None,
    log_dir: Path | None = None,
    profiles_dir: Path | None = None,
) -> None:
    """Resolve and freeze the four writable root directories.

    Idempotent: the first successful call wins; subsequent calls are ignored.
    Callers must invoke this exactly once at startup before any module that
    depends on the getters is imported in earnest.
    """
    global _data_dir, _cache_dir, _log_dir, _profiles_dir, _initialized
    if _initialized:
        return

    cwd = Path.cwd().resolve()

    def _resolve(arg: Path | None, env_var: str, default_name: str) -> Path:
        if arg is not None:
            return Path(arg).resolve()
        env_val = os.environ.get(env_var)
        if env_val:
            return Path(env_val).resolve()
        return (cwd / default_name).resolve()

    _data_dir = _resolve(data_dir, "TAGDB_DATA_DIR", "data")
    _cache_dir = _resolve(cache_dir, "TAGDB_CACHE_DIR", "cache")
    _log_dir = _resolve(log_dir, "TAGDB_LOG_DIR", "logs")
    _profiles_dir = _resolve(profiles_dir, "TAGDB_PROFILES_DIR", "profiles")

    for d in (_data_dir, _cache_dir, _log_dir, _profiles_dir):
        d.mkdir(parents=True, exist_ok=True)

    _initialized = True


def _require(value: Path | None, name: str) -> Path:
    if value is None:
        raise RuntimeError(
            f"{name} requested before init_app_paths() was called. "
            "core.paths.init_app_paths() must run first at startup."
        )
    return value


def get_data_dir() -> Path:
    return _require(_data_dir, "get_data_dir")


def get_cache_dir() -> Path:
    return _require(_cache_dir, "get_cache_dir")


def get_log_dir() -> Path:
    return _require(_log_dir, "get_log_dir")


def get_profiles_dir() -> Path:
    return _require(_profiles_dir, "get_profiles_dir")


def data_path(*parts: str) -> Path:
    """Return ``get_data_dir() / parts[0] / parts[1] / ...``."""
    return get_data_dir().joinpath(*parts)


def cache_path(*parts: str) -> Path:
    return get_cache_dir().joinpath(*parts)


def log_path(*parts: str) -> Path:
    return get_log_dir().joinpath(*parts)


def profiles_path(*parts: str) -> Path:
    return get_profiles_dir().joinpath(*parts)

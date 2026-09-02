"""Compatibility facade for web_ui startup helpers.

Internal code should prefer the split ``startup_*`` modules when practical.
This file remains to preserve older import paths.
"""

from core.web.startup_args import (
    apply_debug_env_from_args,
    build_webui_parser,
    resolve_config_path,
    resolve_server_bind_and_pin,
)
from core.web.startup_banner import print_startup_banner
from core.web.startup_build import maybe_install_deps, maybe_rebuild_ts
from core.web.startup_db import check_db_schema_and_print_rescan
from core.web.startup_mode import resolve_headless, resolve_server_mode
from core.web.startup_restart import apply_restart_config

__all__ = [
    "build_webui_parser",
    "apply_debug_env_from_args",
    "resolve_config_path",
    "resolve_server_bind_and_pin",
    "check_db_schema_and_print_rescan",
    "apply_restart_config",
    "maybe_install_deps",
    "maybe_rebuild_ts",
    "print_startup_banner",
    "resolve_server_mode",
    "resolve_headless",
]

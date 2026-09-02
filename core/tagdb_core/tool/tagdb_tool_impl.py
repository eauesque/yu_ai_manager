"""Legacy facade module for tagdb_tool compatibility."""

from .tagdb_tool_commands import (
    build_tag_filter_sql,
    cmd_add_root,
    cmd_cleanup,
    cmd_db_info,
    cmd_find_duplicates,
    cmd_init,
    cmd_list_roots,
    cmd_remove_root,
    cmd_scan,
    cmd_scan_all,
    cmd_search,
    load_config_json,
    load_or_default_config,
    save_config_json,
)
from .tagdb_tool_entry import build_parser, main

__all__ = [
    "cmd_scan",
    "cmd_cleanup",
    "cmd_find_duplicates",
    "build_tag_filter_sql",
    "cmd_search",
    "load_or_default_config",
    "load_config_json",
    "save_config_json",
    "cmd_scan_all",
    "cmd_add_root",
    "cmd_list_roots",
    "cmd_remove_root",
    "cmd_db_info",
    "cmd_init",
    "build_parser",
    "main",
]

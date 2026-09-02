"""CLI command compatibility layer.

Actual implementations live in `core.tagdb_core.tool.tagdb_tool_impl`.
"""

from core.tagdb_core.tool.tagdb_tool_impl import (
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
)

__all__ = [
    "cmd_scan",
    "cmd_scan_all",
    "cmd_add_root",
    "cmd_list_roots",
    "cmd_remove_root",
    "cmd_cleanup",
    "cmd_find_duplicates",
    "cmd_search",
    "cmd_db_info",
    "cmd_init",
]

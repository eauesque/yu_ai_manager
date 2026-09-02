"""Tools API package -- backward-compat re-export.

Route registration callables now live in ``core/tools_api/``. This package is
preserved as a thin re-export so external imports keep working.
"""

from core.tools_api import (
    register_tools_archive_cleanup_routes,
    register_tools_backup_routes,
    register_tools_log_routes,
    register_tools_misc_routes,
    register_tools_ops_routes,
)

__all__ = [
    "register_tools_ops_routes",
    "register_tools_misc_routes",
    "register_tools_backup_routes",
    "register_tools_log_routes",
    "register_tools_archive_cleanup_routes",
]

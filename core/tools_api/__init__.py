"""Tools API service layer.

Pure-sync ops: cache config, backups, archive cleanup, duplicates, file/folder
inspect, etc. Plus route registration callables (``routes_*.py``) that attach
handlers to the parent Blueprint owned by ``routes/tools.py``.
"""

from core.tools_api.routes_archive_cleanup import register_tools_archive_cleanup_routes
from core.tools_api.routes_backup import register_tools_backup_routes
from core.tools_api.routes_log import register_tools_log_routes
from core.tools_api.routes_misc import register_tools_misc_routes
from core.tools_api.routes_ops import register_tools_ops_routes

__all__ = [
    "register_tools_ops_routes",
    "register_tools_misc_routes",
    "register_tools_backup_routes",
    "register_tools_log_routes",
    "register_tools_archive_cleanup_routes",
]

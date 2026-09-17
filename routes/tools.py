"""Tools API blueprint assembly."""

from quart import Blueprint

from core.tools_api import (
    register_tools_archive_cleanup_routes,
    register_tools_backup_routes,
    register_tools_log_routes,
    register_tools_misc_routes,
    register_tools_ops_routes,
)

bp = Blueprint("tools", __name__)

register_tools_ops_routes(bp)
register_tools_misc_routes(bp)
register_tools_backup_routes(bp)
register_tools_log_routes(bp)
register_tools_archive_cleanup_routes(bp)

"""DB maintenance routes: stats, VACUUM, ANALYZE, scan-error-stats."""

from quart import Blueprint

from core.infra_core.api_errors import api_error, api_success
from core.services_core.db_async import run_db_sync
from core.services_core.db_write import run_db_write
from core.services_core.maintenance_service import (
    analyze_database,
    get_db_stats,
    get_scan_error_stats,
    vacuum_database,
)
from core.web.auth_restart import is_local_request

bp = Blueprint("maintenance", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/maintenance/db-stats")
async def api_db_stats():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    stats = await run_db_sync(get_db_stats)
    return api_success(stats)


@bp.route("/api/maintenance/scan-error-stats")
async def api_scan_error_stats():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    errors = await run_db_sync(get_scan_error_stats)
    return api_success({"errors": errors})


@bp.route("/api/maintenance/vacuum", methods=["POST"])
async def api_vacuum():
    if not is_local_request():
        return api_error("ローカルアクセスのみ許可されています", 403)
    return api_success(await run_db_write(vacuum_database))


@bp.route("/api/maintenance/analyze", methods=["POST"])
async def api_analyze():
    if not is_local_request():
        return api_error("ローカルアクセスのみ許可されています", 403)
    return api_success(await run_db_write(analyze_database))

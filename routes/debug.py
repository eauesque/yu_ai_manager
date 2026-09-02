"""Debug API -- metadata inspection, model check, scanned roots."""

import os

from quart import Blueprint, request

from core.debug_api import (
    file_meta_payload,
    model_check_payload,
    purge_db_root,
    readonly_query_payload,
    scanned_roots_payload,
)
from core.infra_core.api_errors import api_result
from core.services_core.db_async import run_db_sync

bp = Blueprint("debug", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/debug/file-meta/<int:file_id>")
async def api_debug_file_meta(file_id):
    """Inspect file metadata details (internal debug API -- no frontend UI)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await run_db_sync(file_meta_payload, file_id)
    return api_result(payload, status)


# ==========================================================
# Debug: model_name verification
# ==========================================================

@bp.route("/api/debug/model-check")
async def api_debug_model_check():
    """Check templates.model_name storage status (internal debug API -- no frontend UI)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(await run_db_sync(model_check_payload), 200)


@bp.route("/api/scanned-roots")
async def api_scanned_roots():
    """Extract root directories from files registered in the DB."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await run_db_sync(scanned_roots_payload)
    return api_result(payload, status)


@bp.route("/api/debug/enabled", methods=["GET"])
async def api_debug_enabled():
    """Report whether YU_DEBUG_MODE is enabled (no 403 noise on tools page probe)."""
    enabled = os.environ.get("YU_DEBUG_MODE", "0") == "1"
    return api_result({"enabled": enabled}, 200)


@bp.route("/api/debug/query", methods=["POST"])
async def api_debug_query():
    """Execute a readonly SQL query (requires YU_DEBUG_MODE=1)."""
    data = await request.get_json(silent=True) or {}
    sql = data.get("sql", "")
    limit = data.get("limit", 100)
    payload, status = await run_db_sync(readonly_query_payload, sql, limit)
    return api_result(payload, status)



@bp.route("/api/scanned-roots/purge", methods=["POST"])
async def api_scanned_roots_purge():
    """Permanently delete file records under the specified path from the DB."""
    data = await request.get_json(silent=True) or {}
    path = data.get("path", "")
    payload, status = await run_db_sync(purge_db_root, path)
    return api_result(payload, status)

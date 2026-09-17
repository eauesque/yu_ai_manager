"""Archive file API -- file info, open folder, ZIP/archive extraction."""

import contextlib
import logging

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_params import clamp_sqlite_int
from core.infra_core.api_request import require_json_dict
from core.infra_core.debug_log import dlog
from core.services_core.db_async import run_db_sync
from core.zip_api import (
    extract_from_zip,
    get_container_members_payload,
    get_file_info_payload,
    open_folder_for_file,
)

logger = logging.getLogger(__name__)
bp = Blueprint("zip_files", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

# ===== ZIP File APIs =====

@bp.route("/api/file-info/<int:file_id>")
async def api_file_info(file_id):
    """File detail info (including ZIP-related info)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        payload, status = await run_db_sync(get_file_info_payload, file_id)
        return api_result(payload, status)
    except Exception:
        logger.exception("file-info error for file_id=%d", file_id)
        return api_error("Failed to get file info", 500, code="file_info_error")


@bp.route("/api/open-folder/<int:file_id>", methods=["POST"])
async def api_open_folder(file_id):
    """Open file location in Explorer/Finder."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        payload, status = await run_db_sync(open_folder_for_file, file_id)
        return api_result(payload, status)
    except Exception:
        logger.exception("open-folder error for file_id=%d", file_id)
        return api_error("Failed to open folder", 500, code="open_folder_error")


@bp.route("/api/extract-from-zip", methods=["POST"])
async def api_extract_from_zip():
    """Extract file from archive."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        file_id = data.get("file_id")
        if file_id is not None:
            with contextlib.suppress(TypeError, ValueError):
                file_id = clamp_sqlite_int(int(file_id))
        remote_addr = request.remote_addr
        payload, status = await run_db_sync(extract_from_zip, file_id, remote_addr)
        return api_result(payload, status)
    except Exception as e:
        dlog("zip", "extract.error", exc_type=type(e).__name__, detail=str(e))
        logger.exception("extract-from-zip error")
        return api_error(
            "ZIP extraction failed",
            500,
            code="zip_extract_error",
        )


@bp.route("/api/container-members/<int:file_id>")
async def api_container_members(file_id):
    """Return list of members in a ZIP container."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        payload, status = await run_db_sync(get_container_members_payload, file_id)
        return api_result(payload, status)
    except Exception:
        logger.exception("container-members error for file_id=%d", file_id)
        return api_error("Failed to get container members", 500, code="container_members_error")


# ===== End ZIP APIs =====

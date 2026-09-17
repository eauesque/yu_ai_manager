"""Share API -- QR code sharing and export."""

import logging

from quart import Blueprint, render_template

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.share_ops import build_share_data_payload

logger = logging.getLogger(__name__)
bp = Blueprint("share", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/share/<int:file_id>")
async def api_share_data(file_id):
    """Generate prompt data for QR code sharing."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        payload, status = await run_db_sync(build_share_data_payload, file_id)
        return api_result(payload, status)
    except Exception:
        logger.exception("share data error for file_id=%d", file_id)
        return api_error("Failed to build share data", 500)


@bp.route("/share")
async def share_view():
    """Display page for shared data after QR code scan."""
    return await render_template("share.html")

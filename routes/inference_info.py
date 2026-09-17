"""Inference system info API.

Returns GPU info and ORT provider status.
"""

import logging

from quart import Blueprint

from core.infra_core.api_errors import api_result
from core.infra_core.blocking_tasks import run_blocking_sync

bp = Blueprint("inference_info", __name__)
logger = logging.getLogger(__name__)

# Backward-compatible patch point for existing route tests. Despite the legacy
# name, this now uses the non-DB blocking executor.
run_db_sync = run_blocking_sync


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/system/inference-info")
async def api_inference_info():
    """Return GPU info and ORT provider status."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        from importlib import import_module
        _ort_mod = import_module("extensions.builtin_inference.core_impl.ort_provider")
        get_provider_info = _ort_mod.get_provider_info

        info = await run_db_sync(get_provider_info)
        return api_result(info, 200)
    except Exception:
        logger.exception("Failed to fetch inference provider info")
        return api_result({"error": "Inference provider unavailable", "available": False}, 200)

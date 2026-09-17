"""Stream transcription API endpoints facade."""

import logging

from quart import jsonify, request

from core.web.apikey_auth.key_scopes import key_has_scope

from .s2t_stream_control_routes import register_stream_control_routes
from .s2t_stream_export_routes import register_stream_export_routes
from .s2t_stream_llm_routes import register_stream_llm_routes
from .s2t_stream_media_routes import register_stream_media_routes

logger = logging.getLogger(__name__)


def _require_admin_scope():
    key_info = getattr(request, "api_key_info", None)
    if key_info and not key_has_scope(key_info, "admin"):
        return jsonify(
            {
                "status": "error",
                "message": "Insufficient scope: requires 'admin'",
            }
        ), 403
    return None


def register_stream_routes(bp) -> None:
    """Register stream transcription endpoints on the blueprint."""

    register_stream_control_routes(bp, _require_admin_scope, logger)
    register_stream_media_routes(bp, logger)
    register_stream_export_routes(bp, _require_admin_scope)
    register_stream_llm_routes(bp)

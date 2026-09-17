"""Model management routes for Hailo semantic search."""

import logging

from quart import jsonify

logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_model_routes(bp):
    @bp.route("/api/model/status")
    async def api_model_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            from core.clip_onnx_core.model_download import get_model_status
            return jsonify(get_model_status())
        except ImportError:
            return jsonify({"ready": False, "message": "clip_onnx_core not available"})

    @bp.route("/api/model/download", methods=["POST"])
    async def api_model_download():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            from core.clip_onnx_core.model_download import download_model, is_model_downloaded
            if is_model_downloaded():
                return jsonify({"status": "already_downloaded"})
            download_model()
            return jsonify({"status": "ok"})
        except ImportError:
            return jsonify({"status": "error", "message": "clip_onnx_core not available"}), 503
        except RuntimeError as exc:
            logger.warning("Semantic search model download failed: %s", exc)
            return jsonify({"status": "error", "message": "Model download failed"}), 500

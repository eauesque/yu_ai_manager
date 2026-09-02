import asyncio
import logging
import os
import threading

from core.extensions_core.extensions_admin import get_extension_config_value, save_extension_config_values
from quart import jsonify, request

from core.helpers_core.helpers_text_path import sanitize_user_path
from core.jobs_core.jobs import job_manager
from core.services_core.db_state import get_config

from . import scanner

logger = logging.getLogger(__name__)
_MD_SCAN_JOB_ID = "md_scan"
_EXT_NAME = "builtin-md-viewer"


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_scan_routes(bp):
    @bp.route("/api/scan", methods=["POST"])
    async def api_scan():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        if job_manager.is_running(_MD_SCAN_JOB_ID):
            return jsonify({"error": "scan already running"}), 409
        scan_roots = get_md_scan_roots()
        if not scan_roots:
            return jsonify({"error": "scan_roots not configured"}), 400
        job = job_manager.start(_MD_SCAN_JOB_ID, "MD file scan")

        def _run():
            try:
                scanner.scan_md_files(scan_roots, job=job)
            except Exception as exc:
                logger.error("MD scan failed: %s", exc)
                job.fail(str(exc))

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"status": "started", "job_id": _MD_SCAN_JOB_ID})

    @bp.route("/api/scan/status")
    async def api_scan_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        status = job_manager.get_job(_MD_SCAN_JOB_ID)
        if not status:
            return jsonify({"running": False, "phase": "idle", "current": 0, "total": 0, "percent": 0, "message": "", "error": None})
        return jsonify(status)

    @bp.route("/api/scan-roots")
    async def api_scan_roots():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        roots = get_md_scan_roots()
        is_custom = get_extension_config_value(_EXT_NAME, "md_scan_roots", None) is not None
        # `roots` are operator-configured and may be network paths; a dead
        # mount would block the event loop for the mount timeout.
        entries = await asyncio.to_thread(
            lambda: [{"path": r, "exists": os.path.isdir(r)} for r in roots]
        )
        return jsonify({"roots": entries, "is_custom": is_custom})

    @bp.route("/api/scan-roots", methods=["POST"])
    async def api_save_scan_roots():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        raw_roots = data.get("roots")
        if not isinstance(raw_roots, list):
            return jsonify({"error": "roots must be an array"}), 400
        seen = set()
        clean = []
        for root in raw_roots:
            if not isinstance(root, str):
                continue
            path = sanitize_user_path(root)
            if not path:
                continue
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            clean.append(path)
        save_extension_config_values(_EXT_NAME, {"md_scan_roots": clean})
        return jsonify({"ok": True, "roots": clean})

    @bp.route("/api/scan-roots/<int:index>", methods=["DELETE"])
    async def api_delete_scan_root(index: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        roots = list(get_md_scan_roots())
        if index < 0 or index >= len(roots):
            return jsonify({"error": "index out of range"}), 400
        removed = roots.pop(index)
        save_extension_config_values(_EXT_NAME, {"md_scan_roots": roots})
        return jsonify({"ok": True, "removed": removed, "roots": roots})


def get_md_scan_roots() -> list[str]:
    roots = get_extension_config_value(_EXT_NAME, "md_scan_roots", None)
    if roots is not None:
        return roots
    try:
        raw = get_config().get("scan_roots", [])
        normalized = []
        for item in raw:
            if isinstance(item, str):
                normalized.append(item)
            elif isinstance(item, dict) and item.get("enabled", True):
                path = item.get("path", "")
                if path:
                    normalized.append(path)
        if normalized:
            return normalized
    except Exception:
        logger.warning("scan roots could not be read from config", exc_info=True)
    docs_dir = os.path.join(os.getcwd(), "docs")
    return [docs_dir] if os.path.isdir(docs_dir) else []

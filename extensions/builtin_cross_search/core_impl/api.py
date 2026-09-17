"""Cross Search API Blueprint.

Worker process management is in api_worker.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)
from quart import Blueprint, jsonify, render_template, request

from core.services_core.db_state import get_readonly_db

# Re-export for backward compatibility
from .api_worker import (  # noqa: F401
    worker_cmd as _worker_cmd,
)

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-cross-search"
_JOB_ID = "cross_search_scan"


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def create_cross_search_blueprint(import_name: str) -> Blueprint:
    bp = Blueprint(
        "cross_search",
        import_name,
        template_folder=str(
            Path(__file__).resolve().parent.parent / "templates"
        ),
    )

    # -- UI page --
    @bp.route("/")
    async def index():
        return await render_template("cross_search/cross_search.html")

    # -- Cross search API --
    @bp.route("/api/search")
    async def api_search():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"error": "query is required"}), 400
        targets = request.args.get("target", "md,chat,prompt,txt")
        limit = _int_param("limit", 50, 1, 200)

        con = get_readonly_db()
        from .search import search_all
        results = search_all(con, q, targets=targets, limit=limit)
        return jsonify({"results": results, "query": q, "total": len(results)})

    # -- Document scan API (worker process method) --
    @bp.route("/api/scan", methods=["POST"])
    async def api_scan():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        roots = _get_scan_roots()
        if not roots:
            return jsonify({"error": "Scan directory not configured. Please add a directory first."}), 400

        from .worker_ipc import is_worker_running as ipc_running
        if ipc_running():
            return jsonify({"error": "scan already running"}), 409

        from core.jobs_core.jobs import job_manager
        if job_manager.is_running(_JOB_ID):
            return jsonify({"error": "scan already running"}), 409

        from .api_worker import start_worker_and_bridge
        start_worker_and_bridge(roots)
        return jsonify({"job_id": _JOB_ID, "message": "Document scan started"})

    @bp.route("/api/scan/stop", methods=["POST"])
    async def api_scan_stop():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .worker_ipc import is_worker_running as ipc_running
        from .worker_ipc import signal_stop
        if not ipc_running():
            return jsonify({"error": "scan is not running"}), 400
        if signal_stop():
            return jsonify({"ok": True, "message": "Stop signal sent"})
        return jsonify({"error": "Failed to send stop signal"}), 500

    @bp.route("/api/scan/status")
    async def api_scan_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.jobs_core.jobs import job_manager

        from .worker_ipc import (
            get_worker_memory_rss,
            read_pid,
            read_progress,
        )
        from .worker_ipc import (
            is_worker_running as ipc_running,
        )

        # Read directly from worker process (latest info)
        progress = read_progress()
        if progress and (progress.get("running", False) or ipc_running()):
            pid = read_pid()
            memory_rss = get_worker_memory_rss(pid) if pid else None
            return jsonify({
                "running": progress.get("running", True),
                "phase": progress.get("phase", ""),
                "message": progress.get("message", ""),
                "current": progress.get("current", 0),
                "total": progress.get("total", 0),
                "percent": progress.get("percent", 0),
                "detail": progress.get("detail", ""),
                "elapsed_seconds": progress.get("elapsed_seconds", 0),
                "worker_pid": pid,
                "memory_rss": memory_rss,
            })

        # Fallback to JobManager when worker not running (for just-completed status)
        raw = job_manager.get_raw_job(_JOB_ID)
        if raw and raw.running:
            return jsonify({
                "running": True,
                "phase": raw.phase,
                "message": raw.message,
                "current": raw.current,
                "total": raw.total,
            })

        # Final progress (after completion)
        if progress and not progress.get("running", True):
            return jsonify({
                "running": False,
                "phase": progress.get("phase", ""),
                "message": progress.get("message", ""),
                "current": progress.get("current", 0),
                "total": progress.get("total", 0),
                "elapsed_seconds": progress.get("elapsed_seconds", 0),
            })

        return jsonify({"running": False})

    # -- File detail API --
    @bp.route("/api/txt/<int:file_id>")
    async def api_txt_detail(file_id: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        con = get_readonly_db()
        from .store import ensure_tables, get_text_file
        ensure_tables()
        f = get_text_file(con, file_id)
        if not f:
            return jsonify({"error": "not found"}), 404
        return jsonify(f)

    # -- Open file in system API --
    @bp.route("/api/open-file", methods=["POST"])
    async def api_open_file():
        data = await request.get_json(silent=True) or {}
        path = data.get("path", "")
        if not path:
            return jsonify({"error": "path is required"}), 400

        # Prevent path traversal: only allow files under scan_roots
        real_path = os.path.realpath(path)
        allowed_roots = _get_scan_roots()
        if not allowed_roots or not any(
            real_path.startswith(os.path.realpath(r) + os.sep)
            or real_path == os.path.realpath(r)
            for r in allowed_roots
        ):
            return jsonify({"error": "path is not within allowed scan roots"}), 403

        if not os.path.exists(real_path):
            return jsonify({"error": "file not found"}), 404

        try:
            from core.platform.file_manager import open_in_file_manager
            open_in_file_manager(real_path)
            return jsonify({"success": True})
        except Exception:
            logger.exception("Failed to open file in system file manager")
            return jsonify({"error": "Failed to open file"}), 500

    # -- Scan root management --
    @bp.route("/api/scan-roots")
    async def api_scan_roots():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        custom = get_extension_config_value(_EXT_NAME, "txt_scan_roots", None)
        is_custom = custom is not None and len(custom) > 0
        roots = _get_scan_roots()
        # `roots` are operator-configured and may be network paths; a dead
        # mount would block the event loop for the mount timeout.
        result = await asyncio.to_thread(
            lambda: [{"path": r, "exists": os.path.isdir(r)} for r in roots]
        )
        return jsonify({"roots": result, "is_custom": is_custom})

    @bp.route("/api/scan-roots", methods=["POST"])
    async def api_save_scan_roots():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        roots = data.get("roots", [])
        if not isinstance(roots, list):
            return jsonify({"error": "roots must be a list"}), 400
        # Path normalization and deduplication
        seen = set()
        clean = []
        for r in roots:
            r = str(r).strip()
            if not r:
                continue
            norm = os.path.normpath(r)
            if norm not in seen:
                seen.add(norm)
                clean.append(norm)
        save_extension_config_values(_EXT_NAME, {"txt_scan_roots": clean})
        return jsonify({"ok": True})

    @bp.route("/api/scan-roots/<int:idx>", methods=["DELETE"])
    async def api_delete_scan_root(idx: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        custom = get_extension_config_value(_EXT_NAME, "txt_scan_roots", None)
        if custom is None:
            # Copy from global and switch to independent settings
            custom = _get_scan_roots()
        if idx < 0 or idx >= len(custom):
            return jsonify({"error": "index out of range"}), 400
        custom.pop(idx)
        save_extension_config_values(_EXT_NAME, {"txt_scan_roots": custom})
        return jsonify({"ok": True})

    # -- Statistics --
    @bp.route("/api/stats")
    async def api_stats():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .store import count_text_files, ensure_tables
        ensure_tables()  # Create tables with write connection
        con = get_readonly_db()
        return jsonify({"txt_count": count_text_files(con)})

    return bp


# -- Helpers --

def _get_scan_roots():
    """Get scan roots. Extension config -> global scan_roots fallback."""
    roots = get_extension_config_value(_EXT_NAME, "txt_scan_roots", None)
    if roots:
        return list(roots)
    try:
        from core.services_core.db_state import get_config
        config = get_config()
        scan_roots = config.get("scan_roots", [])
        normalized = []
        for item in scan_roots:
            if isinstance(item, str):
                normalized.append(item)
            elif isinstance(item, dict) and item.get("enabled", True):
                path = item.get("path", "")
                if path:
                    normalized.append(path)
        return normalized
    except Exception:
        return []


def _int_param(name: str, default: int, min_val: int, max_val: int) -> int:
    try:
        v = int(request.args.get(name, default))
        return max(min_val, min(max_val, v))
    except (ValueError, TypeError):
        return default

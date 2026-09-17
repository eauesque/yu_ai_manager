"""builtin-auto-scan-watcher Extension entrypoint."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
_ext_dir = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_ext_dir) not in sys.path:
    sys.path.insert(0, str(_ext_dir))

from quart import Blueprint, jsonify, render_template, request
from watcher_core import ScanWatcher  # noqa: E402

logger = logging.getLogger(__name__)

# Module-level singleton
_watcher = ScanWatcher()
_scan_archives: bool = True


def _on_scan_roots_changed(_event) -> None:
    """Restart watcher when scan_roots config changes."""
    if not _watcher.running:
        return
    try:
        roots, db_path, config = _get_roots_and_paths()
        enabled = [r for r in roots if r.get("enabled", True)]
        if enabled and db_path:
            _watcher.restart(enabled, _get_scan_exts(_scan_archives), db_path, config)
        else:
            _watcher.stop()
    except Exception:
        logger.warning("Watcher restart on config change failed", exc_info=True)


_ARCHIVE_EXTS = {".zip", ".7z"}


def _get_scan_exts(include_archives: bool = True) -> set:
    from core.scan.runtime_prepare import SCAN_EXTS
    exts = set(SCAN_EXTS)
    if include_archives:
        exts.update(_ARCHIVE_EXTS)
    return exts


def _get_roots_and_paths() -> tuple:
    """Return (scan_roots list, db_path, config dict).

    scan_roots is re-read from disk: CRUD ops (Python and the Rust
    yu-server front-end alike) write config.json directly without ever
    refreshing the process-wide CONFIG snapshot from get_config(), so
    reading scan_roots from it here would restart the watcher with a
    stale root list on every add/remove/toggle.
    """
    from core.configuration.api import load_config_json
    from core.services_core.db_state import get_config, get_db_path
    config = get_config()
    roots = load_config_json(None).get("scan_roots", [])
    db_path = get_db_path()
    return roots, db_path, config


def get_blueprint() -> Blueprint:
    bp = Blueprint(
        "ext_auto_scan_watcher",
        __name__,
        template_folder="templates",
    )

    @bp.record_once
    def _on_register(state):
        """Auto-start watcher if configured."""
        global _scan_archives
        app = state.app
        ext_cfg = app.config.get("EXTENSIONS", {}).get("builtin-auto-scan-watcher", {})
        auto_start = ext_cfg.get("auto_start", True)
        debounce = ext_cfg.get("debounce_seconds", 3.0)
        _scan_archives = ext_cfg.get("scan_archives", True)

        if debounce != 3.0:
            _watcher._debounce = debounce

        if auto_start:
            try:
                roots, db_path, config = _get_roots_and_paths()
                if roots and db_path:
                    _watcher.start(roots, _get_scan_exts(_scan_archives), db_path, config)
            except Exception:
                logger.warning("Watcher auto-start failed", exc_info=True)

        from core.event_bus import event_bus
        from core.event_bus.event_types import SCAN_ROOTS_CHANGED
        event_bus.subscribe(SCAN_ROOTS_CHANGED, _on_scan_roots_changed)

    @bp.route("/")
    async def watcher_ui():
        return await render_template("watcher_status.html")

    @bp.route("/info")
    async def watcher_info():
        return jsonify({
            "running": _watcher.running,
            "watched_roots": _watcher.watched_roots,
            "stats": _watcher.stats,
        })

    @bp.route("/start", methods=["POST"])
    async def watcher_start():
        if _watcher.running:
            return jsonify({"ok": False, "error": "Already running"}), 409
        try:
            data = await request.get_json(silent=True) or {}
            debounce = data.get("debounce_seconds", _watcher._debounce)
            _watcher._debounce = debounce

            roots, db_path, config = _get_roots_and_paths()
            if not roots:
                return jsonify({"ok": False, "error": "No scan_roots configured"}), 400
            _watcher.start(roots, _get_scan_exts(_scan_archives), db_path, config)
            return jsonify({"ok": True, "watched_roots": _watcher.watched_roots})
        except Exception:
            logger.exception("Watcher start failed")
            return jsonify({"ok": False, "error": "Watcher start failed"}), 500

    @bp.route("/stop", methods=["POST"])
    async def watcher_stop():
        if not _watcher.running:
            return jsonify({"ok": False, "error": "Not running"}), 409
        _watcher.stop()
        return jsonify({"ok": True})

    return bp


__all__ = ["get_blueprint"]

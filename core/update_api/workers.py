"""Update runtime background worker launch helpers."""

from __future__ import annotations

import logging
import sys
import threading
import time

from core.update_api.state import mark_update_finished
from core.web.auth_core import restart_state

logger = logging.getLogger(__name__)


def trigger_restart(app) -> None:
    """Restart the current process after a short delay."""
    time.sleep(1.0)
    restart_state["in_progress"] = True
    restart_state["last_requested_at"] = time.time()
    exec_args = app.config.get("RESTART_EXEC_ARGS") or [
        sys.executable, *sys.argv
    ]
    from core.platform import exec_restart
    exec_restart(exec_args)


def start_single_update_worker(app, install_type: str) -> None:
    """Run single-system update in a background thread."""

    def _update_worker():
        try:
            from core.event_bus import emit

            def emit_progress(step: str, status: str, detail: str = ""):
                emit("update.progress", {
                    "step": step,
                    "status": status,
                    "detail": detail,
                })

            if install_type == "portable":
                from core.update_core.portable_updater import run_portable_update
                result = run_portable_update(emit_progress)
            else:
                from core.update_core.git_updater import run_git_update
                result = run_git_update(emit_progress)

            if result["success"]:
                emit("update.complete", {
                    "success": True,
                    "steps": result["steps_completed"],
                })
                if result.get("restart_required"):
                    trigger_restart(app)
            else:
                emit("update.complete", {
                    "success": False,
                    "error": result.get("error", "unknown error"),
                    "steps": result["steps_completed"],
                })
        except Exception as exc:
            logger.exception("Update worker failed")
            try:
                from core.event_bus import emit
                emit("update.complete", {
                    "success": False,
                    "error": str(exc),
                })
            except Exception:
                logger.warning("step failed", exc_info=True)
        finally:
            mark_update_finished()

    threading.Thread(target=_update_worker, daemon=True).start()


def start_unified_update_worker(
    app,
    *,
    update_system: bool,
    update_extensions: bool,
    extension_names,
) -> None:
    """Run unified update in a background thread."""

    def _unified_worker():
        try:
            from core.event_bus import emit
            from core.update_core.unified_manager import apply_unified_updates

            def emit_progress(step: str, status: str, detail: str = ""):
                emit("update.progress", {
                    "step": step,
                    "status": status,
                    "detail": detail,
                    "unified": True,
                })

            result = apply_unified_updates(
                emit_progress,
                update_system=update_system,
                update_extensions=update_extensions,
                extension_names=extension_names,
            )

            emit("update.complete", {
                "success": result["success"],
                "unified": True,
                "extension_results": result["extension_results"],
            })

            if result.get("restart_required"):
                trigger_restart(app)
        except Exception as exc:
            logger.exception("Unified update worker failed")
            try:
                from core.event_bus import emit
                emit("update.complete", {
                    "success": False,
                    "error": str(exc),
                    "unified": True,
                })
            except Exception:
                logger.warning("step failed", exc_info=True)
        finally:
            mark_update_finished()

    threading.Thread(target=_unified_worker, daemon=True).start()

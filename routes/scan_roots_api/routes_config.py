"""Route registrations for checkpoints and scan-roots config APIs."""


from quart import request

from core.infra_core.api_errors import api_result
from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_local as _require_local
from routes.scan_roots_api.routes_config_handlers import (
    handle_add_scan_root,
    handle_batch_toggle_scan_roots,
    handle_checkpoints,
    handle_edit_scan_root,
    handle_get_scan_roots,
    handle_recovery_apply,
    handle_recovery_check,
    handle_recovery_dismiss,
    handle_remove_scan_root,
    handle_reorder_scan_roots,
    handle_toggle_scan_root,
)


def register_scan_roots_config_routes(bp) -> None:
    @bp.route("/api/checkpoints")
    def api_checkpoints():
        """List available checkpoints (models)."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = handle_checkpoints()
        return api_result(payload, status)

    @bp.route("/api/scan-roots", methods=["GET"])
    def api_get_scan_roots():
        """Get list of registered scan roots."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = handle_get_scan_roots()
        return api_result(payload, status)

    @bp.route("/api/scan-roots", methods=["POST"])
    async def api_add_scan_root():
        """Add a scan root."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = await handle_add_scan_root()
        return api_result(payload, status)

    @bp.route("/api/scan-roots/<int:index>", methods=["DELETE"])
    def api_remove_scan_root(index):
        """Remove a scan root."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = handle_remove_scan_root(index)
        return api_result(payload, status)

    @bp.route("/api/scan-roots/<int:index>/toggle", methods=["POST"])
    def api_toggle_scan_root(index):
        """Toggle scan root enabled/disabled."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = handle_toggle_scan_root(index)
        return api_result(payload, status)

    @bp.route("/api/scan-roots/batch-toggle", methods=["POST"])
    async def api_batch_toggle_scan_roots():
        """Enable or disable all scan roots at once."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = await handle_batch_toggle_scan_roots()
        return api_result(payload, status)

    @bp.route("/api/scan-roots/reorder", methods=["POST"])
    async def api_reorder_scan_roots():
        """Reorder scan roots."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = await handle_reorder_scan_roots()
        return api_result(payload, status)

    @bp.route("/api/scan-roots/<int:index>", methods=["PUT"])
    async def api_edit_scan_root(index):
        """Edit scan root path."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = await handle_edit_scan_root(index)
        return api_result(payload, status)

    @bp.route("/_internal/scan-roots-changed", methods=["POST"])
    async def _internal_scan_roots_changed():
        """Internal notify endpoint called by Rust after scan_roots mutations."""
        err = _require_local("scan-roots-changed notify")
        if err:
            return err
        from core.event_bus import emit
        from core.event_bus.event_types import SCAN_ROOTS_CHANGED

        data = await request.get_json(silent=True) or {}
        emit(SCAN_ROOTS_CHANGED, data)
        return api_result({"ok": True}, 200)

    @bp.route("/api/scan-roots/recovery-check")
    def api_scan_roots_recovery_check():
        """Is a one-time scan_roots recovery banner still warranted?"""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = handle_recovery_check()
        return api_result(payload, status)

    @bp.route("/api/scan-roots/recovery-apply", methods=["POST"])
    async def api_scan_roots_recovery_apply():
        """Register the recovery banner's chosen candidates as scan roots."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = await handle_recovery_apply()
        return api_result(payload, status)

    @bp.route("/api/scan-roots/recovery-dismiss", methods=["POST"])
    def api_scan_roots_recovery_dismiss():
        """Dismiss the one-time scan_roots recovery banner without applying it."""
        auth_err = _require_admin_scope()
        if auth_err:
            return api_result(*auth_err)
        payload, status = handle_recovery_dismiss()
        return api_result(payload, status)

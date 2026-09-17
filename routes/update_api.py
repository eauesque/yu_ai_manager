"""Self-update API endpoints: check, status, apply."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from quart import Blueprint, current_app, request, session

from core.infra_core.api_errors import api_error, api_success
from core.services_core.db_async import run_db_sync
from core.update_api import (
    accepted_update_response,
    begin_update_request,
    check_update_auth,
    get_update_state_snapshot,
    get_version_string,
    start_single_update_worker,
    start_unified_update_worker,
)

logger = logging.getLogger(__name__)

bp = Blueprint("update_api", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/system/update/check", methods=["GET"])
async def api_update_check():
    """Check for available updates from GitHub releases."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.update_core.version_check import check_for_update

    # Outer bound: the fetch carries its own socket timeout, but that does not
    # cover `getaddrinfo`, so a host with an unreachable resolver stalls past
    # any caller. "We could not check" is a fine answer for an update poll.
    try:
        result = await asyncio.wait_for(run_db_sync(check_for_update), timeout=6.0)
    except TimeoutError:
        result = {"error": "update check timed out", "update_available": False}
    return api_success(result)


@bp.route("/api/system/update/status", methods=["GET"])
async def api_update_status():
    """Return current install type, update state, and version."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.update_core.detect import detect_install_type

    state = get_update_state_snapshot()

    return api_success({
        "install_type": detect_install_type(),
        "update_in_progress": state["in_progress"],
        "version": get_version_string(),
    })


@bp.route("/api/system/update/apply", methods=["POST"])
async def api_update_apply():
    """Apply an update (git or portable installs)."""
    from core.update_core.detect import detect_install_type

    app = current_app._get_current_object()

    auth_err = check_update_auth(app, bool(session.get("pin_ok")))
    if auth_err:
        return auth_err

    # Only git and portable installs can self-update
    install_type = detect_install_type()
    if install_type not in ("git", "portable"):
        return api_error(
            f"自動更新は git / portable インストールのみ対応しています (現在: {install_type})",
            400,
            code="unsupported_install_type",
        )

    begin_err = begin_update_request()
    if begin_err:
        return begin_err

    start_single_update_worker(app, install_type)

    return accepted_update_response(
        message="更新を開始しました。進捗は SSE イベント (update.progress) で通知されます。",
        code="update_accepted",
    )


# ------------------------------------------------------------------
# Unified update manager: system + extensions
# ------------------------------------------------------------------


@bp.route("/api/system/update/unified-check", methods=["GET"])
async def api_unified_check():
    """Check update status for system and all extensions at once."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.update_core.unified_manager import check_unified_updates

    force = request.args.get("force", "").lower() in ("1", "true", "yes")
    # Same outer bound as /update/check: this fans out to the same network.
    try:
        result = await asyncio.wait_for(
            run_db_sync(lambda: check_unified_updates(force=force)), timeout=6.0
        )
    except TimeoutError:
        result = {
            "error": "update check timed out",
            "system": {"update_available": False},
            "extensions": [],
        }
    return api_success(result)


@bp.route("/api/system/update/unified-apply", methods=["POST"])
async def api_unified_apply():
    """Apply updates for system and/or extensions."""
    from core.update_core.detect import detect_install_type

    app = current_app._get_current_object()

    auth_err = check_update_auth(app, bool(session.get("pin_ok")))
    if auth_err:
        return auth_err

    # Parse request body
    data = {}
    with contextlib.suppress(Exception):
        data = await request.get_json(force=True) or {}

    update_system = data.get("update_system", True)
    update_extensions = data.get("update_extensions", True)
    extension_names = data.get("extension_names", None)

    # Validate system update capability
    if update_system:
        install_type = detect_install_type()
        if install_type not in ("git", "portable"):
            update_system = False

    if not update_system and not update_extensions:
        return api_error(
            "更新対象がありません",
            400,
            code="nothing_to_update",
        )

    begin_err = begin_update_request()
    if begin_err:
        return begin_err

    start_unified_update_worker(
        app,
        update_system=update_system,
        update_extensions=update_extensions,
        extension_names=extension_names,
    )

    return accepted_update_response(
        message="統合更新を開始しました。進捗は SSE イベント (update.progress) で通知されます。",
        code="unified_update_accepted",
        update_system=update_system,
        update_extensions=update_extensions,
    )

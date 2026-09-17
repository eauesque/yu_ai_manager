"""UI management API routes."""

import re

from quart import Blueprint, current_app, request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.ui_core.manager import install_ui, list_uis, switch_ui, uninstall_ui
from core.web.auth_core import is_local_request

bp = Blueprint("ui_api", __name__)

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/ui/list")
async def api_ui_list():
    """List all installed UIs."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result({"data": {"uis": await run_db_sync(list_uis)}}, 200)


@bp.route("/api/ui/switch", methods=["POST"])
async def api_ui_switch():
    """Switch active UI. Requires restart."""
    data = await request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name or not _SAFE_NAME_RE.match(name):
        return api_error("Invalid UI name", 400)
    config_path = current_app.config.get("CONFIG_PATH", "config.json")
    result, status = await run_db_sync(switch_ui, name, config_path=config_path)
    return api_result(result, status) if status == 200 else api_error(result.get("error", ""), status)


@bp.route("/api/ui/install", methods=["POST"])
async def api_ui_install():
    """Install a UI from URL. Localhost only."""
    if not is_local_request():
        return api_error("Install is only allowed from localhost", 403)
    data = await request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return api_error("URL is required", 400)
    result, status = await run_db_sync(install_ui, url)
    return api_result(result, status) if status == 200 else api_error(result.get("error", ""), status)


@bp.route("/api/ui/<name>/uninstall", methods=["DELETE"])
async def api_ui_uninstall(name: str):
    """Uninstall a UI. Localhost only."""
    if not is_local_request():
        return api_error("Uninstall is only allowed from localhost", 403)
    if not _SAFE_NAME_RE.match(name):
        return api_error("Invalid UI name", 400)
    result, status = await run_db_sync(uninstall_ui, name)
    return api_result(result, status) if status == 200 else api_error(result.get("error", ""), status)

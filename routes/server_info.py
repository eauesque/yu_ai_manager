"""REST API for server mode, subsystem introspection, and diagnostics."""

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_request import require_json_dict
from core.web.error_bundle import enrich_error_bundle

bp = Blueprint("server_info", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/server/mode", methods=["GET"])
async def api_server_mode():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from quart import current_app
    return api_result({
        "mode": current_app.config.get("SERVER_MODE", "full"),
        "headless": current_app.config.get("HEADLESS", False),
    })


@bp.route("/api/server/subsystems", methods=["GET"])
async def api_server_subsystems():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from quart import current_app

    from core.web.runtime_subsystems import BACKGROUND_TASKS, SUBSYSTEMS
    from core.web.startup_mode import _should_run_bg_task, _should_run_subsystem

    mode = current_app.config.get("SERVER_MODE", "full")
    subs = [{"name": s.name, "modes": s.modes,
             "enabled": _should_run_subsystem(s, mode),
             "env_override": s.env_override or None} for s in SUBSYSTEMS]
    tasks = [{"name": t.name, "modes": t.modes,
              "enabled": _should_run_bg_task(t, mode),
              "env_enable": t.env_enable or None,
              "env_disable": t.env_disable or None} for t in BACKGROUND_TASKS]
    return api_result({"mode": mode, "subsystems": subs, "background_tasks": tasks})


@bp.route("/api/error-report/enrich", methods=["POST"])
async def api_error_report_enrich():
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    bundle = data.get("bundle")
    if not isinstance(bundle, dict):
        return api_error("bundle object is required", 400)
    return api_result({"ok": True, "bundle": enrich_error_bundle(bundle)})

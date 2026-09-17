"""GET /api/ai-context — AI self-description endpoint."""

from __future__ import annotations

from quart import Blueprint, current_app

from core.configuration.json_rw import load_config_json
from core.infra_core.ai_context import build_ai_context
from core.infra_core.api_errors import api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope
from core.web.request_hooks import get_csrf_description

bp = Blueprint("ai_context", __name__)


@bp.route("/api/ai-context")
async def api_ai_context():
    """Return AI-navigable self-description of this YU AI Manager instance.

    Authentication: require_admin_scope() — PIN session, cookie, trusted-proxy,
    or admin-scope API Key. Read-scope API Key returns 403.
    """
    if err := require_admin_scope():
        return err

    config: dict = await run_db_sync(load_config_json)
    registered_names: set[str] = set(current_app.blueprints.keys())

    data = build_ai_context(
        csrf_note=get_csrf_description(),
        registered_names=registered_names,
        config=config,
    )

    return api_result({"data": data}, 200)

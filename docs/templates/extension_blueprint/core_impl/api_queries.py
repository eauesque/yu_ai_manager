# docs/templates/extension_blueprint/core_impl/api_queries.py
"""Query routes (GET) for __EXTNAME__ extension."""
from __future__ import annotations

from core.infra_core.api_errors import api_error, api_result
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from ._blueprint import bp


@bp.route("/api/__EXTNAME__/resources", methods=["GET"])
async def list_resources():
    """List all resources."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    # TODO: implement
    return api_result({"data": []})


@bp.route("/api/__EXTNAME__/resources/<int:resource_id>", methods=["GET"])
async def get_resource(resource_id: int):
    """Get a single resource."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    # TODO: implement
    return api_error(f"Resource {resource_id} not found", 404)

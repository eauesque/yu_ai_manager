# docs/templates/extension_blueprint/core_impl/api_mutations.py
"""Mutation routes (POST/PUT/DELETE) for __EXTNAME__ extension.

SCOPE GATE RULE: Every POST/PUT/DELETE/PATCH route MUST call
require_admin_scope() / require_local() / require_pin() before
any request.get_json() or await run_db_sync() call.
Violation -> pre-push FAIL in Phase 2.
"""
from __future__ import annotations

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from ._blueprint import bp


@bp.route("/api/__EXTNAME__/resource", methods=["POST"])
async def create_resource():
    """Create a new resource.

    Body: {"name": str}
    """
    # ── scope gate (REQUIRED before any request processing) ──────────
    # DO NOT remove or move below request.get_json() / run_db_sync().
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    # ── /scope gate ──────────────────────────────────────────────────

    data = await request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return api_error("name is required", 400)

    # TODO: implement
    return api_result({"ok": True, "name": name})


@bp.route("/api/__EXTNAME__/resource/<int:resource_id>", methods=["PUT"])
async def update_resource(resource_id: int):
    """Update an existing resource.

    Body: {"name": str?}
    """
    # ── scope gate ───────────────────────────────────────────────────
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    # ── /scope gate ──────────────────────────────────────────────────

    _data = await request.get_json(silent=True) or {}  # noqa: F841
    # TODO: implement
    return api_result({"ok": True, "id": resource_id})


@bp.route("/api/__EXTNAME__/resource/<int:resource_id>", methods=["DELETE"])
async def delete_resource(resource_id: int):
    """Delete a resource."""
    # ── scope gate ───────────────────────────────────────────────────
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    # ── /scope gate ──────────────────────────────────────────────────

    # TODO: implement
    return api_result({"ok": True})

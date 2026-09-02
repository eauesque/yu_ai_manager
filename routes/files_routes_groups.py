"""Thin dispatch handlers for /api/groups-* and /api/container-thumb-ids.

Logic lives in ``core/group_api/``. Registered by ``routes/files.py``.
"""

from quart import jsonify, request

from core.group_api import (
    build_container_thumb_ids_response,
    build_group_members_response,
    build_groups_index_response,
    build_groups_index_warm_response,
)
from core.infra_core.inflight_dedupe import dedupe_db_get
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


async def groups_index():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    # Heavy index build hit on every cold load — dedupe concurrent fetches.
    payload = await dedupe_db_get("groups-index", None, build_groups_index_response)
    return jsonify(payload)


async def groups_index_warm():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload = await dedupe_db_get("groups-index-warm", None, build_groups_index_warm_response)
    return jsonify(payload)


async def group_members():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    key = request.args.get("key", "").strip()
    if not key:
        return jsonify({"ids": [], "error": "missing key"}), 400
    payload = await dedupe_db_get("group-members", key, build_group_members_response, key)
    return jsonify(payload)


async def container_thumb_ids():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        limit = max(1, min(int(request.args.get("limit", "500")), 2000))
    except (ValueError, TypeError):
        limit = 500
    payload = await run_db_sync(build_container_thumb_ids_response, limit)
    return jsonify(payload)

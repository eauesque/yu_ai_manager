"""REST API for LLM endpoint CRUD and connection testing."""

from __future__ import annotations

import logging

from quart import Blueprint, request

from core.infra_core.api_errors import api_result
from routes.llm_endpoint_agent import get_agent_capabilities, run_agent_request, run_chat
from routes.llm_endpoint_config import (
    delete_endpoint,
    get_config,
    list_endpoints,
    test_endpoint_connection,
    update_endpoint,
)

logger = logging.getLogger(__name__)

bp = Blueprint("llm_endpoints", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/settings/llm-endpoints", methods=["GET"])
async def api_list():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return api_result(list_endpoints(get_config()))


@bp.route("/api/settings/llm-endpoints", methods=["PUT"])
async def api_set():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await update_endpoint(await request.get_json(silent=True) or {})


@bp.route("/api/settings/llm-endpoints/<category>", methods=["DELETE"])
async def api_delete(category: str):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await delete_endpoint(category)


@bp.route("/api/settings/llm-endpoints/test", methods=["POST"])
async def api_test():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await test_endpoint_connection(await request.get_json(silent=True) or {})


@bp.route("/api/llm/chat", methods=["POST"])
async def api_chat():
    return await run_chat(await request.get_json(silent=True) or {})


@bp.route("/api/llm/agent", methods=["POST"])
async def api_agent():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_agent_request(await request.get_json(silent=True) or {})


@bp.route("/api/llm/agent/capabilities", methods=["GET"])
async def api_agent_capabilities():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await get_agent_capabilities()

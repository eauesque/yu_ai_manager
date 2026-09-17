from __future__ import annotations

import json

from quart import Blueprint, Response, request

from core.gateway.auth import extract_bearer, get_auth
from core.gateway.capabilities import build_capabilities
from core.gateway.errors import openai_error
from core.gateway.scopes import Scope

bp = Blueprint("gateway_status", __name__)
_probe = None


def set_probe(probe) -> None:
    global _probe
    _probe = probe


def get_probe():
    return _probe


def _bearer() -> str | None:
    return extract_bearer(request.headers.get("Authorization"), request.headers.get("x-api-key"))


@bp.route("/v1/router/capabilities")
async def capabilities():
    auth = get_auth()
    result = auth.check_request(bearer=_bearer(), remote_addr=request.remote_addr or "")
    if result is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not auth.has_scope(result, Scope.LLM_MODELS):
        return openai_error(
            "Insufficient scope", "insufficient_scope", 403, param=str(Scope.LLM_MODELS)
        )
    try:
        from core.llm_router.state import get_catalog
        catalog = get_catalog()
        models = [{"id": m.alias} for m in catalog.list_backends()]
    except Exception:
        models = []
    return Response(
        json.dumps(build_capabilities(models=models), ensure_ascii=False),
        content_type="application/json",
    )


@bp.route("/v1/node/services")
async def node_services():
    auth = get_auth()
    result = auth.check_request(bearer=_bearer(), remote_addr=request.remote_addr or "")
    if result is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not auth.has_scope(result, Scope.NODE_STATUS):
        return openai_error(
            "Insufficient scope", "insufficient_scope", 403, param=str(Scope.NODE_STATUS)
        )
    services = []
    if _probe is not None:
        for bid, state in _probe.get_all_states().items():
            services.append({
                "id": bid,
                "state": str(state),
                "endpoint": getattr(_probe._backends.get(bid), "base_url", ""),
            })
    return Response(
        json.dumps({"services": services}, ensure_ascii=False),
        content_type="application/json",
    )

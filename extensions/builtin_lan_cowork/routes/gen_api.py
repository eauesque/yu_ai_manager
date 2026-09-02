"""extensions/builtin_lan_cowork/routes/gen_api.py
REST endpoint for receiving generation jobs from peers.

Peer relay is implemented as a thin invoker around the central handler
registry in `core.bridge_core.bridge_handlers`. Both the local route
(`/ext/<bridge>/api/generate`) and this peer-relay route call the same
handler — request shape and response shape are guaranteed to match by
construction. See `docs/development/development_docs/LAN_COWORK_PATH_ASYMMETRY.md`.
"""
from __future__ import annotations

from pydantic import ValidationError
from quart import Blueprint, request

from core.bridge_core.bridge_handlers import get_cancel, get_generate, get_progress, known_bridges
from core.infra_core.api_errors import api_error
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import PeerGenerationRequest, PeerProgressCancelRequest

_AUTH_PREFIX = "/ext/lan_cowork"


def _validation_error_response(exc: ValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ())) or "body"
    msg = first.get("msg", "invalid value")
    return api_error(f"invalid request body: {loc}: {msg}", 400)


def register_routes(bp: Blueprint, get_manager) -> None:
    from ..core_impl.peer_auth import require_peer_auth

    _auth = require_peer_auth(get_manager)

    @auth_route(bp, "/api/peer/generate", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def peer_generate():
        mgr = get_manager()
        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return api_error("body must be a JSON object", 400)
        try:
            PeerGenerationRequest.model_validate(data)
        except ValidationError as exc:
            return _validation_error_response(exc)
        bridge_raw = data.get("bridge")
        bridge_id = bridge_raw.strip() if isinstance(bridge_raw, str) else ""
        handler = get_generate(bridge_id)
        if handler is None:
            return api_error(
                f"unknown bridge {bridge_id!r}; known: {known_bridges()}",
                400,
            )
        # Track local generation state for queue-depth scheduling.
        mgr.local_peer.generating = True
        try:
            return await handler(data)
        finally:
            mgr.local_peer.generating = False

    @auth_route(bp, "/api/peer/progress", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def peer_progress():
        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return api_error("body must be a JSON object", 400)
        try:
            PeerProgressCancelRequest.model_validate(data)
        except ValidationError as exc:
            return _validation_error_response(exc)
        bridge_raw = data.get("bridge")
        bridge_id = bridge_raw.strip() if isinstance(bridge_raw, str) else ""
        handler = get_progress(bridge_id)
        if handler is None:
            return api_error(f"unknown bridge {bridge_id!r}", 400)
        return await handler(data)

    @auth_route(bp, "/api/peer/cancel", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def peer_cancel():
        data = await request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return api_error("body must be a JSON object", 400)
        try:
            PeerProgressCancelRequest.model_validate(data)
        except ValidationError as exc:
            return _validation_error_response(exc)
        bridge_raw = data.get("bridge")
        bridge_id = bridge_raw.strip() if isinstance(bridge_raw, str) else ""
        handler = get_cancel(bridge_id)
        if handler is None:
            return api_error(f"unknown bridge {bridge_id!r}", 400)
        return await handler(data)

"""Local proxy endpoints for browser-initiated pairing.

These endpoints sit between the browser (session-authenticated) and the
remote peer's pair/request + pair/verify APIs.  The browser cannot call
the remote directly, so it calls these local proxies instead.
"""
from __future__ import annotations

from quart import Blueprint, jsonify, request

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import ClientPairRequest, ClientPairVerifyRequest

_AUTH_PREFIX = "/ext/lan_cowork"


def register_routes(bp: Blueprint, *, get_manager, session_guard) -> None:

    @auth_route(bp, "/api/client/pair/request", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def client_pair_request():
        """Browser asks local server to initiate pairing with a remote peer."""
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, ClientPairRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        peer_id = data.peer_id

        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "service unavailable"}), 503

        peer = mgr.registry.get(peer_id)
        if peer is None:
            return jsonify({"ok": False, "error": "peer not found"}), 404

        ok, request_id, sas, error = await mgr.auth_client.request_pairing(peer)
        if not ok:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify({"ok": True, "request_id": request_id, "sas": sas}), 202

    @auth_route(bp, "/api/client/pair/verify", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def client_pair_verify():
        """Browser submits PIN to complete pairing (proxy to remote peer/pair/verify)."""
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, ClientPairVerifyRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        peer_id = data.peer_id
        request_id = data.request_id
        pin = data.pin

        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "service unavailable"}), 503

        peer = mgr.registry.get(peer_id)
        if peer is None:
            return jsonify({"ok": False, "error": "peer not found"}), 404

        ok, error = await mgr.auth_client.verify_pin(peer, request_id, pin)
        if not ok:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify({"ok": True})

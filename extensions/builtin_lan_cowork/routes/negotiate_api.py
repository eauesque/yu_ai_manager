"""extensions/builtin_lan_cowork/routes/negotiate_api.py
REST endpoint for receiving negotiation proposals from peers.
"""
from __future__ import annotations

import logging

from quart import Blueprint, jsonify, request

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import PeerNegotiateRequest

# Max tokens budget for the negotiation LLM call
_NEGOTIATE_MAX_TOKENS = 128

logger = logging.getLogger(__name__)
_AUTH_PREFIX = "/ext/lan_cowork"


def register_routes(bp: Blueprint, get_manager) -> None:
    """Register /api/peer/negotiate route on the given blueprint."""
    from ..core_impl.peer_auth import require_peer_auth

    _auth = require_peer_auth(get_manager)

    @auth_route(bp, "/api/peer/negotiate", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def peer_negotiate():
        # Note: @_auth (require_peer_auth) already returns 503 when mgr is None,
        # so mgr is guaranteed to be non-None here.
        mgr = get_manager()
        data, err = await require_json_model(request, PeerNegotiateRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        payload = data.model_dump(exclude_none=True)

        # Check LLM is available on this node
        llm_client = mgr.inference_state.get_llm_client()
        if llm_client is None:
            return jsonify({
                "proposal_id": payload.get("proposal_id", ""),
                "accept": False,
                "reason": "No LLM configured on this node",
                "responder_peer_id": mgr.local_peer.peer_id,
            })

        # Build node status — psutil is optional, fall back to 0 if not installed
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=None)
        except ImportError:
            cpu_pct = 0
        node_status = {
            "cpu_percent": cpu_pct,
            "queue_depth": mgr.local_peer.queue_depth,
            "inference_types": mgr.local_peer.inference_types,
            "generating": mgr.local_peer.generating,
        }

        # Build prompt and ask LLM
        from ..core_impl.negotiation.prompts import (
            build_system_prompt,
            build_user_message,
            parse_llm_response,
        )
        from ..core_impl.negotiation.protocol import Proposal

        try:
            proposal = Proposal.from_dict(payload)
        except (KeyError, TypeError) as exc:
            return jsonify({"ok": False, "error": f"invalid proposal: {exc}"}), 400
        sys_prompt = build_system_prompt(node_status)
        user_msg = build_user_message(proposal)

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ]

        try:
            resp = await llm_client.chat(
                messages=messages,
                max_tokens=_NEGOTIATE_MAX_TOKENS,
                temperature=0.3,
            )
            accept, reason = parse_llm_response(resp.content)
        except Exception as exc:
            logger.warning("Negotiation LLM call failed: %s", exc)
            accept, reason = False, f"LLM error: {exc}"

        logger.info(
            "Negotiate %s: accept=%s reason=%s",
            payload.get("proposal_id", "?")[:8], accept, reason,
        )

        return jsonify({
            "proposal_id": payload.get("proposal_id", ""),
            "accept": accept,
            "reason": reason,
            "responder_peer_id": mgr.local_peer.peer_id,
        })

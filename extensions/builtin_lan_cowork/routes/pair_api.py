"""/api/peer/pair/* endpoints — request, approve, reject, verify, list."""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import time
from collections import deque
from collections.abc import Callable

from quart import Blueprint, jsonify, request

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import PairRequestId, PairVerifyRequest, PeerPairRequest

logger = logging.getLogger(__name__)
_AUTH_PREFIX = "/ext/lan_cowork"

_VERIFY_RATE_PER_MIN = 30
_verify_ip_log: dict[str, deque[float]] = {}


def _verify_rate_ok(source_ip: str) -> bool:
    now = time.time()
    dq = _verify_ip_log.setdefault(source_ip, deque())
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= _VERIFY_RATE_PER_MIN:
        return False
    dq.append(now)
    return True


def _verify_ip_log_gc() -> None:
    """Remove stale entries from the module-level rate-limit log."""
    now = time.time()
    for ip in list(_verify_ip_log):
        dq = _verify_ip_log[ip]
        while dq and now - dq[0] > 60:
            dq.popleft()
        if not dq:
            del _verify_ip_log[ip]


def register_routes(
    bp: Blueprint,
    *,
    pairing_service: Callable,
    session_guard: Callable,
    get_manager: Callable | None = None,
) -> None:
    """pairing_service() -> PairingService; session_guard() -> bool (pin_ok)."""

    async def _call_service(method_name: str, *args, **kwargs):
        svc = pairing_service()
        if svc is None:
            return None, (jsonify({"ok": False, "error": "service unavailable"}), 503)
        method = getattr(svc, method_name)
        if getattr(svc, "threadsafe_provider", False):
            return await asyncio.to_thread(method, *args, **kwargs), None
        return method(*args, **kwargs), None

    @auth_route(bp, "/api/peer/pair/request", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    async def pair_request():
        data, err = await require_json_model(request, PeerPairRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        peer_id = data.peer_id
        host = data.host
        port = data.port
        try:
            pubkey = base64.b64decode(data.pubkey, validate=True)
            x25519_pk = (
                base64.b64decode(data.x25519_pk, validate=True)
                if data.x25519_pk is not None
                else None
            )
            commit = base64.b64decode(data.commit, validate=True)
        except (binascii.Error, ValueError):
            return jsonify({"ok": False, "error": "invalid pairing fields"}), 400
        try:
            result, err = await _call_service(
                "request",
                peer_id=peer_id,
                host=host,
                port=port,
                source_ip=request.remote_addr or "",
                pubkey=pubkey,
                x25519_pk=x25519_pk,
                commit_hash=commit,
            )
            if err is not None:
                return err
        except pairing_service().RateLimitExceeded:
            return jsonify({"ok": False, "error": "rate limit"}), 429
        except pairing_service().PendingCapExceeded:
            return jsonify({"ok": False, "error": "pending cap exceeded"}), 429
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            logger.exception("pair/request DB error: %s", exc)
            return jsonify({"ok": False, "error": f"internal error: {exc}"}), 500
        rid, sas = result
        # Emit SSE event for UI banner (best-effort)
        try:
            from core.event_bus import emit
            emit("peer.pairing_request", {"request_id": rid, "peer_id": peer_id, "host": host})
        except Exception:
            # The operator is supposed to see a banner and approve; without it
            # the request sits there unanswered.
            logger.warning("pairing request banner was not emitted", exc_info=True)
        return jsonify({"ok": True, "request_id": rid, "sas": sas}), 202

    @auth_route(bp, "/api/peer/pair/approve", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def pair_approve():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, PairRequestId)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        rid = data.request_id
        try:
            pin, err = await _call_service("approve", rid)
            if err is not None:
                return err
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 409
        return jsonify({"ok": True, "pin": pin, "expires_in": 300})

    @auth_route(bp, "/api/peer/pair/reject", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def pair_reject():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, PairRequestId)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        rid = data.request_id
        _, err = await _call_service("reject", rid)
        if err is not None:
            return err
        return jsonify({"ok": True})

    @auth_route(bp, "/api/peer/pair/verify", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    async def pair_verify():
        source_ip = request.remote_addr or ""
        if not _verify_rate_ok(source_ip):
            return jsonify({"ok": False, "error": "rate limit"}), 429
        data, err = await require_json_model(request, PairVerifyRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        rid = data.request_id
        row, err = await _call_service("get", rid)
        if err is not None:
            return err
        if row and row["status"] == "completed":
            return jsonify({"ok": False, "error": "already completed"}), 410
        try:
            bundle = base64.b64decode(data.encrypted_bundle, validate=True)
        except (binascii.Error, ValueError):
            return jsonify({"ok": False, "error": "invalid bundle"}), 400
        result, err = await _call_service("verify", rid, bundle, source_ip=source_ip)
        if err is not None:
            return err
        ok, token, expires_at, peer_pubkey = result
        if not ok:
            return jsonify({"ok": False, "error": "pairing verification failed"}), 401
        mgr = get_manager() if get_manager is not None else None
        if mgr is not None:
            mgr.complete_pairing(rid, peer_pubkey)
        # Notify approver-side UI (the host that issued the PIN) so it can toast.
        try:
            from core.event_bus import emit
            emit("peer.paired", {"request_id": rid, "peer_id": row["peer_id"]})
        except Exception:
            logger.warning("pairing-complete notice was not emitted", exc_info=True)
        local = getattr(mgr, "local_peer", None)
        response = {"ok": True, "token": token, "expires_at": expires_at, "peer_id": row["peer_id"]}
        if local is not None:
            response["server_pubkey"] = base64.b64encode(local.pubkey).decode()
            response["server_x25519_pk"] = base64.b64encode(local.x25519_pk).decode()
        return jsonify(response)

    @auth_route(bp, "/api/peer/pair/requests", methods=["GET"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def pair_list_pending():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        requests_data, err = await _call_service("list_pending")
        if err is not None:
            return err
        return jsonify({"ok": True, "requests": requests_data})

    # Triple-gated test-only endpoint: YU_AI_TEST_MODE=1 + __debug__ + registered at setup
    if os.environ.get("YU_AI_TEST_MODE") == "1" and __debug__:
        @bp.route("/api/peer/pair/requests/<rid>/_test_pin", methods=["GET"])
        async def _test_pin(rid: str):
            # Returns raw PIN — only enabled in test mode. Never accessible in production.
            svc = pairing_service()
            raw = getattr(svc, "_test_raw_pins", {}).get(rid) if svc is not None else None
            return jsonify({"pin": raw})

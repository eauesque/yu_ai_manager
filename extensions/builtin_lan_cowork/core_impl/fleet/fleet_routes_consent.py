"""Consent-related fleet route registrations."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from quart import jsonify, request

from core.infra_core.api_request import require_json_dict
from core.web.auth_route_policy import auth_route

from .fleet_route_deps import FleetConsentRouteDeps
from .fleet_route_guards import build_local_chief_getter, build_manager_getter, ensure_session

logger = logging.getLogger(__name__)

_AUTH_PREFIX = "/ext/lan_cowork"


def register_fleet_consent_routes(
    bp,
    get_manager,
    deps: FleetConsentRouteDeps,
):
    auth_decorator = deps.auth_decorator
    session_ok = deps.session_ok
    fleet_cfg = deps.fleet_cfg
    consent_lock = deps.consent_lock
    consent_store = deps.consent_store
    deny_cooldown = deps.deny_cooldown
    run_consent_janitor_once = deps.run_consent_janitor_once
    relay_consent_request = deps.relay_consent_request
    relay_consent_status = deps.relay_consent_status
    logger = deps.logger

    require_manager = build_manager_getter(get_manager)
    require_local_chief = build_local_chief_getter(require_manager, session_ok)

    @auth_route(bp, "/fleet/consent/request", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer_or_session")
    @auth_decorator
    async def fleet_consent_request():
        from .fleet_config import get_fleet_timings

        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]
        chief_peer_id = request.headers.get("X-Peer-Id", "").strip()
        timings = get_fleet_timings(fleet_cfg(mgr))
        timeout_sec = timings.get("consent_timeout_sec", 300)

        data, err = await require_json_dict(request)
        if err:
            return jsonify(err[0]), err[1]
        assert data is not None
        request_id = str(data.get("request_id", "")).strip()
        if not request_id:
            return jsonify({"error": "request_id required"}), 400

        async with consent_lock:
            cooldown_exp = deny_cooldown.get(chief_peer_id, 0)
            if time.time() < cooldown_exp:
                return jsonify({"error": "deny_cooldown", "retry_after_sec": int(cooldown_exp - time.time())}), 429
            for _rid, entry in consent_store.items():
                if entry.get("decision") is None and time.time() < entry.get("expires_at", 0):
                    return jsonify({
                        "error": "consent_pending",
                        "remaining_sec": int(entry["expires_at"] - time.time()),
                    }), 409
            consent_store[request_id] = {
                "chief_peer_id": chief_peer_id,
                "expires_at": time.time() + timeout_sec,
                "decision": None,
                "permanent": False,
                "decided_at": None,
            }

        try:
            from core.event_bus import emit as _emit

            _emit("fleet.consent_request", {
                "request_id": request_id,
                "chief_peer_id": chief_peer_id,
                "remaining_sec": timeout_sec,
            })
        except Exception:
            # The route answers "accepted"; without the event nobody is asked.
            logger.warning("consent request %s was not surfaced", request_id, exc_info=True)
        return jsonify({"status": "accepted"}), 200

    @auth_route(bp, "/fleet/consent/respond", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer_or_session")
    async def fleet_consent_respond():
        failure = ensure_session(session_ok)
        if failure:
            return jsonify(failure[0]), failure[1]

        data, err = await require_json_dict(request)
        if err:
            return jsonify(err[0]), err[1]
        assert data is not None
        request_id = str(data.get("request_id", "")).strip()
        decision = str(data.get("decision", "")).strip()
        permanent = data.get("permanent", False)
        if not request_id or decision not in ("approved", "denied"):
            return jsonify({"error": "invalid request"}), 400
        if not isinstance(permanent, bool):
            return jsonify({"error": "permanent must be a boolean"}), 400

        async with consent_lock:
            entry = consent_store.get(request_id)
            if entry is None:
                return jsonify({"error": "not_found"}), 404
            if time.time() > entry.get("expires_at", 0):
                del consent_store[request_id]
                return jsonify({"error": "expired"}), 410

            entry["decision"] = decision
            entry["permanent"] = permanent
            entry["decided_at"] = time.time()
            if decision == "denied":
                mgr, _failure = require_manager()
                deny_sec = 300
                if mgr is not None:
                    from .fleet_config import get_fleet_timings

                    deny_sec = get_fleet_timings(fleet_cfg(mgr)).get("consent_timeout_sec", 300)
                deny_cooldown[entry["chief_peer_id"]] = time.time() + deny_sec

        if decision == "approved" and permanent:
            try:
                def _persist_allow_remote_update():
                    from core.extensions_core.lifecycle.extensions_admin import (
                        get_extension_config_value,
                        save_extension_config_values,
                    )

                    ext_name = "builtin-lan-cowork"
                    cfg = dict(get_extension_config_value(ext_name, "fleet", {}) or {})
                    cfg["allow_remote_update"] = True
                    save_extension_config_values(ext_name, {"fleet": cfg})

                await asyncio.to_thread(_persist_allow_remote_update)
            except Exception:
                logger.warning("fleet.consent: failed to persist allow_remote_update")

        logger.info(
            "fleet.consent decision: request_id=%s chief=%s decision=%s permanent=%s",
            request_id,
            entry["chief_peer_id"],
            decision,
            permanent,
        )
        return jsonify({"status": "ok"}), 200

    @auth_route(bp, "/fleet/consent/status/<request_id>", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer_or_session")
    @auth_decorator
    async def fleet_consent_status(request_id: str):
        async with consent_lock:
            entry = consent_store.get(request_id)
        if entry is None:
            return jsonify({"status": "not_found", "permanent": False, "remaining_sec": 0}), 200

        now = time.time()
        if entry.get("decision") is None and now > entry.get("expires_at", 0):
            async with consent_lock:
                consent_store.pop(request_id, None)
            return jsonify({"status": "expired", "permanent": False, "remaining_sec": 0}), 200

        status = entry.get("decision") or "pending"
        remaining = max(0, int(entry.get("expires_at", now) - now)) if status == "pending" else 0
        return jsonify({
            "status": status,
            "permanent": entry.get("permanent", False),
            "remaining_sec": remaining,
        }), 200

    @auth_route(bp, "/fleet/consent/pending", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer_or_session")
    async def fleet_consent_pending():
        failure = ensure_session(session_ok)
        if failure:
            return jsonify(failure[0]), failure[1]

        now = time.time()
        async with consent_lock:
            for rid, entry in list(consent_store.items()):
                if entry.get("decision") is None and now < entry.get("expires_at", 0):
                    return jsonify({
                        "pending": {
                            "request_id": rid,
                            "chief_peer_id": entry["chief_peer_id"],
                            "remaining_sec": int(entry["expires_at"] - now),
                        }
                    }), 200
        return jsonify({"pending": None}), 200

    @auth_route(bp, "/fleet/consent/relay/request", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer_or_session")
    async def fleet_consent_relay_request_route():
        mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        data, err = await require_json_dict(request)
        if err:
            return jsonify(err[0]), err[1]
        assert data is not None
        peer_id = str(data.get("peer_id", "")).strip()
        request_id = str(data.get("request_id", "")).strip()
        if not peer_id or not request_id:
            return jsonify({"error": "peer_id and request_id required"}), 400
        peer = mgr.registry.get(peer_id)
        if peer is None:
            return jsonify({"error": "peer_not_found"}), 404

        body, status = await relay_consent_request(mgr, peer, request_id=request_id)
        return jsonify(body), status

    @auth_route(bp, "/fleet/consent/relay/status", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer_or_session")
    async def fleet_consent_relay_status_route():
        mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        peer_id = request.args.get("peer_id", "").strip()
        req_id = request.args.get("request_id", "").strip()
        if not peer_id or not req_id:
            return jsonify({"error": "peer_id and request_id required"}), 400
        peer = mgr.registry.get(peer_id)
        if peer is None:
            return jsonify({"status": "not_found", "permanent": False, "remaining_sec": 0}), 200

        body, status = await relay_consent_status(mgr, peer, request_id=req_id)
        return jsonify(body), status

    janitor_task: list = []

    @bp.before_app_serving
    async def _start_consent_janitor():
        async def _loop():
            while True:
                with contextlib.suppress(Exception):
                    await run_consent_janitor_once()
                await asyncio.sleep(60)

        janitor_task.append(asyncio.ensure_future(_loop()))

    @bp.after_app_serving
    async def _stop_consent_janitor():
        if janitor_task:
            janitor_task[0].cancel()
            janitor_task.clear()

"""Restart routes for fleet management."""
from __future__ import annotations

import asyncio
import uuid

from quart import jsonify, request

from core.infra_core.api_request import require_json_dict
from core.web.auth_route_policy import auth_route

from .fleet_routes_update_helpers import validate_peer_ids


def register_fleet_restart_routes(
    bp,
    *,
    auth_decorator,
    require_manager,
    require_local_chief,
    runtime,
    gc_dispatches_fn,
    auth_prefix: str,
):
    @auth_route(
        bp,
        "/fleet/restart",
        methods=["POST"],
        absolute_prefix=auth_prefix,
        bypass_session=True,
        require="peer",
    )
    @auth_decorator
    async def fleet_restart():
        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]

        requester_peer_id = request.headers.get("X-Peer-Id", "").strip()
        allowed, error_code = await runtime["check_restart_allowed"](
            mgr,
            requester_peer_id,
            allow_consent=True,
        )
        if not allowed:
            return jsonify({"error": error_code, "message": error_code}), 403

        import sys as _sys
        import threading as _threading

        from core.platform import exec_restart as _exec_restart

        exec_args = [_sys.executable, *_sys.argv]

        def _delayed_restart():
            import time as _time

            _time.sleep(1.5)
            _exec_restart(exec_args)

        _threading.Thread(target=_delayed_restart, daemon=True).start()
        return jsonify({"accepted": True, "message": "restart scheduled"})

    @bp.route("/fleet/restart/dispatch", methods=["POST"])
    async def fleet_restart_dispatch():
        mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        data, err = await require_json_dict(request)
        if err:
            return jsonify(err[0]), err[1]
        assert data is not None
        peer_ids, peer_ids_error = validate_peer_ids(data.get("peer_ids", []) or [])
        if peer_ids_error:
            return jsonify(peer_ids_error[0]), peer_ids_error[1]
        if not peer_ids:
            return jsonify({"error": "no_peers", "message": "peer_ids is required"}), 400
        if mgr.local_peer.peer_id in peer_ids:
            return jsonify({
                "error": "cannot_dispatch_self",
                "message": "chief cannot dispatch to itself",
            }), 400

        dispatch_id = "rstrt_" + uuid.uuid4().hex[:8]
        try:
            runner = runtime["restart_dispatch_runner_cls"](
                mgr=mgr,
                dispatch_id=dispatch_id,
                peer_ids=peer_ids,
            )
        except ValueError as exc:
            return jsonify({"error": "cannot_dispatch_self", "message": str(exc)}), 400

        runtime["dispatches"][dispatch_id] = runner

        async def _run_and_persist():
            try:
                await runner.run()
                runtime["save_dispatch_history"](
                    runtime["data_dir"],
                    runner.get_status(),
                )
            finally:
                gc_dispatches_fn()

        asyncio.ensure_future(_run_and_persist())
        return jsonify({"dispatch_id": dispatch_id, "peer_count": len(peer_ids)})

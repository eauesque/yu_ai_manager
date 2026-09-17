"""Dispatch routes for fleet update management."""
from __future__ import annotations

import asyncio
import uuid

from quart import jsonify, request

from core.infra_core.api_request import require_json_dict

from .fleet_routes_update_helpers import validate_consent_tokens, validate_peer_ids


def register_fleet_update_dispatch_routes(
    bp,
    *,
    require_local_chief,
    runtime,
    gc_dispatches_fn,
):
    @bp.route("/fleet/update/dispatch", methods=["POST"])
    async def fleet_update_dispatch():
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
        source = data.get("source", "origin")
        branch = data.get("branch", "main")
        consent_tokens, consent_tokens_error = validate_consent_tokens(
            data.get("consent_tokens", {}) or {}
        )
        if consent_tokens_error:
            return jsonify(consent_tokens_error[0]), consent_tokens_error[1]
        if not isinstance(source, str) or not source.strip():
            return jsonify({
                "error": "invalid_source",
                "message": "source must be a non-empty string",
            }), 400
        if not isinstance(branch, str) or not branch.strip():
            return jsonify({
                "error": "invalid_branch",
                "message": "branch must be a non-empty string",
            }), 400
        source = source.strip()
        branch = branch.strip()
        if not peer_ids:
            return jsonify({"error": "no_peers", "message": "peer_ids is required"}), 400
        if mgr.local_peer.peer_id in peer_ids:
            return jsonify({
                "error": "cannot_dispatch_self",
                "message": "chief cannot dispatch to itself",
            }), 400

        dispatch_id = "disp_" + uuid.uuid4().hex[:8]
        try:
            runner = runtime["dispatch_runner_cls"](
                mgr=mgr,
                dispatch_id=dispatch_id,
                peer_ids=peer_ids,
                source=source,
                branch=branch,
                consent_tokens=consent_tokens,
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

    @bp.route("/fleet/update/dispatch/status", methods=["GET"])
    async def fleet_update_dispatch_status():
        _mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        dispatch_id = request.args.get("dispatch_id", "").strip()
        runner = runtime["dispatches"].get(dispatch_id)
        if runner is not None:
            return jsonify(runner.get_status())

        history = runtime["load_dispatch_history"](runtime["data_dir"])
        for entry in history:
            if entry.get("dispatch_id") == dispatch_id:
                return jsonify(entry)
        return jsonify({"error": "dispatch_not_found"}), 404

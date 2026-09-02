"""Update job routes for fleet management."""
from __future__ import annotations

import asyncio
import uuid

from quart import jsonify, request

from core.infra_core.api_request import require_json_dict
from core.web.auth_route_policy import auth_route


def register_fleet_update_job_routes(
    bp,
    *,
    auth_decorator,
    require_manager,
    runtime,
    auth_prefix: str,
):
    @auth_route(
        bp,
        "/fleet/update",
        methods=["POST"],
        absolute_prefix=auth_prefix,
        bypass_session=True,
        require="peer",
    )
    @auth_decorator
    async def fleet_update():
        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]

        requester_peer_id = request.headers.get("X-Peer-Id", "").strip()
        allowed, error_code = await runtime["check_update_allowed"](
            mgr,
            requester_peer_id,
        )
        if not allowed:
            return jsonify({"error": error_code, "message": error_code}), 403

        data, err = await require_json_dict(request)
        if err:
            return jsonify(err[0]), err[1]
        assert data is not None
        source = data.get("source", "origin")
        if not isinstance(source, str):
            return jsonify({
                "error": "invalid_source",
                "message": "source must be a string",
            }), 400
        branch = data.get("branch", "main")
        if not isinstance(branch, str):
            return jsonify({
                "error": "invalid_branch",
                "message": "branch must be a string",
            }), 400
        if source != "origin" and not source.startswith("local:"):
            return jsonify({
                "error": "invalid_source",
                "message": "source must be 'origin' or 'local:<path>'",
            }), 400

        cfg = runtime["fleet_cfg"](mgr)
        allowed_branches = cfg.get("allowed_branches", ["main"]) or ["main"]
        if branch not in allowed_branches:
            return jsonify({
                "error": "branch_not_allowed",
                "message": f"branch {branch!r} not in allowed_branches",
            }), 400

        for job_id, job in runtime["active_jobs"].items():
            if job.get("status") in (
                runtime["update_status"].PENDING,
                runtime["update_status"].RUNNING,
                runtime["update_status"].RESTARTING,
            ):
                return jsonify({
                    "error": "update_in_progress",
                    "current_job_id": job_id,
                }), 409

        job_id = uuid.uuid4().hex[:12]
        runtime["active_jobs"][job_id] = {
            "job_id": job_id,
            "status": runtime["update_status"].PENDING,
            "started_at": None,
            "finished_at": None,
            "steps": [],
            "error": None,
        }
        allowed_local = cfg.get("allowed_local_sources", []) or []

        async def _run():
            runtime["active_jobs"][job_id]["status"] = runtime["update_status"].RUNNING
            try:
                result = await runtime["run_update_job"](
                    job_id=job_id,
                    source=source,
                    branch=branch,
                    repo_path=runtime["repo_root"],
                    local_peer_id=mgr.local_peer.peer_id,
                    allowed_branches=allowed_branches,
                    allowed_local_sources=allowed_local,
                    data_dir=runtime["data_dir"],
                )
                runtime["active_jobs"][job_id].update(result)
                runtime["save_last_job"](runtime["data_dir"], result)
            except Exception as exc:
                runtime["active_jobs"][job_id]["status"] = runtime["update_status"].FAILED
                runtime["active_jobs"][job_id]["error"] = str(exc)
            finally:
                terminal = [
                    item_id
                    for item_id, job in runtime["active_jobs"].items()
                    if job.get("status") not in (
                        runtime["update_status"].PENDING,
                        runtime["update_status"].RUNNING,
                        runtime["update_status"].RESTARTING,
                    )
                ]
                for old_id in terminal[:-5]:
                    runtime["active_jobs"].pop(old_id, None)

        asyncio.ensure_future(_run())
        return jsonify({"job_id": job_id, "status": "pending"})

    @auth_route(
        bp,
        "/fleet/update/status",
        methods=["GET"],
        absolute_prefix=auth_prefix,
        bypass_session=True,
        require="peer",
    )
    @auth_decorator
    async def fleet_update_status():
        # The record this returns carries the git commit SHA and every step's
        # git output. Authentication alone -- any paired peer holding a token --
        # was the only gate, so an operator who had turned remote fleet
        # operations off was still handing that record out.
        #
        # allow_remote_update is the master switch the UI advertises, and the
        # consent flow persists it as True before an update runs, so gating on
        # it cannot cut off a legitimate consent-driven poll. Whether the
        # *allowlist* should apply here as well is a separate decision, recorded
        # in TODO.md: it would refuse a peer that reached the update through a
        # consent token, and the job record carries no requester to exempt.
        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]
        if not runtime["fleet_cfg"](mgr).get("allow_remote_update", False):
            return jsonify({
                "error": "remote_update_disabled",
                "message": "remote fleet operations are disabled on this node",
            }), 403

        job_id = request.args.get("job_id", "").strip()
        if not job_id:
            return jsonify({"error": "missing job_id"}), 400

        job = runtime["active_jobs"].get(job_id)
        if job is None:
            job = runtime["load_last_job"](
                runtime["data_dir"],
                repo_path=runtime["repo_root"],
            )
            if job is None or job.get("job_id") != job_id:
                return jsonify({"error": "job_not_found"}), 404
        return jsonify(job)

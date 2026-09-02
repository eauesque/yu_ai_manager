"""Route registration for tools operation APIs."""

import threading

from quart import request

from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict
from core.jobs_core.jobs import job_manager
from core.services_core.db_async import run_db_sync
from core.tools_api.duplicates_ops import (
    compute_hashes_payload,
    delete_duplicates_payload,
    find_duplicates_payload,
    normalize_tags_payload,
    tools_scan_payload,
)
from core.tools_api.similar_ops import find_similar_payload
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

_FIND_DUP_JOB_ID = "find_duplicates"


def _run_find_duplicates_job(args: dict) -> None:
    """Background worker: run find_duplicates and store result in job."""
    job = job_manager.get_raw_job(_FIND_DUP_JOB_ID)
    if job is None:
        return
    try:
        job.update(phase="running", message="重複ファイルを検索中...")
        payload, status = find_duplicates_payload(args)
        if status == 200:
            job.result = payload
            total = payload.get("total_duplicates", 0)
            job.complete(message=f"{total} 件の重複を検出")
        else:
            job.fail(payload.get("error", "duplicate search failed"))
    except Exception as exc:
        job.fail(str(exc))


def register_tools_ops_routes(bp):
    """Register duplicate/hash/scan related tool routes."""

    @bp.route("/api/tools/find-duplicates")
    async def api_tools_find_duplicates():
        """Synchronous duplicate search (backwards-compatible, fast for hash/size).

        For phash with large DBs (avg 30s+) use the async endpoints:
          POST /api/tools/find-duplicates/start   → {"job_id": "find_duplicates"}
          GET  /api/tools/find-duplicates/status  → job status + result when done
        """
        args = dict(request.args)
        payload, status = await run_db_sync(find_duplicates_payload, args)
        return api_result(payload, status)

    @bp.route("/api/tools/find-duplicates/start", methods=["POST"])
    async def api_tools_find_duplicates_start():
        """Start an async duplicate search job.

        Request body (JSON):
          method       (str)  "hash" | "phash" | "size"  default "hash"
          cross_directory (bool)  default false
          threshold    (int)  pHash hamming threshold 0-64, default 5

        Returns immediately with {"job_id": "find_duplicates"}.
        Poll GET /api/tools/find-duplicates/status for progress and result.
        """
        if job_manager.is_running(_FIND_DUP_JOB_ID):
            return api_result({"job_id": _FIND_DUP_JOB_ID, "already_running": True})

        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        args = {
            "method": str(data.get("method", "hash")),
            "cross_directory": "true" if data.get("cross_directory") else "false",
            "threshold": str(data.get("threshold", 5)),
        }

        job_manager.start(_FIND_DUP_JOB_ID, "重複検索")
        t = threading.Thread(
            target=_run_find_duplicates_job,
            args=(args,),
            daemon=True,
            name="find-duplicates",
        )
        t.start()
        return api_result({"job_id": _FIND_DUP_JOB_ID, "started": True})

    @bp.route("/api/tools/find-duplicates/status")
    async def api_tools_find_duplicates_status():
        """Poll the current duplicate search job status and result.

        Response when running:  {"phase": "running", "running": true, ...}
        Response when complete: {"phase": "complete", "running": false, "result": {...}}
        Response when no job:   {"phase": "idle", "running": false}
        """
        job = job_manager.get_job(_FIND_DUP_JOB_ID)
        if job is None:
            return api_result({"phase": "idle", "running": False, "job_id": None})
        return api_result(job)

    @bp.route("/api/tools/compute-hashes", methods=["POST"])
    async def api_tools_compute_hashes():
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        return api_result(await run_db_sync(compute_hashes_payload, data), 200)

    @bp.route("/api/tools/delete-duplicates", methods=["POST"])
    async def api_tools_delete_duplicates():
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        return api_result(await run_db_sync(delete_duplicates_payload, data), 200)

    @bp.route("/api/tools/normalize-tags")
    async def api_tools_normalize_tags():
        args = dict(request.args)
        # Security C-case fix: this GET route mutates the DB by default
        # (dry_run defaults to false) with no scope check, matching Rust's
        # tools_ops.rs::normalize_tags fix. The dry_run=true preview stays
        # ungated.
        dry_run = str(args.get("dry_run", "false")).lower() == "true"
        if not dry_run:
            auth_err = _require_admin_scope()
            if auth_err:
                return auth_err
        return api_result(await run_db_sync(normalize_tags_payload, args), 200)

    @bp.route("/api/tools/find-similar")
    async def api_tools_find_similar():
        args = dict(request.args)
        payload, status = await run_db_sync(find_similar_payload, args)
        return api_result(payload, status)

    @bp.route("/api/tools/scan", methods=["POST"])
    async def api_tools_scan():
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        payload, status = await run_db_sync(tools_scan_payload, data)
        return api_result(payload, status)

"""Tagger Server Registry API routes.

Manages mesh-based tagger peers and batch tagging operations.
"""

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync

bp = Blueprint("tagger_servers", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _parse_bool_field(data: dict, key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _parse_int_field(
    data: dict,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


# -- Server list (mesh peers) ---------------------------------------------

@bp.route("/api/tagger-servers", methods=["GET"])
async def api_ts_list():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.mesh_inference import get_router
    router = get_router()
    if router is None:
        return api_result({"mode": "mesh", "servers": []})
    peers = router.get_available_peers("tagger")
    servers = [{
        "id": p.peer_id,
        "name": p.name,
        "type": "mesh",
        "priority": 0,
        "enabled": True,
        "status": p.status,
    } for p in peers]
    return api_result({"mode": "mesh", "servers": servers})


# -- Health ---------------------------------------------------------------

@bp.route("/api/tagger-servers/health", methods=["GET"])
async def api_ts_health_all():
    """Check health of all mesh tagger peers."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.mesh_inference import get_router, has_mesh
    if not has_mesh():
        return api_result({"peers": []})
    router = get_router()
    local = router._local_peer
    remote = router._registry.list_online()
    results = []
    for p in [local] + remote:
        if "tagger" in (p.inference_types or []):
            results.append({
                "peer_id": p.peer_id,
                "name": p.name,
                "status": p.status,
                "is_local": p.peer_id == local.peer_id,
            })
    return api_result({"peers": results})


# -- Batch tagging ---------------------------------------------------------

@bp.route("/api/tagger-servers/batch", methods=["POST"])
async def api_ts_batch():
    data = await request.get_json(silent=True) or {}
    file_ids = data.get("file_ids")
    try:
        limit = _parse_int_field(data, "limit", default=500, minimum=1, maximum=2000)
        force = _parse_bool_field(data, "force", False)
    except ValueError as exc:
        return api_error(str(exc), 400, code="invalid_value")
    threshold = data.get("threshold")
    if threshold is not None:
        if not isinstance(threshold, (int, float)) or not 0.0 <= float(threshold) <= 1.0:
            return api_error(
                "threshold must be a number between 0.0 and 1.0",
                400,
                code="invalid_value",
            )
        threshold = float(threshold)

    if file_ids is not None and not isinstance(file_ids, list):
        return api_error("file_ids must be a list", 400, code="invalid_input")
    if isinstance(file_ids, list) and len(file_ids) > 2000:
        return api_error("file_ids max 2000", 400, code="batch_too_large")

    def _batch(fids, lim, f, th):
        from core.mesh_inference.dispatch_sync import run_tagger_batch as run_batch
        return run_batch(file_ids=fids, limit=lim, force=f, threshold=th)

    result = await run_db_sync(_batch, file_ids, limit, force, threshold)
    if "error" in result:
        return api_error(result["error"], 409, code=result.get("code", "batch_error"))
    return api_result(result)


@bp.route("/api/tagger-servers/batch/cancel", methods=["POST"])
async def api_ts_batch_cancel():
    """Cancel running tagger cluster batch job."""
    from core.jobs_core.jobs import job_manager
    if job_manager.cancel_job("tagger_cluster"):
        return api_result({"status": "cancelling", "message": "Tagger cluster cancel requested"})
    return api_error("No running tagger cluster job", 404, code="job_not_running")


# -- Tag CRUD (per file) --------------------------------------------------

@bp.route("/api/tagger-servers/tags/<int:file_id>", methods=["GET"])
async def api_ts_tags_get(file_id):
    def _get(fid):
        from core.mesh_inference.tagger_store import get_tagger_tags
        return get_tagger_tags(fid)
    tags = await run_db_sync(_get, file_id)
    return api_result({"file_id": file_id, "tags": tags})


@bp.route("/api/tagger-servers/tags/<int:file_id>", methods=["DELETE"])
async def api_ts_tags_delete(file_id):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    def _del(fid):
        from core.mesh_inference.tagger_store import delete_tagger_tags
        return delete_tagger_tags(fid)
    count = await run_db_sync(_del, file_id)
    return api_result({"file_id": file_id, "deleted": count})


# -- Stats ----------------------------------------------------------------

@bp.route("/api/tagger-servers/stats", methods=["GET"])
async def api_ts_stats():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    def _stats():
        from core.mesh_inference.tagger_store import count_untagged_files
        return {"untagged_count": count_untagged_files()}
    return api_result(await run_db_sync(_stats))

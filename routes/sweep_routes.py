"""Sweep XMP introspection + resume routes."""

from __future__ import annotations

from pathlib import Path

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.blocking_tasks import run_blocking_sync
from core.services_core.db_api import get_readonly_db
from core.services_core.db_async import run_db_sync
from routes.sweep_route_helpers import (
    HISTORY_LIMIT_MAX,
    IMAGE_SUFFIXES,
    attach_file_ids,
    attrs_to_meta,
    query_sweep_history,
    read_sweep_attrs,
    resolve_path,
    scan_folder_for_sweep,
)
from routes.sweep_route_helpers import (
    SWEEP_FOLDER_SCAN_IMAGE_LIMIT as _SWEEP_FOLDER_SCAN_IMAGE_LIMIT,
)

bp = Blueprint("sweep_routes", __name__)
SWEEP_FOLDER_SCAN_IMAGE_LIMIT = _SWEEP_FOLDER_SCAN_IMAGE_LIMIT

# Backward-compatible aliases for tests and any internal callers.
_attrs_to_meta = attrs_to_meta
_read_sweep_attrs = read_sweep_attrs


def _scan_folder_for_sweep(folder: str, sweep_id: str):
    # Simple wrapper kept for backward compatibility with any callers that
    # hold a reference to this private function. The original implementation
    # restored helpers.read_sweep_attrs to itself (a no-op) while introducing
    # a thread-safety hazard; the direct call is equivalent and safe.
    return scan_folder_for_sweep(folder, sweep_id)


@bp.get("/api/sweep/info/<int:file_id>")
async def api_sweep_info(file_id: int):
    path = await run_db_sync(resolve_path, file_id)
    if not path:
        return api_error("file not found or not on disk", 404)
    if Path(path).suffix.lower() not in IMAGE_SUFFIXES:
        return api_error("unsupported file type for XMP", 400)

    attrs = await run_blocking_sync(read_sweep_attrs, path)
    meta = attrs_to_meta(attrs)
    if not meta:
        return api_error("no sweep metadata in this file", 404, code="no_sweep_xmp")
    return api_success({"meta": meta, "path": path})


@bp.get("/api/sweeps/history")
async def api_sweeps_history():
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        limit = 50
    limit = max(1, min(HISTORY_LIMIT_MAX, limit))
    rows = await run_db_sync(
        query_sweep_history,
        limit=limit,
        ref_id=request.args.get("ref") or None,
        match_keys=[k for k in (request.args.get("match") or "").split(",") if k.strip()],
        tolerances={
            "steps": request.args.get("tol_steps") or "exact",
            "cfg": request.args.get("tol_cfg") or "exact",
        },
        completed_only=request.args.get("completed_only") == "1",
        saved_only=request.args.get("saved_only") == "1",
        axis_count=request.args.get("axis_count") or "all",
        date_range=request.args.get("date_range") or "all",
    )

    def _count_total() -> int:
        c = get_readonly_db().execute("SELECT COUNT(*) AS n FROM sweeps").fetchone()
        return int(c["n"]) if c else 0

    total = await run_db_sync(_count_total)
    return api_success(data={"entries": rows, "total": total})


@bp.get("/api/sweep/files/<sweep_id>")
async def api_sweep_files(sweep_id: str):
    if not sweep_id:
        return api_error("sweep_id is required", 400)
    hint_id_raw = request.args.get("file_id")
    if not hint_id_raw:
        return api_error("file_id query parameter is required as folder hint", 400)
    try:
        hint_id = int(hint_id_raw)
    except ValueError:
        return api_error("file_id must be an integer", 400)

    hint_path = await run_db_sync(resolve_path, hint_id)
    if not hint_path:
        return api_error("hint file not found", 404)
    folder = str(Path(hint_path).parent)
    matches = await run_blocking_sync(scan_folder_for_sweep, folder, sweep_id)
    await run_db_sync(attach_file_ids, matches)
    return api_success({"sweep_id": sweep_id, "folder": folder, "matches": matches})

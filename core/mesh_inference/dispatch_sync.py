"""Sync-to-async bridge for mesh inference dispatch."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from core.mesh_inference import get_router
from core.mesh_inference.dispatch_sync_batch import _tagger_batch_coordinator
from core.mesh_inference.tagger_store import get_untagged_file_ids

__all__ = [
    "dispatch_inference_sync",
    "run_tagger_batch",
    "_filter_untagged",
    "_tag_local",
    "_tagger_batch_coordinator",
    "get_router",
    "get_untagged_file_ids",
]

logger = logging.getLogger(__name__)


def dispatch_inference_sync(
    router: Any,
    inference_type: str,
    items: list[Any],
    **kwargs: Any,
) -> Any:
    if not items:
        return []

    async def _run() -> Any:
        return await router.dispatch_inference(inference_type, items, **kwargs)

    return asyncio.run(_run())


def run_tagger_batch(
    file_ids: list[int] | None = None,
    limit: int = 500,
    force: bool = False,
    threshold: float | None = None,
) -> dict:
    from core.jobs_core.jobs import job_manager

    threshold = 0.35 if threshold is None else threshold

    try:
        job = job_manager.start("tagger_cluster", "Tagger Cluster batch (mesh)")
    except ValueError:
        return {"error": "Tagger batch is already running", "code": "job_running"}

    thread = threading.Thread(
        target=_tagger_batch_coordinator,
        args=(job, file_ids, limit, force, threshold),
        daemon=True,
        name="tagger-mesh-coordinator",
    )
    thread.start()
    return {"started": True, "job_id": "tagger_cluster"}


def _filter_untagged(file_ids: list[int]) -> list[int]:
    if not file_ids:
        return []

    from core.services_core.db_state import get_readonly_db

    con = get_readonly_db()
    untagged: list[int] = []
    batch_size = 500
    for index in range(0, len(file_ids), batch_size):
        batch = file_ids[index : index + batch_size]
        placeholders = ",".join("?" * len(batch))
        active = {
            row[0]
            for row in con.execute(
                f"""SELECT id FROM (
                        SELECT f.id
                        FROM files f
                        WHERE f.id IN ({placeholders}) AND f.is_deleted = 0
                    ) sub
                    WHERE NOT EXISTS (
                        SELECT 1 FROM file_hailo_tags h WHERE h.file_id = sub.id
                    )""",
                batch,
            )
        }
        untagged.extend(fid for fid in batch if fid in active)
    return untagged


def _tag_local(filepath: str, threshold: float) -> list[dict] | None:
    try:
        import sys
        from pathlib import Path as _Path

        ext_path = str(_Path(__file__).resolve().parent.parent.parent / "extensions" / "builtin_lan_cowork")
        if ext_path not in sys.path:
            sys.path.insert(0, ext_path)
        from lan_cowork_ext import _get_manager  # type: ignore[import]

        mgr = _get_manager()
        if mgr is None:
            return None
        inf_state = getattr(mgr, "inference_state", None)
        if inf_state is None:
            return None
        engine = inf_state.get_tagger_engine()
        if engine is None:
            return None

        image_bytes = _Path(filepath).read_bytes()
        return engine.predict(image_bytes)
    except Exception as exc:
        logger.debug("Local tagger failed for %s: %s", filepath, exc)
        return None

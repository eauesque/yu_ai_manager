"""Batch WD-Tagger operations.

Run tagging on multiple files using the job manager for progress tracking.

NOTE: Image/video batch processors have been moved to batch_processors.py.
This module re-exports all public symbols for backward compatibility.
"""

from __future__ import annotations

import logging
import threading

from core.event_bus import emit
from core.event_bus.event_types import WD_TAGGER_COMPLETE

from .batch_processors import (  # noqa: F401 -- re-export
    process_image_batch as _process_image_batch,
)
from .batch_processors import (
    process_video_items as _process_video_items,
)

logger = logging.getLogger(__name__)


def run_batch_tagging(
    file_ids: list[int] | None = None,
    limit: int = 100,
    force: bool = False,
    scan_root: str = "",
) -> dict:
    """Start batch WD-Tagger tagging in a background thread.

    Args:
        file_ids: Specific file IDs to tag (None = auto-select untagged)
        limit: Max files to process when auto-selecting
        force: Re-tag files that already have tags
        scan_root: Limit to files under this directory path

    Returns:
        dict with job status or error
    """
    # Delegate to worker process if enabled
    if _try_submit_to_worker(file_ids, limit, force, scan_root):
        return {"started": True, "job_id": "wd_tagger", "worker": True}

    from core.jobs_core.jobs import job_manager

    try:
        job = job_manager.start("wd_tagger", "WD-Tagger batch")
    except ValueError:
        return {"error": "WD-Tagger batch is already running", "code": "job_running"}

    thread = threading.Thread(
        target=_batch_worker,
        args=(job, file_ids, limit, force, scan_root),
        daemon=True,
    )
    thread.start()

    return {"started": True, "job_id": "wd_tagger"}


def _try_submit_to_worker(
    file_ids: list[int] | None, limit: int, force: bool, scan_root: str = "",
) -> bool:
    """Submit task to inference worker if enabled."""
    try:
        from core.configuration.api import load_config_json
        config = load_config_json(None)
        worker_cfg = config.get("inference_worker", {})
        if not worker_cfg.get("enabled", False):
            return False

        from core.inference_worker.bridge import inference_bridge
        if not inference_bridge.is_running:
            return False

        from core.jobs_core.jobs import job_manager
        job_manager.start("wd_tagger", "WD-Tagger batch")

        from core.inference_worker.task_types import InferenceTask, TaskType
        task = InferenceTask(
            task_id="wd_tagger",
            task_type=TaskType.WD_TAGGER_BATCH,
            file_ids=file_ids or [],
            config={
                "force": force,
                "limit": limit,
                "scan_root": scan_root,
                "video_analysis": config.get("video_analysis", {}),
            },
        )
        return inference_bridge.submit_task(task)
    except Exception:
        return False


def _batch_worker(job, file_ids, limit, force, scan_root=""):
    """Background worker for batch tagging.

    Image files are processed via tag_images_batch() for GPU efficiency.
    Video files require keyframe extraction and are processed individually.
    """
    from core.files_core.media_types import is_taggable_file, is_video_file

    from .config_ops import get_config
    from .engine_factory import get_engine
    from .store import (
        get_files_with_wd_tags,
        get_untagged_unknown_files,
    )
    from .tag_postprocess import TagPostProcessor

    try:
        config = get_config()
        engine = get_engine(config)
        pp = TagPostProcessor()
        allow_nsfw = not config.get("nsfw_filter", False)

        if not engine.is_available():
            job.fail("Model not downloaded")
            return

        # Determine target files. The auto-select path already returns
        # paths (avoid an unnecessary 300k-row round trip), the explicit
        # file_ids path needs a path lookup. ``get_active_file_paths``
        # internally chunks IDs to stay under SQLITE_MAX_VARIABLE_NUMBER.
        from core.services_core.wd_tagger_query_service import get_active_file_paths
        if file_ids:
            targets = [{"id": fid} for fid in file_ids]
            path_map = get_active_file_paths(list(file_ids))
        else:
            targets = get_untagged_unknown_files(limit=limit, scan_root=scan_root)
            path_map = {t["id"]: t["path"] for t in targets}

        total = len(targets)
        if total == 0:
            job.complete("No untagged files found")
            return

        job.update(phase="wd_tagger", message=f"WD-Tagger: 0/{total}")
        job.progress(0, total)

        tagged = 0
        skipped = 0
        errors = 0
        xmp_failed = 0

        from pathlib import Path

        # --- Phase 1: pre-scan targets to classify as image/video ---
        image_items: list[tuple[int, int, str]] = []   # (target_idx, fid, filepath)
        video_items: list[tuple[int, int, str]] = []    # (target_idx, fid, filepath)
        skip_indices: set[int] = set()

        # Resolve "already tagged" set in ONE query rather than per-file.
        # Auto-select path is already filtered by NOT EXISTS in
        # get_untagged_unknown_files, so we only need the lookup when the
        # caller passed explicit file_ids and force=False.
        already_tagged: set[int] = set()
        if file_ids and not force:
            already_tagged = get_files_with_wd_tags(list(file_ids))

        for i, target in enumerate(targets):
            fid = target["id"] if isinstance(target, dict) else target
            filepath = path_map.get(fid)
            if not filepath:
                skip_indices.add(i)
                skipped += 1
                continue

            if not Path(filepath).exists():
                skip_indices.add(i)
                skipped += 1
                continue

            if not is_taggable_file(filepath):
                skip_indices.add(i)
                skipped += 1
                continue

            if not force and fid in already_tagged:
                skip_indices.add(i)
                skipped += 1
                continue

            if is_video_file(filepath):
                video_items.append((i, fid, filepath))
            else:
                image_items.append((i, fid, filepath))

        # processed_count: for progress tracking (including skipped)
        processed_count = len(skip_indices)

        # --- Phase 2: batch inference for image files ---
        tagged, errors, processed_count, xmp_failed = _process_image_batch(
            image_items, engine, pp, allow_nsfw, config,
            job, total, tagged, errors, processed_count, xmp_failed,
        )

        if job.cancelled:
            return

        # --- Phase 3: individual processing for video files ---
        tagged, errors, processed_count, xmp_failed = _process_video_items(
            video_items, engine, pp, allow_nsfw, config,
            job, total, tagged, errors, processed_count, xmp_failed,
        )

        if job.cancelled:
            return
        summary = (
            f"WD-Tagger complete: {tagged} tagged, "
            f"{skipped} skipped, {errors} errors"
        )
        if xmp_failed:
            summary += f", {xmp_failed} XMP write failed"
        job.complete(summary)
        emit(WD_TAGGER_COMPLETE, {
            "total": total, "tagged": tagged, "errors": errors,
            "xmp_failed": xmp_failed,
        })
        try:
            from routes.wd_tagger_batch_routes import invalidate_wt_stats_cache
            invalidate_wt_stats_cache()
        except Exception:
            logger.debug("WD-Tagger stats cache invalidate skipped", exc_info=True)

    except Exception as exc:
        logger.error("WD-Tagger batch error: %s", exc)
        job.fail(str(exc))

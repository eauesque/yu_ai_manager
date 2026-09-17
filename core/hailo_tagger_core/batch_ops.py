"""Batch Hailo Remote Tagger operations.

Run tagging on multiple files sequentially via the remote Hailo endpoint.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def run_batch_tagging(
    file_ids: list[int] | None = None,
    limit: int = 100,
    force: bool = False,
) -> dict:
    """Start batch Hailo tagging in a background thread.

    Args:
        file_ids: Specific file IDs to tag (None = auto-select untagged)
        limit: Max files to process when auto-selecting
        force: Re-tag files that already have tags

    Returns:
        dict with job status or error
    """
    from core.jobs_core.jobs import job_manager

    try:
        job = job_manager.start("hailo_tagger", "Hailo Remote Tagger batch")
    except ValueError:
        return {"error": "Hailo Tagger batch is already running", "code": "job_running"}

    thread = threading.Thread(
        target=_batch_worker,
        args=(job, file_ids, limit, force),
        daemon=True,
    )
    thread.start()

    return {"started": True, "job_id": "hailo_tagger"}


def _batch_worker(job, file_ids, limit, force):
    """Background worker for batch Hailo tagging."""
    from .single_ops import tag_one_file
    from .store import get_untagged_files

    try:
        # Determine target files
        targets = [{"id": fid} for fid in file_ids] if file_ids else get_untagged_files(limit=limit)

        total = len(targets)
        if total == 0:
            job.complete("No untagged files found")
            return

        job.update(phase="hailo_tagger", message=f"Hailo Tagger: 0/{total}")
        job.progress(0, total)

        tagged = 0
        skipped = 0
        errors = 0

        for i, target in enumerate(targets):
            if job.cancelled:
                return

            fid = target["id"] if isinstance(target, dict) else target

            try:
                result = tag_one_file(fid, force=force)
                if "error" in result:
                    errors += 1
                elif result.get("skipped"):
                    skipped += 1
                else:
                    tagged += 1
            except Exception as exc:
                logger.error("Hailo batch error for file %d: %s", fid, exc)
                errors += 1

            processed = i + 1
            job.progress(processed, total)
            job.update(
                phase="hailo_tagger",
                message=f"Hailo Tagger: {processed}/{total} (tagged={tagged})",
            )

        job.complete(
            f"Hailo Tagger complete: {tagged} tagged, {skipped} skipped, {errors} errors"
        )

    except Exception as exc:
        logger.error("Hailo Tagger batch error: %s", exc)
        job.fail(str(exc))

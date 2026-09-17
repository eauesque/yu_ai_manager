"""Background scan runner for routes.scan."""

import logging
import time

from core.event_bus import emit
from core.event_bus.event_types import SCAN_DB_BUSY, SCAN_ERROR, SCAN_PROGRESS, SCAN_START
from core.scan.hash_backfill import pause_backfill, resume_backfill
from core.scan.runtime_execute_loop import execute_scan_loop
from core.scan.runtime_finalize import finalize_scan_runtime
from core.scan.runtime_post import auto_register_scan_root
from core.scan.runtime_prepare import (
    collect_scan_targets,
    ensure_remote_access,
    filter_already_scanned,
    init_scan_context,
)
from core.scan_core.scan_state import clear_scan_state
from core.services_core.db_api import get_db
from core.services_core.db_state import close_thread_connections

logger = logging.getLogger(__name__)


def run_scan_background(
    root_path: str,
    recursive: bool,
    force: bool,
    scan_zips: bool = False,
    job=None,
    compute_hash_explicit: bool = False,
    resume: bool = False,
):
    """Run scan in background thread.

    When *job* is provided externally (e.g. from scan-all), this function
    does NOT call job.complete / job.complete_cancelled / job.fail so the
    caller retains full lifecycle control and the job stays ``running=True``
    between roots.
    """
    from core.jobs_core.jobs import job_manager

    _own_job = job is None
    if _own_job:
        try:
            job = job_manager.start("scan", "フォルダスキャン")
        except ValueError:
            return

    scan_started = time.time()
    job_id = job.job_id if hasattr(job, "job_id") else "scan"
    pause_backfill()
    try:
        job.update(phase="initializing")
        job_label = getattr(job, "label", None) or job_id
        emit(SCAN_START, {"root": root_path, "recursive": recursive,
                          "force": force, "job_id": job_id,
                          "label": job_label}, source="scan")
        emit(SCAN_DB_BUSY, {"busy": True, "job_id": job_id}, source="scan")

        # Register to scan_roots immediately at scan start (idempotent: duplicate paths ignored)
        auto_register_scan_root(root_path, recursive)

        ctx = init_scan_context(root_path)
        config = ctx["config"]
        root = ctx["root"]
        is_remote = ctx["is_remote"]
        rfs = ctx["rfs"]

        if is_remote:
            job.update(phase="connecting", message=f"接続確認中: {root_path}")
            if not ensure_remote_access(root, root_path, rfs, job):
                resume_backfill()
                if _own_job and job.cancelled:
                    job.complete_cancelled("接続確認中にキャンセルされました")
                return

        job.update(phase="counting", message="ファイル数をカウント中...")
        emit(SCAN_PROGRESS, {
            "current": 0, "total": 0, "percent": 0,
            "job_id": job_id, "label": job_label,
            "detail": "ファイル数をカウント中...",
            "phase": "counting",
        }, source="scan")
        exclude_dirs = config.get("scan_exclude_dirs", [])
        all_files, enum_errors, archive_cache = collect_scan_targets(
            root, recursive, scan_zips, is_remote, rfs, job,
            exclude_dirs=exclude_dirs,
        )

        # Cancel check after file enumeration
        if job.cancelled:
            clear_scan_state()
            resume_backfill()
            if _own_job:
                job.complete_cancelled("ファイル列挙中にキャンセルされました")
            return

        # On resume: filter out files already registered in DB
        if resume and not force:
            total_before = len(all_files)
            job.update(phase="filtering", message="スキャン済みファイルをフィルタリング中...")
            all_files = filter_already_scanned(all_files, root_path)
            skipped = total_before - len(all_files)
            if skipped > 0:
                emit(SCAN_PROGRESS, {
                    "current": 0, "total": len(all_files), "percent": 0,
                    "job_id": job_id, "label": job_label,
                    "detail": f"{skipped} 件スキップ、残り {len(all_files)} 件をスキャン",
                    "phase": "scanning",
                }, source="scan")

        total_files = len(all_files)
        if total_files == 0:
            msg = f"0ファイル検出 (path={root}, remote={is_remote})"
            if is_remote:
                msg += (
                    " ⚠ リモートパスが応答していない可能性があります。"
                    f"エクスプローラーで {root_path} を開いてから再試行してください。"
                )
            if _own_job:
                job.complete(msg)
            else:
                job.update(message=msg)
            resume_backfill()
            return

        job.update(phase="scanning", message=f"{total_files} files")
        job.progress(0, total_files)

        con = get_db()
        loop_result = execute_scan_loop(
            con,
            all_files,
            config,
            root_path=root_path,
            recursive=recursive,
            force=force,
            scan_zips=scan_zips,
            compute_hash_explicit=compute_hash_explicit,
            job=job,
            archive_cache=archive_cache,
        )

        if loop_result["cancelled"]:
            clear_scan_state()
            resume_backfill()
            if _own_job:
                job.complete_cancelled()
            return

        finalize_scan_runtime(
            root_path=root_path,
            recursive=recursive,
            job=job,
            own_job=_own_job,
            job_id=job_id,
            job_label=job_label,
            scan_started=scan_started,
            count=loop_result["count"],
            enum_errors=enum_errors,
            loop_result=loop_result,
        )

        resume_backfill()
    except Exception as e:
        resume_backfill()
        clear_scan_state()
        emit(SCAN_ERROR, {"error": str(e), "job_id": job_id}, source="scan")
        if _own_job:
            job.fail(str(e))
        else:
            job.update(message=f"Error: {e}")
    finally:
        close_thread_connections()

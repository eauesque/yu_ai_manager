"""Hailo VLM subprocess batch analysis.

Runs AI analysis in a separate process to avoid blocking the Quart
server (Hailo VLM holds the GIL during NPU inference).
"""

import logging
import multiprocessing
import threading

logger = logging.getLogger(__name__)


def _run_in_subprocess(file_ids: list) -> None:
    """Run batch analysis in a separate process (for Hailo VLM)."""
    from core.hailo_device_core.hailo_npu_lock import HailoNpuLock
    from core.services_core.db_state import get_db_path

    db_path = str(get_db_path())

    # Acquire NPU lock before spawning subprocess
    npu_lock = HailoNpuLock(timeout=5.0)
    if not npu_lock.try_acquire():
        logger.warning(
            "Hailo NPU is busy (held by another process). "
            "Cannot start batch AI analysis now."
        )
        return

    # Communicate progress to the main process via shared memory
    shared_current = multiprocessing.Value("i", 0)
    shared_total = multiprocessing.Value("i", len(file_ids))
    shared_analyzed = multiprocessing.Value("i", 0)

    proc = multiprocessing.Process(
        target=_subprocess_batch_entry,
        args=(file_ids, db_path, shared_current, shared_total, shared_analyzed),
        daemon=True,
        name="hailo-ai-analysis",
    )
    proc.start()
    logger.info(
        "Hailo AI analysis started in subprocess (pid=%d, files=%d)",
        proc.pid, len(file_ids),
    )

    # Monitor thread: detect process completion, update JobManager, release lock
    threading.Thread(
        target=_monitor_subprocess,
        args=(proc, shared_current, shared_total, shared_analyzed, npu_lock),
        daemon=True,
    ).start()


def _subprocess_batch_entry(
    file_ids: list, db_path: str,
    shared_current=None, shared_total=None, shared_analyzed=None,
) -> None:
    """Entry point executed in the subprocess for batch analysis."""
    import ai_analysis
    from core.analysis_api.single_ops import _resolve_with_fallback
    from core.configuration.api import load_config_json
    from core.services_core.db_cipher import apply_key as _apply_key
    from core.services_core.db_cipher import sqlite3 as _cipher_sqlite3

    config = load_config_json(None)
    ai_config = config.get("ai_analysis", {})
    engine_type, engine_kwargs, err = _resolve_with_fallback(ai_config)
    if err:
        return

    engine = ai_analysis.get_engine(engine_type, **engine_kwargs)
    read_con = _cipher_sqlite3.connect(db_path, timeout=5.0)
    _apply_key(read_con)
    read_con.row_factory = _cipher_sqlite3.Row
    read_con.execute("PRAGMA query_only=ON")
    read_con.execute("PRAGMA journal_mode=WAL")
    write_con = _cipher_sqlite3.connect(db_path, timeout=30.0)
    _apply_key(write_con)
    write_con.row_factory = _cipher_sqlite3.Row
    write_con.execute("PRAGMA journal_mode=WAL")
    write_con.execute("PRAGMA busy_timeout=30000")
    write_con.execute("PRAGMA synchronous=NORMAL")
    total = len(file_ids)
    analyzed = 0
    save_batch: list[tuple[int, str, object]] = []
    save_batch_size = 8

    if shared_total is not None:
        shared_total.value = total

    try:
        from pathlib import Path

        from core.analysis_api.batch_runner import _iter_analysis_inputs
        from core.files_core.media_types import is_video_file
        from core.files_core.video_keyframes import video_keyframes_context

        for item in _iter_analysis_inputs(read_con, file_ids):
            fid = item["id"]
            try:
                file_path = Path(item["path"])
                if not file_path.exists():
                    continue
                existing_tags = item["tags"]
                existing_prompt = item["prompt"]

                if is_video_file(str(file_path)):
                    va_cfg = config.get("video_analysis", {})
                    with video_keyframes_context(
                        str(file_path),
                        count=va_cfg.get("keyframe_count", 4),
                        strategy=va_cfg.get("strategy", "uniform"),
                        scene_threshold=va_cfg.get("scene_threshold", 0.4),
                    ) as frames:
                        if not frames:
                            continue
                        result = engine.analyze_image(
                            frames[0], existing_tags, existing_prompt,
                        )
                else:
                    result = engine.analyze_image(
                        file_path, existing_tags, existing_prompt,
                    )
                save_batch.append((fid, engine.get_name(), result))
                if len(save_batch) >= save_batch_size:
                    ai_analysis.save_analysis_batch(write_con, save_batch)
                    save_batch.clear()
                analyzed += 1
            except Exception:
                # Per file, inside the batch loop: one file is skipped and the
                # count simply does not advance for it.
                logger.debug("analysis failed for file %s", fid, exc_info=True)

            # Write progress to shared memory
            if shared_current is not None:
                shared_current.value = item["position"] + 1
            if shared_analyzed is not None:
                shared_analyzed.value = analyzed

        if save_batch:
            ai_analysis.save_analysis_batch(write_con, save_batch)
    finally:
        read_con.close()
        write_con.close()


def _monitor_subprocess(proc: multiprocessing.Process,
                        shared_current=None, shared_total=None,
                        shared_analyzed=None, npu_lock=None) -> None:
    """Periodically reflect subprocess progress to JobManager and detect completion."""
    import time

    from core.jobs_core.jobs import job_manager

    while proc.is_alive():
        try:
            job = job_manager.get_raw_job("ai_analysis")
            if job and shared_current is not None and shared_total is not None:
                cur = shared_current.value
                tot = shared_total.value
                done = shared_analyzed.value if shared_analyzed is not None else 0
                job.progress(cur, tot)
                job.update(message=f"AI分析中... {cur}/{tot} ({done}件完了)")
        except Exception:
            # Progress reporting only; the analysis itself carries on.
            logger.debug("progress update failed", exc_info=True)
        time.sleep(2)

    # Release NPU lock after process completion
    if npu_lock is not None:
        import contextlib
        with contextlib.suppress(Exception):
            npu_lock.release()

    # Reflect final state
    try:
        job = job_manager.get_raw_job("ai_analysis")
        if job and job.running:
            if shared_current is not None and shared_total is not None:
                cur = shared_current.value
                tot = shared_total.value
                done = shared_analyzed.value if shared_analyzed is not None else 0
                job.progress(cur, tot)
            if proc.exitcode == 0:
                done = shared_analyzed.value if shared_analyzed is not None else 0
                tot = shared_total.value if shared_total is not None else 0
                job.complete(f"AI分析完了: {done}/{tot}件 (Hailo VLM)")
            else:
                job.fail(f"Hailo VLM プロセスが異常終了 (exit={proc.exitcode})")
    except Exception:
        # This is the block that calls complete()/fail(). If it throws, the job
        # is never marked done and the UI shows "AI分析中..." forever.
        logger.error("analysis job was left unfinished", exc_info=True)


def _cleanup_stale_hailo_job() -> None:
    """Clean up a job stuck in running state after its subprocess has terminated."""
    import os

    from core.jobs_core.jobs import job_manager

    job = job_manager.get_raw_job("ai_analysis")
    if not job or not job.running:
        return

    # Check if the hailo-ai-analysis process is still alive
    for proc_name in ("hailo-ai-analysis",):
        try:
            # Scan /proc to check process name
            for pid_dir in os.listdir("/proc"):
                if not pid_dir.isdigit():
                    continue
                try:
                    with open(f"/proc/{pid_dir}/cmdline", "rb") as _cmdline_f:
                        cmdline = _cmdline_f.read()
                    if proc_name.encode() in cmdline:
                        return  # Still running
                except (OSError, PermissionError):
                    continue
        except OSError:
            pass

    # Process not found -- clean up the job
    logger.info("Stale Hailo AI analysis job detected, cleaning up")
    job.fail("Hailo VLM プロセスが予期せず終了しました (サーバー再起動等)")

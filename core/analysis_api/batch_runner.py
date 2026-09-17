"""Background batch analyzer runner."""

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

import ai_analysis
from core.analysis_api.single_ops import _resolve_with_fallback
from core.configuration.api import load_config_json
from core.event_bus import emit
from core.event_bus.event_types import BATCH_ANALYSIS_COMPLETE
from core.files_core.media_types import is_video_file
from core.files_core.video_keyframes import video_keyframes_context
from core.jobs_core.jobs import job_manager
from core.services_core.db_api import get_db
from core.services_core.db_state import get_readonly_db

_INPUT_CHUNK_SIZE = 200


def run_batch_analyze(file_ids: list, server_ids: list[str] | None = None):
    """Execute batch analysis.

    When multiple server_ids are specified, files are distributed
    round-robin across servers for parallel execution.
    """
    if server_ids and len(server_ids) > 1:
        _run_parallel_batch(file_ids, server_ids)
        return

    # Single server (legacy behavior)
    server_id = server_ids[0] if server_ids else None
    _run_single_batch(file_ids, server_id=server_id)


def _run_single_batch(
    file_ids: list,
    server_id: str | None = None,
    *,
    progress_cb=None,
    cancel_check=None,
):
    """Execute batch analysis on a single server.

    When progress_cb/cancel_check are None, JobManager is used (legacy behavior).
    In parallel mode, these are passed from the coordinator.
    """
    use_job = progress_cb is None
    job = None

    if use_job:
        try:
            job = job_manager.start("ai_analysis", "AI分析")
        except ValueError:
            return
        progress_cb = lambda cur, tot, msg: (
            job.progress(cur, tot),
            job.update(message=msg),
        )
        cancel_check = lambda: job.cancelled

    try:
        config = load_config_json(None)
        ai_config = config.get("ai_analysis", {})
        engine_type, engine_kwargs, err = _resolve_with_fallback(
            ai_config, server_id=server_id,
        )
        if err:
            if job:
                job.fail(err)
            return 0
        engine = ai_analysis.get_engine(engine_type, **engine_kwargs)
        read_con = get_readonly_db()
        write_con = get_db()
        total = len(file_ids)
        analyzed = 0
        save_batch: list[tuple[int, str, object]] = []
        save_batch_size = 8

        if use_job:
            job.update(phase="ai_analysis", message=f"AI分析中... 0/{total}")
            job.progress(0, total)

        for item in _iter_analysis_inputs(read_con, file_ids):
            if cancel_check and cancel_check():
                if save_batch:
                    ai_analysis.save_analysis_batch(write_con, save_batch)
                    save_batch.clear()
                if job:
                    job.complete_cancelled()
                return analyzed
            fid = item["id"]
            try:
                file_path = Path(item["path"])
                if not file_path.exists():
                    continue
                existing_tags = item["tags"]
                existing_prompt = item["prompt"]

                if is_video_file(str(file_path)):
                    va_cfg = config.get("video_analysis", {})
                    va_count = va_cfg.get("keyframe_count", 4)
                    va_strategy = va_cfg.get("strategy", "uniform")
                    va_scene_th = va_cfg.get("scene_threshold", 0.4)
                    with video_keyframes_context(
                        str(file_path), count=va_count, strategy=va_strategy,
                        scene_threshold=va_scene_th,
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
            except Exception as e:
                logger.error("[AI Analysis] Error for file %d: %s", fid, e)
            if progress_cb:
                progress_cb(
                    item["position"] + 1, total,
                    f"AI分析中... {item['position'] + 1}/{total} ({analyzed}件完了)",
                )
        if save_batch:
            ai_analysis.save_analysis_batch(write_con, save_batch)
        if job:
            job.complete(f"AI分析完了: {analyzed}/{total}件")
        emit(BATCH_ANALYSIS_COMPLETE, {"total": total, "analyzed": analyzed})
        return analyzed
    except Exception as e:
        if job:
            job.fail(str(e))
        return 0


def _iter_analysis_inputs(read_con, file_ids: list[int]):
    """Yield path/tags/prompt rows for file_ids in caller order.

    Batch analysis used to run three SELECTs per file. Chunked preload keeps
    memory bounded while reducing DB round-trips for large batches.
    """
    for start in range(0, len(file_ids), _INPUT_CHUNK_SIZE):
        chunk = file_ids[start:start + _INPUT_CHUNK_SIZE]
        if not chunk:
            continue
        placeholders = ",".join("?" for _ in chunk)
        cursor = read_con.execute(
            "SELECT f.id, f.path, tm.raw_prompt "
            "FROM files f "
            "LEFT JOIN templates tm ON tm.file_id = f.id "
            f"WHERE f.id IN ({placeholders}) AND f.is_deleted = 0",
            chunk,
        )
        by_id = {
            int(row["id"]): {
                "id": int(row["id"]),
                "path": row["path"],
                "prompt": row["raw_prompt"],
                "tags": [],
            }
            for row in cursor
        }
        tag_rows = read_con.execute(
            "SELECT ft.file_id, t.tag "
            "FROM file_tags ft JOIN tags t ON t.id = ft.tag_id "
            f"WHERE ft.file_id IN ({placeholders})",
            chunk,
        )
        for row in tag_rows:
            item = by_id.get(int(row["file_id"]))
            if item is not None:
                item["tags"].append(row["tag"])
        for offset, fid in enumerate(chunk):
            item = by_id.get(int(fid))
            if item is not None:
                out = dict(item)
                out["position"] = start + offset
                yield out


# ── Parallel batch (multiple servers) ──────────────────────────────────────

def _run_parallel_batch(file_ids: list, server_ids: list[str]):
    """Distribute files round-robin across multiple servers and execute in parallel."""
    try:
        job = job_manager.start("ai_analysis", "AI分析 (並列)")
    except ValueError:
        return

    n_servers = len(server_ids)
    # Round-robin distribution
    chunks: list[list[int]] = [[] for _ in range(n_servers)]
    for i, fid in enumerate(file_ids):
        chunks[i % n_servers].append(fid)

    total = len(file_ids)
    job.update(
        phase="ai_analysis",
        message=f"AI分析中 ({n_servers}サーバー並列)... 0/{total}",
    )
    job.progress(0, total)

    # Track progress of each worker
    lock = threading.Lock()
    progress = {"done": [0] * n_servers, "total": [len(c) for c in chunks]}
    cancel_event = threading.Event()
    errors: list[str] = []

    def cancel_check():
        return job.cancelled or cancel_event.is_set()

    def make_progress_cb(idx):
        def cb(cur, tot, msg):
            with lock:
                progress["done"][idx] = cur
                all_done = sum(progress["done"])
                job.progress(all_done, total)
                # Progress message including server name
                analyzed_total = sum(progress["done"])
                job.update(
                    message=f"AI分析中 ({n_servers}サーバー並列)... "
                            f"{analyzed_total}/{total}",
                )
        return cb

    def worker(idx, chunk, sid):
        try:
            result = _run_single_batch(
                chunk, server_id=sid,
                progress_cb=make_progress_cb(idx),
                cancel_check=cancel_check,
            )
            if result is None:
                result = 0
            with lock:
                progress["done"][idx] = len(chunk)
        except Exception as e:
            logger.error("Parallel batch worker %s failed: %s", sid, e)
            with lock:
                errors.append(f"{sid}: {e}")

    threads = []
    for idx, (chunk, sid) in enumerate(zip(chunks, server_ids, strict=False)):
        if not chunk:
            continue
        t = threading.Thread(
            target=worker, args=(idx, chunk, sid),
            daemon=True, name=f"ai-batch-{sid}",
        )
        threads.append(t)
        t.start()

    # Wait for all workers to complete
    for t in threads:
        t.join()

    all_done = sum(progress["done"])
    if errors:
        err_msg = "; ".join(errors)
        job.complete(f"AI分析完了: {all_done}/{total}件 (エラーあり: {err_msg})")
    else:
        job.complete(f"AI分析完了: {all_done}/{total}件 ({n_servers}サーバー並列)")

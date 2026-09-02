"""WD-Tagger batch handler (inside worker process).

Subprocess-only handler. Receives DB path and config as arguments.
Progress is reported to the Quart web process via TaskQueue.
"""

import logging
from importlib import import_module
from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3


def _wt(module_name: str):
    """Import a module from the WD-Tagger extension core_impl package."""
    return import_module(
        f"extensions.builtin_wd_tagger.core_impl.{module_name}"
    )

from .task_queue import TaskQueue
from .task_types import (
    InferenceResult,
    InferenceTask,
    ProgressUpdate,
    TaskStatus,
)

logger = logging.getLogger(__name__)


def run_wd_tagger_batch(
    queue: TaskQueue,
    task: InferenceTask,
    db_path: str,
) -> InferenceResult:
    """Execute WD-Tagger batch inference."""
    from core.files_core.media_types import is_taggable_file, is_video_file
    from core.files_core.video_keyframes import video_keyframes_context
    from core.files_core.video_tag_merge import merge_wd_tag_results
    get_config = _wt("config_ops").get_config
    get_engine = _wt("engine_factory").get_engine
    _store = _wt("store")
    get_untagged_unknown_files = _store.get_untagged_unknown_files
    get_wd_tags = _store.get_wd_tags
    save_wd_tags_batch = _store.save_wd_tags_batch
    write_xmp_to_file = _wt("xmp_write").write_xmp_to_file
    build_xmp_packet = _wt("xmp_xml").build_xmp_packet

    wt_config = get_config()
    engine = get_engine(wt_config)

    if not engine.is_available():
        return InferenceResult(
            task_id=task.task_id, status=TaskStatus.ERROR,
            error="Model not downloaded",
        )

    force = task.config.get("force", False)
    video_config = task.config.get("video_analysis", {})

    # Determine target files
    if task.file_ids:
        targets = [{"id": fid} for fid in task.file_ids]
    else:
        limit = task.config.get("limit", 100)
        targets = get_untagged_unknown_files(limit=limit)

    total = len(targets)
    if total == 0:
        return InferenceResult(
            task_id=task.task_id, status=TaskStatus.COMPLETE,
            result={"processed": 0, "message": "No untagged files found"},
        )

    queue.put_result(ProgressUpdate(
        task_id=task.task_id, phase="wd_tagger",
        message=f"WD-Tagger: 0/{total}", current=0, total=total,
    ))

    read_con = sqlite3.connect(db_path, timeout=5.0)
    apply_key(read_con)
    read_con.row_factory = sqlite3.Row
    read_con.execute("PRAGMA query_only=ON")
    read_con.execute("PRAGMA journal_mode=WAL")
    tagged = 0
    skipped = 0
    errors = 0
    xmp_failed = 0
    save_batch: list[tuple[int, object]] = []
    save_batch_size = 8

    try:
        for i, target in enumerate(targets):
            fid = target["id"] if isinstance(target, dict) else target
            filepath = None

            try:
                row = read_con.execute(
                    "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
                    (fid,),
                ).fetchone()
                if not row:
                    skipped += 1
                    continue

                filepath = row["path"]
                if not Path(filepath).exists():
                    skipped += 1
                    continue

                if not is_taggable_file(filepath):
                    skipped += 1
                    continue

                if not force:
                    existing = get_wd_tags(fid)
                    if existing:
                        skipped += 1
                        continue

                is_video = is_video_file(filepath)
                if is_video:
                    kf_count = video_config.get("keyframe_count", 4)
                    strategy = video_config.get("strategy", "uniform")
                    scene_th = video_config.get("scene_threshold", 0.4)
                    store_per_kf = video_config.get("store_per_keyframe", False)
                    with video_keyframes_context(
                        filepath, count=kf_count, strategy=strategy,
                        scene_threshold=scene_th,
                    ) as frames:
                        if not frames:
                            errors += 1
                            continue
                        frame_results = [
                            engine.tag_image(str(f)) for f in frames
                        ]
                    result = merge_wd_tag_results(frame_results)
                    if store_per_kf:
                        from core.files_core.video_keyframe_store import (
                            save_keyframe_results,
                        )
                        kf_data = []
                        for kidx, fr in enumerate(frame_results):
                            kf_data.append({
                                "keyframe_idx": kidx,
                                "timestamp_ms": 0,
                                "wd_tags": [
                                    {
                                        "tag": t.tag,
                                        "confidence": t.confidence,
                                        "category": t.category,
                                    }
                                    for t in fr.tags
                                ],
                            })
                        save_keyframe_results(
                            fid, kf_data, model=result.model,
                        )
                else:
                    result = engine.tag_image(filepath)

                save_batch.append((fid, result))
                if len(save_batch) >= save_batch_size:
                    save_wd_tags_batch(save_batch)
                    save_batch.clear()

                if not is_video and wt_config.get("write_xmp", True):
                    tag_names = [t.tag for t in result.tags]
                    xmp_xml = build_xmp_packet(
                        tag_names=tag_names,
                        model=result.model,
                        general_threshold=wt_config.get(
                            "general_threshold", 0.35,
                        ),
                        character_threshold=wt_config.get(
                            "character_threshold", 0.85,
                        ),
                    )
                    if not write_xmp_to_file(filepath, xmp_xml):
                        xmp_failed += 1

                tagged += 1

            except Exception as exc:
                logger.warning("WD-Tagger error for file %s: %s", fid, exc)
                errors += 1

            queue.put_result(ProgressUpdate(
                task_id=task.task_id, phase="wd_tagger",
                message=(
                    f"WD-Tagger: {i + 1}/{total} "
                    f"({tagged} tagged, {skipped} skipped)"
                ),
                current=i + 1, total=total,
            ))

        if save_batch:
            save_wd_tags_batch(save_batch)
    finally:
        read_con.close()

    msg = (
        f"WD-Tagger complete: {tagged} tagged, "
        f"{skipped} skipped, {errors} errors"
    )
    if xmp_failed:
        msg += f", {xmp_failed} XMP write failed"
    return InferenceResult(
        task_id=task.task_id,
        status=TaskStatus.COMPLETE,
        result={"processed": tagged, "total": total, "message": msg},
    )

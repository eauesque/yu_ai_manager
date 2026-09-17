"""AI Analysis batch handler (inside worker process).

Subprocess-only handler. Receives DB path and config as arguments.
Progress is reported to the Quart web process via TaskQueue.
"""

import logging
from pathlib import Path

from core.analysis_api.batch_runner import _iter_analysis_inputs
from core.services_core.db_cipher import apply_key, sqlite3

from .task_queue import TaskQueue
from .task_types import (
    InferenceResult,
    InferenceTask,
    ProgressUpdate,
    TaskStatus,
)

logger = logging.getLogger(__name__)


def run_ai_analysis_batch(
    queue: TaskQueue,
    task: InferenceTask,
    db_path: str,
) -> InferenceResult:
    """Execute AI Analysis batch inference."""
    import ai_analysis

    ai_config = task.config.get("ai_analysis", {})
    video_config = task.config.get("video_analysis", {})

    engine_type, engine_kwargs, err = _resolve_engine(ai_config)
    if err:
        return InferenceResult(
            task_id=task.task_id, status=TaskStatus.ERROR, error=err,
        )

    engine = ai_analysis.get_engine(engine_type, **engine_kwargs)
    read_con = sqlite3.connect(db_path, timeout=5.0)
    apply_key(read_con)
    read_con.row_factory = sqlite3.Row
    read_con.execute("PRAGMA query_only=ON")
    read_con.execute("PRAGMA journal_mode=WAL")
    write_con = sqlite3.connect(db_path, timeout=30.0)
    apply_key(write_con)
    write_con.row_factory = sqlite3.Row
    write_con.execute("PRAGMA journal_mode=WAL")
    write_con.execute("PRAGMA busy_timeout=30000")
    write_con.execute("PRAGMA synchronous=NORMAL")

    file_ids = task.file_ids
    total = len(file_ids)
    analyzed = 0
    save_batch: list[tuple[int, str, object]] = []
    save_batch_size = 8

    queue.put_result(ProgressUpdate(
        task_id=task.task_id, phase="ai_analysis",
        message=f"AI\u5206\u6790\u4e2d... 0/{total}", current=0, total=total,
    ))

    try:
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
                    va_count = video_config.get("keyframe_count", 4)
                    va_strategy = video_config.get("strategy", "uniform")
                    va_scene_th = video_config.get("scene_threshold", 0.4)
                    with video_keyframes_context(
                        str(file_path), count=va_count,
                        strategy=va_strategy, scene_threshold=va_scene_th,
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
                logger.warning("AI Analysis error for file %s: %s", fid, e)

            queue.put_result(ProgressUpdate(
                task_id=task.task_id, phase="ai_analysis",
                message=(
                    f"AI\u5206\u6790\u4e2d... {item['position'] + 1}/{total} "
                    f"({analyzed}\u4ef6\u5b8c\u4e86)"
                ),
                current=item["position"] + 1, total=total,
            ))

        if save_batch:
            ai_analysis.save_analysis_batch(write_con, save_batch)
    finally:
        read_con.close()
        write_con.close()

    return InferenceResult(
        task_id=task.task_id,
        status=TaskStatus.COMPLETE,
        result={
            "processed": analyzed,
            "total": total,
            "message": f"AI\u5206\u6790\u5b8c\u4e86: {analyzed}/{total}\u4ef6",
        },
    )


def _resolve_engine(ai_config: dict):
    """Resolve engine type and parameters.

    When ``fallback_local_only`` is enabled, cloud engines are denied.
    """
    engine_type = ai_config.get("engine", "")
    if not engine_type:
        engine_type = "ollama"

    local_only = bool(ai_config.get("fallback_local_only", False))

    kwargs: dict = {}
    if engine_type == "claude_api":
        if local_only:
            return None, None, (
                "\u30ed\u30fc\u30ab\u30eb\u9650\u5b9a\u30e2\u30fc\u30c9\u304c\u6709\u52b9\u306e\u305f\u3081"
                "Claude API \u306f\u4f7f\u7528\u3067\u304d\u307e\u305b\u3093"
            )
        kwargs["api_key"] = ai_config.get("api_key", "")
        kwargs["model"] = ai_config.get("model", "claude-sonnet-4-6-20250514")
        if not kwargs["api_key"]:
            return None, None, "Claude API\u30ad\u30fc\u304c\u8a2d\u5b9a\u3055\u308c\u3066\u3044\u307e\u305b\u3093"
    elif engine_type == "openai":
        if local_only:
            return None, None, (
                "\u30ed\u30fc\u30ab\u30eb\u9650\u5b9a\u30e2\u30fc\u30c9\u304c\u6709\u52b9\u306e\u305f\u3081"
                "OpenAI API \u306f\u4f7f\u7528\u3067\u304d\u307e\u305b\u3093"
            )
        kwargs["api_key"] = ai_config.get("openai_api_key", "")
        kwargs["model"] = ai_config.get("openai_model", "gpt-4o-mini")
        if not kwargs["api_key"]:
            return None, None, "OpenAI API\u30ad\u30fc\u304c\u8a2d\u5b9a\u3055\u308c\u3066\u3044\u307e\u305b\u3093"
    elif engine_type == "ollama":
        kwargs["base_url"] = ai_config.get("ollama_url", "http://localhost:11434")
        kwargs["model"] = ai_config.get("ollama_model", "llava:latest")
    elif engine_type == "openai_compat":
        base_url = ai_config.get("openai_compat_url", "")
        if local_only:
            from core.analysis_api.config_ops import _is_private_url
            if not _is_private_url(base_url):
                return None, None, (
                    "\u30ed\u30fc\u30ab\u30eb\u9650\u5b9a\u30e2\u30fc\u30c9\u304c\u6709\u52b9\u3067\u3059\u304c"
                    "\u3001OpenAI\u4e92\u63db\u30b5\u30fc\u30d0\u30fc\u306e URL \u304c"
                    "\u30ed\u30fc\u30ab\u30eb\u30a2\u30c9\u30ec\u30b9\u3067\u306f\u3042\u308a\u307e\u305b\u3093"
                )
        kwargs["base_url"] = base_url
        kwargs["api_key"] = ai_config.get("openai_compat_api_key", "")
        kwargs["model"] = ai_config.get("openai_compat_model", "")
    elif engine_type == "hailo_vlm":
        kwargs["model_name"] = ai_config.get(
            "hailo_vlm_model", "qwen2-vl-2b-instruct",
        )
    else:
        return None, None, f"Unknown engine: {engine_type}"

    return engine_type, kwargs, None

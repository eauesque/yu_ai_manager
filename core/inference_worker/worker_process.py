"""Inference worker main loop (Quart-independent subprocess).

Runs in a separate process, retrieving tasks from the task queue and executing inference.
Freed from Python's GIL constraints; Quart responses are not delayed during GPU inference.
"""

import logging
import sys
import threading
import time
import traceback

from .task_queue import TaskQueue
from .task_types import (
    ControlResponse,
    InferenceResult,
    InferenceTask,
    ProgressUpdate,
    ShutdownSentinel,
    StreamingToken,
    TaskStatus,
    TaskType,
)

logger = logging.getLogger(__name__)

# Module-level dict for cancel flags shared between main and control daemon
_cancel_flags: dict[str, bool] = {}


def _control_daemon(queue: TaskQueue, cancel_flags: dict[str, bool], current_task_id: list[str | None] | None = None) -> None:
    """Daemon thread to handle control messages from Quart.
    
    Polls the control queue and processes commands like cancel, status_query, etc.
    """
    try:
        while True:
            msg = queue.get_control(timeout=0.5)
            if msg is None:
                continue

            if msg.op == "cancel":
                if msg.task_id in cancel_flags:
                    cancel_flags[msg.task_id] = True
                    resp = ControlResponse(
                        task_id=msg.task_id,
                        op="cancel",
                        ok=True,
                    )
                else:
                    resp = ControlResponse(
                        task_id=msg.task_id,
                        op="cancel",
                        ok=False,
                        error="Task not found",
                    )
                queue.put_control_response(resp)
            elif msg.op == "close_llm":
                try:
                    from core.inference_worker.handler_hailo_llm import (
                        release_llm_lock_holder,
                    )
                    release_llm_lock_holder()
                    resp = ControlResponse(
                        task_id=msg.task_id,
                        op=msg.op,
                        ok=True,
                        result={"action": "llm_released"},
                    )
                except Exception as e:
                    logger.error(f"Error releasing LLM: {e}")
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=False, error=str(e),
                    )
                queue.put_control_response(resp)
            elif msg.op == "close_vlm":
                # Release VLM owned by worker subprocess (used by AI analysis batch)
                try:
                    from core.hailo_device_core.device_manager import release_device
                    release_device("vlm")
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=True,
                        result={"action": "vlm_released"},
                    )
                except Exception as e:
                    logger.error(f"Error releasing VLM: {e}")
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=False, error=str(e),
                    )
                queue.put_control_response(resp)
            elif msg.op == "clear_context":
                try:
                    from core.inference_worker.handler_hailo_llm import clear_llm_context
                    ok = clear_llm_context()
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=ok,
                        result={"cleared": ok},
                    )
                except Exception as e:
                    logger.error(f"Error clearing LLM context: {e}")
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=False, error=str(e),
                    )
                queue.put_control_response(resp)
            elif msg.op == "unload":
                # Release a specific owner. payload={"model": "llm"|"vlm"|...}
                target = (msg.payload or {}).get("model", "llm")
                try:
                    if target in ("llm", "llm_subprocess"):
                        from core.inference_worker.handler_hailo_llm import (
                            release_llm_lock_holder,
                        )
                        release_llm_lock_holder()
                    else:
                        from core.hailo_device_core.device_manager import release_device
                        release_device(target)
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=True,
                        result={"unloaded": target},
                    )
                except Exception as e:
                    logger.error(f"Error unloading {target}: {e}")
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=False, error=str(e),
                    )
                queue.put_control_response(resp)
            elif msg.op == "status_query":
                # Report worker-side LLM / VLM state
                try:
                    from core.hailo_device_core.device_manager import is_model_active
                    from core.inference_worker.handler_hailo_llm import llm_status

                    result = {
                        "current_task": current_task_id[0] if current_task_id else None,
                        "llm_active": is_model_active("llm_subprocess"),
                        "vlm_active": is_model_active("vlm"),
                    }
                    result.update(llm_status())
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=True, result=result,
                    )
                except Exception as e:
                    resp = ControlResponse(
                        task_id=msg.task_id, op=msg.op, ok=False, error=str(e),
                    )
                queue.put_control_response(resp)
            else:
                resp = ControlResponse(
                    task_id=msg.task_id,
                    op=msg.op,
                    ok=False,
                    error=f"Unknown operation: {msg.op}",
                )
                queue.put_control_response(resp)
    except Exception as exc:
        logger.error("Control daemon error: %s", exc)


def _configure_worker_logging() -> None:
    """Set up dedicated logging for the spawned worker subprocess.

    The child has no inherited logging config under spawn. We attach a
    file handler so tracebacks (including import-time failures of handlers)
    end up in logs/inference_worker.log instead of vanishing to stderr.
    """
    import os
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    log_dir = repo_root / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    log_path = log_dir / "inference_worker.log"
    handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"
        )
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.info("Worker logging initialised (pid=%d cwd=%s)", os.getpid(), os.getcwd())


def worker_main(queue: TaskQueue, db_path: str, config: dict) -> None:
    """Worker process entry point.

    Args:
        queue: Bidirectional communication queue
        db_path: DB file path (string -- Path may not be picklable)
        config: Application configuration (dict)
    """
    _configure_worker_logging()
    try:
        _worker_main_inner(queue, db_path, config)
    except BaseException:
        logger.critical("Worker crashed during startup:\n%s", traceback.format_exc())
        raise


def _worker_main_inner(queue: TaskQueue, db_path: str, config: dict) -> None:
    logger.info("Inference worker started (pid=%d)", __import__("os").getpid())

    current_task_id: list[str | None] = [None]
    control_thread = threading.Thread(
        target=_control_daemon,
        args=(queue, _cancel_flags, current_task_id),
        daemon=True,
        name="control-daemon",
    )
    control_thread.start()

    while True:
        task = queue.get_task(timeout=2.0)
        if task is None:
            # Timeout — no task ready, keep polling
            continue
        if isinstance(task, ShutdownSentinel):
            logger.info("Inference worker shutting down")
            break

        try:
            _handle_task(queue, task, db_path, config, current_task_id)
        except Exception as exc:
            logger.error(
                "Task %s failed: %s\n%s",
                task.task_id, exc, traceback.format_exc(),
            )
            queue.put_result(InferenceResult(
                task_id=task.task_id,
                status=TaskStatus.ERROR,
                error=str(exc),
            ))
        finally:
            _cancel_flags.pop(task.task_id, None)


def _handle_task(
    queue: TaskQueue,
    task: InferenceTask,
    db_path: str,
    config: dict,
    current_task_id: list[str | None] | None = None,
) -> None:
    """Execute inference according to the task type."""
    if current_task_id is not None:
        current_task_id[0] = task.task_id
    
    queue.put_result(ProgressUpdate(
        task_id=task.task_id,
        phase="starting",
        message=f"Starting {task.task_type.value}",
    ))

    try:
        # Register cancel flag for this task
        _cancel_flags[task.task_id] = False

        if task.task_type == TaskType.WD_TAGGER_BATCH:
            result = _run_wd_tagger_batch(queue, task, db_path, config)
        elif task.task_type == TaskType.AI_ANALYSIS_BATCH:
            result = _run_ai_analysis_batch(queue, task, db_path, config)
        elif task.task_type == TaskType.LLM_CHAT_STREAM:
            result = _run_llm_chat_stream(queue, task, db_path, config)
        else:
            result = InferenceResult(
                task_id=task.task_id,
                status=TaskStatus.ERROR,
                error=f"Unknown task type: {task.task_type}",
            )

        queue.put_result(result)
    finally:
        if current_task_id is not None:
            current_task_id[0] = None


def _run_wd_tagger_batch(
    queue: TaskQueue,
    task: InferenceTask,
    db_path: str,
    config: dict,
) -> InferenceResult:
    """WD-Tagger batch inference (inside worker process)."""
    from .handler_wd_tagger import run_wd_tagger_batch
    return run_wd_tagger_batch(queue, task, db_path)


def _run_ai_analysis_batch(
    queue: TaskQueue,
    task: InferenceTask,
    db_path: str,
    config: dict,
) -> InferenceResult:
    """AI Analysis batch inference (inside worker process)."""
    from .handler_ai_analysis import run_ai_analysis_batch
    return run_ai_analysis_batch(queue, task, db_path)


def _run_llm_chat_stream(
    queue: TaskQueue,
    task: InferenceTask,
    db_path: str,
    config: dict,
) -> InferenceResult:
    """LLM chat streaming inference (inside worker process)."""
    if task.config.get("mock"):
        return _run_mock_llm_stream(queue, task.task_id, _cancel_flags)
    from .handler_hailo_llm import run_llm_chat_stream
    return run_llm_chat_stream(queue, task, _cancel_flags)


def _run_mock_llm_stream(
    queue: TaskQueue,
    task_id: str,
    cancel_flags: dict[str, bool],
) -> InferenceResult:
    """Generate deterministic mock LLM tokens without extension imports."""
    num_tokens = 50
    for seq in range(num_tokens):
        if cancel_flags.get(task_id, False):
            queue.put_result(StreamingToken(task_id=task_id, token="<CANCEL>", seq=seq, terminal=True))
            return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED)
        queue.put_result(StreamingToken(task_id=task_id, token=f"tok{seq}", seq=seq, terminal=False))
        time.sleep(0.02)

    queue.put_result(StreamingToken(task_id=task_id, token="", seq=num_tokens, terminal=True))
    return InferenceResult(task_id=task_id, status=TaskStatus.COMPLETE)

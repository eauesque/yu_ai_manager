"""LLM chat streaming inference handler (mock + real Hailo).

Mock mode generates synthetic tokens for testing.
Real Hailo path (Phase 0b) integrates HailoNpuLock + acquire_genai + generate_stream.
"""

import logging
import time

from core.hailo_device_core.hailo_npu_lock import HailoNpuLock
from extensions.builtin_hailo_genai.core_impl.llm_inference import (
    _filter_token,
    _normalise_prompt,
    get_hef_path,
)

from .task_queue import TaskQueue
from .task_types import InferenceResult, StreamingToken, TaskStatus

logger = logging.getLogger(__name__)

_llm_lock_holder = None
# Module-level reference to the active LLM instance (set by the handler
# after acquire_genai succeeds). Used by control RPCs (clear_context /
# unload / status_query) so they don't need the in-flight task config.
_llm_instance: object | None = None


def release_llm_lock_holder() -> None:
    """Release the singleton NPU lock + model (called on unload / close_llm)."""
    global _llm_lock_holder, _llm_instance
    # Release the Hailo model bound to "llm_subprocess"
    try:
        from core.hailo_device_core.device_manager import release_device
        release_device("llm_subprocess")
    except Exception as e:
        logger.error(f"Error releasing LLM model: {e}")
    _llm_instance = None
    if _llm_lock_holder is not None:
        try:
            _llm_lock_holder.release()
        except Exception as e:
            logger.error(f"Error releasing LLM lock: {e}")
        _llm_lock_holder = None


def clear_llm_context() -> bool:
    """Clear the active LLM's conversation context. Returns True on success."""
    if _llm_instance is None:
        return False
    try:
        _llm_instance.clear_context()  # type: ignore[attr-defined]
        return True
    except Exception as e:
        logger.error(f"Error clearing LLM context: {e}")
        return False


def llm_status() -> dict:
    """Return a snapshot of the worker-side LLM state."""
    info: dict = {"llm_loaded": _llm_instance is not None}
    if _llm_instance is not None:
        try:
            info["context_usage"] = _llm_instance.get_context_usage_size()  # type: ignore[attr-defined]
            info["context_capacity"] = _llm_instance.max_context_capacity()  # type: ignore[attr-defined]
        except Exception:
            logger.warning("inference worker step failed", exc_info=True)
    return info


def run_llm_chat_stream(
    queue: TaskQueue,
    task,
    cancel_flags: dict[str, bool],
) -> InferenceResult:
    """Run LLM chat stream task (dispatch mock or real path)."""
    task_id = task.task_id
    mock_mode = task.config.get("mock", False)

    if mock_mode:
        return _run_mock_stream(queue, task_id, cancel_flags)
    return _run_real_hailo_stream(queue, task, cancel_flags)


def _emit_terminal(
    queue: TaskQueue,
    task_id: str,
    seq: int,
    error: str | None = None,
) -> None:
    queue.put_result(
        StreamingToken(
            task_id=task_id,
            token="",
            seq=seq,
            terminal=True,
            error=error,
        )
    )


def _run_real_hailo_stream(
    queue: TaskQueue,
    task,
    cancel_flags: dict[str, bool],
) -> InferenceResult:
    """Stream tokens from real Hailo LLM with NPU lock coordination."""
    global _llm_lock_holder
    task_id = task.task_id
    seq = 0

    try:
        if _llm_lock_holder is None:
            _llm_lock_holder = HailoNpuLock(timeout=5.0)
            if not _llm_lock_holder.try_acquire():
                _llm_lock_holder = None
                _emit_terminal(queue, task_id, seq, error="hailo_npu_busy")
                return InferenceResult(
                    task_id=task_id,
                    status=TaskStatus.ERROR,
                    error="hailo_npu_busy",
                )

        model_name = task.config.get("model", "qwen3-1.7b-instruct")
        messages = task.config.get("messages", [])
        temperature = task.config.get("temperature", 0.7)
        max_tokens = task.config.get("max_tokens", 512)

        try:
            from hailo_platform.genai import LLM

            from core.hailo_device_core.device_manager import acquire_genai

            hef_path = str(get_hef_path(model_name))
            llm_instance = acquire_genai(
                "llm_subprocess",
                hef_path,
                lambda vd, p: LLM(vd, p),
            )
            # Cache module-level ref so control RPCs (clear_context /
            # status_query / unload) can reach the live model without
            # plumbing through an in-flight task.
            global _llm_instance
            _llm_instance = llm_instance
        except Exception as acquire_error:
            logger.error(f"Error acquiring model: {acquire_error}")
            release_llm_lock_holder()
            err = f"model_load_error: {type(acquire_error).__name__}"
            _emit_terminal(queue, task_id, seq, error=err)
            return InferenceResult(
                task_id=task_id,
                status=TaskStatus.ERROR,
                error=err,
            )

        # During cold_load (~71s) the C extension holds the GIL, so the
        # control daemon thread cannot process cancel messages. They queue
        # up and are processed only after cold_load releases the GIL. Give
        # the daemon a short window to drain pending controls, then check
        # the cancel flag BEFORE invoking generate() — otherwise we would
        # always run at least one token of generation for an abandoned
        # request (wasted compute and avoidable Hailo state churn).
        import time as _time
        _time.sleep(0.05)
        if cancel_flags.get(task_id, False):
            _emit_terminal(queue, task_id, seq, error="cancelled")
            return InferenceResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                error="cancelled",
            )

        # Normalise structured prompt content to plain strings (same as
        # in-process HailoLLM._prepare_prompt). Strip system role when the
        # LLM already has context to satisfy HailoRT's chat template.
        normalised = _normalise_prompt(messages)
        try:
            if llm_instance.get_context_usage_size() > 0:
                normalised = [m for m in normalised if m.get("role") != "system"]
        except Exception:
            logger.warning("inference worker step failed", exc_info=True)

        try:
            gen_start = time.monotonic()
            first_token_ts: float | None = None
            with llm_instance.generate(
                prompt=normalised,
                temperature=max(temperature, 0.01),
                max_generated_tokens=max_tokens,
            ) as gen:
                for token in gen:
                    if cancel_flags.get(task_id, False):
                        _emit_terminal(queue, task_id, seq, error="cancelled")
                        return InferenceResult(
                            task_id=task_id,
                            status=TaskStatus.CANCELLED,
                            error="cancelled",
                        )

                    filtered = _filter_token(token)
                    if filtered:
                        if first_token_ts is None:
                            first_token_ts = time.monotonic()
                        queue.put_result(
                            StreamingToken(
                                task_id=task_id,
                                token=filtered,
                                seq=seq,
                                terminal=False,
                            )
                        )
                        seq += 1

            _emit_terminal(queue, task_id, seq)
            # Phase 4: observability — token rate + first-token latency
            total_ms = int((time.monotonic() - gen_start) * 1000)
            ttft_ms = (
                int((first_token_ts - gen_start) * 1000)
                if first_token_ts is not None
                else total_ms
            )
            tokens_per_sec = (seq * 1000 / total_ms) if total_ms > 0 else 0.0
            logger.info(
                "subprocess_io task=%s tokens=%d total_ms=%d ttft_ms=%d tok_per_sec=%.2f",
                task_id, seq, total_ms, ttft_ms, tokens_per_sec,
            )
            return InferenceResult(
                task_id=task_id,
                status=TaskStatus.COMPLETE,
            )
        except Exception as gen_error:
            logger.error(f"Error during token generation: {gen_error}")
            err = f"generation_error: {type(gen_error).__name__}"
            _emit_terminal(queue, task_id, seq, error=err)
            return InferenceResult(
                task_id=task_id,
                status=TaskStatus.ERROR,
                error=err,
            )

    except Exception as e:
        logger.error(f"Unexpected error in real_hailo_stream: {e}", exc_info=True)
        err = f"unexpected_error: {type(e).__name__}"
        _emit_terminal(queue, task_id, seq, error=err)
        return InferenceResult(
            task_id=task_id,
            status=TaskStatus.ERROR,
            error=err,
        )


def _run_mock_stream(
    queue: TaskQueue,
    task_id: str,
    cancel_flags: dict[str, bool],
) -> InferenceResult:
    """Generate mock tokens for testing."""
    num_tokens = 50
    sleep_interval = 0.02

    for seq in range(num_tokens):
        if cancel_flags.get(task_id, False):
            queue.put_result(
                StreamingToken(
                    task_id=task_id,
                    token="<CANCEL>",
                    seq=seq,
                    terminal=True,
                )
            )
            return InferenceResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
            )

        queue.put_result(
            StreamingToken(
                task_id=task_id,
                token=f"tok{seq}",
                seq=seq,
                terminal=False,
            )
        )
        time.sleep(sleep_interval)

    queue.put_result(
        StreamingToken(
            task_id=task_id,
            token="",
            seq=num_tokens,
            terminal=True,
        )
    )
    return InferenceResult(
        task_id=task_id,
        status=TaskStatus.COMPLETE,
    )

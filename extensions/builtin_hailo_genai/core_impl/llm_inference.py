"""Hailo-10H LLM inference wrapper (singleton).

Wraps ``hailo_platform.genai.LLM`` with device_manager integration
and provides both streaming and non-streaming generation.

Prompt normalisation:
  Some chat templates (Llama) expect ``content`` as a plain string,
  while others (Qwen) accept the structured
  ``[{"type": "text", "text": "..."}]`` form.  For LLM (text-only),
  we always flatten to plain strings for maximum compatibility.
"""

import logging
import threading
import time
from collections.abc import Iterator
from typing import Any, Optional

from .model_download import get_hef_path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance: Optional["HailoLLM"] = None


def _dlog(event: str, **fields) -> None:
    try:
        from core.infra_core.debug_log import dlog
        dlog("llm", event, **fields)
    except Exception:
        logger.debug("llm dlog failed", exc_info=True)

# Model stop/special tokens -- filter when mixed into output
_STOP_TOKENS = frozenset({
    "<|im_end|>",       # Qwen
    "<|im_start|>",     # Qwen
    "<|eot_id|>",       # Llama 3
    "<|end_header_id|>",  # Llama 3
    "<|end_of_response|>",  # DeepSeek
    "<|end|>",          # DeepSeek
    "<|endoftext|>",    # Generic
})


def _filter_token(token: str) -> str | None:
    """Remove special tokens. Returns None for stop tokens."""
    if token in _STOP_TOKENS:
        return None
    # Also remove when special tokens appear within token text
    for st in _STOP_TOKENS:
        if st in token:
            token = token.replace(st, "")
    return token if token else None


def _normalise_prompt(messages: list) -> list:
    """Flatten structured content arrays to plain strings.

    ``[{"type":"text","text":"hello"}]``  ->  ``"hello"``

    This ensures compatibility with all chat templates.
    """
    out: list[dict] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text parts only (ignore image/video markers for LLM)
            parts = [
                p["text"] for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            content = "\n".join(parts)
        out.append({"role": msg["role"], "content": content})
    return out


class HailoLLM:
    """Thin wrapper around ``hailo_platform.genai.LLM``."""

    def __init__(self, model_name: str):
        from hailo_platform.genai import LLM

        from core.hailo_device_core.device_manager import acquire_genai
        from core.hailo_device_core.hailo_npu_lock import HailoNpuLock

        # Acquire NPU lock (in-process, try_acquire only)
        self._lock_holder: HailoNpuLock | None = None
        try:
            self._lock_holder = HailoNpuLock(timeout=5.0)
            if not self._lock_holder.try_acquire():
                raise RuntimeError(
                    "Hailo NPU is busy (held by another process). "
                    "Cannot load LLM model. Try again in a moment."
                )
        except Exception as lock_err:
            if self._lock_holder is not None:
                from contextlib import suppress
                with suppress(Exception):
                    self._lock_holder.release()
            self._lock_holder = None
            raise RuntimeError(f"Failed to acquire Hailo NPU lock: {lock_err}") from lock_err

        # Load model (wrapped in try/except to release lock on failure)
        try:
            path = str(get_hef_path(model_name))
            t0 = time.monotonic()
            self._llm = acquire_genai(
                "llm", path,
                lambda vd, p: LLM(vd, p),
            )
            load_ms = int((time.monotonic() - t0) * 1000)
            self._model_name = model_name
            _dlog("load", model=model_name, load_ms=load_ms)
        except BaseException:
            # Release lock on any failure (including KeyboardInterrupt)
            if self._lock_holder is not None:
                from contextlib import suppress
                with suppress(Exception):
                    self._lock_holder.release()
            self._lock_holder = None
            raise

    @property
    def model_name(self) -> str:
        return self._model_name

    def _prepare_prompt(self, prompt: list) -> list:
        """Normalise prompt, stripping system role on continuation turns.

        HailoRT の LLM は最初の generate 呼び出しでのみ system role を
        受け付ける。コンテキストが既にある場合 (2 ターン目以降) は
        system メッセージを自動除外する。
        """
        normalised = _normalise_prompt(prompt)
        if self._llm.get_context_usage_size() > 0:
            normalised = [m for m in normalised if m["role"] != "system"]
        return normalised

    def generate_stream(
        self,
        prompt: list,
        *,
        temperature: float = 0.7,
        max_generated_tokens: int = 512,
        seed: int | None = None,
    ) -> Iterator[str]:
        """Yield tokens as they are generated."""
        # HailoRT 5.3.0+ rejects temperature=0.0 with HAILO_INVALID_ARGUMENT.
        # Clamp to 0.01 to preserve near-deterministic intent.
        temperature = max(temperature, 0.01)
        kwargs = {
            "prompt": self._prepare_prompt(prompt),
            "temperature": temperature,
            "max_generated_tokens": max_generated_tokens,
        }
        if seed is not None:
            kwargs["seed"] = seed
        # Hailo LLM.generate() is used as a context manager
        with self._llm.generate(**kwargs) as gen:
            for token in gen:
                filtered = _filter_token(token)
                if filtered is None:
                    continue
                yield filtered

    def generate_all(
        self,
        prompt: list,
        *,
        temperature: float = 0.7,
        max_generated_tokens: int = 512,
        seed: int | None = None,
    ) -> str:
        """Non-streaming generation; returns full text."""
        # HailoRT 5.3.0+ rejects temperature=0.0 with HAILO_INVALID_ARGUMENT.
        temperature = max(temperature, 0.01)
        kwargs = {
            "prompt": self._prepare_prompt(prompt),
            "temperature": temperature,
            "max_generated_tokens": max_generated_tokens,
        }
        if seed is not None:
            kwargs["seed"] = seed
        text = self._llm.generate_all(**kwargs)
        for st in _STOP_TOKENS:
            text = text.replace(st, "")
        return text.strip()

    def get_context_info(self) -> dict:
        """Return context usage and capacity."""
        return {
            "usage": self._llm.get_context_usage_size(),
            "capacity": self._llm.max_context_capacity(),
        }

    def clear_context(self) -> None:
        self._llm.clear_context()

    def close(self) -> None:
        from core.hailo_device_core.device_manager import release_device
        # Release NPU lock first, then device
        if self._lock_holder is not None:
            try:
                self._lock_holder.release()
            except Exception as e:
                logging.error(f"Error releasing NPU lock in close(): {e}")
            self._lock_holder = None
        release_device("llm")


def get_llm(model_name: str = "qwen3-1.7b-instruct") -> HailoLLM:
    """Return the singleton HailoLLM, loading *model_name* if needed."""
    from core.hailo_device_core.device_manager import is_model_active

    global _instance
    t_wait_start = time.monotonic()
    with _lock:
        wait_ms = int((time.monotonic() - t_wait_start) * 1000)
        t_work = time.monotonic()
        outcome = "hit"
        try:
            if _instance is not None and _instance.model_name == model_name:
                if is_model_active("llm"):
                    return _instance
                logger.info("LLM singleton was evicted externally; reloading")
                _instance = None
                outcome = "reload_evicted"
            if _instance is not None:
                _instance.close()
                _instance = None
                outcome = "reload_swap"
            else:
                if outcome == "hit":
                    outcome = "cold_load"
            _instance = HailoLLM(model_name)
            return _instance
        finally:
            work_ms = int((time.monotonic() - t_work) * 1000)
            _dlog(
                "get_llm",
                model=model_name,
                outcome=outcome,
                lock_wait_ms=wait_ms,
                work_ms=work_ms,
                total_ms=wait_ms + work_ms,
            )


def close_llm() -> None:
    """Release the singleton LLM."""
    global _instance
    t_wait_start = time.monotonic()
    with _lock:
        wait_ms = int((time.monotonic() - t_wait_start) * 1000)
        had_instance = _instance is not None
        if _instance is not None:
            _instance.close()
            _instance = None
        _dlog("close_llm", lock_wait_ms=wait_ms, had_instance=had_instance)


class HailoBusyError(RuntimeError):
    """Raised when Hailo NPU is busy (lock contention or inference_worker busy)."""
    pass


class HailoLLMSubprocessClient:
    """Async client over the inference_worker bridge for LLM streaming."""

    def __init__(self, bridge, task_id: str, model_name: str):
        self._bridge = bridge
        self._task_id = task_id
        self._model_name = model_name
        self._stream_queue = None
        self._is_closed = False

    async def _submit_task(
        self,
        messages: list,
        temperature: float,
        max_tokens: int,
        mock: bool,
    ) -> None:
        """Submit task to the worker and register stream."""
        from core.inference_worker.task_types import InferenceTask, TaskType

        config_dict: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if mock:
            config_dict["mock"] = True

        task = InferenceTask(
            task_id=self._task_id,
            task_type=TaskType.LLM_CHAT_STREAM,
            streaming=True,
            config=config_dict,
        )

        self._stream_queue = self._bridge.register_stream(self._task_id)

        if not self._bridge.submit_task(task):
            self._bridge.unregister_stream(self._task_id)
            self._stream_queue = None
            raise RuntimeError("Failed to submit LLM task to worker")

    async def stream(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 512,
        mock: bool = False,
    ):
        """Async generator yielding token strings.

        Raises HailoBusyError on lock contention. Other terminal errors are
        surfaced via the StreamingToken object (consumer can inspect .error).
        """
        try:
            await self._submit_task(messages, temperature, max_tokens, mock)

            async for token in self._bridge.iter_stream(self._task_id):
                if token.error:
                    if token.error == "hailo_npu_busy":
                        raise HailoBusyError(f"Hailo NPU busy: {token.error}")
                    yield token
                elif token.token:
                    yield token.token
        finally:
            await self.aclose()

    async def generate_all(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 512,
        mock: bool = False,
    ) -> str:
        """Non-streaming: collect all tokens and return concatenated string."""
        tokens: list[str] = []
        async for tok in self.stream(messages, temperature, max_tokens, mock=mock):
            if isinstance(tok, str):
                tokens.append(tok)
        return "".join(tokens)

    async def aclose(self) -> None:
        """Close the stream and send cancel control."""
        if self._is_closed:
            return

        self._is_closed = True

        # Send cancel control if task is still active
        if self._task_id in self._bridge._streaming_queues:
            from core.inference_worker.task_types import ControlMessage

            try:
                cancel_msg = ControlMessage(task_id=self._task_id, op="cancel")
                self._bridge.send_control(cancel_msg)
            except Exception as e:
                logger.warning(f"Error sending cancel control: {e}")

        # Unregister stream
        self._bridge.unregister_stream(self._task_id)
        self._stream_queue = None


async def stream_with_keepalive(async_iter, ping_interval: float = 5.0):
    """Wrap an async iterator and emit a keepalive sentinel when idle.

    Yields:
        ("token", value) — a real value from the wrapped iterator
        ("ping", None)   — emitted every ``ping_interval`` seconds of silence
                            so SSE callers can write a comment line and keep
                            the TCP connection alive during Hailo cold_load
                            (~71s on Pi 5 where the GIL is held).
    """
    import asyncio as _asyncio
    import time

    it = async_iter.__aiter__()
    start = time.monotonic()
    ping_count = 0
    token_count = 0
    while True:
        next_task = _asyncio.create_task(it.__anext__())
        try:
            while True:
                try:
                    value = await _asyncio.wait_for(_asyncio.shield(next_task), timeout=ping_interval)
                    elapsed = time.monotonic() - start
                    logger.debug("stream_with_keepalive: token received (elapsed=%.1fs, pings=%d)", elapsed, ping_count)
                    yield ("token", value)
                    token_count += 1
                    break
                except TimeoutError:
                    ping_count += 1
                    elapsed = time.monotonic() - start
                    logger.debug("stream_with_keepalive: ping #%d (elapsed=%.1fs)", ping_count, elapsed)
                    yield ("ping", None)
        except StopAsyncIteration:
            elapsed_total = time.monotonic() - start
            logger.info(f"LLM inference complete: {token_count=} tokens, {elapsed_total*1000:.1f} ms")
            return
        finally:
            if not next_task.done():
                next_task.cancel()
                try:
                    await _asyncio.wait_for(next_task, timeout=1.0)
                except TimeoutError:
                    logger.warning("cancellation timed out; task may be orphaned")
                except (_asyncio.CancelledError, StopAsyncIteration):
                    pass


def use_subprocess(config: dict | None = None) -> bool:
    """Check if LLM subprocess mode is enabled.
    
    Args:
        config: Application config dict (if available at runtime).
                Defaults to reading from env if not provided.
    
    Returns:
        True if hailo_genai.llm_subprocess is True, False otherwise.
    """
    if config is None:
        return False
    
    hailo_cfg = config.get("hailo_genai", {})
    return bool(hailo_cfg.get("llm_subprocess", False))

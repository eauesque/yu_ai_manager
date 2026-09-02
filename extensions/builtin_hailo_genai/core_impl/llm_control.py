"""Bridge-aware control helpers for LLM / VLM lifecycle.

These wrap the in-process device_manager calls so callers can be written
once and automatically dispatch to either the in-process facade or the
inference_worker subprocess based on the ``hailo_genai.llm_subprocess``
config flag. Use the ``async_*`` variants from async routes / Quart
handlers, and ``sync_*`` wrappers only where you cannot await (rare).

The subprocess path issues a ControlMessage RPC over the inference bridge
and waits for the ControlResponse. The in-process path goes straight to
``device_manager`` / ``HailoLLM`` / ``HailoVLM`` singletons.

Parent-side ``status_query`` results are cached for 1 second to avoid
flooding the worker on hot status polls (spec §3.5).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from .llm_inference import use_subprocess

logger = logging.getLogger(__name__)

_status_cache: dict[str, Any] = {}
_status_cache_ts: float = 0.0
_STATUS_CACHE_TTL = 1.0  # seconds


async def _control_rpc(op: str, payload: dict | None = None, timeout: float = 10.0) -> dict:
    """Send a control RPC to the worker subprocess and return its result dict."""
    from core.inference_worker.bridge import inference_bridge
    from core.inference_worker.task_types import ControlMessage

    msg = ControlMessage(
        task_id=uuid.uuid4().hex,
        op=op,  # type: ignore[arg-type]
        payload=payload or {},
    )
    resp = await inference_bridge.send_control_and_wait(msg, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"Control RPC {op} failed: {resp.error}")
    return resp.result or {}


async def async_close_llm(config: dict | None = None) -> None:
    """Release the LLM (close subprocess copy when in subprocess mode)."""
    global _status_cache_ts
    _status_cache_ts = 0.0
    if use_subprocess(config):
        await _control_rpc("close_llm")
    else:
        from .llm_inference import close_llm
        close_llm()


async def async_close_vlm(config: dict | None = None) -> None:
    """Release the VLM (worker subprocess instance in subprocess mode)."""
    global _status_cache_ts
    _status_cache_ts = 0.0
    if use_subprocess(config):
        # The worker subprocess may also have a VLM instance (used by
        # AI analysis batch). Drop both worker-side AND any in-process
        # VLM the parent might still hold for legacy paths.
        try:
            await _control_rpc("close_vlm")
        except Exception as e:
            logger.warning(f"worker close_vlm RPC failed (continuing): {e}")
    # Always also touch the parent-side singleton — VLM is technically
    # out of subprocess scope (Phase 1) so the in-process module remains
    # active for VLM endpoints.
    try:
        from .vlm_inference import close_vlm as _local_close_vlm
        _local_close_vlm()
    except Exception:
        logger.warning("VLM was not closed", exc_info=True)


async def async_clear_llm_context(config: dict | None = None) -> None:
    """Clear the active LLM's conversation context."""
    if use_subprocess(config):
        await _control_rpc("clear_context")
    else:
        from . import llm_inference as _ll
        if _ll._instance is not None:
            _ll._instance.clear_context()


async def async_unload_model(model: str, config: dict | None = None) -> None:
    """Release a specific owner (e.g. 'llm', 'vlm', 's2t')."""
    global _status_cache_ts
    _status_cache_ts = 0.0
    if use_subprocess(config) and model in ("llm", "llm_subprocess"):
        await _control_rpc("unload", payload={"model": model})
    elif use_subprocess(config) and model == "vlm":
        try:
            await _control_rpc("unload", payload={"model": "vlm"})
        except Exception as e:
            logger.warning(f"worker unload vlm RPC failed: {e}")
        from .vlm_inference import close_vlm
        close_vlm()
    else:
        from core.hailo_device_core.device_manager import release_device
        release_device(model)


async def async_status(config: dict | None = None, force: bool = False) -> dict:
    """Return worker-side model status (subprocess mode) with 1s cache."""
    global _status_cache, _status_cache_ts
    now = time.monotonic()
    if not force and (now - _status_cache_ts) < _STATUS_CACHE_TTL and _status_cache:
        return dict(_status_cache)

    if use_subprocess(config):
        try:
            result = await _control_rpc("status_query", timeout=2.0)
        except Exception as e:
            logger.warning(f"status_query RPC failed: {e}")
            return {"llm_active": False, "vlm_active": False, "error": str(e)}
        _status_cache = result
        _status_cache_ts = now
        return dict(result)

    # in-process fallback
    from core.hailo_device_core.device_manager import is_model_active
    result = {
        "llm_active": is_model_active("llm"),
        "vlm_active": is_model_active("vlm"),
        "s2t_active": is_model_active("s2t"),
    }
    _status_cache = result
    _status_cache_ts = now
    return dict(result)


async def async_is_model_active(model: str, config: dict | None = None) -> bool:
    """Convenience: is the given model active?"""
    status = await async_status(config)
    return bool(status.get(f"{model}_active", False))

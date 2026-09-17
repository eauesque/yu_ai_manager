"""GenAI acquisition helpers for the Hailo device manager."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.hailo_device_core.device_helpers import (
    _estimate_cma_mb,
    _read_cma_free_mb,
    log_hailo_cma_event,
)

from .device_manager_state import _ensure_vdevice, _maybe_reset_vdevice, _release_model_internal


def _get_reject_tracker() -> Any:
    from core.hailo_device_core.auto_reboot import get_reject_tracker

    return get_reject_tracker()


def acquire_genai(owner: str, model_path: str, genai_factory: Callable) -> object:
    """Acquire or reuse a GenAI model on the shared VDevice."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        existing = facade._models.get(owner)
        if existing and existing.get("hef") == model_path:
            facade.logger.debug("GenAI reused for '%s' (%s)", owner, model_path)
            log_hailo_cma_event("acquire_reuse", owner=owner, hef=model_path)
            _get_reject_tracker().record_success()
            return existing["genai_instance"]

        if existing:
            facade.logger.info("GenAI switch for '%s': releasing old model", owner)
            _release_model_internal(owner)

        required_mb = _estimate_cma_mb(model_path)
        free_mb = _read_cma_free_mb()
        if free_mb is not None and free_mb < required_mb:
            log_hailo_cma_event(
                "acquire_low_cma_observed",
                owner=owner, hef=model_path,
                note=f"estimate={required_mb}MB; telemetry_only=true",
            )
            facade.logger.warning(
                "Low CmaFree before Hailo GenAI load for '%s': %s MB "
                "(model estimate %s MB). Continuing because CmaFree is telemetry, "
                "not an allocation-capacity limit.",
                owner,
                free_mb,
                required_mb,
            )

        try:
            vd = _ensure_vdevice()
            log_hailo_cma_event("acquire_pre", owner=owner, hef=model_path)
            genai_instance = genai_factory(vd, model_path)
            log_hailo_cma_event("acquire_post", owner=owner, hef=model_path)
            facade._models[owner] = {
                "type": "genai",
                "genai_instance": genai_instance,
                "hef": model_path,
            }
            facade.logger.info("Hailo GenAI acquired by '%s': %s", owner, model_path)
            _get_reject_tracker().record_success()
            return genai_instance
        except Exception as exc:
            # Log before classifying. Non-memory factory errors preserve reject state.
            log_hailo_cma_event(
                "acquire_failed",
                owner=owner, hef=model_path,
                note=f"{type(exc).__name__}: {exc}",
            )
            _maybe_reset_vdevice()
            exc_str = str(exc)
            is_oom = (
                "OUT_OF_HOST_MEMORY" in exc_str
                or "errno:12" in exc_str
                or "unmatched '}' in format string" in exc_str
                or (exc.__class__.__name__ == "HailoRTStatusException" and exc_str.strip() == "3")
            )
            if is_oom:
                _get_reject_tracker().record_reject(
                    reason="hailort_host_memory_error",
                    free_mb=_read_cma_free_mb(),
                    required_mb=required_mb,
                )
                raise RuntimeError(
                    f"Hailo GenAI load failed for '{owner}': HailoRT reported a "
                    f"host-memory allocation error. Stop unused Hailo workloads "
                    f"and retry. CmaFree is logged as telemetry but is not, by "
                    f"itself, proof that the model cannot load."
                ) from exc
            raise RuntimeError(
                f"Failed to initialise Hailo GenAI for '{owner}': {exc}. "
                f"Is hailo-ollama running with a different group_id? "
                f"Try: systemctl stop hailo-ollama"
            ) from exc

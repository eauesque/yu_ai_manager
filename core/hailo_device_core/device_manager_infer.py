"""Infer-model acquisition helpers for the Hailo device manager."""

from __future__ import annotations

import gc

from core.hailo_device_core.device_helpers import _extract_all_quant_params

from .device_manager_state import _ensure_vdevice, _maybe_reset_vdevice, _release_model_internal


def acquire_device(owner: str, hef_path: str):
    """Acquire or reuse an InferModel on the shared VDevice."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        existing = facade._models.get(owner)
        if existing and existing.get("hef") == hef_path:
            facade.logger.debug("Device reused for '%s' (%s)", owner, hef_path)
            return (
                existing["infer_model"],
                existing["configured"],
                existing["quant_params"],
            )

        if existing:
            facade.logger.info("Model switch for '%s': releasing old HEF", owner)
            _release_model_internal(owner)

        try:
            vd = _ensure_vdevice()
            infer_model = vd.create_infer_model(hef_path)
            configured = infer_model.configure()
            quant_params_list = _extract_all_quant_params(infer_model)

            facade._models[owner] = {
                "type": "infer",
                "infer_model": infer_model,
                "configured": configured,
                "quant_params": quant_params_list,
                "hef": hef_path,
            }

            facade.logger.info(
                "Hailo model acquired by '%s': %s (%d outputs)",
                owner, hef_path, len(quant_params_list),
            )
            return infer_model, configured, quant_params_list
        except Exception as exc:
            exc_str = str(exc)
            is_oom = (
                "OUT_OF_HOST_MEMORY" in exc_str
                or "errno:12" in exc_str
                or (exc.__class__.__name__ == "HailoRTStatusException" and exc_str.strip() == "3")
            )
            if is_oom:
                raise RuntimeError(
                    f"Hailo InferModel load failed for '{owner}': HailoRT reported "
                    f"a host-memory allocation error. Stop unused Hailo workloads "
                    f"and retry. CmaFree is telemetry and does not, by itself, "
                    f"prove exhaustion or require a reboot."
                ) from exc
            raise RuntimeError(
                f"Failed to initialise Hailo device for '{owner}': {exc}. "
                f"Is hailo-ollama running with a different group_id? "
                f"Try: systemctl stop hailo-ollama"
            ) from exc


def release_device(owner: str) -> bool:
    """Release a model held by *owner*."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        if owner not in facade._models:
            return False
        _release_model_internal(owner)
        _maybe_reset_vdevice()
        gc.collect()
        return True

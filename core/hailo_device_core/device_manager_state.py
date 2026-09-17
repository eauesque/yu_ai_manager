"""Shared state helpers for the Hailo device manager."""

from __future__ import annotations

import gc

from core.hailo_device_core.device_helpers import log_hailo_cma_event


def _ensure_vdevice():
    """Create the shared VDevice if it doesn't exist (caller holds _lock)."""
    from core.hailo_device_core import device_manager as facade

    if facade._vdevice is not None:
        log_hailo_cma_event("vdevice_reuse")
        return facade._vdevice

    from hailo_platform import VDevice

    log_hailo_cma_event("vdevice_create_pre")
    params = VDevice.create_params()
    params.group_id = facade._GROUP_ID
    facade._vdevice = VDevice(params)
    log_hailo_cma_event("vdevice_create_post")
    facade.logger.info(
        "Shared Hailo VDevice created (group_id=%s)", facade._GROUP_ID,
    )
    return facade._vdevice


def _release_model_internal(owner: str) -> None:
    """Release a single model registration (caller holds _lock)."""
    from core.hailo_device_core import device_manager as facade

    entry = facade._models.pop(owner, None)
    if entry is None:
        return

    hef = entry.get("hef") if isinstance(entry, dict) else None
    log_hailo_cma_event("release_pre", owner=owner, hef=hef)
    try:
        if entry["type"] == "genai" and entry.get("genai_instance") is not None:
            try:
                entry["genai_instance"].release()
            except Exception as exc:
                facade.logger.debug("GenAI release warning for '%s': %s", owner, exc)
        elif entry["type"] == "infer":
            entry.pop("configured", None)
            entry.pop("infer_model", None)
    except Exception as exc:
        facade.logger.debug("Model cleanup warning for '%s': %s", owner, exc)
    log_hailo_cma_event("release_post", owner=owner, hef=hef)

    facade.logger.info("Hailo model released: '%s'", owner)


def _maybe_reset_vdevice() -> None:
    """Keep the shared VDevice alive for the entire process lifetime."""


def shutdown_all() -> None:
    """Release all models and the shared VDevice. For process exit."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        owners = list(facade._models.keys())
        for owner in owners:
            _release_model_internal(owner)

        if facade._vdevice is not None:
            log_hailo_cma_event("shutdown_vdevice_pre")
            try:
                facade._vdevice.release()
            except Exception as exc:
                facade.logger.debug("VDevice release warning: %s", exc)
            facade._vdevice = None
            log_hailo_cma_event("shutdown_vdevice_post")

        gc.collect()
        log_hailo_cma_event("shutdown_complete", note=f"released={len(owners)}")

    if owners:
        facade.logger.info(
            "Hailo shutdown complete (released: %s)", ", ".join(owners),
        )


def get_current_owner() -> str | None:
    """Return one of the current model owners, or None."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        if not facade._models:
            return None
        return next(iter(reversed(facade._models)))


def get_active_owners() -> list[str]:
    """Return all currently registered model owners."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        return list(facade._models.keys())


def get_current_mode() -> str | None:
    """Return the mode of the most recent model, or None."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        if not facade._models:
            return None
        last = next(iter(reversed(facade._models)))
        return facade._models[last]["type"]


def is_model_active(owner: str) -> bool:
    """Check if *owner* currently has a model loaded."""
    from core.hailo_device_core import device_manager as facade

    with facade._lock:
        return owner in facade._models


def is_hailo_available() -> bool:
    """Check if Hailo hardware + runtime are available."""
    try:
        from hailo_platform import VDevice  # noqa: F401
        return True
    except ImportError:
        return False


def is_genai_available() -> bool:
    """Check if Hailo GenAI classes are importable."""
    try:
        from hailo_platform.genai import LLM  # noqa: F401
        return True
    except ImportError:
        return False


def list_device_paths() -> list[str]:
    """Return paths of all detected Hailo device nodes."""
    import platform
    from pathlib import Path

    if platform.system() == "Windows":
        if is_hailo_available():
            return ["hailo-win-0"]
        return []

    found: list[str] = []
    for prefix in ("hailo", "h1x-"):
        for idx in range(8):
            path = Path(f"/dev/{prefix}{idx}")
            if path.exists():
                found.append(str(path))
    return found

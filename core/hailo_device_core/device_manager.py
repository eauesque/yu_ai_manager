"""Shared Hailo-10H VDevice lifecycle manager.

Provides a single shared VDevice that multiple models (CLIP, YOLO,
LLM, VLM, Speech2Text) can use **concurrently**.  The VDevice's
``group_id`` enables sharing with external processes (e.g. hailo-ollama).

The internal scheduler (ROUND_ROBIN) time-slices hardware access
across all loaded models automatically.

Key facts (verified on HailoRT 5.2.0, Hailo-10H):
  - Multiple InferModels can be configured and run on a single VDevice.
  - InferModel and GenAI models coexist on the same VDevice.
  - All models must be created on the **same** VDevice instance
    (separate VDevice instances with the same group_id do NOT work
    for InferModel.run()).

Backward-compatible API:
  - ``acquire_device()`` / ``acquire_genai()`` still work but no
    longer release other owners' models.
  - ``release_device()`` releases an individual model, not the VDevice.
  - ``shutdown_all()`` releases everything (for process exit).
"""

import logging
import os
import threading

from .device_manager_genai import acquire_genai
from .device_manager_infer import acquire_device, release_device
from .device_manager_state import (
    get_active_owners,
    get_current_mode,
    get_current_owner,
    is_genai_available,
    is_hailo_available,
    is_model_active,
    list_device_paths,
    shutdown_all,
)

logger = logging.getLogger(__name__)


_lock = threading.Lock()

# Shared VDevice (process-lifetime singleton)
_vdevice = None

# Per-owner registrations  {owner: {type, infer_model, configured,
#                                    quant_params, genai_instance, hef}}
_models: dict[str, dict] = {}

# Configurable group_id for inter-process sharing.
# Priority: env var > config.json hailo.vdevice_group_id > default
def _resolve_group_id() -> str:
    env = os.environ.get("HAILO_VDEVICE_GROUP_ID")
    if env:
        return env
    try:
        from core.configuration.api import load_config_json
        cfg = load_config_json()
        gid = cfg.get("hailo", {}).get("vdevice_group_id")
        if gid:
            return str(gid)
    except Exception:
        logger.warning("hailo device step failed", exc_info=True)
    return "YU_SHARED"


_GROUP_ID = _resolve_group_id()

def _maybe_reset_vdevice() -> None:
    """Keep the shared VDevice alive for the entire process lifetime.

    Historically this function called _vdevice.release() when no models were
    loaded.  That was removed for two reasons:

    1. **No CMA benefit**: VDevice.release() does NOT return CMA to the kernel
       within a running OS session (HailoRT 5.3.0 on Pi 5, verified).  CMA is
       only reclaimed when the server process exits.

    2. **Firmware hang / GIL blockage**: VDevice.release() triggers a
       VideoCore firmware call (RPI_FIRMWARE_SET_POWER_STATE, mailbox opcode
       0x00030087) that can block for hundreds of milliseconds to seconds.
       While that C extension holds the GIL the asyncio event loop cannot run,
       causing the web server to become unresponsive — the very "stop video →
       server hangs" symptom reported by users.

    InferModels are released individually by _release_model_internal().  The
    VDevice stays alive and is reused for subsequent acquire_device() calls
    (fast: just vd.create_infer_model(), no device re-init).  The VDevice is
    only released in shutdown_all() at process exit.
    """
    # No-op: VDevice lives until shutdown_all().


__all__ = [
    "acquire_device",
    "acquire_genai",
    "is_genai_available",
    "is_hailo_available",
    "is_model_active",
    "get_active_owners",
    "get_current_mode",
    "get_current_owner",
    "list_device_paths",
    "release_device",
    "shutdown_all",
]

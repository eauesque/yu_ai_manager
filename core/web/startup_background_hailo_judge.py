"""Background entry for the Hailo auto-reboot judge loop."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def startup_hailo_auto_reboot_judge() -> None:
    from core.hailo_device_core.auto_reboot import (
        AutoRebootConfig,
        AutoRebootJudge,
        get_reject_tracker,
        register_judge,
    )
    from core.hailo_device_core.auto_reboot_logger import log_auto_reboot_event
    from core.hailo_device_core.device_helpers import _read_cma_free_mb
    from core.services_core.app_runtime_state import get_config

    cfg_raw = ((get_config().get("hailo") or {}).get("auto_reboot") or {})
    cfg = AutoRebootConfig.from_dict(cfg_raw)

    log_auto_reboot_event(
        "boot_baseline",
        cma_free_mb=_read_cma_free_mb(),
        hailo_runtime_version=_safe_runtime_version(),
        mode=cfg.mode,
        dry_run=cfg.dry_run,
        state="idle",
        consecutive_rejects=0,
        poll_interval_seconds=cfg.poll_interval_seconds,
    )

    judge = AutoRebootJudge(
        config=cfg,
        cma_reader=_read_cma_free_mb,
        reject_tracker=get_reject_tracker(),
        event_logger=log_auto_reboot_event,
        runtime_version_reader=_safe_runtime_version,
    )
    register_judge(judge)

    while True:
        try:
            judge.tick()
        except Exception:
            logger.exception("hailo_auto_reboot judge tick failed; continuing")
        time.sleep(cfg.poll_interval_seconds)


def _safe_runtime_version() -> str | None:
    try:
        import hailo_platform  # type: ignore[import-not-found]

        return getattr(hailo_platform, "__version__", None)
    except Exception:
        return None

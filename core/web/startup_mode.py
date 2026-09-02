"""Server mode resolution and declarative subsystem/task definitions."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _env_truthy(name: str) -> bool:
    """Check if env var is set to a truthy value."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def resolve_server_mode(args, server_cfg: dict) -> str:
    """Resolve server mode from CLI > env > config. Default: 'full'."""
    cli_mode = getattr(args, "mode", None)
    if cli_mode is not None:
        return cli_mode
    env_mode = os.environ.get("TAGDB_MODE", "").strip().lower()
    if env_mode in ("full", "gateway", "server"):
        return env_mode
    cfg_mode = server_cfg.get("mode", "").strip().lower()
    if cfg_mode in ("full", "gateway", "server"):
        return cfg_mode
    return "full"


def resolve_headless(args) -> bool:
    """Resolve headless mode from CLI or env."""
    if getattr(args, "headless", False):
        return True
    return _env_truthy("TAGDB_HEADLESS")


@dataclass
class SubsystemDef:
    """Declarative subsystem definition."""
    name: str
    modes: list[str]
    init: Callable[..., None]
    env_override: str = ""


@dataclass
class BackgroundTaskDef:
    """Declarative background startup task."""
    name: str
    modes: list[str]
    target: Callable[[], None]
    env_enable: str = ""
    env_disable: str = ""
    critical: bool = False
    precondition: Callable[[], bool] | None = None


def _should_run_subsystem(sub: SubsystemDef, mode: str) -> bool:
    """Determine if a subsystem should run in the given mode."""
    from core.system.safe_mode import is_safe_mode

    if is_safe_mode():
        return False
    if mode in sub.modes:
        return True
    return bool(sub.env_override and _env_truthy(sub.env_override))


def _should_run_bg_task(task: BackgroundTaskDef, mode: str) -> bool:
    """Determine if a background task should run."""
    from core.system.safe_mode import is_safe_mode

    if is_safe_mode():
        return False
    if task.env_disable and _env_truthy(task.env_disable):
        return False
    if task.env_enable and _env_truthy(task.env_enable):
        pass
    elif mode not in task.modes:
        return False
    return not (task.precondition and not task.precondition())

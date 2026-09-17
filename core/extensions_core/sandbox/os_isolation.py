"""Extension OS-level isolation Phase D.

This module is a re-export facade. The implementation is split into:
- os_isolation_apparmor.py  -- AppArmor (Linux) helpers
- os_isolation_platform.py  -- macOS/Windows + common interface
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

# ── Config dataclass (kept here to avoid circular imports) ──


@dataclass
class OsIsolationConfig:
    """OS isolation configuration."""

    enabled: bool = False
    # Linux
    apparmor: bool = True
    # macOS
    macos_user_isolation: bool = False
    macos_sandbox_exec: bool = False  # deprecated, experimental
    # Windows
    windows_restricted_token: bool = True
    windows_job_object: bool = True
    windows_job_limits: dict[str, Any] = field(default_factory=lambda: {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10,
    })


IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


def load_os_isolation_config(config: dict) -> OsIsolationConfig:
    """Load OS isolation settings from config.json."""
    section = config.get("os_isolation", {})
    if not section:
        return OsIsolationConfig()

    linux = section.get("linux", {})
    macos = section.get("macos", {})
    windows = section.get("windows", {})

    return OsIsolationConfig(
        enabled=section.get("enabled", False),
        apparmor=linux.get("apparmor", True),
        macos_user_isolation=macos.get("user_isolation", False),
        macos_sandbox_exec=macos.get("sandbox_exec", False),
        windows_restricted_token=windows.get("restricted_token", True),
        windows_job_object=windows.get("job_object", True),
        windows_job_limits=windows.get("job_limits", {
            "memory_mb": 512,
            "cpu_percent": 50,
            "max_processes": 10,
        }),
    )


# ── Re-exports from os_isolation_apparmor ──

from .os_isolation_apparmor import apparmor_profile_name as _apparmor_profile_name  # noqa: E402, F401
from .os_isolation_apparmor import (
    build_apparmor_command,  # noqa: E402, F401
    generate_apparmor_profile,  # noqa: E402, F401
    is_apparmor_available,  # noqa: E402, F401
    is_apparmor_sudoers_configured,  # noqa: E402, F401
    load_apparmor_profile,  # noqa: E402, F401
    unload_apparmor_profile,  # noqa: E402, F401
)
from .os_isolation_apparmor import build_setup_guidance as _build_setup_guidance  # noqa: E402, F401
from .os_isolation_apparmor import check_apparmor_kernel as _check_apparmor_kernel  # noqa: E402, F401

# ── Re-exports from os_isolation_platform ──
from .os_isolation_platform import (  # noqa: E402, F401
    apply_os_isolation,
    build_sandbox_exec_command,
    cleanup_os_isolation,
    get_os_isolation_info,
    is_sandbox_exec_available,
)
